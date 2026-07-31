import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from db_session import get_db
from models.team import Team
from models.credential import GITHUB_INTEGRATION, EncryptedCredential
from models.github_integration import TeamGithubIntegration

from auth.dependencies import AuthenticatedUser, get_current_user, assert_can_manage_team, assert_can_view_team
from crypto import encrypt_fields, decrypt_fields, masked_preview

router = APIRouter(prefix="/api/teams", tags=["github-integration"])


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


def _serialize(integ: TeamGithubIntegration, credential: EncryptedCredential | None) -> dict:
    return {
        "id": str(integ.id), "team_id": integ.team_id, "auth_mode": integ.auth_mode,
        "repo_full_name": integ.repo_full_name, "base_branch": integ.base_branch,
        "token_masked": credential.masked_preview if credential else None,
        "status": integ.status, "last_checked_at": integ.last_checked_at, "last_error": integ.last_error,
        "enabled": integ.enabled,
    }


@router.get("/{team_id}/github-integration")
def get_github_integration(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_view_team(user, team_id, team.org_id)
    integ = db.query(TeamGithubIntegration).filter_by(team_id=team_id).one_or_none()
    if not integ:
        return None
    cred = db.get(EncryptedCredential, integ.credential_id)
    return _serialize(integ, cred)


# "owner/repo" only — matches GitHub's own naming rules and rejects "/", "?",
# "#", ".." before this value is ever spliced into a GitHub API URL path
# (here or in actions.py's raise_pr).
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GithubIntegrationBody(BaseModel):
    repo_full_name: str
    base_branch: str = "main"
    token: str | None = None  # write-only; omit to leave an existing token unchanged

    @field_validator("repo_full_name")
    @classmethod
    def _validate_repo_full_name(cls, v: str) -> str:
        if not _REPO_RE.match(v):
            raise ValueError("repo_full_name must look like 'owner/repo'")
        return v


@router.put("/{team_id}/github-integration")
def upsert_github_integration(
    team_id: int, body: GithubIntegrationBody,
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    now = datetime.now(timezone.utc)
    integ = db.query(TeamGithubIntegration).filter_by(team_id=team_id).one_or_none()
    cred = db.get(EncryptedCredential, integ.credential_id) if integ else None

    if not integ and not body.token:
        raise HTTPException(400, "token is required when first configuring this integration")

    if body.token:
        fields = {"token": body.token}
        if cred:
            cred.ciphertext = encrypt_fields(fields)
            cred.field_names = ["token"]
            cred.masked_preview = masked_preview(fields)
            cred.updated_at = now
        else:
            cred = EncryptedCredential(
                id=uuid.uuid4(), team_id=team_id, owner_type=GITHUB_INTEGRATION, owner_id=None,
                ciphertext=encrypt_fields(fields), field_names=["token"], masked_preview=masked_preview(fields),
                created_by_user_id=user.id, created_at=now, updated_at=now,
            )
            db.add(cred)
            db.flush()

    if integ:
        integ.repo_full_name = body.repo_full_name
        integ.base_branch = body.base_branch
        integ.updated_at = now
    else:
        integ = TeamGithubIntegration(
            id=uuid.uuid4(), team_id=team_id, repo_full_name=body.repo_full_name, base_branch=body.base_branch,
            credential_id=cred.id, created_by_user_id=user.id, created_at=now, updated_at=now,
        )
        db.add(integ)
        db.flush()
        cred.owner_id = integ.id

    db.commit()
    return _serialize(integ, cred)


@router.delete("/{team_id}/github-integration", status_code=204)
def delete_github_integration(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    integ = db.query(TeamGithubIntegration).filter_by(team_id=team_id).one_or_none()
    if not integ:
        raise HTTPException(404, "Not found")
    cred = db.get(EncryptedCredential, integ.credential_id)
    if cred:
        db.delete(cred)
    db.delete(integ)
    db.commit()


@router.post("/{team_id}/github-integration/test-connection")
def test_github_integration(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    integ = db.query(TeamGithubIntegration).filter_by(team_id=team_id).one_or_none()
    if not integ:
        raise HTTPException(404, "Not found")
    cred = db.get(EncryptedCredential, integ.credential_id)

    import urllib.request, urllib.error, urllib.parse
    now = datetime.now(timezone.utc)
    try:
        if not _REPO_RE.match(integ.repo_full_name):
            raise ValueError(f"Stored repo_full_name {integ.repo_full_name!r} is not a valid 'owner/repo' name")
        token = decrypt_fields(cred.ciphertext)["token"]
        req = urllib.request.Request(
            f"https://api.github.com/repos/{urllib.parse.quote(integ.repo_full_name, safe='/')}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        integ.status, integ.last_error = "connected", None
    except urllib.error.HTTPError as e:
        integ.status, integ.last_error = "error", f"GitHub API returned {e.code}"
    except Exception as e:
        integ.status, integ.last_error = "error", str(e)[:500]
    integ.last_checked_at = now
    db.commit()
    return {"status": integ.status, "last_error": integ.last_error}
