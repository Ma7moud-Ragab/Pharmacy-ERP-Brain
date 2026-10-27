"""roles, grants and seed rule_config rows

Revision ID: 0005_roles_grants_seed
Revises: 0004_audit_agent
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0005_roles_grants_seed"
down_revision = '0004_audit_agent'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0005_roles_grants_seed.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    # Roles are cluster-level and are intentionally left in place. Remove the seeded rule sets only.
    op.execute("DELETE FROM intel.rule_config WHERE created_by = 'migration'")
