"""Fix team_github_integrations FK ondelete + add missing tenant-scoping indexes

1. team_github_integrations.credential_id had no ON DELETE action (default
   RESTRICT), unlike the identical-shaped credential_id FKs on
   team_data_sources/team_mcp_instances (both ON DELETE SET NULL). Unlike
   those two, though, a GitHub integration's credential isn't optional
   metadata — every row always has exactly one (upsert_github_integration
   requires a token on first create) — so this uses CASCADE, not SET NULL:
   deleting the credential should take the whole integration row with it.
   Without this, delete_github_integration's credential-then-integration
   delete order could raise a FK violation depending on flush ordering.

2. team_ingestion_keys.team_id had no index at all, yet list_ingestion_keys
   filters by it on every call.

3. encrypted_credentials only had an (owner_type, owner_id) index, but
   data_sources.py/mcp.py both list credentials by (owner_type, team_id) — a
   combination that index can't serve, so both call paths full-scan the
   table as it grows.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-31
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "team_github_integrations_credential_id_fkey",
        "team_github_integrations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "team_github_integrations_credential_id_fkey",
        "team_github_integrations",
        "encrypted_credentials",
        ["credential_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index("idx_team_ingestion_keys_team_id", "team_ingestion_keys", ["team_id"])
    op.create_index("idx_encrypted_credentials_owner_type_team_id", "encrypted_credentials", ["owner_type", "team_id"])


def downgrade() -> None:
    op.drop_index("idx_encrypted_credentials_owner_type_team_id", table_name="encrypted_credentials")
    op.drop_index("idx_team_ingestion_keys_team_id", table_name="team_ingestion_keys")

    op.drop_constraint(
        "team_github_integrations_credential_id_fkey",
        "team_github_integrations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "team_github_integrations_credential_id_fkey",
        "team_github_integrations",
        "encrypted_credentials",
        ["credential_id"],
        ["id"],
    )
