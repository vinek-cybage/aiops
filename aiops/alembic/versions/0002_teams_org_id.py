"""add org_id to teams, backfill to Default Org, tighten to NOT NULL

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column("teams", sa.Column("org_id", UUID(as_uuid=True), nullable=True))
    op.execute(sa.text("UPDATE teams SET org_id = :org_id WHERE org_id IS NULL").bindparams(org_id=DEFAULT_ORG_ID))
    op.alter_column("teams", "org_id", nullable=False)
    op.create_foreign_key(
        "fk_teams_org_id_organizations", "teams", "organizations", ["org_id"], ["id"], ondelete="CASCADE"
    )
    # was UNIQUE(name) globally, now unique per-org
    op.execute("ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_name_key")
    op.create_unique_constraint("uq_teams_org_id_name", "teams", ["org_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_teams_org_id_name", "teams", type_="unique")
    op.create_unique_constraint("teams_name_key", "teams", ["name"])
    op.drop_constraint("fk_teams_org_id_organizations", "teams", type_="foreignkey")
    op.drop_column("teams", "org_id")
