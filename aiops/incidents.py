import json
from datetime import datetime, timezone
from database import get_conn


def _next_inc_id(cur) -> str:
    cur.execute("SELECT COUNT(*) AS cnt FROM incidents")
    return f"INC-{(cur.fetchone()['cnt'] + 1):04d}"

def _row_to_dict(row) -> dict:
    d = dict(row)
    for f in ("hypotheses", "evidence", "timeline", "latest_logs", "cascades"):
        if isinstance(d.get(f), str): d[f] = json.loads(d[f])
    for f in ("first_seen", "last_seen"):
        if isinstance(d.get(f), datetime): d[f] = d[f].isoformat()
    return d

def get_open_incidents(org_id: str) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT inc_id, title, severity, ai_summary FROM incidents WHERE status='open' AND org_id=%s ORDER BY last_seen DESC LIMIT 20",
        (org_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def get_all_incidents(org_id: str, services: list[str] | None = None) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    if services:
        cur.execute("SELECT * FROM incidents WHERE org_id=%s AND services && %s ORDER BY last_seen DESC", (org_id, services))
    else:
        cur.execute("SELECT * FROM incidents WHERE org_id=%s ORDER BY last_seen DESC", (org_id,))
    rows = [_row_to_dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def get_incident_by_id(inc_id: str, org_id: str) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM incidents WHERE inc_id = %s AND org_id = %s", (inc_id, org_id))
    row = cur.fetchone()
    cur.close(); conn.close()
    return _row_to_dict(row) if row else None

def resolve_incident(inc_id: str, org_id: str) -> dict | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE incidents SET status='resolved' WHERE inc_id=%s AND org_id=%s RETURNING *", (inc_id, org_id))
    row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return _row_to_dict(row) if row else None

def save_incident(result: dict, logs: list[dict], org_id: str) -> dict:
    now  = datetime.now(timezone.utc)
    conn = get_conn(); cur = conn.cursor()

    # 1. DUPLICATE
    dup_id = result.get("duplicate_of")
    if not dup_id:
        cur.execute("SELECT inc_id FROM incidents WHERE title=%s AND status='open' AND org_id=%s", (result["title"], org_id))
        row = cur.fetchone()
        if row: dup_id = row["inc_id"]

    if dup_id:
        cur.execute("SELECT timeline FROM incidents WHERE inc_id=%s AND org_id=%s", (dup_id, org_id))
        dup_row = cur.fetchone()
        if not dup_row:
            cur.close(); conn.close()
            return {"action": "ignored", "tag": "invalid_duplicate_of", "incident": None}
        tl = dup_row["timeline"]
        timeline = json.loads(tl) if isinstance(tl, str) else (tl or [])
        timeline.append({"time": now.strftime("%H:%M:%S"), "event": "Occurred again", "color": "#fbbf24"})
        cur.execute("""UPDATE incidents SET occurrences=occurrences+1, last_seen=NOW(),
                       latest_logs=%s, timeline=%s WHERE inc_id=%s AND org_id=%s RETURNING *""",
                    (json.dumps(logs), json.dumps(timeline), dup_id, org_id))
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return {"action": "updated", "tag": "recurring", "incident": _row_to_dict(row)}

    # 2. CASCADE
    cascade_root  = result.get("cascade_of")
    cascade_entry = result.get("cascade_entry")
    if isinstance(cascade_entry, str):
        try: cascade_entry = json.loads(cascade_entry)
        except: cascade_entry = {"service": "unknown", "symptom": cascade_entry}

    if cascade_root and isinstance(cascade_entry, dict):
        cur.execute("SELECT cascades, timeline FROM incidents WHERE inc_id=%s AND org_id=%s", (cascade_root, org_id))
        root = cur.fetchone()
        if root:
            cascades = json.loads(root["cascades"]) if isinstance(root["cascades"], str) else (root["cascades"] or [])
            cascades.append({"service": cascade_entry.get("service", "unknown"),
                             "symptom": cascade_entry.get("symptom", ""), "detected_at": now.isoformat()})
            timeline = json.loads(root["timeline"]) if isinstance(root["timeline"], str) else (root["timeline"] or [])
            timeline.append({"time": now.strftime("%H:%M:%S"),
                             "event": f"Cascade: {cascade_entry.get('service','?')} — {cascade_entry.get('symptom','')}",
                             "color": "#fb923c"})
            cur.execute("""UPDATE incidents SET cascades=%s, timeline=%s, last_seen=NOW()
                           WHERE inc_id=%s AND org_id=%s RETURNING *""",
                        (json.dumps(cascades), json.dumps(timeline), cascade_root, org_id))
            row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
            return {"action": "cascade", "tag": "cascade", "incident": _row_to_dict(row)}

    # 3. NEW
    timeline = [
        {"time": now.strftime("%H:%M:%S"), "event": "Logs analyzed by AI agent",        "color": "#818cf8"},
        {"time": now.strftime("%H:%M:%S"), "event": "Root cause hypotheses generated",  "color": "#a78bfa"},
        {"time": now.strftime("%H:%M:%S"), "event": "Supporting evidence collected",    "color": "#34d399"},
        {"time": now.strftime("%H:%M:%S"), "event": f"Routed to {result.get('team','?')}", "color": "#60a5fa"},
    ]
    inc_id = _next_inc_id(cur)
    cur.execute("""INSERT INTO incidents
        (inc_id,title,severity,status,services,team,hypotheses,evidence,timeline,ai_summary,cascades,latest_logs,org_id)
        VALUES (%s,%s,%s,'open',%s,%s,%s,%s,%s,%s,'[]',%s,%s) RETURNING *""",
        (inc_id, result["title"], result["severity"],
         result.get("affected_services", []), result.get("team", "Unknown"),
         json.dumps(result.get("hypotheses", [])), json.dumps(result.get("evidence", [])),
         json.dumps(timeline), result.get("ai_summary", ""), json.dumps(logs), org_id))
    row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
    return {"action": "created", "tag": "new", "incident": _row_to_dict(row)}
