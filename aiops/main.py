import os, re, time, json, logging, urllib.request, urllib.parse
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s", force=True)
logger = logging.getLogger("aiops")

from database import init_db
from agent import analyze
from incidents import save_incident, get_open_incidents, get_all_incidents, get_incident_by_id, resolve_incident
from teams import get_all_teams, create_team, update_team, delete_team, get_all_users, get_user, create_user, delete_user

app = FastAPI(title="AIOps POC")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

LOKI_URL  = os.getenv("LOKI_URL",  "http://loki:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://tempo:3200")

# ── Service catalog (built from webhook payloads, no polling) ─────────────────
_catalog: dict = {"apps": set(), "services": set(), "last_updated": None}

def _catalog_add(app: str | None, service: str | None):
    changed = False
    if app and app not in _catalog["apps"]:
        _catalog["apps"].add(app)
        changed = True
    if service and service not in _catalog["services"]:
        _catalog["services"].add(service)
        changed = True
    if changed:
        _catalog["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info("Catalog updated — apps=%s services=%s", len(_catalog["apps"]), len(_catalog["services"]))


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms  = round((time.time() - start) * 1000, 1)
    lvl = "ERROR" if response.status_code >= 500 else "WARN" if response.status_code >= 400 else "INFO"
    logger.log(getattr(logging, lvl), "aiops-api | %s %s | %d | %sms",
               request.method, request.url.path, response.status_code, ms)
    return response


@app.on_event("startup")
def startup():
    for i in range(10):
        try: init_db(); logger.info("DB ready"); break
        except Exception as e: logger.warning("DB not ready (%d/10): %s", i+1, e); time.sleep(2)
    else:
        raise RuntimeError("DB unavailable after 10 attempts")
    logger.info("DB ready — catalog will populate from incoming webhooks")


# ── auth helpers ───────────────────────────────────────────────────────────────
def _get_user(x_user_id):
    try: return get_user(int(x_user_id)) if x_user_id else None
    except: return None

def _admin(x_user_id):
    u = _get_user(x_user_id)
    if not u or u["role"] != "admin": raise HTTPException(403, "Admin access required")
    return u


# ── request bodies ─────────────────────────────────────────────────────────────
class TeamBody(BaseModel):
    name: str; services: list[str] = []

class UserBody(BaseModel):
    name: str; team_id: int | None = None; role: str = "member"


# ── routes ─────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health(): return {"status": "ok"}

@app.get("/api/catalog")
def catalog():
    return {
        "apps":         sorted(_catalog["apps"]),
        "services":     sorted(_catalog["services"]),
        "last_updated": _catalog["last_updated"],
    }


@app.post("/api/analyze/upload")
async def analyze_upload(file: UploadFile = File(...)):
    if not file.filename.endswith((".log", ".txt", ".out")):
        raise HTTPException(400, "Only .log, .txt, .out files supported")
    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip(): raise HTTPException(400, "File is empty")
    result = analyze(content, get_open_incidents())
    return save_incident(result, result.get("logs", []))

@app.get("/api/incidents")
def list_incidents(x_user_id: Optional[str] = Header(None)):
    u = _get_user(x_user_id)
    if u and u["role"] != "admin" and u.get("team_services"):
        return get_all_incidents(services=u["team_services"])
    return get_all_incidents()

@app.get("/api/incidents/{inc_id}")
def get_incident(inc_id: str):
    inc = get_incident_by_id(inc_id)
    if not inc: raise HTTPException(404, "Not found")
    return inc

@app.patch("/api/incidents/{inc_id}/resolve")
def resolve(inc_id: str):
    inc = resolve_incident(inc_id)
    if not inc: raise HTTPException(404, "Not found")
    return inc

@app.get("/api/teams")
def list_teams(): return get_all_teams()

@app.post("/api/teams", status_code=201)
def add_team(body: TeamBody, x_user_id: Optional[str] = Header(None)):
    _admin(x_user_id); return create_team(body.name, body.services)

@app.put("/api/teams/{team_id}")
def edit_team(team_id: int, body: TeamBody, x_user_id: Optional[str] = Header(None)):
    _admin(x_user_id)
    t = update_team(team_id, body.name, body.services)
    if not t: raise HTTPException(404, "Not found")
    return t

@app.delete("/api/teams/{team_id}", status_code=204)
def remove_team(team_id: int, x_user_id: Optional[str] = Header(None)):
    _admin(x_user_id)
    if not delete_team(team_id): raise HTTPException(404, "Not found")

@app.get("/api/users")
def list_users(): return get_all_users()

@app.post("/api/users", status_code=201)
def add_user(body: UserBody, x_user_id: Optional[str] = Header(None)):
    _admin(x_user_id); return create_user(body.name, body.team_id, body.role)

@app.delete("/api/users/{user_id}", status_code=204)
def remove_user(user_id: int, x_user_id: Optional[str] = Header(None)):
    _admin(x_user_id)
    if not delete_user(user_id): raise HTTPException(404, "Not found")


# ── webhook (Grafana / Prometheus alertmanager format) ─────────────────────────
def _alert_to_text(payload: dict) -> str:
    lines = []
    for alert in payload.get("alerts", [payload]):
        lb, an = alert.get("labels", {}), alert.get("annotations", {})
        lines += [
            f"[ALERT] status={alert.get('status','firing')} startsAt={alert.get('startsAt','')}",
            f"  alertname={lb.get('alertname','unknown')}",
            f"  severity={lb.get('severity', lb.get('priority','unknown'))}",
            f"  service={lb.get('service_name', lb.get('job','unknown'))}",
            f"  summary={an.get('summary', an.get('message',''))}",
            f"  description={an.get('description','')}",
        ] + [f"  {k}={v}" for k, v in lb.items()
             if k not in ("alertname","severity","priority","service_name","job")]
    return "\n".join(lines)

def _fetch_loki_logs(lookback: int = 120, limit: int = 100, trace_id: str = None, service: str = None) -> str:
    """Fetch logs from Loki. If trace_id given, fetch logs for that specific trace.
    If service given, scope to that service. Falls back to recent ERROR/WARN logs."""
    try:
        end   = int(time.time() * 1e9)
        start = end - int(lookback * 1e9)

        if trace_id:
            query = f'{{app=~"demo-service|aiops-api"}} |= "trace_id={trace_id}"'
        elif service:
            query = f'{{app=~"demo-service|aiops-api"}} |= "{service}" |~ "ERROR|CRITICAL|WARN"'
        else:
            query = '{app=~"demo-service|aiops-api"} |~ "ERROR|CRITICAL|WARN"'

        params = urllib.parse.urlencode({
            "query": query, "limit": limit,
            "start": start, "end": end, "direction": "forward",
        })
        with urllib.request.urlopen(f"{LOKI_URL}/loki/api/v1/query_range?{params}", timeout=5) as r:
            data = json.loads(r.read())
        lines = [line for s in data.get("data", {}).get("result", []) for _, line in s.get("values", [])]
        return "\n".join(lines[-limit:])
    except Exception as e:
        logger.warning("Loki fetch failed: %s", e); return ""


def _fetch_tempo_trace(trace_id: str) -> str:
    """Fetch full trace from Tempo and format spans as readable context for LLM."""
    try:
        with urllib.request.urlopen(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=5) as r:
            data = json.loads(r.read())
        lines = [f"TRACE {trace_id}:"]
        for batch in data.get("batches", []):
            svc = next((a["value"]["stringValue"] for a in batch.get("resource", {}).get("attributes", [])
                        if a["key"] == "service.name"), "unknown")
            for span in batch.get("scopeSpans", [{}])[0].get("spans", []):
                name     = span.get("name", "")
                status   = span.get("status", {})
                dur_ns   = int(span.get("endTimeUnixNano", 0)) - int(span.get("startTimeUnixNano", 0))
                dur_ms   = round(dur_ns / 1e6, 1)
                err      = status.get("code") == 2 or status.get("message", "")
                attrs    = {a["key"]: a.get("value", {}).get("stringValue", a.get("value", {}).get("intValue", ""))
                            for a in span.get("attributes", [])}
                err_flag = " [ERROR]" if err else ""
                attr_str = " | ".join(f"{k}={v}" for k, v in attrs.items() if k not in ("http.method",))
                lines.append(f"  [{svc}] {name}{err_flag} duration={dur_ms}ms {attr_str}".rstrip())
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Tempo trace fetch failed for %s: %s", trace_id, e); return ""


def _fetch_recent_traces_for_service(service: str, limit: int = 3) -> list[str]:
    """Find recent trace IDs for a service from Tempo search."""
    try:
        params = urllib.parse.urlencode({"service.name": service, "limit": limit})
        with urllib.request.urlopen(f"{TEMPO_URL}/api/search?{params}", timeout=5) as r:
            data = json.loads(r.read())
        return [t["traceID"] for t in data.get("traces", [])]
    except Exception as e:
        logger.warning("Tempo search failed: %s", e); return []


def _extract_trace_ids(text: str) -> list[str]:
    """Extract trace_id values from log lines."""
    return list(dict.fromkeys(re.findall(r"trace_id=([a-f0-9]{16,32})", text)))


def _process_webhook(payload: dict):
    firing = [a for a in payload.get("alerts", [payload]) if a.get("status", "firing") == "firing"]
    if not firing:
        return

    alert_service = None
    alert_app = None
    for a in firing:
        lb = a.get("labels", {})
        alert_service = lb.get("service_name") or lb.get("service") or None
        alert_app     = lb.get("app") or lb.get("job") or None
        if alert_service:
            break
    _catalog_add(alert_app, alert_service)

    alert_text = _alert_to_text(payload)
    context    = alert_text

    # If payload includes inline context (mock mode), use it directly — no Loki/Tempo needed
    inline = payload.get("context", {})
    inline_logs   = "\n".join(inline.get("logs",   []))
    inline_traces = "\n".join(inline.get("traces", []))

    if inline_logs or inline_traces:
        if inline_logs:
            context += f"\n\n[LOGS — service={alert_service or 'all'}]\n{inline_logs}"
        if inline_traces:
            context += f"\n\n[TRACES]\n{inline_traces}"
        logger.info("Webhook (inline context): %d alerts | service=%s | %d log lines | %d trace lines",
                    len(firing), alert_service, inline_logs.count('\n') + 1 if inline_logs else 0,
                    inline_traces.count('\n') + 1 if inline_traces else 0)
    else:
        # Live mode — fetch from Loki and Tempo
        label_trace_id = None
        for a in firing:
            label_trace_id = a.get("labels", {}).get("trace_id")
            if label_trace_id:
                break

        if label_trace_id:
            loki_logs = _fetch_loki_logs(lookback=90, limit=50, trace_id=label_trace_id)
            if not loki_logs:
                loki_logs = _fetch_loki_logs(lookback=90, limit=50, service=alert_service)
            trace_ids = [label_trace_id]
        else:
            loki_logs = _fetch_loki_logs(lookback=300, limit=50, service=alert_service)
            trace_ids = _extract_trace_ids(loki_logs)
            if not trace_ids and alert_service:
                trace_ids = _fetch_recent_traces_for_service(alert_service, limit=2)

        trace_sections = [t for tid in trace_ids[:2] if (t := _fetch_tempo_trace(tid))]

        if loki_logs:
            context += f"\n\n[LOKI LOGS — service={alert_service or 'all'}, last 5min]\n{loki_logs}"
        if trace_sections:
            context += f"\n\n[TEMPO TRACES — {len(trace_sections)} traces]\n" + "\n\n".join(trace_sections)

        logger.info("Webhook (live): %d alerts | service=%s | %d log lines | %d traces",
                    len(firing), alert_service, loki_logs.count('\n') + 1 if loki_logs else 0, len(trace_sections))
    try:
        result = analyze(context, get_open_incidents())
        saved  = save_incident(result, result.get("logs", []))
        logger.info("Incident %s (%s)", saved["incident"]["inc_id"], saved["action"])
    except Exception:
        logger.exception("Webhook processing failed")


@app.post("/api/webhook/grafana", status_code=202)
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try: payload = await request.json()
    except: raise HTTPException(400, "Invalid JSON")

    firing = [a for a in payload.get("alerts", [payload]) if a.get("status", "firing") == "firing"]
    if not firing:
        return {"status": "ignored", "reason": "no firing alerts"}

    background_tasks.add_task(_process_webhook, payload)
    return {"status": "accepted"}


_frontend = os.getenv("FRONTEND_DIR", "/app/web")
app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
