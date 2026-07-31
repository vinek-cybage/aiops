from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException

from .jwt import decode_access_token
from models.user import PLATFORM_ADMIN


@dataclass
class AuthenticatedUser:
    id: int
    org_id: str
    role: str
    team_roles: dict[int, str]

    @property
    def is_platform_admin(self) -> bool:
        return self.role == PLATFORM_ADMIN

    @property
    def team_ids(self) -> list[int]:
        return list(self.team_roles.keys())

    def is_team_admin(self, team_id: int) -> bool:
        return self.team_roles.get(team_id) == "team_admin"


def get_current_user(authorization: str | None = Header(None)) -> AuthenticatedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization[len("Bearer "):]
    try:
        claims = decode_access_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Access token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "Invalid access token")
    return AuthenticatedUser(
        id=int(claims["sub"]),
        org_id=claims["org_id"],
        role=claims["role"],
        team_roles={int(k): v for k, v in claims.get("team_roles", {}).items()},
    )


def require_role(*allowed: str):
    def _resolved(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed and not user.is_platform_admin:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return _resolved


def assert_can_manage_team(user: AuthenticatedUser, team_id: int, team_org_id) -> None:
    """Raise 403/404 unless the user may manage (invite/remove members, edit
    config) the given team. platform_admin bypasses everything; org_admin can
    manage any team in their own org; team_admin only their own team(s)."""
    if user.is_platform_admin:
        return
    if str(team_org_id) != user.org_id:
        # 404, not 403 — don't reveal that a team in another org exists.
        raise HTTPException(404, "Not found")
    if user.role == "org_admin" or user.is_team_admin(team_id):
        return
    raise HTTPException(403, "Team admin access required")


def assert_can_view_team(user: AuthenticatedUser, team_id: int, team_org_id) -> None:
    """Raise 403/404 unless the user may view (read-only) the given team —
    any org member for their own org's teams, not just team members, since
    e.g. incident routing needs every org member to see the team roster."""
    if user.is_platform_admin:
        return
    if str(team_org_id) != user.org_id:
        raise HTTPException(404, "Not found")
