"""users: add org_id/email/password_hash/auth columns, backfill; create team_memberships

Note: users.team_id (the legacy single-team FK) is intentionally left in place —
aiops/teams.py's raw-SQL functions still read/write it directly and haven't been
ported to the ORM yet (see plan: coexistence, not big-bang). team_memberships is
additive and backfilled from it so new RBAC code can start using the many-to-many
model immediately.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-25
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    conn = op.get_bind()

    # ── users: add columns nullable first ──────────────────────────────────
    op.add_column("users", sa.Column("org_id", UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_secret", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # ── backfill: org_id -> Default Org, email -> synthetic, password_hash ->
    # an unguessable argon2 hash of a random secret nobody knows (forces a
    # password-reset flow before these legacy demo accounts can log in) ──────
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    rows = conn.execute(sa.text("SELECT id, name FROM users")).fetchall()
    for row in rows:
        # "local"/"invalid"/"test"/"example" TLDs are RFC 6761 special-use
        # names that email-validator (EmailStr) always rejects — must not use
        # one here or these backfilled accounts could never pass validation
        # even after a real password reset.
        synthetic_email = f"user{row.id}@pending.aiops-placeholder.com"
        random_hash = hasher.hash(uuid.uuid4().hex)
        conn.execute(
            sa.text(
                "UPDATE users SET org_id = :org_id, email = :email, password_hash = :password_hash WHERE id = :id"
            ),
            {"org_id": DEFAULT_ORG_ID, "email": synthetic_email, "password_hash": random_hash, "id": row.id},
        )

    op.alter_column("users", "org_id", nullable=False)
    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)

    # remap legacy flat role ('admin'/'member') onto the new org-scoped role enum
    conn.execute(sa.text("UPDATE users SET role = 'org_admin' WHERE role = 'admin'"))
    op.create_foreign_key("fk_users_org_id_organizations", "users", "organizations", ["org_id"], ["id"], ondelete="CASCADE")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key")
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # ── team_memberships (new, additive) ────────────────────────────────────
    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_role", sa.String(), nullable=False, server_default="member"),
        sa.UniqueConstraint("user_id", "team_id"),
    )
    conn.execute(
        sa.text(
            "INSERT INTO team_memberships (user_id, team_id, team_role) "
            "SELECT id, team_id, CASE WHEN role = 'admin' THEN 'team_admin' ELSE 'member' END "
            "FROM users WHERE team_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_table("team_memberships")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("users_name_key", "users", ["name"])
    op.drop_constraint("fk_users_org_id_organizations", "users", type_="foreignkey")
    for col in ("last_login_at", "created_at", "mfa_secret", "email_verified", "is_active", "password_hash", "email", "org_id"):
        op.drop_column("users", col)
