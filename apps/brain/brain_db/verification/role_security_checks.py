"""Database-role checks for D-45 (brain_worker vs brain_app) and D-51 (least privilege after 0008). Hand-written, not generated.

Usage: build an EMPTY scratch database as the migration owner (`alembic upgrade head` or brain_db_mvp.sql; D-50), then
    python role_security_checks.py <dbname>
Connection (no superuser, D-50; see bbsetup.py): BB_ADMIN_DSN (role administrator, CREATEROLE only) creates two test
logins (bb_test_worker IN ROLE brain_worker, bb_test_app IN ROLE brain_app) and the script connects as them; BB_OWNER_DSN
(the migration owner) reads the catalogs and seeds proposals in tenant T's context. Login password: BB_TEST_ROLE_PASSWORD
(default: none, for trust/peer auth on a local scratch server). Needs psycopg 3.
Exits non-zero if any check fails.
Since migration 0007 (N-02) both runtime connections run every transaction with the transaction-local tenant context
(set_config('app.tenant_id', T, true)); without it RLS hides every row. Cross-tenant RLS checks: tenancy_rls_checks.py.
"""
import os, sys, uuid
import psycopg
import bbsetup

DB = sys.argv[1]
T = "00000000-0000-0000-0000-000000000001"
H = "d67ad9758d7806f685b4294e16a538f84157456e2de40b23aa5ca9c6993b57ce"
TRACE = "0" * 32
ARGS = '{"supplier_id":"c0ffee00-0000-4000-8000-000000000001","lines":[{"product_id":"b3f1c2a0-4e51-4a2e-9d3e-000000000001","quantity":110}]}'

db_owner = bbsetup.owner(DB)  # the migration owner: NOT a superuser, and RLS binds it
adm = bbsetup.admin(DB)
for login, role in [("bb_test_worker", "brain_worker"), ("bb_test_app", "brain_app")]:
    bbsetup.create_login(adm, login, role)
wk = bbsetup.login_connect(DB, "bb_test_worker")
app = bbsetup.login_connect(DB, "bb_test_app")
res = []


def report(name, passed, detail=""):
    res.append(passed)
    print(("PASS" if passed else "FAIL"), name, "" if passed else str(detail)[:300])


def tenant_ctx(conn):
    """Transaction-local tenant context (N-02); the owner needs it too (FORCE RLS)."""
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (T,))


def ok(conn, name, *stmts):
    try:
        with conn.transaction():
            tenant_ctx(conn)
            for s in stmts: conn.execute(s)
        report(name, True)
    except psycopg.Error as e:
        report(name, False, str(e))


def refused(conn, name, expect_msg, *stmts):
    try:
        with conn.transaction():
            tenant_ctx(conn)
            for s in stmts: conn.execute(s)
        report(name, False, "statement was accepted")
    except psycopg.Error as e:
        report(name, expect_msg in str(e), f"wrong error: {e}")


def proposal(conn=db_owner):
    pid = str(uuid.uuid4())
    with conn.transaction():
        tenant_ctx(conn)
        conn.execute("INSERT INTO agent.action_proposal(id,tenant_id,proposed_by,tool_name,tool_version,arguments,arguments_sha256,policy_version,"
                     f"reason,idempotency_key,expires_at,trace_id) VALUES ('{pid}','{T}','rules','create_purchase_order','1.0','{ARGS}','{H}',"
                     f"'static-policy@1','Stockout risk high','{pid}',now()+interval '24 hours','{TRACE}')")
    return pid


def approval(pid, decision="approved", rnd=1, actor="u-1"):
    aid = str(uuid.uuid4())
    return aid, (f"INSERT INTO agent.action_approval(id,tenant_id,proposal_id,approval_round,decision,decided_by_actor_id,decider_scopes,"
                 f"arguments_sha256,trace_id) VALUES ('{aid}','{T}','{pid}',{rnd},'{decision}','{actor}',ARRAY['agent:approve'],'{H}','{TRACE}')")


def status(pid, s):
    return f"UPDATE agent.action_proposal SET status='{s}' WHERE id='{pid}'"


def execution(pid, aid, attempt):
    eid = str(uuid.uuid4())
    return eid, (f"INSERT INTO agent.action_execution(id,tenant_id,proposal_id,approval_id,attempt_no,arguments_sha256,idempotency_key,"
                 f"on_behalf_of_actor_id,trace_id) VALUES ('{eid}','{T}','{pid}','{aid}',{attempt},'{H}','{pid}','u-1','{TRACE}')")


def fail_exec(eid, certainty="unknown"):
    return (f"UPDATE agent.action_execution SET status='failed', outcome_certainty='{certainty}', error_code='timeout', "
            f"completed_at=now() WHERE id='{eid}'")


# ---------- 1. Role attributes and membership ----------
for r in ["brain_app", "brain_worker", "brain_retention", "brain_readonly", "brain_provisioner"]:
    row = db_owner.execute("SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname=%s", (r,)).fetchone()
    report(f"{r}: no superuser/createrole/createdb/replication/bypassrls/login", row == (False,) * 6, str(row))
m = db_owner.execute("SELECT pg_has_role('brain_worker','brain_app','MEMBER'), pg_has_role('brain_app','brain_worker','MEMBER')").fetchone()
report("brain_worker and brain_app are not members of each other", m == (False, False), str(m))
own = db_owner.execute("SELECT count(*) FROM pg_tables WHERE schemaname IN ('ingest','feat','intel','agent','audit') "
                 "AND tableowner IN ('brain_app','brain_worker','bb_test_worker','bb_test_app')").fetchone()[0]
report("no runtime role owns a table (so none can disable triggers)", own == 0, str(own))

# ---------- 2. Worker cannot decide, re-decide, or bypass guards ----------
p1 = proposal()
refused(wk, "worker cannot insert a decision (approve)", "permission denied for table action_approval", approval(p1)[1])
refused(wk, "worker cannot move pending -> approved", "brain_worker may not move action_proposal pending -> approved", status(p1, "approved"))
refused(wk, "worker cannot move pending -> cancelled", "brain_worker may not move", status(p1, "cancelled"))
refused(wk, "worker cannot change proposal arguments (column privilege)", "permission denied for table action_proposal",
        f"UPDATE agent.action_proposal SET arguments='{{}}' WHERE id='{p1}'")
refused(wk, "worker cannot create proposals", "permission denied for table action_proposal",
        f"INSERT INTO agent.action_proposal(tenant_id,proposed_by,tool_name,tool_version,arguments,arguments_sha256,policy_version,reason,"
        f"idempotency_key,expires_at,trace_id) VALUES ('{T}','rules','x','1','{{}}','{H}','p','r','{uuid.uuid4()}',now()+interval '1 hour','{TRACE}')")
refused(wk, "worker cannot DELETE a proposal", "permission denied", f"DELETE FROM agent.action_proposal WHERE id='{p1}'")
refused(wk, "worker cannot TRUNCATE the audit log", "permission denied", "TRUNCATE audit.audit_log")
refused(wk, "worker cannot UPDATE the audit log", "permission denied", "UPDATE audit.audit_log SET outcome = outcome")
refused(wk, "worker cannot disable lifecycle triggers", "must be owner", "ALTER TABLE agent.action_proposal DISABLE TRIGGER USER")
refused(wk, "worker cannot switch off triggers with session_replication_role", "permission denied", "SET session_replication_role = replica")
refused(wk, "worker cannot assume the app role", "permission denied to set role", "SET ROLE brain_app")
refused(wk, "worker cannot read or write sessions (API-only table)", "permission denied",
        "SELECT 1 FROM agent.agent_session LIMIT 1")

p2 = proposal(); a2, x2 = approval(p2)
ok(app, "app records the human decision and approves (pending -> approved)", x2, status(p2, "approved"))
refused(wk, "worker cannot move approved -> executing (execution starts in the API after a decision)", "brain_worker may not move",
        status(p2, "executing"))
refused(wk, "worker cannot move approved -> cancelled", "brain_worker may not move", status(p2, "cancelled"))
ok(app, "app starts execution (approved -> executing)", status(p2, "executing"))
e2, x2e = execution(p2, a2, 1)
ok(app, "app inserts attempt 1 and it times out (unknown)", x2e, fail_exec(e2))
e2b, x2b = execution(p2, a2, 2)
ok(wk, "worker same-key retry while executing (allowed, D-43)", x2b, fail_exec(e2b))
ok(wk, "worker writes its audit row", "INSERT INTO audit.audit_log(tenant_id,event_type,outcome,actor_type,actor_id,subject_type,subject_id,trace_id) "
   f"VALUES ('{T}','execution.failed','failure','system','system:execution_retry','action_proposal','{p2}','{TRACE}')")
ok(wk, "worker gives up: executing -> failed", status(p2, "failed"))
refused(wk, "worker cannot re-approve: no decision insert (round 2)", "permission denied for table action_approval", approval(p2, rnd=2)[1])
refused(wk, "worker cannot move failed -> approved", "brain_worker may not move action_proposal failed -> approved", status(p2, "approved"))
refused(wk, "worker cannot add an attempt to the failed proposal", "execution requires the proposal to be executing", execution(p2, a2, 3)[1])
refused(app, "app cannot record a decision under a job actor id", "ck_action_approval__human_actor", approval(p2, rnd=2, actor="system:proposal_expiry")[1])
r2, x2r = approval(p2, rnd=2, actor="u-2")
ok(app, "app records a human round-2 decision and re-approves", x2r, status(p2, "approved"))

p3 = proposal()
ok(wk, "worker expiry sweep: pending -> expired (allowed)", status(p3, "expired"))
p4 = proposal(); a4, x4 = approval(p4)
ok(app, "app approves and starts executing p4", x4, status(p4, "approved"), status(p4, "executing"))
e4, x4e = execution(p4, a4, 1)
ok(wk, "worker completes an execution: attempt succeeded, executing -> succeeded", x4e,
   f"UPDATE agent.action_execution SET status='succeeded', completed_at=now(), external_ref_type='purchase_order', external_ref_id='PO-9' WHERE id='{e4}'",
   status(p4, "succeeded"))

# ---------- 3. Privilege matrix: worker has exactly the documented table privileges (calendar since 0008, D-51) ----------
expected = {
    "ingest.sync_checkpoint": "SIU", "ingest.ingest_failure": "SIU", "ingest.canonical_cache": "SIU", "ingest.sales_fact": "SIU",
    "ingest.sales_day_coverage": "SIU", "feat.calendar_day": "SIU", "feat.feature_daily": "SIU", "intel.rule_config": "S",
    "intel.training_run": "SIU", "intel.model_registry": "SIU", "intel.model_evaluation": "SI", "intel.forecast": "SI",
    "intel.forecast_point": "SI", "intel.anomaly_event": "SIU", "intel.risk_assessment": "SIU", "intel.recommendation": "SIU",
    "intel.briefing": "SIU", "audit.llm_usage": "", "audit.audit_log": "I", "agent.agent_session": "", "agent.agent_message": "",
    "agent.agent_action": "", "agent.action_proposal": "S", "agent.action_approval": "S", "agent.action_execution": "SIU",
    "ingest.tenant_registry": "S",
}
names = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE", "T": "TRUNCATE"}


def matrix(role, expected, label):
    bad = []
    for tbl, exp in expected.items():
        if not db_owner.execute("SELECT to_regclass(%s) IS NOT NULL", (tbl,)).fetchone()[0]:
            continue
        got = "".join(k for k in "SIUDT" if db_owner.execute("SELECT has_table_privilege(%s, %s, %s)", (role, tbl, names[k])).fetchone()[0])
        if got != exp:
            bad.append(f"{tbl}: expected {exp or '-'} got {got or '-'}")
    report(f"{role} table privileges match the {label}", not bad, "; ".join(bad))


def update_cols(role, tbl):
    return db_owner.execute("SELECT string_agg(attname, ',' ORDER BY attname) FROM pg_attribute WHERE attrelid=%s::regclass AND attnum > 0 "
                      "AND NOT attisdropped AND has_column_privilege(%s, attrelid, attnum, 'UPDATE')", (tbl, role)).fetchone()[0]


LIFECYCLE = "row_version,status,status_changed_at,updated_at"
matrix("brain_worker", expected, "D-45 matrix plus the calendar (D-51; no DELETE/TRUNCATE anywhere)")
report("brain_worker may UPDATE only the lifecycle columns of action_proposal", update_cols("brain_worker", "agent.action_proposal") == LIFECYCLE,
       update_cols("brain_worker", "agent.action_proposal"))

# ---------- 4. brain_app after 0008 (B1, D-51): reads the pipeline, writes only the API's own tables ----------
PIPELINE = [t for t, v in expected.items() if t.split(".")[0] in ("ingest", "feat", "intel")]
app_expected = {t: "S" for t in PIPELINE}
app_expected.update({"agent.agent_session": "SIU", "agent.agent_message": "SI", "agent.agent_action": "SI", "agent.action_proposal": "SI",
                     "agent.action_approval": "SI", "agent.action_execution": "SIU", "audit.llm_usage": "SI", "audit.audit_log": "SI"})
matrix("brain_app", app_expected, "D-51 matrix (pipeline read-only, no DELETE/TRUNCATE anywhere)")
report("brain_app may UPDATE only the lifecycle columns of action_proposal (column-level since 0008)",
       update_cols("brain_app", "agent.action_proposal") == LIFECYCLE, update_cols("brain_app", "agent.action_proposal"))
refused(app, "app cannot write a pipeline table (sales_fact)", "permission denied for table sales_fact",
        f"INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, day_status, source_updated_at) "
        f"VALUES ('{T}', 'b3f1c2a0-4e51-4a2e-9d3e-000000000001', '2026-10-17', 1, 0, 1, 'closed', now())")
refused(app, "app cannot write recommendations", "permission denied for table recommendation",
        "UPDATE intel.recommendation SET status = 'expired'")
refused(app, "app cannot switch a rule set", "permission denied for table rule_config",
        "UPDATE intel.rule_config SET is_active = false WHERE rule_set = 'risk'")
refused(app, "app cannot add a rule-set version", "permission denied for table rule_config",
        f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, created_by) "
        f"VALUES ('{T}', 'risk', 99, 'risk-rules@9.9.9', '{{}}', 'api')")
refused(app, "app cannot delete canonical cache rows", "permission denied for table canonical_cache", "DELETE FROM ingest.canonical_cache")
refused(app, "app cannot change proposal arguments (column privilege)", "permission denied for table action_proposal",
        f"UPDATE agent.action_proposal SET arguments='{{}}' WHERE id='{p1}'")
ok(wk, "worker writes the tenant calendar (B7)",
   f"INSERT INTO feat.calendar_day (tenant_id, calendar_date) VALUES ('{T}', '2026-10-20') ON CONFLICT (tenant_id, calendar_date) "
   f"DO UPDATE SET is_holiday = EXCLUDED.is_holiday")

# ---------- 5. brain_provisioner (D-46, D-51): registry, rule-set seeding and switching, audit insert; nothing else ----------
prov_expected = {t: "" for t in expected}
prov_expected.update({"ingest.tenant_registry": "SIU", "intel.rule_config": "SI", "audit.audit_log": "I"})
matrix("brain_provisioner", prov_expected, "D-51 matrix (no business data, no DELETE)")
report("brain_provisioner may UPDATE only is_active of rule_config", update_cols("brain_provisioner", "intel.rule_config") == "is_active",
       update_cols("brain_provisioner", "intel.rule_config"))
fns = db_owner.execute("SELECT p.oid::regprocedure::text FROM pg_proc p WHERE p.proname IN ('audit_rule_config_change', 'check_rule_set_still_active') "
                 "AND p.pronamespace = 'intel'::regnamespace AND NOT p.prosecdef ORDER BY 1").fetchall()
report("the rule_config audit and keep-active functions run with the caller's rights (no SECURITY DEFINER)", len(fns) == 2, fns)

wk.close(); app.close()
for login in ["bb_test_worker", "bb_test_app"]:
    bbsetup.drop_login(adm, login)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
