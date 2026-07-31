import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Integer, LargeBinary, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# owner_type values — which feature owns a given encrypted_credentials row.
MCP_INSTANCE = "mcp_instance"
DATA_SOURCE = "data_source"
GITHUB_INTEGRATION = "github_integration"


class EncryptedCredential(Base):
    """One shared, polymorphic credential store for MCP instances, data
    sources, and GitHub integrations — a single place to own encryption,
    masking, and (later) key rotation instead of three ad-hoc secret columns."""

    __tablename__ = "encrypted_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    owner_type: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    field_names: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    masked_preview: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
