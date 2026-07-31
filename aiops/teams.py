import uuid

from argon2 import PasswordHasher

from database import get_conn

_DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
_hasher = PasswordHasher()


def get_all_teams(org_id: str) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM teams WHERE org_id = %s ORDER BY name", (org_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close(); return rows

def create_team(name: str, services: list[str], org_id: str = _DEFAULT_ORG_ID) -> dict:
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO teams (name, services, org_id) VALUES (%s, %s, %s) RETURNING *",
        (name, services, org_id),
    )
    row = dict(cur.fetchone()); conn.commit(); cur.close(); conn.close(); return row

def update_team(team_id: int, name: str, services: list[str], org_id: str) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "UPDATE teams SET name=%s, services=%s WHERE id=%s AND org_id=%s RETURNING *",
        (name, services, team_id, org_id),
    )
    row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return dict(row) if row else None

def delete_team(team_id: int, org_id: str) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM teams WHERE id=%s AND org_id=%s RETURNING id", (team_id, org_id))
    deleted = cur.fetchone() is not None; conn.commit(); cur.close(); conn.close(); return deleted


def get_all_users(org_id: str) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, t.services AS team_services
                   FROM users u LEFT JOIN teams t ON t.id=u.team_id
                   WHERE u.org_id = %s ORDER BY u.role DESC, u.name""", (org_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close(); return rows

def get_user(user_id: int, org_id: str | None = None) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    if org_id is not None:
        cur.execute("""SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, t.services AS team_services
                       FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=%s AND u.org_id=%s""",
                    (user_id, org_id))
    else:
        cur.execute("""SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, t.services AS team_services
                       FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=%s""", (user_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def create_user(name: str, team_id: int | None, role: str, org_id: str) -> dict | None:
    conn = get_conn(); cur = conn.cursor()

    if team_id is not None:
        # Reject a team_id belonging to a different org outright, rather than
        # silently attaching the new user to someone else's team.
        cur.execute("SELECT 1 FROM teams WHERE id=%s AND org_id=%s", (team_id, org_id))
        if cur.fetchone() is None:
            cur.close(); conn.close()
            return None

    # This legacy path (no email/password collected) is superseded by the
    # invite/registration flow in aiops/auth/routes.py — it still needs to
    # satisfy the users table's NOT NULL auth columns, so it fabricates a
    # placeholder email/password that must go through password-reset before
    # this account can actually log in via the new auth system.
    # NOTE: "local"/"invalid"/"test"/"example" TLDs are RFC 6761 special-use
    # names that email-validator (used by the new auth system's EmailStr
    # fields) always rejects — this placeholder must use an ordinary-looking
    # domain so these accounts can still complete a real password reset later.
    placeholder_email = f"user-{uuid.uuid4().hex[:10]}@pending.aiops-placeholder.com"
    placeholder_password_hash = _hasher.hash(uuid.uuid4().hex)

    cur.execute(
        """INSERT INTO users (name, team_id, role, org_id, email, password_hash)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (name, team_id, role, org_id, placeholder_email, placeholder_password_hash),
    )
    new_id = cur.fetchone()["id"]; conn.commit(); cur.close(); conn.close()
    return get_user(new_id, org_id)

def delete_user(user_id: int, org_id: str) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s AND org_id=%s RETURNING id", (user_id, org_id))
    deleted = cur.fetchone() is not None; conn.commit(); cur.close(); conn.close(); return deleted


def get_services_for_teams(team_ids: list[int], org_id: str) -> list[str]:
    """Flattened, de-duplicated `services` across the given team_ids, scoped to
    org_id. Used to narrow incident/case listings to a non-admin's own teams —
    team_ids must come from the authenticated JWT's team_roles, never a
    client-supplied header, since that's the only tamper-proof source."""
    if not team_ids:
        return []
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT services FROM teams WHERE id = ANY(%s) AND org_id = %s",
        (team_ids, org_id),
    )
    services: set[str] = set()
    for row in cur.fetchall():
        services.update(row["services"] or [])
    cur.close(); conn.close()
    return sorted(services)
