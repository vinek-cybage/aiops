import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TeamGithubIntegration(Base):
    """Replaces the global GITHUB_TOKEN/GITHUB_REPO/GITHUB_BASE_BRANCH env
    vars in aiops/actions.py — one row per team, one active integration each."""

    __tablename__ = "team_github_integrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False)
    auth_mode: Mapped[str] = mapped_column(String, nullable=False, default="pat")
    repo_full_name: Mapped[str] = mapped_column(String, nullable=False)
    base_branch: Mapped[str] = mapped_column(String, nullable=False, default="main")
    # CASCADE (not SET NULL like team_data_sources/team_mcp_instances' identical
    # FK) — unlike those, this credential isn't optional metadata: every row
    # always has exactly one (upsert_github_integration requires a token on
    # first create), so deleting the credential should take the whole
    # integration with it rather than leave a credential-less row behind.
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encrypted_credentials.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
