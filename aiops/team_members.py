import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from db_session import get_db
from models.team import Team
from models.team_membership import TEAM_ROLES, TeamMembership
from models.user import ORG_ADMIN, User
from models.invitation import ACCEPTED, PENDING, REVOKED, Invitation

from auth.dependencies import AuthenticatedUser, get_current_user, require_role, assert_can_manage_team, assert_can_view_team
from auth.jwt import generate_refresh_token, hash_token

router = APIRouter(prefix="/api/teams", tags=["team-members"])


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


def _team_out(team: Team) -> dict:
    return {"id": team.id, "name": team.name, "services": team.services, "org_id": str(team.org_id)}


# ── teams ────────────────────────────────────────────────────────────────────

@router.get("")
def list_teams(user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    teams = db.execute(select(Team).where(Team.org_id == user.org_id).order_by(Team.name)).scalars().all()
    return [_team_out(t) for t in teams]


class CreateTeamBody(BaseModel):
    name: str
    services: list[str] = []


@router.post("", status_code=201)
def create_team(
    body: CreateTeamBody,
    user: AuthenticatedUser = Depends(require_role(ORG_ADMIN)),
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(Team).where(Team.org_id == user.org_id, Team.name == body.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A team with this name already exists")

    team = Team(org_id=user.org_id, name=body.name, services=body.services)
    db.add(team)
    db.commit()
    db.refresh(team)
    return _team_out(team)


# ── members ──────────────────────────────────────────────────────────────────

@router.get("/{team_id}/members")
def list_members(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_view_team(user, team_id, team.org_id)

    rows = db.execute(
        select(TeamMembership, User).join(User, User.id == TeamMembership.user_id).where(TeamMembership.team_id == team_id)
    ).all()
    return [
        {
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "org_role": u.role,
            "team_role": tm.team_role,
            "is_active": u.is_active,
        }
        for tm, u in rows
    ]


class UpdateMemberBody(BaseModel):
    team_role: str


@router.patch("/{team_id}/members/{user_id}")
def update_member_role(
    team_id: int,
    user_id: int,
    body: UpdateMemberBody,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)
    if body.team_role not in TEAM_ROLES:
        raise HTTPException(400, f"team_role must be one of {TEAM_ROLES}")

    membership = db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(404, "Membership not found")

    membership.team_role = body.team_role
    db.commit()
    return {"user_id": user_id, "team_id": team_id, "team_role": membership.team_role}


@router.delete("/{team_id}/members/{user_id}", status_code=204)
def remove_member(
    team_id: int, user_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    membership = db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(404, "Membership not found")

    db.delete(membership)
    db.commit()


# ── invitations ──────────────────────────────────────────────────────────────

class CreateInvitationBody(BaseModel):
    email: EmailStr
    team_role: str = "member"


@router.get("/{team_id}/invitations")
def list_invitations(team_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    rows = db.execute(
        select(Invitation).where(Invitation.team_id == team_id, Invitation.status == PENDING)
    ).scalars().all()
    return [
        {"id": str(inv.id), "email": inv.email, "role": inv.role, "status": inv.status, "expires_at": inv.expires_at}
        for inv in rows
    ]


@router.post("/{team_id}/invitations", status_code=201)
def create_invitation(
    team_id: int,
    body: CreateInvitationBody,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)
    if body.team_role not in TEAM_ROLES:
        raise HTTPException(400, f"team_role must be one of {TEAM_ROLES}")

    existing_user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing_user and str(existing_user.org_id) == str(team.org_id):
        raise HTTPException(409, "This person is already a member of your organization")

    raw_token = generate_refresh_token()
    invitation = Invitation(
        id=uuid.uuid4(),
        org_id=team.org_id,
        team_id=team_id,
        email=body.email,
        role=body.team_role,
        token_hash=hash_token(raw_token),
        invited_by=user.id,
        status=PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_at=datetime.now(timezone.utc),
    )
    db.add(invitation)
    db.commit()

    # No email delivery yet — the inviting admin shares this link directly.
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "team_role": invitation.role,
        "invite_link": f"/invite/{raw_token}",
    }


@router.delete("/{team_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    team_id: int,
    invitation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = _get_team_or_404(db, team_id)
    assert_can_manage_team(user, team_id, team.org_id)

    invitation = db.get(Invitation, uuid.UUID(invitation_id))
    if not invitation or invitation.team_id != team_id:
        raise HTTPException(404, "Invitation not found")

    invitation.status = REVOKED
    db.commit()
