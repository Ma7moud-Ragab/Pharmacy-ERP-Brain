"""Helpers for Alembic revisions that execute the reviewed DDL files in ./ddl."""
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# Default layout: <repo>/ddl next to <repo>/python. Override with BRAIN_DDL_DIR in other layouts.
DDL_DIR = Path(os.environ.get("BRAIN_DDL_DIR", Path(__file__).resolve().parents[3] / "ddl"))


def run_ddl(filename: str) -> None:
    """Execute one DDL file. Colons are escaped so SQLAlchemy text() does not treat ':name' as a bind parameter.

    Requires a SYNCHRONOUS driver for Alembic (e.g. postgresql+psycopg://): the files contain many statements and
    asyncpg cannot run multi-statement strings. The application itself may still use asyncpg.
    """
    sql = (DDL_DIR / filename).read_text(encoding="utf-8")
    op.execute(sa.text(sql.replace(":", "\\:")))


def guard_destructive_downgrade() -> None:
    if os.environ.get("BRAIN_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Downgrade drops data. Set BRAIN_ALLOW_DESTRUCTIVE_DOWNGRADE=1 (dev/test databases only)."
        )
