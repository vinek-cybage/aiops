"""Writes each error incident into the real `incidents` table.

Based on the schema:
- inc_id: TEXT UNIQUE NOT NULL
- title: TEXT NOT NULL
- severity: TEXT NOT NULL
- status: TEXT NOT NULL DEFAULT 'open'
- services: TEXT[]
- team: TEXT (set to the service name - acts as team identifier)
- hypotheses: JSONB (optional)
- evidence: JSONB (optional)
- timeline: JSONB
- ai_summary: TEXT (optional)
- occurrences: INT NOT NULL DEFAULT 1
- cascades: JSONB NOT NULL DEFAULT '[]'
- first_seen: TIMESTAMPTZ NOT NULL DEFAULT NOW()
- last_seen: TIMESTAMPTZ NOT NULL DEFAULT NOW()
- latest_logs: JSONB

Team Management:
- Each service is its own team (team = service name)
- Users can be added to teams via the users table
- Team members are managed separately via the teams/users schema
"""

import json
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from pull_logs import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

SEVERITY = "critical"
MAX_TIMELINE = 10  # rolling window — a hot incident recurring 700+ times must not grow an unbounded JSONB array


def get_conn():
    """Get a PostgreSQL connection with RealDictCursor."""
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _now_str():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def next_inc_id_counter(conn):
    """Seed a monotonic counter from the highest existing INC-#### row, so a
    restarted service never collides with (or overwrites) past incidents."""
    cur = conn.cursor()
    cur.execute(r"""
        SELECT COALESCE(MAX((substring(inc_id from '^INC-(\d+)$'))::int), 0) AS n
        FROM incidents
    """)
    n = cur.fetchone()["n"]
    cur.close()
    return n


def ensure_team_exists(conn, team_name):
    """Ensure a team exists in the teams table.
    
    This allows us to automatically create teams based on service names
    so users can be added to them later via the users table.
    """
    cur = conn.cursor()
    
    # Check if team exists
    cur.execute("SELECT id FROM teams WHERE name = %s", (team_name,))
    team = cur.fetchone()
    
    if not team:
        # Create the team with the service name
        cur.execute("""
            INSERT INTO teams (name, services)
            VALUES (%s, %s)
        """, (team_name, [team_name]))  # The service name becomes the team name
        cur.close()
        return True
    else:
        # Update services array if team exists but doesn't have this service
        cur.execute("""
            UPDATE teams
            SET services = array_append(services, %s)
            WHERE name = %s AND NOT (%s = ANY(services))
        """, (team_name, team_name, team_name))
        cur.close()
        return False


def insert_incident(conn, inc_id, template, log):
    """Insert a new incident into the incidents table.
    
    Team is set to the service name (team = service).
    Also ensures the team exists in the teams table for future user assignment.
    """
    cur = conn.cursor()
    
    # Ensure the team exists in the teams table
    team_name = log["service"]
    ensure_team_exists(conn, team_name)
    
    # Prepare the timeline entry
    timeline = json.dumps([{"time": _now_str(), "event": "Incident opened", "color": "#818cf8"}])
    
    # Prepare services array (PostgreSQL array format)
    services = [log["service"]]
    
    # Prepare latest_logs as JSON array
    latest_logs = json.dumps([log])
    
    # Insert with team = service name
    cur.execute("""
        INSERT INTO incidents (
            inc_id, title, severity, status, services, team,
            timeline, occurrences, first_seen, last_seen, latest_logs
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
    """, (
        inc_id,                          # inc_id
        template,                        # title
        SEVERITY,                        # severity
        'open',                          # status
        services,                        # services (array)
        team_name,                       # team = service name
        timeline,                        # timeline (jsonb)
        1,                               # occurrences (initial count)
        log["ts"],                       # first_seen
        log["ts"],                       # last_seen
        latest_logs                      # latest_logs (jsonb)
    ))
    cur.close()


def update_incident_on_duplicate(conn, inc_id, log, logs_window):
    """Update an existing incident on duplicate.
    
    Updates:
    - occurrences: Increment by 1
    - last_seen: Current log timestamp
    - latest_logs: Rolling window of logs
    - timeline: Append recurrence event (capped at MAX_TIMELINE)
    """
    cur = conn.cursor()
    
    # Get current timeline
    cur.execute("SELECT timeline FROM incidents WHERE inc_id = %s", (inc_id,))
    row = cur.fetchone()
    
    if row and row["timeline"]:
        timeline = row["timeline"]
    else:
        timeline = []
    
    # Add recurrence event
    timeline.append({"time": _now_str(), "event": f"Recurred ({log['service']})", "color": "#fbbf24"})
    
    # Cap timeline size
    if len(timeline) > MAX_TIMELINE:
        timeline = timeline[-MAX_TIMELINE:]

    # Update with occurrences increment
    cur.execute("""
        UPDATE incidents
        SET occurrences = occurrences + 1,
            last_seen   = %s,
            latest_logs = %s::jsonb,
            timeline    = %s::jsonb
        WHERE inc_id = %s
    """, (log["ts"], json.dumps(logs_window), json.dumps(timeline), inc_id))
    cur.close()


# Helper functions for team management

def add_user_to_team(conn, user_name, team_name, role="member"):
    """Add a user to a team.
    
    Args:
        conn: Database connection
        user_name: The username to add
        team_name: The team name (typically the service name)
        role: User role (default: 'member')
    """
    cur = conn.cursor()
    
    # Check if user exists
    cur.execute("SELECT id FROM users WHERE name = %s", (user_name,))
    user = cur.fetchone()
    
    if not user:
        # Create the user first
        cur.execute("""
            INSERT INTO users (name, role)
            VALUES (%s, %s)
            RETURNING id
        """, (user_name, role))
        user_id = cur.fetchone()["id"]
    else:
        user_id = user["id"]
    
    # Ensure team exists
    ensure_team_exists(conn, team_name)
    
    # Get team ID
    cur.execute("SELECT id FROM teams WHERE name = %s", (team_name,))
    team = cur.fetchone()
    
    if team:
        # Update user's team
        cur.execute("""
            UPDATE users
            SET team_id = %s
            WHERE id = %s
        """, (team["id"], user_id))
        
        cur.close()
        return True
    else:
        cur.close()
        return False


def list_team_members(conn, team_name):
    """List all members of a team."""
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.role
        FROM users u
        JOIN teams t ON u.team_id = t.id
        WHERE t.name = %s
        ORDER BY u.name
    """, (team_name,))
    members = cur.fetchall()
    cur.close()
    return members


def list_all_teams(conn):
    """List all teams (services) and their members."""
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.id,
            t.name as team_name,
            t.services,
            COUNT(u.id) as member_count,
            ARRAY_AGG(u.name) as members
        FROM teams t
        LEFT JOIN users u ON u.team_id = t.id
        GROUP BY t.id, t.name, t.services
        ORDER BY t.name
    """)
    teams = cur.fetchall()
    cur.close()
    return teams