import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class McpCatalogEntry(Base):
    """Platform-curated "app store" listing. credential_schema/config_schema
    are JSON-schema-ish field lists so the marketplace UI can render a
    dynamic "configure this MCP" form for any new listing without a
    frontend redeploy — e.g. [{"key":"api_key","label":"API Key","type":"secret","required":true}]."""

    __tablename__ = "mcp_catalog_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    connection_type: Mapped[str] = mapped_column(String, nullable=False, default="streamable_http")
    default_endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    credential_schema: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    config_schema: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TeamMcpInstance(Base):
    """A team's installed/configured MCP server — either picked from the
    catalog (source='catalog') or a fully custom/remote one they registered
    themselves (source='custom', catalog_entry_id NULL)."""

    __tablename__ = "team_mcp_instances"
    __table_args__ = (UniqueConstraint("team_id", "display_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    catalog_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_catalog_entries.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False, default="catalog")
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    connection_type: Mapped[str] = mapped_column(String, nullable=False, default="streamable_http")
    endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encrypted_credentials.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
