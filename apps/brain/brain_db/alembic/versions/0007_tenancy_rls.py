"""tenant registry (N-01) and row-level security on every tenant table (N-02)

Revision ID: 0007_tenancy_rls
Revises: 0006_optional_briefing

If you skip the optional 0006 revision, point down_revision at 0005_roles_grants_seed: the DDL applies RLS to
intel.briefing only when that table exists.
"""
from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0007_tenancy_rls"
down_revision = '0006_optional_briefing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0007_tenancy_rls.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    # Drops the tenant registry and every RLS policy. brain_provisioner is cluster-level and stays, as in 0005.
    run_ddl("0007_tenancy_rls.down.sql")
