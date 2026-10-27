"""audit and agent schemas

Revision ID: 0004_audit_agent
Revises: 0003_intel
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0004_audit_agent"
down_revision = '0003_intel'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0004_audit_agent.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    op.execute("DROP SCHEMA IF EXISTS agent CASCADE")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("CREATE SCHEMA agent")
    op.execute("CREATE SCHEMA audit")
