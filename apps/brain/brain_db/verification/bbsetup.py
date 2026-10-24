"""Superuser-free setup for the verification suites (D-50, D-51). Hand-written, not generated.

No suite connects as a superuser. Each one uses three kinds of connection:
* BB_ADMIN_DSN: the role administrator (CREATEROLE only, the one that ran ddl/bootstrap_roles.sql). It creates the
  test logins, each granted ONE runtime role, and drops them at the end.
* BB_OWNER_DSN: the migration owner of the database (no role attributes). It reads the catalogs and seeds fixtures.
  FORCE ROW LEVEL SECURITY binds it too, so every write it makes runs inside `tenant(conn, T)`: one transaction with a
  transaction-local app.tenant_id (and app.actor_id = test:setup, which rule_config changes require since D-51).
* the test logins themselves, which run every check.
Both DSNs are libpq conninfo strings without a dbname, e.g. "host=/tmp/pg port=5433 user=brain_migrator"; the database
name is the suite's first argument. Passwords for the test logins: BB_TEST_ROLE_PASSWORD (default none).
"""
import os
import sys
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict

PW = os.environ.get("BB_TEST_ROLE_PASSWORD")


def _dsn(var):
    v = os.environ.get(var)
    if not v:
        sys.exit(f"{var} is not set; see brain_db/verification/bbsetup.py")
    return v


def _connect(dsn, db, label):
    conn = psycopg.connect(dsn, dbname=db, autocommit=True)
    sup = conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]
    if sup:
        sys.exit(f"{label} connection is SUPERUSER or BYPASSRLS; the suites must run without one (D-50)")
    return conn


def owner(db):
    return _connect(_dsn("BB_OWNER_DSN"), db, "owner")


def admin(db):
    return _connect(_dsn("BB_ADMIN_DSN"), db, "admin")


def server():
    """host and port of the owner DSN, for SQLAlchemy URLs of the test logins."""
    d = conninfo_to_dict(_dsn("BB_OWNER_DSN"))
    return d.get("host", ""), d.get("port", "5432")


def login_connect(db, user):
    host, port = server()
    return psycopg.connect(host=host, port=port, dbname=db, user=user, password=PW, autocommit=True)


def create_login(adm, name, role):
    adm.execute(f"DROP ROLE IF EXISTS {name}")
    adm.execute(f"CREATE ROLE {name} LOGIN IN ROLE {role}" + (f" PASSWORD '{PW}'" if PW else ""))


def drop_login(adm, name):
    adm.execute(f"DROP ROLE IF EXISTS {name}")


def set_tenant(conn, tenant):
    conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', 'test:setup', true)", (tenant,))


@contextmanager
def tenant(conn, tenant_id):
    """One transaction in tenant_id's context (transaction-local, so nothing survives it)."""
    with conn.transaction():
        set_tenant(conn, tenant_id)
        yield conn
