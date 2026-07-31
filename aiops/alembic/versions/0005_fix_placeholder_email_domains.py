"""fix placeholder emails that used RFC 6761 reserved TLDs (.local)

Revision 0003's backfill (and the pre-fix aiops/teams.py legacy create_user
path) generated placeholder emails like "user5@default.local" and
"user-xxxx@pending.local" — email-validator (used by EmailStr on every new
auth endpoint) always rejects "local" as a special-use TLD, so these accounts
could never pass login/password-reset validation. Rewrites them onto a
non-reserved domain; existing password hashes are untouched.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE users SET email = replace(email, '@default.local', '@pending.aiops-placeholder.com') "
            "WHERE email LIKE '%@default.local'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET email = replace(email, '@pending.local', '@pending.aiops-placeholder.com') "
            "WHERE email LIKE '%@pending.local'"
        )
    )


def downgrade() -> None:
    # Not reversible (can't tell which rows originally had @default.local vs
    # @pending.local) — and there's no reason to revert onto a broken domain.
    pass
