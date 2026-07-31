"""create organizations table + seed Default Org

Revision ID: 0001
Revises:
Create Date: 2026-07-25
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES (:id, 'Default Org', 'default', true)"
        ).bindparams(id=str(DEFAULT_ORG_ID))
    )


def downgrade() -> None:
    op.drop_table("organizations")
