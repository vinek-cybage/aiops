import json
from datetime import datetime, timezone

from database import get_conn
from teams import get_all_teams

DEFAULT_SEVERITY = "warning"


def _parse_case_id(inc_id) -> int | None:
    try:
        return int(str(inc_id).rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        return None


def _team_for_service(service: str | None, teams: list[dict]) -> str:
    for t in teams:
        if service and service in (t.get("services") or []):
            return t["name"]
    return "Unassigned"


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _row_to_case(row: dict, teams: list[dict]) -> dict:
    d = dict(row)
    for f in ("hypotheses", "evidence", "timeline"):
        if isinstance(d.get(f), str):
            d[f] = json.loads(d[f])
    return {
        "inc_id":      f"CASE-{d['id']:04d}",
        "title":       d.get("title") or f"{d['primary_service']} — investigating",
        "severity":    d.get("severity") or DEFAULT_SEVERITY,
        "status":      "resolved" if d["status"] == "RESOLVED" else "open",
        "services":    [d["primary_service"]] if d.get("primary_service") else [],
        "team":        _team_for_service(d.get("primary_service"), teams),
        "hypotheses":  d.get("hypotheses") or [],
        "evidence":    d.get("evidence") or [],
        "timeline":    d.get("timeline") or [],
        "ai_summary":  d.get("ai_summary") or "",
        "occurrences": d.get("occurrence_count", 1),
        "cascades":    [],
        "first_seen":  _iso(d.get("opened_at")),
        "last_seen":   _iso(d.get("updated_at")),
        "latest_logs": None,
    }


def _append_timeline(cur, case_id: int, event: str, color: str, now: datetime):
    entry = json.dumps([{"time": now.strftime("%H:%M:%S"), "event": event, "color": color}])
    cur.execute("UPDATE cases SET timeline = timeline || %s::jsonb WHERE id = %s", (entry, case_id))


def get_all_cases(org_id: str, services: list[str] | None = None) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    if services:
        cur.execute(
            "SELECT * FROM cases WHERE org_id = %s AND primary_service = ANY(%s) ORDER BY updated_at DESC",
            (org_id, services),
        )
    else:
        cur.execute("SELECT * FROM cases WHERE org_id = %s ORDER BY updated_at DESC", (org_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    teams = get_all_teams(org_id)
    return [_row_to_case(r, teams) for r in rows]


def get_case_by_id(inc_id: str, org_id: str) -> dict | None:
    """org_id-scoped — a case belonging to another org 404s exactly like a
    non-existent one, rather than leaking a 403 that would confirm its id is real."""
    case_id = _parse_case_id(inc_id)
    if case_id is None:
        return None
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE id = %s AND org_id = %s", (case_id, org_id))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None
    case = _row_to_case(row, get_all_teams(org_id))
    cur.execute("""
        SELECT ca.id, ca.action_id, ca.similarity_score, ca.status, ca.applied_by, ca.applied_at, ca.result,
               a.name, a.action_type, a.description
        FROM case_actions ca JOIN actions a ON a.id = ca.action_id
        WHERE ca.case_id = %s ORDER BY ca.similarity_score DESC NULLS LAST
    """, (case_id,))
    case["actions"] = [dict(a) for a in cur.fetchall()]
    cur.close(); conn.close()
    return case


def resolve_case(inc_id: str, org_id: str) -> dict | None:
    case_id = _parse_case_id(inc_id)
    if case_id is None:
        return None
    now = datetime.now(timezone.utc)
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "UPDATE cases SET status='RESOLVED', updated_at=%s WHERE id=%s AND org_id=%s RETURNING id",
        (now, case_id, org_id),
    )
    row = cur.fetchone()
    if row:
        _append_timeline(cur, case_id, "Case resolved", "#34d399", now)
        conn.commit()
    cur.close(); conn.close()
    return get_case_by_id(inc_id, org_id) if row else None


def get_case_actions(inc_id: str, org_id: str) -> list[dict] | None:
    case = get_case_by_id(inc_id, org_id)
    return case["actions"] if case is not None else None


def apply_action(inc_id: str, action_id: int, org_id: str, user_id: str | None) -> dict | None:
    from actions import raise_pr, GitHubNotConfigured

    case_id = _parse_case_id(inc_id)
    if case_id is None:
        return None

    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE id = %s AND org_id = %s", (case_id, org_id))
    case = cur.fetchone()
    if not case:
        cur.close(); conn.close()
        return None

    cur.execute("""
        SELECT ca.id AS case_action_id, ca.status AS case_action_status,
               a.id AS action_id, a.name, a.action_type, a.description
        FROM case_actions ca JOIN actions a ON a.id = ca.action_id
        WHERE ca.case_id = %s AND ca.action_id = %s
    """, (case_id, action_id))
    ca = cur.fetchone()
    if not ca:
        cur.close(); conn.close()
        return {"error": "This action was not suggested for this case"}

    now = datetime.now(timezone.utc)
    try:
        if ca["action_type"] == "raise_pr":
            cur.execute(
                "SELECT id FROM teams WHERE org_id = %s AND %s = ANY(services) LIMIT 1",
                (org_id, case["primary_service"]),
            )
            team_row = cur.fetchone()
            result       = raise_pr(case, ca, team_row["id"] if team_row else None, org_id)
            event        = f"PR opened: {result['pr_url']} — awaiting merge"
            resolve_case_ = False
        else:
            result       = {"simulated": True, "note": f"Simulated '{ca['action_type']}': {ca['name']}"}
            event        = f"Applied: {ca['name']}"
            resolve_case_ = True
    except GitHubNotConfigured as e:
        cur.close(); conn.close()
        return {"error": str(e)}
    except Exception as e:
        cur.close(); conn.close()
        return {"error": f"Failed to apply action: {e}"}

    cur.execute("""
        UPDATE case_actions SET status='applied', applied_by=%s, applied_at=%s, result=%s
        WHERE id=%s
    """, (user_id, now, json.dumps(result), ca["case_action_id"]))

    _append_timeline(cur, case_id, event, "#60a5fa", now)
    if resolve_case_:
        cur.execute("UPDATE cases SET status='RESOLVED', updated_at=%s WHERE id=%s", (now, case_id))
        _append_timeline(cur, case_id, "Case resolved", "#34d399", now)
    else:
        cur.execute("UPDATE cases SET updated_at=%s WHERE id=%s", (now, case_id))

    conn.commit()
    cur.close(); conn.close()
    return {"result": result, "case": get_case_by_id(inc_id, org_id)}
