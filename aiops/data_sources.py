import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db_session import get_db
from models.team import Team
from models.credential import DATA_SOURCE, EncryptedCredential
from models.data_source import TeamDataSource, TeamIngestionKey

from auth.dependencies import AuthenticatedUser, get_current_user, assert_can_manage_team, assert_can_view_team
from auth.jwt import hash_token
from crypto import encrypt_fields, masked_preview
from net_guard import UnsafeUrlError, safe_get, validate_outbound_url

router = APIRouter(prefix="/api/teams", tags=["data-sources"])


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


def _serialize_data_source(ds: TeamDataSource, credential: EncryptedCredential | None) -> dict:
    return {
        "id": str(ds.id), "team_id": ds.team_id, "type": ds.type, "display_name": ds.display_name,
        "connection_config": ds.connection_config, "credential_masked": credential.masked_preview if credential else None,
        "status": ds.status, "last_checked_at": ds.last_checked_at, "last_error": ds.last_error, "enabled": ds.enabled,
    }


@router.get("/{team_id}/data-sources")
def list_data_sources(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_view_team(user, team_id, team.org_id)
    rows = db.execute(select(TeamDataSource).where(TeamDataSource.team_id == team_id)).scalars().all()
    creds = {
        c.id: c for c in db.execute(
            select(EncryptedCredential).where(EncryptedCredential.owner_type == DATA_SOURCE, EncryptedCredential.team_id == team_id)
        ).scalars()
    }
    return [_serialize_data_source(d, creds.get(d.credential_id)) for d in rows]


class DataSourceBody(BaseModel):
    type: str
    display_name: str
    connection_config: dict = {}
    credentials: dict | None = None


@router.post("/{team_id}/data-sources", status_code=201)
def create_data_source(
    team_id: int, body: DataSourceBody, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    base_url = body.connection_config.get("base_url")
    if base_url:
        try:
            validate_outbound_url(base_url)
        except UnsafeUrlError as e:
            raise HTTPException(400, f"Unsafe base_url: {e}")

    now = datetime.now(timezone.utc)
    credential_id = None
    cred = None
    if body.credentials:
        cred = EncryptedCredential(
            id=uuid.uuid4(), team_id=team_id, owner_type=DATA_SOURCE, owner_id=None,
            ciphertext=encrypt_fields(body.credentials), field_names=list(body.credentials.keys()),
            masked_preview=masked_preview(body.credentials), created_by_user_id=user.id, created_at=now, updated_at=now,
        )
        db.add(cred)
        db.flush()
        credential_id = cred.id

    ds = TeamDataSource(
        id=uuid.uuid4(), team_id=team_id, type=body.type, display_name=body.display_name,
        connection_config=body.connection_config, credential_id=credential_id,
        created_by_user_id=user.id, created_at=now, updated_at=now,
    )
    db.add(ds)
    if credential_id:
        db.flush()
        cred.owner_id = ds.id
    db.commit()
    return _serialize_data_source(ds, cred)


@router.put("/{team_id}/data-sources/{ds_id}")
def update_data_source(
    team_id: int, ds_id: str, body: DataSourceBody,
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    ds = db.get(TeamDataSource, uuid.UUID(ds_id))
    if not ds or ds.team_id != team_id:
        raise HTTPException(404, "Not found")

    base_url = body.connection_config.get("base_url")
    if base_url:
        try:
            validate_outbound_url(base_url)
        except UnsafeUrlError as e:
            raise HTTPException(400, f"Unsafe base_url: {e}")

    ds.type = body.type
    ds.display_name = body.display_name
    ds.connection_config = body.connection_config
    ds.updated_at = datetime.now(timezone.utc)

    cred = db.get(EncryptedCredential, ds.credential_id) if ds.credential_id else None
    if body.credentials:
        now = datetime.now(timezone.utc)
        if cred:
            cred.ciphertext = encrypt_fields(body.credentials)
            cred.field_names = list(body.credentials.keys())
            cred.masked_preview = masked_preview(body.credentials)
            cred.updated_at = now
        else:
            cred = EncryptedCredential(
                id=uuid.uuid4(), team_id=team_id, owner_type=DATA_SOURCE, owner_id=ds.id,
                ciphertext=encrypt_fields(body.credentials), field_names=list(body.credentials.keys()),
                masked_preview=masked_preview(body.credentials), created_by_user_id=user.id, created_at=now, updated_at=now,
            )
            db.add(cred)
            db.flush()
            ds.credential_id = cred.id

    db.commit()
    return _serialize_data_source(ds, cred)


@router.delete("/{team_id}/data-sources/{ds_id}", status_code=204)
def delete_data_source(
    team_id: int, ds_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    ds = db.get(TeamDataSource, uuid.UUID(ds_id))
    if not ds or ds.team_id != team_id:
        raise HTTPException(404, "Not found")
    if ds.credential_id:
        cred = db.get(EncryptedCredential, ds.credential_id)
        if cred:
            db.delete(cred)
    db.delete(ds)
    db.commit()


@router.post("/{team_id}/data-sources/{ds_id}/test-connection")
def test_data_source_connection(
    team_id: int, ds_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    ds = db.get(TeamDataSource, uuid.UUID(ds_id))
    if not ds or ds.team_id != team_id:
        raise HTTPException(404, "Not found")

    base_url = ds.connection_config.get("base_url")
    if not base_url:
        ds.status, ds.last_error = "error", "No base_url configured"
    else:
        try:
            safe_get(base_url)
            ds.status, ds.last_error = "connected", None
        except UnsafeUrlError as e:
            ds.status, ds.last_error = "error", f"Blocked: {e}"
        except Exception as e:
            ds.status, ds.last_error = "error", str(e)[:500]
    ds.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": ds.status, "last_error": ds.last_error}


# ── ingestion keys ────────────────────────────────────────────────────────────

@router.get("/{team_id}/ingestion-keys")
def list_ingestion_keys(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)
    rows = db.execute(
        select(TeamIngestionKey).where(TeamIngestionKey.team_id == team_id, TeamIngestionKey.revoked_at.is_(None))
    ).scalars().all()
    return [
        {"id": str(k.id), "key_prefix": k.key_prefix, "label": k.label, "scopes": k.scopes, "last_used_at": k.last_used_at}
        for k in rows
    ]


class CreateIngestionKeyBody(BaseModel):
    label: str | None = None


@router.post("/{team_id}/ingestion-keys", status_code=201)
def create_ingestion_key(
    team_id: int, body: CreateIngestionKeyBody,
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    raw_key = f"aiops_live_{secrets.token_urlsafe(32)}"
    key = TeamIngestionKey(
        id=uuid.uuid4(), team_id=team_id, key_prefix=raw_key[:16], key_hash=hash_token(raw_key),
        label=body.label, created_by_user_id=user.id, created_at=datetime.now(timezone.utc),
    )
    db.add(key)
    db.commit()
    # plaintext key is returned exactly once — only key_hash is ever persisted.
    return {"id": str(key.id), "key": raw_key, "key_prefix": key.key_prefix, "label": key.label}


@router.delete("/{team_id}/ingestion-keys/{key_id}", status_code=204)
def revoke_ingestion_key(
    team_id: int, key_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    key = db.get(TeamIngestionKey, uuid.UUID(key_id))
    if not key or key.team_id != team_id:
        raise HTTPException(404, "Not found")
    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
