import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db_session import get_db
from models.team import Team
from models.credential import MCP_INSTANCE, EncryptedCredential
from models.mcp import McpCatalogEntry, TeamMcpInstance

from auth.dependencies import AuthenticatedUser, get_current_user, assert_can_manage_team, assert_can_view_team, require_role
from models.user import ORG_ADMIN, PLATFORM_ADMIN
from crypto import encrypt_fields, masked_preview
from net_guard import UnsafeUrlError, safe_get, validate_outbound_url

router = APIRouter(tags=["mcp"])


# ── catalog (platform-level) ─────────────────────────────────────────────────

@router.get("/api/mcp/catalog")
def list_catalog(category: str | None = None, _: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(McpCatalogEntry).where(McpCatalogEntry.is_active.is_(True))
    if category:
        stmt = stmt.where(McpCatalogEntry.category == category)
    entries = db.execute(stmt.order_by(McpCatalogEntry.name)).scalars().all()
    return [_serialize_catalog_entry(e) for e in entries]


@router.get("/api/mcp/catalog/{entry_id}")
def get_catalog_entry(entry_id: str, _: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.get(McpCatalogEntry, uuid.UUID(entry_id))
    if not entry:
        raise HTTPException(404, "Not found")
    return _serialize_catalog_entry(entry)


class CatalogEntryBody(BaseModel):
    slug: str
    name: str
    vendor: str | None = None
    description: str | None = None
    icon_url: str | None = None
    category: str | None = None
    connection_type: str = "streamable_http"
    default_endpoint_url: str | None = None
    credential_schema: list = []
    config_schema: list = []
    is_verified: bool = False


@router.post("/api/mcp/catalog", status_code=201)
def create_catalog_entry(
    body: CatalogEntryBody,
    _: AuthenticatedUser = Depends(require_role(ORG_ADMIN, PLATFORM_ADMIN)),
    db: Session = Depends(get_db),
):
    entry = McpCatalogEntry(id=uuid.uuid4(), created_at=datetime.now(timezone.utc), **body.model_dump())
    db.add(entry)
    db.commit()
    return _serialize_catalog_entry(entry)


@router.delete("/api/mcp/catalog/{entry_id}", status_code=204)
def deactivate_catalog_entry(
    entry_id: str, _: AuthenticatedUser = Depends(require_role(ORG_ADMIN, PLATFORM_ADMIN)), db: Session = Depends(get_db)
):
    entry = db.get(McpCatalogEntry, uuid.UUID(entry_id))
    if not entry:
        raise HTTPException(404, "Not found")
    entry.is_active = False
    db.commit()


def _serialize_catalog_entry(e: McpCatalogEntry) -> dict:
    return {
        "id": str(e.id), "slug": e.slug, "name": e.name, "vendor": e.vendor, "description": e.description,
        "icon_url": e.icon_url, "category": e.category, "connection_type": e.connection_type,
        "default_endpoint_url": e.default_endpoint_url, "credential_schema": e.credential_schema,
        "config_schema": e.config_schema, "is_verified": e.is_verified,
    }


# ── team MCP instances ────────────────────────────────────────────────────────

def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


def _serialize_instance(inst: TeamMcpInstance, credential: EncryptedCredential | None) -> dict:
    return {
        "id": str(inst.id),
        "team_id": inst.team_id,
        "catalog_entry_id": str(inst.catalog_entry_id) if inst.catalog_entry_id else None,
        "source": inst.source,
        "display_name": inst.display_name,
        "connection_type": inst.connection_type,
        "endpoint_url": inst.endpoint_url,
        "config": inst.config,
        "credential_masked": credential.masked_preview if credential else None,
        "status": inst.status,
        "last_checked_at": inst.last_checked_at,
        "last_error": inst.last_error,
        "enabled": inst.enabled,
    }


@router.get("/api/teams/{team_id}/mcp-instances")
def list_team_mcp_instances(
    team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_view_team(user, team_id, team.org_id)
    instances = db.execute(select(TeamMcpInstance).where(TeamMcpInstance.team_id == team_id)).scalars().all()
    creds = {
        c.id: c for c in db.execute(
            select(EncryptedCredential).where(EncryptedCredential.owner_type == MCP_INSTANCE, EncryptedCredential.team_id == team_id)
        ).scalars()
    }
    return [_serialize_instance(i, creds.get(i.credential_id)) for i in instances]


class McpInstanceBody(BaseModel):
    catalog_entry_id: str | None = None
    source: str = "catalog"  # 'catalog' | 'custom'
    display_name: str
    connection_type: str = "streamable_http"
    endpoint_url: str | None = None
    config: dict = {}
    credentials: dict | None = None  # write-only — never echoed back


@router.post("/api/teams/{team_id}/mcp-instances", status_code=201)
def create_team_mcp_instance(
    team_id: int, body: McpInstanceBody,
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    if body.endpoint_url:
        try:
            validate_outbound_url(body.endpoint_url)
        except UnsafeUrlError as e:
            raise HTTPException(400, f"Unsafe endpoint_url: {e}")

    now = datetime.now(timezone.utc)
    credential_id = None
    if body.credentials:
        cred = EncryptedCredential(
            id=uuid.uuid4(), team_id=team_id, owner_type=MCP_INSTANCE, owner_id=None,
            ciphertext=encrypt_fields(body.credentials), field_names=list(body.credentials.keys()),
            masked_preview=masked_preview(body.credentials), created_by_user_id=user.id,
            created_at=now, updated_at=now,
        )
        db.add(cred)
        db.flush()
        credential_id = cred.id

    instance = TeamMcpInstance(
        id=uuid.uuid4(), team_id=team_id,
        catalog_entry_id=uuid.UUID(body.catalog_entry_id) if body.catalog_entry_id else None,
        source=body.source, display_name=body.display_name, connection_type=body.connection_type,
        endpoint_url=body.endpoint_url, config=body.config, credential_id=credential_id,
        created_by_user_id=user.id, created_at=now, updated_at=now,
    )
    db.add(instance)
    if credential_id:
        db.flush()
        cred.owner_id = instance.id
    db.commit()
    return _serialize_instance(instance, cred if credential_id else None)


@router.put("/api/teams/{team_id}/mcp-instances/{instance_id}")
def update_team_mcp_instance(
    team_id: int, instance_id: str, body: McpInstanceBody,
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    instance = db.get(TeamMcpInstance, uuid.UUID(instance_id))
    if not instance or instance.team_id != team_id:
        raise HTTPException(404, "Not found")

    if body.endpoint_url:
        try:
            validate_outbound_url(body.endpoint_url)
        except UnsafeUrlError as e:
            raise HTTPException(400, f"Unsafe endpoint_url: {e}")

    instance.catalog_entry_id = uuid.UUID(body.catalog_entry_id) if body.catalog_entry_id else None
    instance.source = body.source
    instance.display_name = body.display_name
    instance.connection_type = body.connection_type
    instance.endpoint_url = body.endpoint_url
    instance.config = body.config
    instance.updated_at = datetime.now(timezone.utc)

    cred = None
    if body.credentials:
        now = datetime.now(timezone.utc)
        if instance.credential_id:
            cred = db.get(EncryptedCredential, instance.credential_id)
            cred.ciphertext = encrypt_fields(body.credentials)
            cred.field_names = list(body.credentials.keys())
            cred.masked_preview = masked_preview(body.credentials)
            cred.updated_at = now
        else:
            cred = EncryptedCredential(
                id=uuid.uuid4(), team_id=team_id, owner_type=MCP_INSTANCE, owner_id=instance.id,
                ciphertext=encrypt_fields(body.credentials), field_names=list(body.credentials.keys()),
                masked_preview=masked_preview(body.credentials), created_by_user_id=user.id,
                created_at=now, updated_at=now,
            )
            db.add(cred)
            db.flush()
            instance.credential_id = cred.id
    elif instance.credential_id:
        cred = db.get(EncryptedCredential, instance.credential_id)

    db.commit()
    return _serialize_instance(instance, cred)


@router.delete("/api/teams/{team_id}/mcp-instances/{instance_id}", status_code=204)
def delete_team_mcp_instance(
    team_id: int, instance_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    instance = db.get(TeamMcpInstance, uuid.UUID(instance_id))
    if not instance or instance.team_id != team_id:
        raise HTTPException(404, "Not found")

    if instance.credential_id:
        cred = db.get(EncryptedCredential, instance.credential_id)
        if cred:
            db.delete(cred)
    db.delete(instance)
    db.commit()


@router.post("/api/teams/{team_id}/mcp-instances/{instance_id}/test-connection")
def test_mcp_instance_connection(
    team_id: int, instance_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    instance = db.get(TeamMcpInstance, uuid.UUID(instance_id))
    if not instance or instance.team_id != team_id:
        raise HTTPException(404, "Not found")

    now = datetime.now(timezone.utc)
    if not instance.endpoint_url:
        instance.status, instance.last_error = "error", "No endpoint_url configured"
    else:
        try:
            safe_get(instance.endpoint_url)
            instance.status, instance.last_error = "connected", None
        except UnsafeUrlError as e:
            instance.status, instance.last_error = "error", f"Blocked: {e}"
        except Exception as e:
            instance.status, instance.last_error = "error", str(e)[:500]
    instance.last_checked_at = now
    db.commit()
    return {"status": instance.status, "last_error": instance.last_error}
