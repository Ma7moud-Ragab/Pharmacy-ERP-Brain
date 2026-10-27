"""brain/db/session.py against a real PostgreSQL 16 (BB-05 step 4 acceptance; BRAIN_CONTRACTS.md 7.12). Hand-written.

Every connection here is a non-superuser test login granted one runtime role, through the engines and the unit of work
the services will use. Fixtures: tests/conftest.py (`two_tenants` = freshly migrated database with active tenants A and B).
Pooled-connection behaviour (BB-24 group 7) is in tests/isolation/test_g7_pooled_connections.py.
"""
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from brain.db.session import UnsafeLoginError, create_brain_engine, registry_scan, unit_of_work
from harness import A, B, P, PW, ctx, owner_url, url

SALES = text("SELECT tenant_id FROM ingest.sales_fact")


def pgcode(exc):
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


# ---------- startup login check (D-45, D-47) ----------
def test_login_check_accepts_each_runtime_login(two_tenants, engine_for):
    for role in ("brain_app", "brain_worker", "brain_provisioner", "brain_readonly"):
        engine_for(role)  # raises if the check fails


def test_login_check_refuses_the_migration_owner():
    with pytest.raises(UnsafeLoginError, match="owns"):
        create_brain_engine(owner_url(), role="brain_app")


def test_login_check_refuses_a_login_used_for_the_wrong_role(logins):
    with pytest.raises(UnsafeLoginError, match="must hold exactly brain_worker"):
        create_brain_engine(url(logins["brain_app"], PW), role="brain_worker")


def test_login_check_refuses_a_login_holding_two_runtime_roles(two_tenants):
    import harness
    with harness.connect("BB_ADMIN_DSN") as adm:
        adm.execute("DROP ROLE IF EXISTS bb_it_both")
        adm.execute("CREATE ROLE bb_it_both LOGIN IN ROLE brain_app, brain_worker" + (f" PASSWORD '{PW}'" if PW else ""))
        try:
            with pytest.raises(UnsafeLoginError, match=r"holds \['brain_app', 'brain_worker'\]"):
                create_brain_engine(url("bb_it_both", PW), role="brain_app")
        finally:
            adm.execute("DROP ROLE bb_it_both")


# ---------- the unit of work refuses a missing or malformed context ----------
@pytest.mark.parametrize("bad, err", [
    ({"tenant_id": str(A)}, TypeError), ({"actor_id": ""}, ValueError), ({"trace_id": "X" * 32}, ValueError)])
def test_unit_of_work_refuses_a_bad_context(two_tenants, engine_for, bad, err):
    with pytest.raises(err):
        with unit_of_work(engine_for("brain_app"), replace(ctx(A), **bad)):
            pass


# ---------- reads and writes are confined to the context's tenant ----------
def test_each_tenant_reads_only_its_own_rows(two_tenants, engine_for):
    app = engine_for("brain_app")
    for t in (A, B):
        with unit_of_work(app, ctx(t)) as s:
            assert {r[0] for r in s.execute(SALES)} == {t}
            other = B if t == A else A
            assert s.execute(text("SELECT count(*) FROM ingest.sales_fact WHERE tenant_id = :o"), {"o": other}).scalar() == 0
            assert s.execute(text("SELECT count(*) FROM agent.action_proposal WHERE id = :p"), {"p": two_tenants.proposal[other]}).scalar() == 0


def test_insert_without_tenant_id_fails(two_tenants, engine_for):
    with pytest.raises(DBAPIError) as e:
        with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
            s.execute(text("INSERT INTO ingest.sales_fact (product_id, sales_date, day_status, source_updated_at) "
                           "VALUES (:p, '2026-10-02', 'closed', now())"), {"p": P})
    assert pgcode(e.value) in ("23502", "42501")   # NOT NULL, or RLS WITH CHECK on the NULL tenant


def test_a_write_for_another_tenant_is_refused_and_rolled_back(two_tenants, engine_for):
    worker = engine_for("brain_worker")
    with pytest.raises(ProgrammingError, match="row-level security"):
        with unit_of_work(worker, ctx(A)) as s:
            s.execute(text("INSERT INTO ingest.sync_checkpoint (tenant_id, resource) VALUES (:t, 'sales_poll')"), {"t": A})
            s.execute(text("INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, "
                           "day_status, source_updated_at) VALUES (:t, :p, '2026-10-03', 1, 0, 1, 'closed', now())"), {"t": B, "p": P})
    with unit_of_work(worker, ctx(A)) as s:   # the whole unit rolled back, including A's own row
        assert s.execute(text("SELECT count(*) FROM ingest.sync_checkpoint")).scalar() == 0


def test_updates_of_another_tenants_rows_change_nothing(two_tenants, engine_for):
    with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
        assert s.execute(text("UPDATE ingest.sales_fact SET units_sold = 99, net_units = 99 WHERE tenant_id = :b"), {"b": B}).rowcount == 0
        assert s.execute(text("UPDATE agent.action_proposal SET status = 'expired' WHERE id = :p"), {"p": two_tenants.proposal[B]}).rowcount == 0
    with unit_of_work(engine_for("brain_app"), ctx(B)) as s:
        assert s.execute(text("SELECT units_sold FROM ingest.sales_fact")).scalar() == 5
        assert s.execute(text("SELECT status FROM agent.action_proposal WHERE id = :p"), {"p": two_tenants.proposal[B]}).scalar() == "pending"


def test_api_login_cannot_write_pipeline_tables_or_rule_sets(two_tenants, engine_for):
    for sql in ("UPDATE ingest.sales_fact SET units_sold = 1", "UPDATE intel.rule_config SET is_active = false WHERE rule_set = 'risk'"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with unit_of_work(engine_for("brain_app"), ctx(A)) as s:
                s.execute(text(sql))


# ---------- the scheduler's tenant list ----------
def test_registry_scan_lists_active_tenants_for_the_worker_only(two_tenants, engine_for):
    with registry_scan(engine_for("brain_worker")) as s:
        assert {r[0] for r in s.execute(text("SELECT tenant_id FROM ingest.tenant_registry WHERE status = 'active'"))} == {A, B}
        assert s.execute(text("SELECT count(*) FROM ingest.sales_fact")).scalar() == 0
    with registry_scan(engine_for("brain_app")) as s:
        assert s.execute(text("SELECT count(*) FROM ingest.tenant_registry")).scalar() == 0
    with pytest.raises(DBAPIError, match="read-only transaction"):
        with registry_scan(engine_for("brain_worker")) as s:
            s.execute(text("UPDATE ingest.sync_checkpoint SET last_status = 'failed'"))


# ---------- actor and trace reach the audit trail (D-51) ----------
def test_rule_set_switch_through_the_unit_of_work_is_audited_with_the_run_context(two_tenants, engine_for):
    prov = engine_for("brain_provisioner")
    c = ctx(B, actor="ops:alice")
    with unit_of_work(prov, c) as s:
        s.execute(text("INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
                       "VALUES (:t, 'risk', 2, 'risk-rules@2.0.0', '{}', false, 'provision')"), {"t": B})
        s.execute(text("UPDATE intel.rule_config SET is_active = false WHERE rule_set = 'risk' AND version = 1"))
        s.execute(text("UPDATE intel.rule_config SET is_active = true WHERE rule_set = 'risk' AND version = 2"))
    with unit_of_work(engine_for("brain_app"), ctx(B)) as s:
        rows = s.execute(text("SELECT event_type, actor_id FROM audit.audit_log WHERE trace_id = :tr ORDER BY seq"), {"tr": c.trace_id}).all()
    assert rows == [("rule_config.version_added", "ops:alice"), ("rule_config.deactivated", "ops:alice"),
                    ("rule_config.activated", "ops:alice")]
    with unit_of_work(engine_for("brain_app"), ctx(A)) as s:   # tenant A's audit trail did not get B's rows
        assert s.execute(text("SELECT count(*) FROM audit.audit_log WHERE trace_id = :tr"), {"tr": c.trace_id}).scalar() == 0
