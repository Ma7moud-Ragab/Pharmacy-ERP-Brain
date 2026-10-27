"""Engines and the unit of work for brain-api, brain-worker and brain-provision. Hand-written, not generated.

Rules this module enforces (BRAIN_CONTRACTS.md section 7.12; D-45, D-47, D-51):

* One login per process, granted exactly one runtime role: brain-api uses `brain_app` (BRAIN_DB_URL), brain-worker uses
  `brain_worker` (BRAIN_WORKER_DB_URL), the provisioning command uses `brain_provisioner` (BRAIN_PROVISION_DB_URL).
  `create_brain_engine` refuses at startup a login that is SUPERUSER or BYPASSRLS, owns a Brain table, or does not hold
  exactly the expected runtime role.
* Every unit of work is ONE transaction for ONE tenant. Its first statement sets `app.tenant_id` (and `app.actor_id`,
  `app.trace_id`) with `set_config(..., true)`, so the context ends with the commit or rollback. A session-level `SET`
  is never used; the pool `checkout` hook discards any connection that still carries a tenant anyway.
* The tenant comes only from the caller's RunContext (the verified JWT in the API, the registry row in the worker).
  There is no default tenant and no way to run a unit of work without one.

Usage:
    engine = create_brain_engine(os.environ["BRAIN_DB_URL"], role="brain_app")
    with unit_of_work(engine, ctx) as session:
        session.exec(select(Forecast).where(Forecast.tenant_id == ctx.tenant_id))   # repositories still filter
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DisconnectionError
from sqlmodel import Session

RUNTIME_ROLES = ("brain_app", "brain_worker", "brain_retention", "brain_readonly", "brain_provisioner")
BRAIN_SCHEMAS = ("ingest", "feat", "intel", "agent", "audit")
URL_ENV = {"brain_app": "BRAIN_DB_URL", "brain_worker": "BRAIN_WORKER_DB_URL", "brain_provisioner": "BRAIN_PROVISION_DB_URL"}
_TRACE = re.compile(r"[0-9a-f]{32}")


class TenantContext(Protocol):
    """What a unit of work needs from brain.ports.RunContext (structural, so this module does not import the ports)."""

    tenant_id: UUID
    actor_id: str
    trace_id: str


class UnsafeLoginError(RuntimeError):
    """The database login may bypass row-level security or holds the wrong role; the process must not start."""


class TenantContextLeak(DisconnectionError):
    """A pooled connection still carried app.tenant_id at checkout; the pool discards it and opens a new one."""


def _discard_if_tenant_left(dbapi_conn, record, proxy) -> None:
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SELECT nullif(current_setting('app.tenant_id', true), '')")
        leftover = cur.fetchone()[0]
    finally:
        cur.close()
        dbapi_conn.rollback()  # end the probe's implicit transaction; a session-level value would survive it
    if leftover is not None:
        raise TenantContextLeak("tenant context left on a pooled connection; connection discarded")


def check_login(engine: Engine, role: str) -> None:
    """Startup check (D-47): refuse SUPERUSER, BYPASSRLS, table ownership, and any role set other than exactly `role`."""
    if role not in RUNTIME_ROLES:
        raise ValueError(f"unknown runtime role {role!r}")
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT current_user, r.rolsuper, r.rolbypassrls, "
            "       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "         WHERE n.nspname = ANY(:schemas) AND pg_has_role(current_user, c.relowner, 'MEMBER')), "
            "       ARRAY(SELECT x FROM unnest(CAST(:roles AS text[])) AS x WHERE pg_has_role(current_user, x, 'MEMBER') ORDER BY x) "
            "  FROM pg_roles r WHERE r.rolname = current_user"),
            {"schemas": list(BRAIN_SCHEMAS), "roles": list(RUNTIME_ROLES)}).one()
        conn.rollback()
    login, is_super, bypass, owned, held = row
    if is_super or bypass:
        raise UnsafeLoginError(f"login {login} is SUPERUSER or BYPASSRLS; row-level security would not apply")
    if owned:
        raise UnsafeLoginError(f"login {login} owns {owned} Brain relations; FORCE RLS binds owners but owners can alter policies")
    if list(held) != [role]:
        raise UnsafeLoginError(f"login {login} must hold exactly {role}, holds {list(held) or 'no runtime role'} (D-45)")


def create_brain_engine(url: str, *, role: str, verify_login: bool = True, **engine_kwargs) -> Engine:
    """Engine for one runtime role, with the checkout guard installed and the login checked before first use."""
    engine_kwargs.setdefault("pool_pre_ping", True)
    engine = create_engine(url, **engine_kwargs)
    event.listen(engine, "checkout", _discard_if_tenant_left)
    if verify_login:
        check_login(engine, role)
    return engine


def engine_from_env(role: str, **engine_kwargs) -> Engine:
    """brain_app -> BRAIN_DB_URL, brain_worker -> BRAIN_WORKER_DB_URL, brain_provisioner -> BRAIN_PROVISION_DB_URL."""
    return create_brain_engine(os.environ[URL_ENV[role]], role=role, **engine_kwargs)


@contextmanager
def unit_of_work(engine: Engine, ctx: TenantContext) -> Iterator[Session]:
    """One transaction for ctx.tenant_id. Commits on success, rolls back on any exception; the context ends either way."""
    if not isinstance(ctx.tenant_id, UUID):
        raise TypeError("ctx.tenant_id must be a UUID taken from the verified context, never a string or a default")
    if not ctx.actor_id:
        raise ValueError("ctx.actor_id is required (JWT sub, or system:<job>)")
    if not _TRACE.fullmatch(ctx.trace_id or ""):
        raise ValueError("ctx.trace_id must be 32 lowercase hex characters")
    with Session(engine) as session, session.begin():
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true), set_config('app.actor_id', :actor, true), "
                 "set_config('app.trace_id', :trace, true)"),
            {"tenant": str(ctx.tenant_id), "actor": ctx.actor_id, "trace": ctx.trace_id})
        yield session


@contextmanager
def registry_scan(engine: Engine) -> Iterator[Session]:
    """READ ONLY transaction with NO tenant, for the scheduler's list of active tenants (pol_worker_list_tenants).

    Every tenant table reads as empty and refuses writes here; only brain_worker sees registry rows.
    """
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
