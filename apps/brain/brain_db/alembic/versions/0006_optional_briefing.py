"""OPTIONAL intel.briefing (SHOULD-have); delete this revision to skip

Revision ID: 0006_optional_briefing
Revises: 0005_roles_grants_seed
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0006_optional_briefing"
down_revision = '0005_roles_grants_seed'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0006_optional_briefing.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    op.execute("DROP TABLE IF EXISTS intel.briefing")
