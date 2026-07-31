import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db_session import get_db
from models.organization import Organization
from models.team import Team
from models.user import PLATFORM_ADMIN, User

from auth.dependencies import require_role

router = APIRouter(prefix="/api/platform", tags=["platform-admin"])

# Cross-tenant visibility is powerful and easy to misuse — every route here is
# gated to platform_admin only (never org_admin/team_admin, no exceptions),
# and kept on its own route prefix so it's never accidentally reachable via
# the regular org-scoped endpoints.


@router.get("/organizations")
def list_organizations(_: object = Depends(require_role(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    orgs = db.execute(select(Organization).order_by(Organization.created_at)).scalars().all()
    team_counts = dict(db.execute(select(Team.org_id, func.count(Team.id)).group_by(Team.org_id)).all())
    user_counts = dict(db.execute(select(User.org_id, func.count(User.id)).group_by(User.org_id)).all())
    return [
        {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
            "created_at": org.created_at,
            "team_count": team_counts.get(org.id, 0),
            "user_count": user_counts.get(org.id, 0),
        }
        for org in orgs
    ]


@router.get("/organizations/{org_id}")
def get_organization(org_id: str, _: object = Depends(require_role(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    org = db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(404, "Not found")
    teams = db.execute(select(Team).where(Team.org_id == org.id)).scalars().all()
    users = db.execute(select(User).where(User.org_id == org.id)).scalars().all()
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "is_active": org.is_active,
        "created_at": org.created_at,
        "teams": [{"id": t.id, "name": t.name, "services": t.services} for t in teams],
        "users": [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "is_active": u.is_active} for u in users],
    }


class SetActiveBody(BaseModel):
    is_active: bool


@router.patch("/organizations/{org_id}")
def set_organization_active(
    org_id: str, body: SetActiveBody, _: object = Depends(require_role(PLATFORM_ADMIN)), db: Session = Depends(get_db)
):
    org = db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(404, "Not found")
    org.is_active = body.is_active
    db.commit()
    return {"id": str(org.id), "is_active": org.is_active}
