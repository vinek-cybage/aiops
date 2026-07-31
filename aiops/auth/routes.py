import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from db_session import get_db
from models.organization import Organization
from models.team import Team
from models.team_membership import TeamMembership
from models.user import ORG_ADMIN, MEMBER, User
from models.auth_tokens import PasswordResetToken, RefreshToken
from models.invitation import ACCEPTED, EXPIRED, PENDING, Invitation

from .dependencies import get_current_user, AuthenticatedUser
from .jwt import create_access_token, generate_refresh_token, hash_token, refresh_token_expiry
from .passwords import hash_password, verify_password
from .team_context import team_roles_for

logger = logging.getLogger("aiops.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "aiops_refresh_token"
_IS_PROD = os.getenv("ENVIRONMENT", "development") == "production"


def _slugify(name: str) -> str:
    return "-".join(name.strip().lower().split()) or uuid.uuid4().hex[:8]


def _issue_tokens(db: Session, user: User, response: Response, request: Request) -> str:
    team_roles = team_roles_for(db, user.id)
    access_token = create_access_token(user.id, str(user.org_id), user.role, team_roles)

    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            issued_at=datetime.now(timezone.utc),
            expires_at=refresh_token_expiry(),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
    db.commit()

    response.set_cookie(
        REFRESH_COOKIE_NAME,
        raw_refresh,
        httponly=True,
        secure=_IS_PROD,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/api/auth",
    )
    return access_token


class RegisterBody(BaseModel):
    org_name: str
    name: str
    email: EmailStr
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterBody, response: Response, request: Request, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "An account with this email already exists")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    org = Organization(id=uuid.uuid4(), name=body.org_name, slug=_slugify(body.org_name))
    db.add(org)
    db.flush()

    user = User(
        org_id=org.id,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=ORG_ADMIN,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    access_token = _issue_tokens(db, user, response, request)
    return {"access_token": access_token, "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "org_id": str(user.org_id)}}


@router.post("/login")
def login(body: LoginBody, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    access_token = _issue_tokens(db, user, response, request)
    return {"access_token": access_token, "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "org_id": str(user.org_id)}}


@router.post("/refresh")
def refresh(response: Response, request: Request, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise HTTPException(401, "No refresh token")

    token_hash = hash_token(raw_refresh)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if not token_row:
        raise HTTPException(401, "Invalid refresh token")

    if token_row.revoked_at is not None:
        # reuse of an already-rotated/revoked token — signals possible theft;
        # revoke the whole chain for this user and force re-login.
        for chain_row in db.execute(
            select(RefreshToken).where(RefreshToken.user_id == token_row.user_id, RefreshToken.revoked_at.is_(None))
        ).scalars():
            chain_row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected, please log in again")

    if token_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh token expired")

    user = db.get(User, token_row.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Account no longer active")

    # rotate: revoke old, issue new
    token_row.revoked_at = datetime.now(timezone.utc)

    team_roles = team_roles_for(db, user.id)
    access_token = create_access_token(user.id, str(user.org_id), user.role, team_roles)

    new_raw_refresh = generate_refresh_token()
    new_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(new_raw_refresh),
        issued_at=datetime.now(timezone.utc),
        expires_at=refresh_token_expiry(),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(new_token)
    db.flush()
    token_row.replaced_by = new_token.id
    db.commit()

    response.set_cookie(
        REFRESH_COOKIE_NAME,
        new_raw_refresh,
        httponly=True,
        secure=_IS_PROD,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/api/auth",
    )
    return {"access_token": access_token}


@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        token_row = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
        ).scalar_one_or_none()
        if token_row and token_row.revoked_at is None:
            token_row.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConfirmBody(BaseModel):
    token: str
    new_password: str


@router.post("/password-reset/request", status_code=200)
def request_password_reset(body: PasswordResetRequestBody, db: Session = Depends(get_db)):
    # Always return 200 regardless of whether the email exists, to avoid
    # leaking account existence to an attacker probing this endpoint.
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user:
        raw_token = generate_refresh_token()
        db.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        db.commit()
        if _IS_PROD:
            # Email delivery isn't wired up yet. Logging the raw token would let
            # anyone with read access to the shared log volume take over this
            # account within its 1-hour window — in production, fail towards
            # "reset silently doesn't work yet" rather than that leak.
            logger.info("Password reset requested for user_id=%s (token not logged in production)", user.id)
        else:
            logger.info("Password reset requested for %s — token: %s", body.email, raw_token)
    return {"status": "ok"}


@router.post("/password-reset/confirm", status_code=200)
def confirm_password_reset(body: PasswordResetConfirmBody, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    token_row = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token))
    ).scalar_one_or_none()
    if not token_row or token_row.used_at is not None or token_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Invalid or expired reset token")

    user = db.get(User, token_row.user_id)
    if not user:
        raise HTTPException(404, "Not found")

    user.password_hash = hash_password(body.new_password)
    token_row.used_at = datetime.now(timezone.utc)

    # force re-login everywhere after a reset
    for rt in db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).scalars():
        rt.revoked_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "ok"}


def _get_pending_invitation(db: Session, token: str) -> Invitation:
    invitation = db.execute(
        select(Invitation).where(Invitation.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if not invitation:
        raise HTTPException(404, "Invitation not found")
    if invitation.status != PENDING:
        raise HTTPException(410, "This invitation is no longer valid")
    if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        invitation.status = EXPIRED
        db.commit()
        raise HTTPException(410, "This invitation has expired")
    return invitation


@router.get("/invitations/{token}")
def preview_invitation(token: str, db: Session = Depends(get_db)):
    invitation = _get_pending_invitation(db, token)
    org = db.get(Organization, invitation.org_id)
    team = db.get(Team, invitation.team_id) if invitation.team_id else None
    return {
        "email": invitation.email,
        "org_name": org.name if org else None,
        "team_name": team.name if team else None,
        "team_role": invitation.role,
    }


class AcceptInvitationBody(BaseModel):
    name: str
    password: str


@router.post("/invitations/{token}/accept", status_code=201)
def accept_invitation(
    token: str, body: AcceptInvitationBody, response: Response, request: Request, db: Session = Depends(get_db)
):
    invitation = _get_pending_invitation(db, token)
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    existing = db.execute(select(User).where(User.email == invitation.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "An account with this email already exists")

    user = User(
        org_id=invitation.org_id,
        email=invitation.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=MEMBER,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    if invitation.team_id is not None:
        db.add(TeamMembership(user_id=user.id, team_id=invitation.team_id, team_role=invitation.role))

    invitation.status = ACCEPTED
    db.flush()

    access_token = _issue_tokens(db, user, response, request)
    return {
        "access_token": access_token,
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "org_id": str(user.org_id)},
    }


@router.get("/me")
def me(user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(404, "Not found")
    return {
        "id": db_user.id,
        "email": db_user.email,
        "name": db_user.name,
        "role": db_user.role,
        "org_id": str(db_user.org_id),
        "team_ids": user.team_ids,
    }
