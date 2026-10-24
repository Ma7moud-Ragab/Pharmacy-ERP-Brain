"""Shared test harness for brain_db (BB-05 step 4, BB-24). Hand-written, not generated. Fixtures: tests/conftest.py.

No connection in this harness is a superuser (D-50); the harness refuses to start if one is. It needs, once per test
cluster (CI service setup, run by whoever administers the cluster; see tests/integration/README.md):
  BB_ADMIN_DSN  role administrator, CREATEROLE only, that ran ddl/bootstrap_roles.sql (so it may grant the runtime roles)
  BB_OWNER_DSN  migration owner (no role attributes) that owns the test database
  BB_TEST_DB    name of that test database (its contents are dropped and rebuilt)
Both DSNs are libpq conninfo strings without a dbname. Test-login password: BB_TEST_ROLE_PASSWORD (default none).

`fresh_database()` drops every Brain object as the owner, re-runs bootstrap_roles.sql as the administrator and runs
`alembic upgrade head` + `alembic check` as the owner, i.e. the production path of D-50. Two tenants are then provisioned
through brain/db/session.py with the brain_provisioner login (registry row, validated credential reference, audited rule
sets, activation), and their pipeline rows are written by the brain_worker login (`two_tenants` fixture).
"""
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import URL, text

from brain.db.session import unit_of_work
from brain.ports import RunContext

ROOT = Path(__file__).resolve().parents[1]          # brain_db/
A = UUID("00000000-0000-0000-0000-000000000001")    # tenant A (rule sets seeded by migration 0005)
B = UUID("00000000-0000-0000-0000-000000000002")    # tenant B
P = UUID("b3f1c2a0-4e51-4a2e-9d3e-000000000001")
H = "d67ad9758d7806f685b4294e16a538f84157456e2de40b23aa5ca9c6993b57ce"
DAY = date(2026, 10, 16)                            # the same business date in both tenants
MODEL_VERSION = "lgbm-global-1"                     # the same model version in both tenants
LOGINS = {"brain_app": "bb_it_app", "brain_worker": "bb_it_worker", "brain_provisioner": "bb_it_prov",
          "brain_readonly": "bb_it_readonly"}
PW = os.environ.get("BB_TEST_ROLE_PASSWORD")


def env(name):
    v = os.environ.get(name)
    if not v:
        raise pytest.UsageError(f"{name} is not set (see brain_db/tests/integration/README.md); integration tests are never skipped")
    return v


def connect(dsn_var):
    conn = psycopg.connect(env(dsn_var), dbname=env("BB_TEST_DB"), autocommit=True)
    if conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
        raise pytest.UsageError(f"{dsn_var} is a SUPERUSER or BYPASSRLS login; the harness never uses one (D-50)")
    return conn


def url(user, password=None):
    d = conninfo_to_dict(env("BB_OWNER_DSN"))
    return URL.create("postgresql+psycopg", username=user, password=password, database=env("BB_TEST_DB"),
                      query={"host": d.get("host", "localhost"), "port": str(d.get("port", "5432"))})


def owner_url():
    d = conninfo_to_dict(env("BB_OWNER_DSN"))
    return url(d["user"], d.get("password"))


def ctx(tenant, actor="system:test"):
    now = datetime.now(timezone.utc)
    return RunContext(tenant_id=tenant, run_id=uuid4(), trace_id=uuid4().hex, now_utc=now, business_today=now.date(), actor_id=actor)


def alembic(*args):
    e = dict(os.environ, PYTHONPATH=str(ROOT / "python"), BRAIN_DDL_DIR=str(ROOT / "ddl"),
             BRAIN_DB_MIGRATION_URL=owner_url().render_as_string(hide_password=False))
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=e, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}"
    return r.stdout + r.stderr


def bootstrap_roles():
    """Run ddl/bootstrap_roles.sql as the role administrator (idempotent). The test logins are granted these roles."""
    with connect("BB_ADMIN_DSN") as adm:
        adm.execute((ROOT / "ddl" / "bootstrap_roles.sql").read_text())


def fresh_database():
    """Empty the test database as its owner and migrate it to head the way production does (D-50)."""
    with connect("BB_OWNER_DSN") as own:
        own.execute("DROP SCHEMA IF EXISTS ingest, feat, intel, agent, audit, rag CASCADE")
        own.execute("DROP TABLE IF EXISTS public.alembic_version")
        for (fn,) in own.execute("SELECT p.oid::regprocedure::text FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
                                 "AND left(p.proname, 6) = 'brain_' AND pg_has_role(current_user, p.proowner, 'USAGE')").fetchall():
            own.execute(f"DROP FUNCTION {fn} CASCADE")
    bootstrap_roles()
    alembic("upgrade", "head")
    assert "No new upgrade operations detected" in alembic("check")


@dataclass
class Tenants:
    a: UUID
    b: UUID
    proposal: dict  # tenant -> proposal id


def provision(prov, tenant, rule_rows):
    """The brain-provision path (D-46, D-51): registry row, validated credential reference, audited rule sets, activation."""
    with unit_of_work(prov, ctx(tenant, actor="ops:test")) as s:
        s.execute(text("INSERT INTO ingest.tenant_registry (tenant_id, display_label, provisioned_by) VALUES (:t, :l, 'ops:test')"),
                  {"t": tenant, "l": f"tenant {str(tenant)[-1]}"})
        s.execute(text("UPDATE ingest.tenant_registry SET credential_ref = :r, credential_sha256 = :h, credential_validated_at = now() "
                       "WHERE tenant_id = :t"), {"r": f"canonical/{tenant}", "h": H, "t": tenant})
        for rule_set, version, label, params in rule_rows:
            s.execute(text("INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
                           "VALUES (:t, :s, :v, :l, CAST(:p AS jsonb), true, 'provision')"),
                      {"t": tenant, "s": rule_set, "v": version, "l": label, "p": params})
        s.execute(text("UPDATE ingest.tenant_registry SET status = 'active' WHERE tenant_id = :t"), {"t": tenant})



TENANT_TABLES_SQL = ("SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                     "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped "
                     "WHERE c.relkind IN ('r','p') AND n.nspname IN ('ingest','feat','intel','agent','audit') ORDER BY 1")


def snapshot(tenant):
    """Every row of every tenant table as seen in `tenant`'s context by the owner (FORCE RLS binds it): BB-24 group 3.

    {table: (row count, md5 of all rows as text in sorted order)}, so a changed value is caught as well as an added or
    removed row. Two snapshots are equal only if every row of every tenant table is byte-for-byte the same.
    """
    with connect("BB_OWNER_DSN") as own:
        tables = [r[0] for r in own.execute(TENANT_TABLES_SQL).fetchall()]
        with own.transaction():
            own.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant),))
            return {t: tuple(own.execute(f"SELECT count(*), md5(coalesce(string_agg(r::text, E'\\n' ORDER BY r::text), '')) "
                                         f"FROM {t} AS r").fetchone()) for t in tables}
