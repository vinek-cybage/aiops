"""add org_id to metrics/logs/traces/cases/alerts/incidents

Backfills existing rows to Default Org, then applies a server-side DEFAULT
(not just a Python-side one) so telemetry-api (C#) and orchestrator's raw-SQL
INSERTs keep working unmodified for any row that doesn't yet set org_id
explicitly — this migration is intentionally non-breaking on its own; the
follow-up code changes in telemetry-api/orchestrator make them org_id-aware
for real multi-tenant ingestion.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

# incidents is the legacy pre-cases table (aiops/incidents.py) — not actively
# queried today, so it just gets the column with no composite index.
TABLES = ["metrics", "logs", "traces", "cases", "alerts", "incidents"]


def upgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        op.add_column(table, sa.Column("org_id", UUID(as_uuid=True), nullable=True))
        conn.execute(sa.text(f"UPDATE {table} SET org_id = :org_id WHERE org_id IS NULL").bindparams(org_id=DEFAULT_ORG_ID))
        op.alter_column(
            table,
            "org_id",
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_ORG_ID}'"),
        )

    op.create_index("idx_metrics_org_service_ts", "metrics", ["org_id", "service", "ts"])
    op.create_index("idx_logs_org_service_ts", "logs", ["org_id", "service", "ts"])
    op.create_index("idx_traces_org_service_ts", "traces", ["org_id", "service", "ts"])
    op.create_index("idx_cases_org_updated_at", "cases", ["org_id", "updated_at"])
    op.create_index("idx_alerts_org_id", "alerts", ["org_id"])


def downgrade() -> None:
    op.drop_index("idx_alerts_org_id", table_name="alerts")
    op.drop_index("idx_cases_org_updated_at", table_name="cases")
    op.drop_index("idx_traces_org_service_ts", table_name="traces")
    op.drop_index("idx_logs_org_service_ts", table_name="logs")
    op.drop_index("idx_metrics_org_service_ts", table_name="metrics")
    for table in TABLES:
        op.drop_column(table, "org_id")
