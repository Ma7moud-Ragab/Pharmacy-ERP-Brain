"""least privilege for brain_app, calendar writes for brain_worker, audited rule-set changes (B1, B7; D-51)

Revision ID: 0008_least_privilege
Revises: 0007_tenancy_rls

Additive on purpose: 0005-0007 keep their original grants and 0008 narrows them, so fresh databases and databases
already at 0007 end in the same state.
"""
from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0008_least_privilege"
down_revision = '0007_tenancy_rls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0008_least_privilege.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    # Restores the 0005-0007 grants and drops the rule-set audit triggers. Audit rows already written stay (append-only).
    run_ddl("0008_least_privilege.down.sql")
