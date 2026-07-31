import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

_DEV_DEFAULT_SECRET = "dev-only-insecure-secret-change-me"
JWT_SECRET = os.getenv("JWT_SECRET", _DEV_DEFAULT_SECRET)
JWT_ALGORITHM = "HS256"

if JWT_SECRET == _DEV_DEFAULT_SECRET:
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError(
            "JWT_SECRET must be set to a real secret in production — refusing to "
            "start with the dev-only default (anyone could forge admin tokens)."
        )
    logging.getLogger("aiops").warning(
        "JWT_SECRET is unset — using the insecure dev-only default. Anyone can "
        "forge access tokens with it. Set a real JWT_SECRET before any real deployment."
    )
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "30"))


def create_access_token(user_id: int, org_id: str, role: str, team_roles: dict[int, str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "org_id": org_id,
        "role": role,
        # JSON object keys are always strings, so team ids are stringified here
        # and parsed back to int in AuthenticatedUser.
        "team_roles": {str(team_id): team_role for team_id, team_role in team_roles.items()},
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
