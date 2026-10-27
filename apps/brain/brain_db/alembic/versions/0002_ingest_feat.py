"""ingest and feat schemas

Revision ID: 0002_ingest_feat
Revises: 0001_foundation
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0002_ingest_feat"
down_revision = '0001_foundation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0002_ingest_feat.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    op.execute("DROP SCHEMA IF EXISTS feat CASCADE")
    op.execute("DROP SCHEMA IF EXISTS ingest CASCADE")
    op.execute("CREATE SCHEMA ingest")
    op.execute("CREATE SCHEMA feat")
