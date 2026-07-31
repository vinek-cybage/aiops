import os, re, time, json, logging, urllib.request, urllib.parse
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
_shared_log_dir = os.getenv("SHARED_LOG_DIR", "/var/log/shared")
os.makedirs(_shared_log_dir, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s", force=True,
                     handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(_shared_log_dir, "aiops-api.log"))])
logger = logging.getLogger("aiops")

from database import init_db
from migrate import run_migrations
from agent import analyze
from incidents import save_incident, get_open_incidents
from cases import get_all_cases, get_case_by_id, resolve_case, get_case_actions, apply_action
from teams import update_team, delete_team, get_all_users, get_user, create_user, delete_user, get_services_for_teams
from models.user import ORG_ADMIN, PLATFORM_ADMIN, ORG_ROLES, MEMBER
from auth.routes import router as auth_router
from auth.dependencies import get_current_user, require_role, AuthenticatedUser
from team_members import router as team_members_router
from platform_admin import router as platform_admin_router
from mcp import router as mcp_router
from data_sources import router as data_sources_router
from github_integration import router as github_integration_router

app = FastAPI(title="AIOps POC")

_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,  # required so the httpOnly refresh-token cookie is sent/accepted
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(team_members_router)
app.include_router(platform_admin_router)
app.include_router(mcp_router)
app.include_router(data_sources_router)
app.include_router(github_integration_router)

LOKI_URL               = os.getenv("LOKI_URL",  "http://loki:3100")
TELEMETRY_API_URL      = os.getenv("TELEMETRY_API_URL", "http://telemetry-api:8080")
TELEMETRY_INTERNAL_TOKEN = os.getenv("TELEMETRY_INTERNAL_TOKEN")

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

    # Alembic owns all tenancy/auth schema (organizations, users.org_id/email/
    # password_hash, team_memberships, refresh/reset tokens, ...) — runs after
    # init_db()'s legacy CREATE TABLE IF NOT EXISTS so base tables exist first.
    run_migrations()
    logger.info("Migrations applied")

    logger.info("DB ready — catalog will populate from incoming webhooks")


# ── request bodies ─────────────────────────────────────────────────────────────
class TeamBody(BaseModel):
    name: str; services: list[str] = []

class UserBody(BaseModel):
    name: str; team_id: int | None = None; role: str = MEMBER


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
async def analyze_upload(file: UploadFile = File(...), user: AuthenticatedUser = Depends(get_current_user)):
    if not file.filename.endswith((".log", ".txt", ".out")):
        raise HTTPException(400, "Only .log, .txt, .out files supported")
    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip(): raise HTTPException(400, "File is empty")
    result = analyze(content, get_open_incidents(user.org_id))
    return save_incident(result, result.get("logs", []), user.org_id)

@app.get("/api/incidents")
def list_incidents(user: AuthenticatedUser = Depends(get_current_user)):
    # org_id (JWT) is the hard tenant boundary. Non-admins are additionally
    # narrowed to the services of teams they actually belong to, per the JWT's
    # own (signed, tamper-proof) team_roles — never a client-supplied header.
    if not user.is_platform_admin and user.role != ORG_ADMIN and user.team_ids:
        services = get_services_for_teams(user.team_ids, user.org_id)
        if services:
            return get_all_cases(user.org_id, services=services)
    return get_all_cases(user.org_id)

@app.get("/api/incidents/{inc_id}")
def get_incident(inc_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    inc = get_case_by_id(inc_id, user.org_id)
    if not inc: raise HTTPException(404, "Not found")
    return inc

@app.patch("/api/incidents/{inc_id}/resolve")
def resolve(inc_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    inc = resolve_case(inc_id, user.org_id)
    if not inc: raise HTTPException(404, "Not found")
    return inc

@app.get("/api/incidents/{inc_id}/actions")
def list_case_actions(inc_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    actions = get_case_actions(inc_id, user.org_id)
    if actions is None: raise HTTPException(404, "Not found")
    return actions

@app.post("/api/incidents/{inc_id}/actions/{action_id}/apply")
def apply_case_action(
    inc_id: str, action_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
):
    actor = get_user(user.id, user.org_id)
    result = apply_action(inc_id, action_id, user.org_id, actor["name"] if actor else None)
    if result is None: raise HTTPException(404, "Not found")
    if "error" in result: raise HTTPException(400, result["error"])
    return result

@app.put("/api/teams/{team_id}")
def edit_team(team_id: int, body: TeamBody, user: AuthenticatedUser = Depends(require_role(ORG_ADMIN))):
    t = update_team(team_id, body.name, body.services, user.org_id)
    if not t: raise HTTPException(404, "Not found")
    return t

@app.delete("/api/teams/{team_id}", status_code=204)
def remove_team(team_id: int, user: AuthenticatedUser = Depends(require_role(ORG_ADMIN))):
    if not delete_team(team_id, user.org_id): raise HTTPException(404, "Not found")

@app.get("/api/users")
def list_users(user: AuthenticatedUser = Depends(require_role(ORG_ADMIN))):
    return get_all_users(user.org_id)

@app.post("/api/users", status_code=201)
def add_user(body: UserBody, user: AuthenticatedUser = Depends(require_role(ORG_ADMIN))):
    if body.role not in ORG_ROLES:
        raise HTTPException(400, f"role must be one of {ORG_ROLES}")
    if body.role == PLATFORM_ADMIN and not user.is_platform_admin:
        raise HTTPException(403, "Only a platform_admin can create another platform_admin")
    created = create_user(body.name, body.team_id, body.role, user.org_id)
    if created is None:
        raise HTTPException(400, "team_id does not belong to your organization")
    return created

@app.delete("/api/users/{user_id}", status_code=204)
def remove_user(user_id: int, user: AuthenticatedUser = Depends(require_role(ORG_ADMIN))):
    if not delete_user(user_id, user.org_id): raise HTTPException(404, "Not found")


# ── webhook (Grafana / Prometheus alertmanager format) ─────────────────────────
def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "alert"


_LOG_LINE_RE = re.compile(r"^\S+\s+\S+\s+(\S+)\s+\[([^\]]+)\]\s+(.*)$")

def _parse_log_line(line: str, event: str) -> dict | None:
    """Parses '<date> <time> <LEVEL> [<service>] <message> | k=v | ... | trace_id=<hex>'
    (the log-line format documented in README.md) into telemetry-api's LogEntry shape."""
    head, *kv_parts = line.split(" | ")
    m = _LOG_LINE_RE.match(head)
    if not m:
        return None
    level, service, message = m.group(1), m.group(2), m.group(3)
    context, trace_id = {}, None
    for kv in kv_parts:
        if "=" not in kv:
            continue
        k, _, v = kv.partition("=")
        k, v = k.strip(), v.strip()
        context[k] = v
        if k == "trace_id":
            trace_id = v
    return {"service": service, "level": level, "event": event,
            "traceId": trace_id, "message": message, "context": context or None}


def _bridge_logs_to_telemetry(log_lines: list[str], alertname: str | None):
    """Writes parsed log lines into the shared aiops-db via telemetry-api's
    POST /api/logs, so orchestrator's Stage 1 poller (which only reads the
    logs/metrics tables) sees fault data on its next tick — load-gen itself
    never calls telemetry-api directly, it only fires this webhook."""
    event = _slugify(alertname) if alertname else "alert"
    entries = [e for line in log_lines if (e := _parse_log_line(line, event))]
    if not entries:
        return
    headers = {"Content-Type": "application/json"}
    if TELEMETRY_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = TELEMETRY_INTERNAL_TOKEN
    req = urllib.request.Request(
        f"{TELEMETRY_API_URL}/api/logs",
        data=json.dumps(entries).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()
    logger.info("Bridged %d log line(s) to telemetry-api", len(entries))


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


def _process_webhook(payload: dict):
    firing = [a for a in payload.get("alerts", [payload]) if a.get("status", "firing") == "firing"]
    if not firing:
        return

    alert_service = None
    alert_app = None
    alertname = None
    for a in firing:
        lb = a.get("labels", {})
        alert_service = lb.get("service_name") or lb.get("service") or None
        alert_app     = lb.get("app") or lb.get("job") or None
        alertname     = alertname or lb.get("alertname")
        if alert_service:
            break
    _catalog_add(alert_app, alert_service)

    # If payload includes inline context (mock mode, used by load-gen), use it directly.
    inline_logs = payload.get("context", {}).get("logs", [])

    if inline_logs:
        log_lines = inline_logs
        logger.info("Webhook (inline context): %d alerts | service=%s | %d log lines",
                    len(firing), alert_service, len(log_lines))
    else:
        # Live mode — fetch from Loki
        label_trace_id = None
        for a in firing:
            label_trace_id = a.get("labels", {}).get("trace_id")
            if label_trace_id:
                break

        if label_trace_id:
            loki_logs = _fetch_loki_logs(lookback=90, limit=50, trace_id=label_trace_id)
            if not loki_logs:
                loki_logs = _fetch_loki_logs(lookback=90, limit=50, service=alert_service)
        else:
            loki_logs = _fetch_loki_logs(lookback=300, limit=50, service=alert_service)

        log_lines = loki_logs.splitlines() if loki_logs else []
        logger.info("Webhook (live): %d alerts | service=%s | %d log lines",
                    len(firing), alert_service, len(log_lines))

    try:
        _bridge_logs_to_telemetry(log_lines, alertname)
    except Exception:
        logger.exception("Webhook -> telemetry-api bridge failed")


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
app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="frontend-assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    # React Router uses real browser paths (/app/dashboard, /login, ...) — a
    # plain StaticFiles(html=True) mount only auto-serves index.html for "/",
    # so a hard refresh on any other client-side route would 404 without this
    # catch-all. Must stay registered last so it never shadows /api/* routes.
    candidate = os.path.join(_frontend, full_path)
    if full_path and os.path.isfile(candidate):
        return FileResponse(candidate)
    return FileResponse(os.path.join(_frontend, "index.html"))
