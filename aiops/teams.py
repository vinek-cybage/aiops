from database import get_conn


def get_all_teams() -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM teams ORDER BY name")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close(); return rows

def create_team(name: str, services: list[str]) -> dict:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO teams (name, services) VALUES (%s, %s) RETURNING *", (name, services))
    row = dict(cur.fetchone()); conn.commit(); cur.close(); conn.close(); return row

def update_team(team_id: int, name: str, services: list[str]) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE teams SET name=%s, services=%s WHERE id=%s RETURNING *", (name, services, team_id))
    row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return dict(row) if row else None

def delete_team(team_id: int) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM teams WHERE id=%s RETURNING id", (team_id,))
    deleted = cur.fetchone() is not None; conn.commit(); cur.close(); conn.close(); return deleted


def get_all_users() -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, t.services AS team_services
                   FROM users u LEFT JOIN teams t ON t.id=u.team_id ORDER BY u.role DESC, u.name""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close(); return rows

def get_user(user_id: int) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, t.services AS team_services
                   FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=%s""", (user_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def create_user(name: str, team_id: int | None, role: str = "member") -> dict:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO users (name, team_id, role) VALUES (%s, %s, %s) RETURNING id", (name, team_id, role))
    new_id = cur.fetchone()["id"]; conn.commit(); cur.close(); conn.close()
    return get_user(new_id)

def delete_user(user_id: int) -> bool:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s RETURNING id", (user_id,))
    deleted = cur.fetchone() is not None; conn.commit(); cur.close(); conn.close(); return deleted
