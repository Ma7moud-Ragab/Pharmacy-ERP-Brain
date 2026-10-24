"""schemas and shared trigger functions

Revision ID: 0001_foundation
Revises: None
"""
from alembic import op

from brain.db.migrations_util import guard_destructive_downgrade, run_ddl

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_ddl("0001_foundation.sql")


def downgrade() -> None:
    guard_destructive_downgrade()
    for fn in ("brain_guard_update", "brain_forbid_truncate", "brain_forbid_update_delete", "brain_forbid_delete", "brain_forbid_update", "brain_set_updated_at"):
        op.execute(f"DROP FUNCTION IF EXISTS public.{fn}() CASCADE")
    for s in ("audit", "agent", "intel", "feat", "ingest"):
        op.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
