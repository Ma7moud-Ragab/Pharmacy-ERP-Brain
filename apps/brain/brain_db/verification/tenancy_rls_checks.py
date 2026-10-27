"""Tenant-isolation checks for N-01 (tenant registry) and N-02 (row-level security). Hand-written, not generated.

Usage: build an EMPTY scratch database as the migration owner (`alembic upgrade head` or brain_db_mvp.sql; D-50), then
    python tenancy_rls_checks.py <dbname>
Connection (no superuser anywhere, D-50; see bbsetup.py): BB_ADMIN_DSN (role administrator, CREATEROLE only) creates
one test login per runtime role, which the checks then use; BB_OWNER_DSN (the migration owner, bound by FORCE RLS like
everyone else) reads the catalogs and seeds two tenants, one tenant per transaction with a transaction-local context
(its rule_config writes carry app.actor_id = test:setup, D-51). Password for the test logins: BB_TEST_ROLE_PASSWORD
(default none, for trust/peer auth on a local scratch server). Needs psycopg 3 and SQLAlchemy 2.
Exits non-zero if any check fails.

What a pass shows: with the database alone (no application code), a runtime login only reads and writes the rows of the
tenant in its transaction-local context, a missing context reads nothing and writes nothing, the context does not
survive a pooled connection's commit or rollback, and no runtime role can bypass the policies. It does NOT show that
brain-api takes the tenant from the verified JWT or that brain-worker takes it from the registry: that is application
code (BB-15, BB-16) and its BB-24 tests.
"""
import os, sys, threading, uuid
import psycopg
import psycopg.types.json
import bbsetup
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import QueuePool

DB = sys.argv[1]
A = "00000000-0000-0000-0000-000000000001"      # tenant A (rule_config seeded by 0005)
B = "00000000-0000-0000-0000-000000000002"      # tenant B
P = "b3f1c2a0-4e51-4a2e-9d3e-000000000001"
H = "d67ad9758d7806f685b4294e16a538f84157456e2de40b23aa5ca9c6993b57ce"
TRACE = "0" * 32
PW = os.environ.get("BB_TEST_ROLE_PASSWORD")
SCHEMAS = ("ingest", "feat", "intel", "agent", "audit")
RUNTIME = ["brain_app", "brain_worker", "brain_retention", "brain_readonly", "brain_provisioner"]
LOGINS = {"app": "brain_app", "worker": "brain_worker", "retention": "brain_retention", "readonly": "brain_readonly",
          "prov": "brain_provisioner"}
RLS_DENIED = "row-level security policy"

ow = bbsetup.owner(DB)   # migration owner: not a superuser; FORCE RLS applies to it
adm = bbsetup.admin(DB)  # role administrator: CREATEROLE only
res = []


def report(name, passed, detail=""):
    res.append(passed)
    print(("PASS" if passed else "FAIL"), name, "" if passed else str(detail)[:300])


def login(key):
    return f"bb_rls_{key}"


for key, role in LOGINS.items():
    bbsetup.create_login(adm, login(key), role)
C = {k: bbsetup.login_connect(DB, login(k)) for k in LOGINS}


def run(conn, tenant, *stmts):
    """One unit of work: transaction-local tenant context (None = no context), then the statements. Returns last rows/rowcount."""
    with conn.transaction():
        if tenant is not None:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        out = None
        for s in stmts:
            cur = conn.execute(s)
            out = cur.fetchall() if cur.description else cur.rowcount
        return out


def ok(name, conn, tenant, *stmts, expect=None):
    try:
        out = run(conn, tenant, *stmts)
        report(name, expect is None or out == expect, f"got {out!r}, expected {expect!r}")
    except psycopg.Error as e:
        report(name, False, e)


def refused(name, conn, tenant, expect_msg, *stmts):
    try:
        run(conn, tenant, *stmts)
        report(name, False, "statement was accepted")
    except psycopg.Error as e:
        msgs = expect_msg if isinstance(expect_msg, tuple) else (expect_msg,)
        report(name, any(m in str(e) for m in msgs), f"wrong error: {e}")


def owner_val(sql, tenant=None):
    """Owner's view: catalog queries need no tenant; table counts run in `tenant`'s context (FORCE RLS binds the owner)."""
    if tenant is None:
        return ow.execute(sql).fetchone()[0]
    with bbsetup.tenant(ow, tenant):
        return ow.execute(sql).fetchone()[0]


# ===================================================================================================================
# 1. Catalog: every tenant table is covered, policies are exact, and no runtime role or login can bypass them
# ===================================================================================================================
tenant_tables = [r[0] for r in ow.execute(
    "SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped "
    "WHERE c.relkind IN ('r','p') AND n.nspname = ANY(%s) ORDER BY 1", (list(SCHEMAS),)).fetchall()]
report(f"found the tenant tables ({len(tenant_tables)}, expected 26 incl. tenant_registry and briefing)", len(tenant_tables) == 26,
       tenant_tables)
no_rls = [t for t, rls, force in ow.execute(
    "SELECT oid::regclass::text, relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid::regclass::text = ANY(%s)",
    (tenant_tables,)).fetchall() if not (rls and force)]
report("every tenant table has ENABLE + FORCE ROW LEVEL SECURITY", not no_rls, no_rls)
pols = ow.execute(
    "SELECT polrelid::regclass::text, polname, polcmd, polpermissive, polroles::regrole[]::text[], "
    "pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid) FROM pg_policy ORDER BY 1, 2").fetchall()
EXPR = "(tenant_id = brain_current_tenant())"
iso = {p[0]: p for p in pols if p[1] == "pol_tenant_isolation"}
bad = [t for t in tenant_tables if t not in iso or iso[t][2:] != ("*", True, ["-"], EXPR, EXPR)]
report("every tenant table has exactly pol_tenant_isolation FOR ALL TO PUBLIC USING/WITH CHECK tenant_id = brain_current_tenant()",
       not bad, [iso.get(t) for t in bad])
others = [p[:5] for p in pols if p[1] != "pol_tenant_isolation"]
report("the only other policy is brain_worker's SELECT on the tenant registry",
       others == [("ingest.tenant_registry", "pol_worker_list_tenants", "r", True, ["brain_worker"])], others)

MEMBERS = """WITH RECURSIVE m(roleid, member) AS (
    SELECT roleid, member FROM pg_auth_members WHERE roleid IN (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
    UNION SELECT a.roleid, a.member FROM pg_auth_members a JOIN m ON a.roleid = m.member)
SELECT r.rolname, r.rolsuper, r.rolbypassrls FROM pg_roles r
 WHERE (r.rolname = ANY(%s) OR r.oid IN (SELECT member FROM m)) AND (r.rolsuper OR r.rolbypassrls) ORDER BY 1"""
offenders = ow.execute(MEMBERS, (RUNTIME, RUNTIME)).fetchall()
report("no runtime role and no login inside one is SUPERUSER or BYPASSRLS", not offenders, offenders)
# The earlier negative control (create a BYPASSRLS login and see the query flag it) needs a superuser, so it no longer
# runs here (it passed on 21 Oct). What the setup can show instead: the role administrator cannot create such a login.
refused("the role administrator (CREATEROLE only) cannot create a BYPASSRLS login", adm, None, "permission denied to create role",
        "CREATE ROLE bb_rls_bypass LOGIN BYPASSRLS IN ROLE brain_app")
own = owner_val("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = ANY(ARRAY"
               "['ingest','feat','intel','agent','audit']) AND c.relkind IN ('r','v','p') AND pg_get_userbyid(c.relowner) = ANY(ARRAY"
               "['brain_app','brain_worker','brain_retention','brain_readonly','brain_provisioner','bb_rls_app','bb_rls_worker',"
               "'bb_rls_retention','bb_rls_readonly','bb_rls_prov'])")
report("no runtime role or test login owns a table or view (FORCE also covers the owner)", own == 0, own)
views = ow.execute("SELECT oid::regclass::text, coalesce(reloptions, '{}') FROM pg_class WHERE relkind = 'v' AND "
                   "relnamespace::regnamespace::text = ANY(ARRAY['intel','agent']) ORDER BY 1").fetchall()
report("the 3 projection views run with security_invoker = true (otherwise they read as the owner, skipping RLS)",
       len(views) == 3 and all("security_invoker=true" in v[1] for v in views), views)
secdef = ow.execute("SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE p.prosecdef AND (n.nspname = ANY(ARRAY['ingest','feat','intel','agent','audit']) OR p.proname LIKE 'brain\\_%%')").fetchall()
report("no SECURITY DEFINER function in the Brain schemas (none can read across tenants on a caller's behalf)", not secdef, secdef)

# ===================================================================================================================
# 2. Seed two tenants as the owner, one tenant per transaction (FORCE RLS applies to the owner too)
# ===================================================================================================================
with bbsetup.tenant(ow, A):  # tenant A's rule sets come from the 0005 seed; tenant B gets copies
    RULES = ow.execute(f"SELECT rule_set, version, version_label, params FROM intel.rule_config WHERE tenant_id = '{A}' AND is_active").fetchall()
for t in (A, B):
    with bbsetup.tenant(ow, t):
        if t != A:
            with ow.cursor() as cur:
                cur.executemany("INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
                                "VALUES (%s, %s, %s, %s, %s, true, 'test')", [(t, r[0], r[1], r[2], psycopg.types.json.Jsonb(r[3])) for r in RULES])
        ow.execute(f"INSERT INTO ingest.tenant_registry (tenant_id, provisioned_by) VALUES ('{t}', 'test:setup')")
        ow.execute(f"UPDATE ingest.tenant_registry SET credential_ref = 'canonical/{t}', credential_sha256 = '{H}', "
                   f"credential_validated_at = now() WHERE tenant_id = '{t}'")
        ow.execute(f"UPDATE ingest.tenant_registry SET status = 'active' WHERE tenant_id = '{t}'")
        ow.execute(f"INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, day_status, "
                   f"source_updated_at) VALUES ('{t}', '{P}', '2026-10-16', 5, 0, 5, 'closed', now())")
        ow.execute(f"INSERT INTO ingest.sync_checkpoint (tenant_id, resource) VALUES ('{t}', 'sales_poll')")
        ow.execute(f"INSERT INTO ingest.canonical_cache (tenant_id, entity_type, entity_id, schema_name, schema_version, payload, "
                   f"payload_sha256) VALUES ('{t}', 'product', '{P}', 'canonical.Product', '1.0', '{{}}', '{H}')")
        ow.execute(f"INSERT INTO ingest.ingest_failure (tenant_id, failure_kind, resource, error_code, trace_id) "
                   f"VALUES ('{t}', 'other', 'sales_poll', 'E1', '{TRACE}')")
        ow.execute(f"INSERT INTO ingest.sales_day_coverage (tenant_id, business_date) VALUES ('{t}', '2026-10-16')")
        ow.execute(f"INSERT INTO feat.calendar_day (tenant_id, calendar_date) VALUES ('{t}', '2026-10-16')")
        rid, cid = str(uuid.uuid4()), str(uuid.uuid4())
        ow.execute(f"INSERT INTO intel.risk_assessment (id, tenant_id, product_id, risk_type, severity, days_of_cover, lead_time_days, "
                   f"input_available_quantity, inventory_as_of, rule_version, rule_config_id) VALUES ('{rid}', '{t}', '{P}', 'stockout_risk', "
                   f"'high', 1.7, 5, 40, now(), 'risk-rules@1.0.0', (SELECT id FROM intel.rule_config WHERE tenant_id = '{t}' "
                   f"AND rule_set = 'risk' AND is_active))")
        ow.execute(f"INSERT INTO intel.recommendation (id, tenant_id, product_id, risk_assessment_id, recommendation_type, payload, "
                   f"expires_at, rule_version, rule_config_id) VALUES ('{cid}', '{t}', '{P}', '{rid}', 'create_purchase_order', '{{}}', "
                   f"now() + interval '1 day', 'rec-rules-v1', (SELECT id FROM intel.rule_config WHERE tenant_id = '{t}' "
                   f"AND rule_set = 'recommendation' AND is_active))")
        ow.execute(f"INSERT INTO agent.agent_session (tenant_id, user_actor_id, expires_at) VALUES ('{t}', 'u-1', now() + interval '4 hours')")
        ow.execute(f"INSERT INTO audit.audit_log (tenant_id, event_type, outcome, actor_type, trace_id) "
                   f"VALUES ('{t}', 'test.seed', 'info', 'system', '{TRACE}')")
        ow.execute(f"INSERT INTO audit.llm_usage (tenant_id, purpose, provider, model, prompt_name, prompt_version, tokens_in, tokens_out, "
                   f"estimated_cost_usd, latency_ms, outcome, trace_id) VALUES ('{t}', 'other', 'none', 'none', 'p', '1', 0, 0, 0, 0, "
                   f"'success', '{TRACE}')")
        pid = str(uuid.uuid4())
        ow.execute(f"INSERT INTO agent.action_proposal (id, tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, "
                   f"policy_version, reason, recommendation_id, idempotency_key, expires_at, trace_id) VALUES ('{pid}', '{t}', 'rules', "
                   f"'create_purchase_order', '1.0', '{{}}', '{H}', 'static-policy@1', 'Stockout risk high', '{cid}', '{pid}', "
                   f"now() + interval '24 hours', '{TRACE}')")
REC_B = owner_val(f"SELECT id FROM intel.recommendation WHERE tenant_id = '{B}'", B)
PROP_B = owner_val(f"SELECT id FROM agent.action_proposal WHERE tenant_id = '{B}'", B)
seeded = [t for t in tenant_tables if owner_val(f"SELECT count(*) FROM {t} WHERE tenant_id = '{A}'", A) and
          owner_val(f"SELECT count(*) FROM {t} WHERE tenant_id = '{B}'", B)]
before_b = {t: owner_val(f"SELECT count(*) FROM {t} WHERE tenant_id = '{B}'", B) for t in tenant_tables}
print(f"seeded both tenants in {len(seeded)} tables: {', '.join(seeded)}")

# ===================================================================================================================
# 3. Reads: every runtime login sees only the tenant of its context, and nothing without one
# ===================================================================================================================
for key in ["app", "worker", "retention", "readonly", "prov"]:
    role = LOGINS[key]
    readable = [t for t in seeded if owner_val(f"SELECT has_table_privilege('{role}', '{t}', 'SELECT')::int")]
    leaks, missing, nocontext = [], [], []
    for t in readable:
        for me, other in ((A, B), (B, A)):
            seen, foreign = run(C[key], me, f"SELECT count(*), count(*) FILTER (WHERE tenant_id <> '{me}') FROM {t}")[0]
            if t == "ingest.tenant_registry" and key == "worker":
                if foreign == 0: missing.append(f"{t}: worker must list all tenants")
                continue
            if foreign: leaks.append(f"{t} ctx={me[-1]} saw {foreign} foreign rows")
            if not seen: missing.append(f"{t} ctx={me[-1]} saw no own rows")
            hit = run(C[key], me, f"SELECT count(*) FROM {t} WHERE tenant_id = '{other}'")[0][0]
            if hit: leaks.append(f"{t} ctx={me[-1]} read {hit} rows by asking for the other tenant explicitly")
        if not (t == "ingest.tenant_registry" and key == "worker"):
            n = run(C[key], None, f"SELECT count(*) FROM {t}")[0][0]
            if n: nocontext.append(f"{t}: {n}")
    report(f"{role}: with tenant A or B in context, {len(readable)} readable tables return only that tenant's rows "
           f"(even WHERE tenant_id = <other>)", not leaks and not missing, leaks + missing)
    report(f"{role}: without a tenant context every table reads as empty", not nocontext, nocontext)
for key in ["app", "readonly"]:
    leaks = []
    for v in ["intel.v_insight_current", "intel.v_alert_open", "agent.v_agent_action"]:
        rows = run(C[key], A, f"SELECT count(*), count(*) FILTER (WHERE tenant_id <> '{A}') FROM {v}")[0]
        if rows[1] or not rows[0]: leaks.append(f"{v}: {rows}")
        if run(C[key], None, f"SELECT count(*) FROM {v}")[0][0]: leaks.append(f"{v}: rows without context")
    report(f"{LOGINS[key]}: the projection views follow RLS (own rows with context, none without)", not leaks, leaks)
refused("brain_worker can list every tenant but still reads 0 sales rows without a tenant context", C["worker"], None,
        "no rows", f"DO $$ BEGIN IF (SELECT count(*) FROM ingest.sales_fact) = 0 THEN RAISE EXCEPTION 'no rows'; END IF; END $$")
refused("a tenant context that is not a UUID raises an error instead of matching rows", C["app"], "not-a-uuid",
        "invalid input syntax for type uuid", "SELECT count(*) FROM ingest.sales_fact")

# ===================================================================================================================
# 4. Writes: brain_app (API) and brain_worker (jobs) cannot create, change, move or delete another tenant's rows
# ===================================================================================================================
SALES_B = (f"INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, day_status, "
           f"source_updated_at) VALUES ('{B}', '{P}', '2026-10-17', 1, 0, 1, 'closed', now())")
for key in ["worker"]:  # since 0008 (D-51) brain_app has no pipeline writes; its own-table variants follow below
    r = LOGINS[key]
    refused(f"{r}: INSERT a tenant-B sales row while in tenant A's context", C[key], A, RLS_DENIED, SALES_B)
    refused(f"{r}: INSERT a tenant-B row without any context", C[key], None, RLS_DENIED, SALES_B)
    refused(f"{r}: INSERT its own tenant's row without a context (missing SET is refused, not defaulted)", C[key], None, RLS_DENIED,
            SALES_B.replace(B, A))
    refused(f"{r}: upsert a tenant-B checkpoint from tenant A (ON CONFLICT)", C[key], A, RLS_DENIED,
            f"INSERT INTO ingest.sync_checkpoint (tenant_id, resource) VALUES ('{B}', 'sales_poll') "
            f"ON CONFLICT (tenant_id, resource) DO UPDATE SET last_status = 'failed'")
    refused(f"{r}: INSERT a tenant-B failure row from tenant A", C[key], A, RLS_DENIED,
            f"INSERT INTO ingest.ingest_failure (tenant_id, failure_kind, resource, error_code) VALUES ('{B}', 'other', 'x', 'E9')")
    refused(f"{r}: INSERT a tenant-B audit row from tenant A", C[key], A, RLS_DENIED,
            f"INSERT INTO audit.audit_log (tenant_id, event_type, outcome, actor_type, trace_id) VALUES ('{B}', 'x.y', 'info', 'system', '{TRACE}')")
    ok(f"{r}: UPDATE of tenant B's sales, checkpoint, cache, risk and recommendation rows from tenant A changes 0 rows", C[key], A,
       f"UPDATE ingest.sales_fact SET units_sold = 99, net_units = 99 WHERE tenant_id = '{B}'",
       f"UPDATE ingest.sync_checkpoint SET last_status = 'failed' WHERE tenant_id = '{B}'",
       f"UPDATE ingest.canonical_cache SET synced_at = now() WHERE tenant_id = '{B}'",
       f"UPDATE intel.risk_assessment SET last_confirmed_at = now() WHERE tenant_id = '{B}'",
       f"UPDATE intel.recommendation SET status = 'expired' WHERE tenant_id = '{B}'", expect=0)
    ok(f"{r}: UPDATE without a tenant context changes 0 rows", C[key], None,
       "UPDATE ingest.sales_fact SET units_sold = 99, net_units = 99", expect=0)
    refused(f"{r}: moving its own row to tenant B (UPDATE ... SET tenant_id) is refused", C[key], A, RLS_DENIED,
            f"UPDATE ingest.sales_fact SET tenant_id = '{B}' WHERE tenant_id = '{A}'")
    ok(f"{r}: control: the same login can write its own tenant's rows", C[key], A,
       f"UPDATE ingest.sync_checkpoint SET last_status = 'running' WHERE tenant_id = '{A}'", expect=1)
ok("brain_worker: seeds its own tenant's calendar day (B7, 0008)", C["worker"], A,
   f"INSERT INTO feat.calendar_day (tenant_id, calendar_date, is_holiday, holiday_name, source) VALUES ('{A}', '2026-10-18', true, 'h', 'seed')",
   f"UPDATE feat.calendar_day SET is_ramadan = true WHERE tenant_id = '{A}' AND calendar_date = '2026-10-18'", expect=1)
refused("brain_worker: a tenant-B calendar day from tenant A is refused", C["worker"], A, RLS_DENIED,
        f"INSERT INTO feat.calendar_day (tenant_id, calendar_date) VALUES ('{B}', '2026-10-18')")
ok("brain_worker: UPDATE of tenant B's calendar from tenant A changes 0 rows", C["worker"], A,
   f"UPDATE feat.calendar_day SET is_holiday = true WHERE tenant_id = '{B}'", expect=0)
refused("brain_worker: cannot DELETE calendar days (no DELETE privilege)", C["worker"], A, "permission denied",
        f"DELETE FROM feat.calendar_day WHERE tenant_id = '{A}'")
ok("brain_worker: lifecycle UPDATE of tenant B's proposal from tenant A changes 0 rows", C["worker"], A,
   f"UPDATE agent.action_proposal SET status = 'expired' WHERE id = '{PROP_B}'", expect=0)
refused("brain_app: a tenant-A proposal pointing at tenant B's recommendation is refused (composite FK)", C["app"], A, "fk_",
        f"INSERT INTO agent.action_proposal (tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, policy_version, "
        f"reason, recommendation_id, idempotency_key, expires_at, trace_id) VALUES ('{A}', 'rules', 'create_purchase_order', '1.0', '{{}}', "
        f"'{H}', 'p', 'r', '{REC_B}', '{uuid.uuid4()}', now() + interval '1 hour', '{TRACE}')")
refused("brain_app: a tenant-B decision on tenant B's proposal from tenant A is refused (the guard cannot even see that proposal)",
        C["app"], A, (RLS_DENIED, "unknown proposal"),
        f"INSERT INTO agent.action_approval (tenant_id, proposal_id, approval_round, decision, decided_by_actor_id, decider_scopes, "
        f"arguments_sha256, trace_id) VALUES ('{B}', '{PROP_B}', 1, 'approved', 'u-1', ARRAY['agent:approve'], '{H}', '{TRACE}')")
refused("brain_app: a tenant-B session from tenant A is refused", C["app"], A, RLS_DENIED,
        f"INSERT INTO agent.agent_session (tenant_id, user_actor_id, expires_at) VALUES ('{B}', 'u-1', now() + interval '1 hour')")

# brain_app (D-51): the same ten isolation checks on the tables the API still writes (sessions, proposals, llm_usage) ...
SESS_A = owner_val(f"SELECT id FROM agent.agent_session WHERE tenant_id = '{A}'", A)
SESS_B = owner_val(f"SELECT id FROM agent.agent_session WHERE tenant_id = '{B}'", B)
USAGE_B = (f"INSERT INTO audit.llm_usage (tenant_id, purpose, provider, model, prompt_name, prompt_version, tokens_in, tokens_out, "
           f"estimated_cost_usd, latency_ms, outcome, trace_id) VALUES ('{B}', 'other', 'none', 'none', 'p', '1', 0, 0, 0, 0, 'success', '{TRACE}')")
app = C["app"]
refused("brain_app: INSERT a tenant-B llm_usage row while in tenant A's context", app, A, RLS_DENIED, USAGE_B)
refused("brain_app: INSERT a tenant-B llm_usage row without any context", app, None, RLS_DENIED, USAGE_B)
refused("brain_app: INSERT its own tenant's session without a context (missing SET is refused, not defaulted)", app, None, RLS_DENIED,
        f"INSERT INTO agent.agent_session (tenant_id, user_actor_id, expires_at) VALUES ('{A}', 'u-1', now() + interval '1 hour')")
refused("brain_app: upsert over tenant B's session from tenant A (ON CONFLICT)", app, A, RLS_DENIED,
        f"INSERT INTO agent.agent_session (id, tenant_id, user_actor_id, expires_at) VALUES ('{SESS_B}', '{B}', 'u-1', now()) "
        f"ON CONFLICT (id) DO UPDATE SET last_activity_at = now()")
refused("brain_app: INSERT a tenant-B proposal from tenant A", app, A, RLS_DENIED,
        f"INSERT INTO agent.action_proposal (tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, policy_version, "
        f"reason, idempotency_key, expires_at, trace_id) VALUES ('{B}', 'rules', 'create_purchase_order', '1.0', '{{}}', '{H}', 'p', 'r', "
        f"'{uuid.uuid4()}', now() + interval '1 hour', '{TRACE}')")
ok("brain_app: UPDATE of tenant B's session, proposal and execution rows from tenant A changes 0 rows", app, A,
   f"UPDATE agent.agent_session SET last_activity_at = now() WHERE tenant_id = '{B}'",
   f"UPDATE agent.action_proposal SET status = 'cancelled' WHERE id = '{PROP_B}'",
   f"UPDATE agent.action_execution SET status = 'failed' WHERE tenant_id = '{B}'", expect=0)
ok("brain_app: UPDATE without a tenant context changes 0 rows", app, None, "UPDATE agent.agent_session SET last_activity_at = now()", expect=0)
refused("brain_app: moving its own session to tenant B (UPDATE ... SET tenant_id) is refused", app, A,
        (RLS_DENIED, "immutable column changed"), f"UPDATE agent.agent_session SET tenant_id = '{B}' WHERE id = '{SESS_A}'")
ok("brain_app: control: the same login can write its own tenant's session", app, A,
   f"UPDATE agent.agent_session SET last_activity_at = now() WHERE id = '{SESS_A}'", expect=1)
refused("brain_app: DELETE of the canonical cache is refused outright (no DELETE privilege since 0008)", app, A, "permission denied",
        f"DELETE FROM ingest.canonical_cache WHERE tenant_id = '{B}'")
# ... and every pipeline write is refused by privilege, even for its own tenant (B1).
for name, sql in [
        ("INSERT a sales row", SALES_B.replace(B, A)),
        ("upsert a checkpoint", f"INSERT INTO ingest.sync_checkpoint (tenant_id, resource) VALUES ('{A}', 'sales_poll') "
                                f"ON CONFLICT (tenant_id, resource) DO UPDATE SET last_status = 'failed'"),
        ("UPDATE a checkpoint", f"UPDATE ingest.sync_checkpoint SET last_status = 'running' WHERE tenant_id = '{A}'"),
        ("INSERT an ingest failure", f"INSERT INTO ingest.ingest_failure (tenant_id, failure_kind, resource, error_code) VALUES ('{A}', 'other', 'x', 'E9')"),
        ("UPDATE a risk assessment", f"UPDATE intel.risk_assessment SET last_confirmed_at = now() WHERE tenant_id = '{A}'"),
        ("UPDATE a recommendation", f"UPDATE intel.recommendation SET status = 'expired' WHERE tenant_id = '{A}'"),
        ("INSERT a calendar day", f"INSERT INTO feat.calendar_day (tenant_id, calendar_date) VALUES ('{A}', '2026-10-17')"),
        ("switch a rule set", f"UPDATE intel.rule_config SET is_active = false WHERE tenant_id = '{A}' AND rule_set = 'risk'"),
        ("add a rule-set version", f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
                                   f"VALUES ('{A}', 'risk', 99, 'risk-rules@9.9.9', '{{}}', false, 'api')")]:
    refused(f"brain_app: {name} in its own tenant is refused (permission denied, D-51)", app, A, "permission denied", sql)
refused("brain_app: changing proposal arguments is refused (column-level UPDATE since 0008)", app, A, "permission denied",
        f"UPDATE agent.action_proposal SET arguments = '{{}}' WHERE tenant_id = '{A}'")
ok("brain_retention: purge of tenant B's rows from tenant A deletes 0 rows", C["retention"], A,
   f"DELETE FROM ingest.canonical_cache WHERE tenant_id = '{B}'", f"DELETE FROM audit.llm_usage WHERE tenant_id = '{B}'", expect=0)
ok("brain_retention: purge without a tenant context deletes 0 rows", C["retention"], None, "DELETE FROM ingest.canonical_cache", expect=0)
after_b = {t: owner_val(f"SELECT count(*) FROM {t} WHERE tenant_id = '{B}'", B) for t in tenant_tables}
changed = owner_val(f"SELECT count(*) FROM ingest.sales_fact WHERE tenant_id = '{B}' AND units_sold <> 5", B)
report("owner's view in tenant B's context after all attempts: tenant B's row counts and sales values are unchanged",
       after_b == before_b and changed == 0, {t: (before_b[t], after_b[t]) for t in tenant_tables if before_b[t] != after_b[t]})

# ===================================================================================================================
# 5. Pooled connections: the tenant context never survives a unit of work (SQLAlchemy QueuePool, as brain-api/worker use)
# ===================================================================================================================
def engine(key, size=1):
    host, port = bbsetup.server()
    url = f"postgresql+psycopg://{login(key)}" + (f":{PW}" if PW else "") + f"@/{DB}?host={host}&port={port}"
    return create_engine(url, poolclass=QueuePool, pool_size=size, max_overflow=0)


def uow(eng, tenant, sql, fail=False):
    """The pattern required for brain/db/session.py: begin, set the context transaction-locally, work, commit/rollback."""
    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        out = c.execute(text(sql)).fetchall()
        if fail:
            raise RuntimeError("simulated failure inside the unit of work")
        return out


PROBE = "SELECT pg_backend_pid(), nullif(current_setting('app.tenant_id', true), ''), (SELECT count(*) FROM ingest.sales_fact)"
for key in ["app", "worker"]:
    r = LOGINS[key]
    eng = engine(key)
    pid_a, ctx_a, n_a = uow(eng, A, PROBE)[0]
    with eng.connect() as c:
        pid2, ctx2, n2 = c.execute(text(PROBE)).fetchone()
    report(f"{r}: after a committed unit of work for A, the same pooled connection has no tenant and reads 0 rows",
           pid2 == pid_a and ctx_a == A and n_a == 1 and ctx2 is None and n2 == 0, (pid_a, ctx_a, n_a, pid2, ctx2, n2))
    try:
        uow(eng, A, PROBE, fail=True)
    except RuntimeError:
        pass
    with eng.connect() as c:
        pid3, ctx3, n3 = c.execute(text(PROBE)).fetchone()
    report(f"{r}: after a unit of work that failed and rolled back, the pooled connection has no tenant",
           pid3 == pid_a and ctx3 is None and n3 == 0, (pid3, ctx3, n3))
    bad = []
    for i in range(40):
        t = A if i % 2 == 0 else B
        pid, ctx, n = uow(eng, t, PROBE)[0]
        foreign = uow(eng, t, f"SELECT count(*) FROM ingest.sales_fact WHERE tenant_id <> '{t}'")[0][0]
        if pid != pid_a or ctx != t or n != 1 or foreign: bad.append((i, pid, ctx, n, foreign))
    report(f"{r}: 40 alternating A/B units of work on ONE pooled connection each see only their own tenant", not bad, bad[:3])

    # Negative control: a session-level SET (the anti-pattern) does leak through the pool ...
    with eng.connect() as c:
        c.execute(text(f"SET app.tenant_id = '{B}'"))
        c.commit()
    with eng.connect() as c:
        leaked = c.execute(text(PROBE)).fetchone()
    report(f"{r}: negative control: a session-level SET survives in the pool (why session.py must use set_config(..., true))",
           leaked[1] == B and leaked[2] == 1, leaked)
    eng.dispose()

    # ... and the checkout guard required for session.py catches it: the poisoned connection is discarded, not reused.
    eng = engine(key)
    discarded = []

    @event.listens_for(eng, "checkout")
    def _guard(dbapi_conn, record, proxy, _d=discarded):
        cur = dbapi_conn.cursor()
        cur.execute("SELECT nullif(current_setting('app.tenant_id', true), '')")
        leftover = cur.fetchone()[0]
        cur.close()
        if leftover is not None:
            _d.append(leftover)
            from sqlalchemy.exc import DisconnectionError
            raise DisconnectionError("tenant context left on a pooled connection")

    with eng.connect() as c:
        c.execute(text(f"SET app.tenant_id = '{B}'"))
        c.commit()
        pid_poisoned = c.execute(text("SELECT pg_backend_pid()")).scalar()
    with eng.connect() as c:
        pid_new, ctx_new, n_new = c.execute(text(PROBE)).fetchone()
    report(f"{r}: the checkout guard discards a connection that still carries a tenant and hands out a clean one",
           discarded == [B] and pid_new != pid_poisoned and ctx_new is None and n_new == 0, (discarded, pid_poisoned, pid_new, ctx_new, n_new))
    eng.dispose()

    eng = engine(key, size=4)
    errors = []

    def worker_thread(t, n=25):
        for _ in range(n):
            rows = uow(eng, t, "SELECT tenant_id::text FROM ingest.sales_fact")
            if [x[0] for x in rows] != [t]:
                errors.append((t, rows))

    threads = [threading.Thread(target=worker_thread, args=(A if i % 2 == 0 else B,)) for i in range(8)]
    for th in threads: th.start()
    for th in threads: th.join()
    report(f"{r}: 8 threads x 25 units of work, tenants A and B interleaved on a pool of 4, never see the other tenant",
           not errors, errors[:3])
    eng.dispose()

# ===================================================================================================================
# 6. Tenant registry (N-01): no silent activation, validated credentials only, provisioning role only
# ===================================================================================================================
TC, TD = str(uuid.uuid4()), str(uuid.uuid4())
ACTOR = "SELECT set_config('app.actor_id', 'ops:test', true)"  # the operator brain-provision records (D-51)
prov = C["prov"]
REG = "ingest.tenant_registry"
refused("provisioner cannot create a tenant directly as active", prov, TC, "must be created in status provisioning",
        f"INSERT INTO {REG} (tenant_id, status, provisioned_by) VALUES ('{TC}', 'active', 'ops:test')")
refused("provisioner cannot create a tenant without the tenant context of that tenant", prov, None, RLS_DENIED,
        f"INSERT INTO {REG} (tenant_id, provisioned_by) VALUES ('{TC}', 'ops:test')")
refused("provisioner cannot create tenant D while in tenant C's context", prov, TC, RLS_DENIED,
        f"INSERT INTO {REG} (tenant_id, provisioned_by) VALUES ('{TD}', 'ops:test')")
ok("provisioner creates tenant C in status provisioning", prov, TC,
   f"INSERT INTO {REG} (tenant_id, display_label, provisioned_by) VALUES ('{TC}', 'Tenant C', 'ops:test')")
refused("a secret-looking credential_ref (URL with password) is refused", prov, TC, "ck_tenant_registry__credential_ref_format",
        f"UPDATE {REG} SET credential_ref = 'https://svc:s3cret@erp/x' WHERE tenant_id = '{TC}'")
refused("a token pasted as credential_ref is refused", prov, TC, "ck_tenant_registry__credential_ref_format",
        f"UPDATE {REG} SET credential_ref = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.Sig' WHERE tenant_id = '{TC}'")
refused("activation without a validated credential is refused", prov, TC, "credential is not validated",
        f"UPDATE {REG} SET status = 'active' WHERE tenant_id = '{TC}'")
ok("provisioner records the credential reference and its validation (server time, version 1)", prov, TC,
   f"UPDATE {REG} SET credential_ref = 'canonical/{TC}', credential_sha256 = '{H}', credential_validated_at = '2000-01-01' "
   f"WHERE tenant_id = '{TC}'",
   f"SELECT credential_version, credential_validated_at > now() - interval '1 minute' FROM {REG} WHERE tenant_id = '{TC}'",
   expect=[(1, True)])
refused("activation without the tenant's rule sets is refused", prov, TC, "no active rule_config for",
        f"UPDATE {REG} SET status = 'active' WHERE tenant_id = '{TC}'")
refused("seeding rule sets without an operator id (app.actor_id) is refused (D-51)", prov, TC, "set app.actor_id",
        f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) VALUES "
        f"('{TC}', 'risk', 1, 'risk-rules@1.0.0', '{{}}', true, 'provision')")
ok("provisioner seeds tenant C's rule sets (N-08 decides their content)", prov, TC, ACTOR,
   f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) VALUES "
   + ", ".join(f"('{TC}', '{s}', 1, '{s}-rules@1.0.0', '{{}}', true, 'provision')" for s in
               ["platform", "anomaly", "risk", "recommendation", "forecast"]))
ok("activation succeeds once the credential is validated and the rule sets exist; activated_at is set", prov, TC,
   f"UPDATE {REG} SET status = 'active' WHERE tenant_id = '{TC}'",
   f"SELECT status, activated_at IS NOT NULL FROM {REG} WHERE tenant_id = '{TC}'", expect=[("active", True)])

# Rule-set version changes (B7, D-51): only brain_provisioner, only is_active, only in its tenant context, attributed and
# audited in the same transaction, and an active tenant never ends up without an active version of a set.
def rc_audit(tenant, trace=None):
    with bbsetup.tenant(ow, tenant):
        return ow.execute("SELECT event_type, actor_id, details->>'rule_set', (details->>'version')::int FROM audit.audit_log "
                          "WHERE tenant_id = %s AND subject_type = 'rule_config'" + (" AND trace_id = %s" if trace else "") +
                          " ORDER BY seq", (tenant, trace) if trace else (tenant,)).fetchall()


report("seeding C's five rule sets wrote five rule_config.version_added audit rows in C, attributed to the operator",
       rc_audit(TC) == [("rule_config.version_added", "ops:test", s, 1) for s in ["platform", "anomaly", "risk", "recommendation", "forecast"]],
       rc_audit(TC))
ok("provisioner adds risk version 2 (inactive) for C", prov, TC, ACTOR,
   f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
   f"VALUES ('{TC}', 'risk', 2, 'risk-rules@2.0.0', '{{\"min_cover_days\": 3}}', false, 'provision')")
V1 = f"UPDATE intel.rule_config SET is_active = false WHERE tenant_id = '{TC}' AND rule_set = 'risk' AND version = 1"
V2 = f"UPDATE intel.rule_config SET is_active = true WHERE tenant_id = '{TC}' AND rule_set = 'risk' AND version = 2"
refused("a rule-set switch without an operator id is refused", prov, TC, "set app.actor_id", V1, V2)
refused("deactivating C's only active risk version without activating another is refused at commit", prov, TC, "would have no active risk",
        ACTOR, V1)
ok("the switch v1 -> v2 in one transaction succeeds", prov, TC, ACTOR, "SELECT set_config('app.trace_id', 'c' || repeat('0', 31), true)",
   V1, V2, f"SELECT version FROM intel.rule_config WHERE tenant_id = '{TC}' AND rule_set = 'risk' AND is_active", expect=[(2,)])
report("the switch wrote deactivated + activated audit rows in C with the operator and the transaction's trace id",
       rc_audit(TC, "c" + "0" * 31) == [("rule_config.deactivated", "ops:test", "risk", 1), ("rule_config.activated", "ops:test", "risk", 2)],
       rc_audit(TC, "c" + "0" * 31))
refused("editing a stored version's params is refused (provisioner may UPDATE is_active only)", prov, TC, "permission denied", ACTOR,
        f"UPDATE intel.rule_config SET params = '{{}}' WHERE tenant_id = '{TC}' AND rule_set = 'risk' AND version = 2")
refused("deleting a rule-set version is refused", prov, TC, "permission denied", f"DELETE FROM intel.rule_config WHERE tenant_id = '{TC}'")
ok("tenant-scoped: from C's context, switching tenant A's risk set changes 0 rows", prov, TC, ACTOR,
   f"UPDATE intel.rule_config SET is_active = NOT is_active WHERE tenant_id = '{A}' AND rule_set = 'risk'", expect=0)
refused("tenant-scoped: from C's context, adding a version for tenant A is refused", prov, TC, RLS_DENIED, ACTOR,
        f"INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) "
        f"VALUES ('{A}', 'risk', 98, 'risk-rules@9.8.0', '{{}}', false, 'provision')")
refused("tenant-scoped: the provisioner cannot write an audit row into another tenant", prov, TC, RLS_DENIED,
        f"INSERT INTO audit.audit_log (tenant_id, event_type, outcome, actor_type, trace_id) VALUES ('{A}', 'x.y', 'info', 'user', '{TRACE}')")
refused("the provisioner cannot read the audit log (insert-only)", prov, TC, "permission denied", "SELECT count(*) FROM audit.audit_log")
refused("rotating an active tenant's credential without a new validation is refused", prov, TC, "without a new validation",
        f"UPDATE {REG} SET credential_ref = 'canonical/{TC}/v2', credential_sha256 = '{'a' * 64}' WHERE tenant_id = '{TC}'")
ok("rotation with a new validation succeeds and bumps credential_version", prov, TC,
   f"UPDATE {REG} SET credential_ref = 'canonical/{TC}/v2', credential_sha256 = '{'a' * 64}', credential_validated_at = now() "
   f"WHERE tenant_id = '{TC}'", f"SELECT credential_version FROM {REG} WHERE tenant_id = '{TC}'", expect=[(2,)])
refused("suspension needs a reason", prov, TC, "ck_tenant_registry__suspended_requirements",
        f"UPDATE {REG} SET status = 'suspended' WHERE tenant_id = '{TC}'")
ok("worker (no context) lists exactly the active tenants", C["worker"], None,
   f"SELECT tenant_id::text FROM {REG} WHERE status = 'active' ORDER BY 1", expect=sorted([(A,), (B,), (TC,)]))
ok("suspending C (with a reason) takes it out of the worker's list", prov, TC,
   f"UPDATE {REG} SET status = 'suspended', status_reason = 'contract ended' WHERE tenant_id = '{TC}'")
ok("worker's active list no longer contains C", C["worker"], None,
   f"SELECT count(*) FROM {REG} WHERE status = 'active' AND tenant_id = '{TC}'", expect=[(0,)])
ok("brain_app sees only its own tenant's registry row", C["app"], A, f"SELECT tenant_id::text, status FROM {REG}", expect=[(A, "active")])
ok("brain_app sees no registry row without a context", C["app"], None, f"SELECT count(*) FROM {REG}", expect=[(0,)])
for key in ["app", "worker", "readonly"]:
    refused(f"{LOGINS[key]} cannot write the tenant registry", C[key], A, "permission denied",
            f"UPDATE {REG} SET status = 'suspended', status_reason = 'x' WHERE tenant_id = '{A}'")
refused("brain_provisioner cannot delete a tenant (no DELETE privilege)", prov, TC, "permission denied", f"DELETE FROM {REG} WHERE tenant_id = '{TC}'")
refused("even the table owner cannot delete a tenant (forbid-delete trigger)", ow, TC, "is not allowed",
        f"DELETE FROM {REG} WHERE tenant_id = '{TC}'")
refused("brain_provisioner cannot read tenant business data", prov, TC, "permission denied", "SELECT count(*) FROM ingest.sales_fact")
refused("tenant_id of a registry row is immutable", prov, TC, "tenant_id is immutable",
        f"UPDATE {REG} SET tenant_id = '{TD}' WHERE tenant_id = '{TC}'")

for c in C.values(): c.close()
for key in LOGINS:
    bbsetup.drop_login(adm, login(key))
print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
