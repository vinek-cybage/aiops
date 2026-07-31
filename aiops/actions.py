import base64, json, os, re, time, urllib.parse, urllib.request

GITHUB_API = "https://api.github.com"

# "owner/repo" only — GitHub repo/owner names are limited to alphanumerics,
# hyphens, underscores, and dots (never "/", "?", "#", ".."), so this also
# rejects path-traversal / query-injection attempts before they ever reach a
# URL. Branch names are far more permissive in real Git, so base_branch is
# just percent-encoded (not format-validated) when it's placed in a URL path.
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# The only org allowed to fall back to the shared global GITHUB_TOKEN/REPO env
# vars below — any other org without its own GitHub integration is refused
# outright, so one tenant's case content (logs, AI summary, hypotheses) can
# never be pushed as a PR into a repo that isn't theirs.
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


class GitHubNotConfigured(Exception):
    pass


def _gh_request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{GITHUB_API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _team_github_config(team_id: int | None) -> tuple[str, str, str] | None:
    """Looks up this team's own GitHub integration (repo_full_name, base_branch,
    decrypted token) if one is configured. Returns None if not — callers fall
    back to the global env vars (deprecated path, kept only until every active
    team has migrated to per-team config)."""
    if team_id is None:
        return None
    from db_session import SessionLocal
    from models.github_integration import TeamGithubIntegration
    from models.credential import EncryptedCredential
    from crypto import decrypt_fields

    db = SessionLocal()
    try:
        integ = db.query(TeamGithubIntegration).filter_by(team_id=team_id, enabled=True).one_or_none()
        if not integ:
            return None
        cred = db.get(EncryptedCredential, integ.credential_id)
        if not cred:
            return None
        token = decrypt_fields(cred.ciphertext).get("token")
        if not token:
            return None
        return integ.repo_full_name, integ.base_branch, token
    finally:
        db.close()


def raise_pr(case: dict, case_action: dict, team_id: int | None, org_id: str) -> dict:
    """Opens a real PR: a new branch off the base branch, a remediation-notes
    file describing the case + suggested action, and a pull request.

    Resolves credentials in order: (1) this case's team's own GitHub
    integration (team_github_integrations, encrypted token), (2) the legacy
    global GITHUB_TOKEN/GITHUB_REPO env vars — available ONLY to the Default
    Org (single-tenant/demo use), never to a real tenant without its own
    integration, since that shared repo is not scoped per-org. Fails closed
    (raises GitHubNotConfigured) if neither applies."""
    team_config = _team_github_config(team_id)
    if team_config:
        repo, base, token = team_config
    else:
        if org_id != _DEFAULT_ORG_ID:
            raise GitHubNotConfigured(
                "GitHub isn't configured for this team — add a GitHub integration in Team "
                "Settings. The shared legacy GITHUB_TOKEN/GITHUB_REPO fallback is only "
                "available to the Default Org, to avoid pushing your case data into a repo "
                "shared with other tenants."
            )
        token = os.getenv("GITHUB_TOKEN")
        repo  = os.getenv("GITHUB_REPO")
        base  = os.getenv("GITHUB_BASE_BRANCH", "main")
        if not token or not repo:
            raise GitHubNotConfigured(
                "GitHub isn't configured for this team — add a GitHub integration in Team Settings, "
                "or set the legacy GITHUB_TOKEN/GITHUB_REPO env vars"
            )

    if not _REPO_RE.match(repo):
        raise GitHubNotConfigured(f"Configured repo {repo!r} is not a valid 'owner/repo' name")
    repo_path = urllib.parse.quote(repo, safe="/")
    base_path = urllib.parse.quote(base, safe="")

    case_id = case["id"]
    branch  = f"remediation/case-{case_id}-{int(time.time())}"

    base_ref = _gh_request("GET", f"/repos/{repo_path}/git/ref/heads/{base_path}", token)
    _gh_request("POST", f"/repos/{repo_path}/git/refs", token,
                {"ref": f"refs/heads/{branch}", "sha": base_ref["object"]["sha"]})

    note = (
        f"# Remediation for {case.get('primary_service')} — Case #{case_id}\n\n"
        f"**Title:** {case.get('title') or 'Untitled case'}\n\n"
        f"**AI summary:** {case.get('ai_summary') or 'n/a'}\n\n"
        f"**Suggested action:** {case_action['name']} — {case_action['description']}\n\n"
        "**Hypotheses:**\n" +
        "\n".join(f"- ({h.get('confidence')}%) {h.get('text')}" for h in (case.get("hypotheses") or []))
    )
    path = f"remediation-notes/CASE-{case_id}.md"
    _gh_request("PUT", f"/repos/{repo_path}/contents/{path}", token, {
        "message": f"Remediation notes for case #{case_id}",
        "content": base64.b64encode(note.encode()).decode(),
        "branch": branch,
    })

    pr = _gh_request("POST", f"/repos/{repo_path}/pulls", token, {
        "title": f"Remediation: {case_action['name']} for case #{case_id}",
        "head": branch,
        "base": base,
        "body": note,
    })

    return {"pr_url": pr["html_url"], "pr_number": pr["number"]}
