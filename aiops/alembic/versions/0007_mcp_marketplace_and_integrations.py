"""MCP marketplace + team data sources/ingestion keys/GitHub integrations

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-25
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_catalog_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("icon_url", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("connection_type", sa.String(), nullable=False, server_default="streamable_http"),
        sa.Column("default_endpoint_url", sa.String(), nullable=True),
        sa.Column("credential_schema", JSONB, nullable=False, server_default="[]"),
        sa.Column("config_schema", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "encrypted_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("field_names", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("masked_preview", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_encrypted_credentials_owner", "encrypted_credentials", ["owner_type", "owner_id"])

    op.create_table(
        "team_mcp_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_entry_id", UUID(as_uuid=True), sa.ForeignKey("mcp_catalog_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="catalog"),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("connection_type", sa.String(), nullable=False, server_default="streamable_http"),
        sa.Column("endpoint_url", sa.String(), nullable=True),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("credential_id", UUID(as_uuid=True), sa.ForeignKey("encrypted_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "display_name"),
    )

    op.create_table(
        "team_data_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("connection_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("credential_id", UUID(as_uuid=True), sa.ForeignKey("encrypted_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "display_name"),
    )

    op.create_table(
        "team_ingestion_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False, unique=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.String()), nullable=False, server_default="{logs,metrics,traces,alerts}"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_team_ingestion_keys_prefix", "team_ingestion_keys", ["key_prefix"])

    op.create_table(
        "team_github_integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("auth_mode", sa.String(), nullable=False, server_default="pat"),
        sa.Column("repo_full_name", sa.String(), nullable=False),
        sa.Column("base_branch", sa.String(), nullable=False, server_default="main"),
        sa.Column("credential_id", UUID(as_uuid=True), sa.ForeignKey("encrypted_credentials.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seed a small curated MCP catalog so the marketplace isn't empty on first boot.
    conn = op.get_bind()
    catalog_seed = [
        {
            "id": str(uuid.uuid4()), "slug": "github-mcp", "name": "GitHub MCP", "vendor": "GitHub",
            "description": "Read/write GitHub issues, PRs, and repo content.", "category": "devops",
            "connection_type": "streamable_http", "default_endpoint_url": None,
            "credential_schema": [{"key": "token", "label": "Personal Access Token", "type": "secret", "required": True}],
            "config_schema": [{"key": "repo", "label": "Repository (owner/repo)", "type": "string", "required": True}],
            "is_verified": True,
        },
        {
            "id": str(uuid.uuid4()), "slug": "grafana-mcp", "name": "Grafana MCP", "vendor": "Grafana Labs",
            "description": "Query dashboards, alerts, and datasources from Grafana.", "category": "observability",
            "connection_type": "streamable_http", "default_endpoint_url": None,
            "credential_schema": [{"key": "api_key", "label": "API Key", "type": "secret", "required": True}],
            "config_schema": [{"key": "base_url", "label": "Grafana URL", "type": "url", "required": True}],
            "is_verified": True,
        },
        {
            "id": str(uuid.uuid4()), "slug": "slack-mcp", "name": "Slack MCP", "vendor": "Community",
            "description": "Post messages and read channel history in Slack.", "category": "communication",
            "connection_type": "streamable_http", "default_endpoint_url": None,
            "credential_schema": [{"key": "bot_token", "label": "Bot Token", "type": "secret", "required": True}],
            "config_schema": [],
            "is_verified": False,
        },
    ]
    insert_stmt = sa.text(
        """
        INSERT INTO mcp_catalog_entries
            (id, slug, name, vendor, description, category, connection_type,
             default_endpoint_url, credential_schema, config_schema, is_verified)
        VALUES
            (:id, :slug, :name, :vendor, :description, :category, :connection_type,
             :default_endpoint_url, :credential_schema, :config_schema, :is_verified)
        """
    ).bindparams(
        sa.bindparam("credential_schema", type_=JSONB),
        sa.bindparam("config_schema", type_=JSONB),
    )
    for entry in catalog_seed:
        conn.execute(insert_stmt, entry)


def downgrade() -> None:
    op.drop_table("team_github_integrations")
    op.drop_index("idx_team_ingestion_keys_prefix", table_name="team_ingestion_keys")
    op.drop_table("team_ingestion_keys")
    op.drop_table("team_data_sources")
    op.drop_table("team_mcp_instances")
    op.drop_index("idx_encrypted_credentials_owner", table_name="encrypted_credentials")
    op.drop_table("encrypted_credentials")
    op.drop_table("mcp_catalog_entries")
