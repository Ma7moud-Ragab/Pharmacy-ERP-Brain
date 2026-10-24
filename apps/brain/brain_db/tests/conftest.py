"""pytest fixtures shared by tests/integration and tests/isolation. Helpers and setup notes: tests/harness.py."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from brain.db.session import create_brain_engine, unit_of_work
from harness import A, B, H, LOGINS, P, PW, Tenants, bootstrap_roles, connect, ctx, fresh_database, provision, url


@pytest.fixture(scope="session")
def logins():
    """One login per runtime role, created by the role administrator (never a superuser) after it bootstrapped the roles."""
    bootstrap_roles()
    with connect("BB_ADMIN_DSN") as adm:
        for role, name in LOGINS.items():
            adm.execute(f"DROP ROLE IF EXISTS {name}")
            adm.execute(f"CREATE ROLE {name} LOGIN IN ROLE {role}" + (f" PASSWORD '{PW}'" if PW else ""))
    yield LOGINS
    with connect("BB_ADMIN_DSN") as adm:
        for name in LOGINS.values():
            adm.execute(f"DROP ROLE IF EXISTS {name}")


@pytest.fixture(scope="session")
def engine_for(logins):
    """engine_for(role, **kw): a session.py engine for that role's test login (login check included)."""
    made = []

    def make(role, **kw):
        e = create_brain_engine(url(logins[role], PW), role=role, **kw)
        made.append(e)
        return e
    yield make
    for e in made:
        e.dispose()


@pytest.fixture(scope="module")
def two_tenants(engine_for):
    """A freshly migrated database with tenants A and B active, each with one sales row, one session and one proposal."""
    fresh_database()
    prov, worker, app = engine_for("brain_provisioner"), engine_for("brain_worker"), engine_for("brain_app")
    with unit_of_work(prov, ctx(A, actor="ops:test")) as s:   # A's rule sets come from migration 0005
        rows = s.execute(text("SELECT rule_set, version, version_label, params::text FROM intel.rule_config WHERE is_active")).all()
    provision(prov, A, [])
    provision(prov, B, rows)
    proposals = {}
    for t in (A, B):
        with unit_of_work(worker, ctx(t, actor="system:sales_poll")) as s:
            s.execute(text("INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, "
                           "day_status, source_updated_at) VALUES (:t, :p, :d, 5, 0, 5, 'closed', now())"),
                      {"t": t, "p": P, "d": date(2026, 10, 16)})
        pid = uuid4()
        with unit_of_work(app, ctx(t, actor="u-1")) as s:
            s.execute(text("INSERT INTO agent.agent_session (tenant_id, user_actor_id, expires_at) VALUES (:t, 'u-1', now() + interval '4 hours')"),
                      {"t": t})
            s.execute(text("INSERT INTO agent.action_proposal (id, tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, "
                           "policy_version, reason, idempotency_key, expires_at, trace_id) VALUES (:id, :t, 'rules', 'create_purchase_order', "
                           "'1.0', '{}', :h, 'static-policy@1', 'Stockout risk high', :id, now() + interval '24 hours', :tr)"),
                      {"id": pid, "t": t, "h": H, "tr": "0" * 32})
        proposals[t] = pid
    return Tenants(a=A, b=B, proposal=proposals)
