"""intel schema (MVP tables)

Revision ID: 0003_intel
Revises: 0002_ingest_feat
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0003_intel"
down_revision = '0002_ingest_feat'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0003_intel.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    op.execute("DROP SCHEMA IF EXISTS intel CASCADE")
    op.execute("CREATE SCHEMA intel")
