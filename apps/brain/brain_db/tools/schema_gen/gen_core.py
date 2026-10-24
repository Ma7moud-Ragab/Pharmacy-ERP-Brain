import re, json, collections
from spec_lib import *
from spec_ingest import TABLES_INGEST
from spec_intel import TABLES_INTEL
from spec_agent import TABLES_AGENT, TABLES_FUTURE
from spec_tenancy import TABLES_TENANCY
import spec_privileges as PRIV

ALL_BASE = TABLES_INGEST + TABLES_INTEL + TABLES_AGENT     # MVP + SHOULD, migrations 0002-0006
ALL = ALL_BASE + TABLES_TENANCY                            # + tenant registry, migration 0007 (N-01)
RUNTIME_ROLES = ["brain_app", "brain_worker", "brain_retention", "brain_readonly", "brain_provisioner"]
BY_Q = {t.qname: t for t in ALL + TABLES_FUTURE}
BY_CLS = {t.cls: t for t in ALL + TABLES_FUTURE}

# ---------- derived constraint sets -------------------------------------------------
def auto_uniques(t):
    u = list(t.uniques)
    if t.fk_target:
        u.insert(0, (f"uq_{t.name}__tenant_id_id", ["tenant_id", "id"]))
    return u

def auto_checks(t):
    ch = list(t.checks)
    for c in t.cols:
        if c.name == "trace_id":
            e = "trace_id ~ '^[0-9a-f]{32}$'" if not c.null else "trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'"
            ch.append((f"ck_{t.name}__trace_id_format", e))
        if c.name.endswith("_sha256"):
            e = f"{c.name} ~ '^[0-9a-f]{{64}}$'" if not c.null else f"{c.name} IS NULL OR {c.name} ~ '^[0-9a-f]{{64}}$'"
            ch.append((f"ck_{t.name}__{c.name}_format", e))
        if c.jsonb:
            e = f"jsonb_typeof({c.name}) = '{c.jsonb}'" if not c.null else f"{c.name} IS NULL OR jsonb_typeof({c.name}) = '{c.jsonb}'"
            ch.append((f"ck_{t.name}__{c.name}_type", e))
    return ch

def is_self(t, fk): return fk.ref == t.qname

# ---------- validation --------------------------------------------------------------
def validate():
    errs = []
    for t in ALL:
        if t.scope == "FUTURE": continue
        if t.qname not in PRIV.APP_TARGET: errs.append(f"{t.qname}: no brain_app target in spec_privileges.py")
        elif not set(PRIV.APP_TARGET[t.qname]) <= set(t.grants): errs.append(f"{t.qname}: 0008 may only remove brain_app privileges")
    names = collections.Counter()
    for t in ALL + TABLES_FUTURE:
        cn = {c.name for c in t.cols}
        if len(cn) != len(t.cols): errs.append(f"{t.qname}: duplicate column")
        for c in t.pk:
            if c not in cn: errs.append(f"{t.qname}: pk col {c} missing")
        for n, cols in auto_uniques(t):
            names[n] += 1
            for c in cols:
                if c not in cn: errs.append(f"{t.qname}: uq {n} col {c} missing")
        for i in t.idxs:
            names[i.name] += 1
            for c in i.cols:
                if c not in cn: errs.append(f"{t.qname}: idx {i.name} col {c} missing")
        names[f"pk_{t.name}"] += 1
        for fk in t.fks:
            names[fk.name] += 1
            for c in fk.cols:
                if c not in cn: errs.append(f"{t.qname}: fk {fk.name} col {c} missing")
            if fk.ref not in BY_Q: errs.append(f"{fk.name}: unknown ref {fk.ref}"); continue
            p = BY_Q[fk.ref]
            pcols = {c.name: c for c in p.cols}
            for c in fk.ref_cols:
                if c not in pcols: errs.append(f"{fk.name}: ref col {c} missing in {fk.ref}")
            targets = [set(p.pk)] + [set(c) for _, c in auto_uniques(p)] + [set(i.cols) for i in p.idxs if i.unique and not i.where]
            if set(fk.ref_cols) not in targets: errs.append(f"{fk.name}: ref cols {fk.ref_cols} not a unique key of {fk.ref}")
            cc = {c.name: c for c in t.cols}
            for a, b in zip(fk.cols, fk.ref_cols):
                if cc[a].typ != pcols[b].typ: errs.append(f"{fk.name}: type mismatch {a} {cc[a].typ} vs {b} {pcols[b].typ}")
        cks = collections.Counter(n for n, _ in auto_checks(t))
        for n, k in cks.items():
            if k > 1: errs.append(f"{t.qname}: duplicate check {n}")
            names[n] += 0
        for n, _ in auto_checks(t):
            if len(n) > 63: errs.append(f"name too long {n}")
        if t.guard_mutable:
            for c in t.guard_mutable:
                if c not in cn: errs.append(f"{t.qname}: guard col {c} missing")
    for n, k in names.items():
        if k > 1: errs.append(f"duplicate object name {n}")
        if len(n) > 63: errs.append(f"object name too long ({len(n)}): {n}")
    return errs

# ---------- DDL ---------------------------------------------------------------------
def comment_text(s): return s.replace('%', ' percent')  # the exact text stored by COMMENT ON (models.py repeats it)
def esc(s): return comment_text(s).replace("'", "''")

def col_ddl(c):
    if c.identity:
        return f"    {c.name} {c.typ} GENERATED ALWAYS AS IDENTITY NOT NULL"
    s = f"    {c.name} {c.typ}"
    if not c.null: s += " NOT NULL"
    if c.default is not None: s += f" DEFAULT {c.default}"
    return s

def table_ddl(t):
    lines = [col_ddl(c) for c in t.cols]
    lines.append(f"    CONSTRAINT pk_{t.name} PRIMARY KEY ({', '.join(t.pk)})")
    for n, cols in auto_uniques(t):
        lines.append(f"    CONSTRAINT {n} UNIQUE ({', '.join(cols)})")
    for n, e in auto_checks(t):
        lines.append(f"    CONSTRAINT {n} CHECK ({e})")
    selfs = []
    for fk in t.fks:
        if is_self(t, fk): selfs.append(fk); continue
        lines.append(f"    CONSTRAINT {fk.name} FOREIGN KEY ({', '.join(fk.cols)}) REFERENCES {fk.ref} ({', '.join(fk.ref_cols)}) ON DELETE {fk.on_delete}")
    out = [f"CREATE TABLE {t.qname} (", ",\n".join(lines), ");"]
    for fk in selfs:
        out.append(f"ALTER TABLE {t.qname} ADD CONSTRAINT {fk.name} FOREIGN KEY ({', '.join(fk.cols)}) REFERENCES {fk.ref} ({', '.join(fk.ref_cols)}) ON DELETE {fk.on_delete};")
    for i in t.idxs:
        u = "UNIQUE " if i.unique else ""
        w = f" WHERE {i.where}" if i.where else ""
        out.append(f"CREATE {u}INDEX {i.name} ON {t.qname} ({', '.join(i.cols)}){w};")
    out.append(f"COMMENT ON TABLE {t.qname} IS '{esc(t.purpose)}';")
    for c in t.cols:
        if c.desc: out.append(f"COMMENT ON COLUMN {t.qname}.{c.name} IS '{esc(c.desc)}';")
    return "\n".join(out)

def std_triggers(t):
    out = []
    if t.updated_at_trigger:
        out.append(f"CREATE TRIGGER trg_{t.name}_set_updated_at BEFORE UPDATE ON {t.qname} FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();")
    if t.guard_mutable:
        args = ", ".join(f"'{c}'" for c in t.guard_mutable)
        out.append(f"CREATE TRIGGER trg_{t.name}_guard_update BEFORE UPDATE ON {t.qname} FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update({args});")
    if t.append_only == "update":
        out.append(f"CREATE TRIGGER trg_{t.name}_forbid_update BEFORE UPDATE ON {t.qname} FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();")
    elif t.append_only == "delete":
        out.append(f"CREATE TRIGGER trg_{t.name}_forbid_delete BEFORE DELETE ON {t.qname} FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();")
    elif t.append_only == "update_delete":
        out.append(f"CREATE TRIGGER trg_{t.name}_forbid_update_delete BEFORE UPDATE OR DELETE ON {t.qname} FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update_delete();")
        out.append(f"CREATE TRIGGER trg_{t.name}_forbid_truncate BEFORE TRUNCATE ON {t.qname} FOR EACH STATEMENT EXECUTE FUNCTION public.brain_forbid_truncate();")
    return out

def topo(tables):
    done, order = set(), []
    pend = list(tables)
    names = {t.qname for t in tables}
    while pend:
        prog = False
        for t in list(pend):
            deps = {fk.ref for fk in t.fks if not is_self(t, fk) and fk.ref in names}
            if deps <= done:
                order.append(t); done.add(t.qname); pend.remove(t); prog = True
        if not prog: raise SystemExit("cycle: " + ", ".join(t.qname for t in pend))
    return order

FOUNDATION = """-- 0001_foundation: schemas and shared trigger functions (no tables)
-- Requires PostgreSQL >= 13 (gen_random_uuid() is built in; no extension needed for the MVP).
CREATE SCHEMA IF NOT EXISTS ingest;   -- event-processing state, canonical cache, sales_fact          (rebuildable / operational)
CREATE SCHEMA IF NOT EXISTS feat;     -- calendar + feature tables                                       (rebuildable)
CREATE SCHEMA IF NOT EXISTS intel;    -- models, forecasts, anomalies, risk, recommendations, rule config (history-bearing derived)
CREATE SCHEMA IF NOT EXISTS agent;    -- sessions, messages, tool calls, proposals, approvals, executions (audit-critical)
CREATE SCHEMA IF NOT EXISTS audit;    -- audit_log, llm_usage                                            (audit-critical)

CREATE OR REPLACE FUNCTION public.brain_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_update() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'UPDATE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (append-only)', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'DELETE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_update_delete() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = TG_OP || ' on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (immutable)', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_truncate() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'TRUNCATE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (immutable)', ERRCODE = 'insufficient_privilege';
END
$fn$;

-- Generic guard: only the columns listed in the trigger arguments may change on UPDATE.
CREATE OR REPLACE FUNCTION public.brain_guard_update() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF (to_jsonb(NEW) - TG_ARGV) IS DISTINCT FROM (to_jsonb(OLD) - TG_ARGV) THEN
    RAISE EXCEPTION USING MESSAGE = 'immutable column changed on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' (mutable: ' || array_to_string(TG_ARGV, ',') || ')', ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$fn$;
"""

def group_sql(title, tables):
    parts = [f"-- {title}"]
    ordered = topo(tables)
    for t in ordered:
        parts.append(f"\n-- ---- {t.qname} ----")
        parts.append(table_ddl(t))
        parts.extend(std_triggers(t))
    custom = [s for t in ordered for s in t.custom_triggers]
    return "\n".join(parts), custom

SEEDS = """-- Seed: default tenant rule sets (illustrative defaults to be tuned by the AI Lead; see OD-16).
INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) VALUES
 ('{T}','platform',1,'platform-config@1.0.0','{{"business_timezone":"Africa/Cairo","inventory_freshness_seconds":900,"supplier_freshness_seconds":86400,"product_freshness_seconds":86400,"reconcile_lookback_days":7,"feature_overlap_minutes":5,"sales_poll_interval_seconds":300,"poll_overlap_seconds":120,"poll_history_start_date":"2024-01-01","intel_window_minutes":60,"end_of_day_run_local_time":"02:00"}}'::jsonb,true,'migration'),
 ('{T}','anomaly',1,'anomaly-rules@1.0.0','{{"zscore_threshold":4,"severity_high_score":0.9,"severity_medium_score":0.7,"min_history_days":28,"isolation_forest_enabled":false}}'::jsonb,true,'migration'),
 ('{T}','risk',1,'risk-rules@1.0.0','{{"margin_days":2,"bound_policy":"median","upgrade_on_high_anomaly":true,"confidence_by_forecast":{{"low":0.4,"medium":0.7,"high":0.9}}}}'::jsonb,true,'migration'),
 ('{T}','recommendation',1,'recommendation-rules@1.0.0','{{"safety_stock_days":1,"recommendation_ttl_hours":24,"quantity_rounding":"ceil","suppress_if_open_po":false}}'::jsonb,true,'migration'),
 ('{T}','forecast',1,'forecast-rules@1.0.0','{{"min_history_weeks_per_sku":8,"backtest_weeks":4,"candidates":["seasonal_naive","lightgbm"],"must_beat_baseline_margin":0.05,"interval_method":"quantile","interval_coverage":0.8,"max_gap_days_ffill":3,"horizon_days":14,"degradation_wape_factor":1.5}}'::jsonb,true,'migration')
ON CONFLICT DO NOTHING;
""".format(T=DEFAULT_TENANT)

def worker_grant_sql(t):
    """brain_worker privileges (D-45). Column-level UPDATE when worker_update_cols is set."""
    mp = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}
    privs = [mp[c] for c in t.worker_grants if not (c == "U" and t.worker_update_cols)]
    out = [f"GRANT {', '.join(privs)} ON {t.qname} TO brain_worker;"] if privs else []
    if t.worker_update_cols:
        out.append(f"GRANT UPDATE ({', '.join(t.worker_update_cols)}) ON {t.qname} TO brain_worker;")
    return out

def role_block(roles, superuser_stmts):
    """B2 (D-50): role statements in a migration. A superuser migrator runs the original statements unchanged; any other
    migrator never creates or alters a role (that needs SUPERUSER/CREATEROLE) and only verifies what
    ddl/bootstrap_roles.sql created, with the same attributes the ALTER ROLE used to set."""
    names = ", ".join(f"'{r}'" for r in roles)
    return ["DO $do$ BEGIN",
            "  IF current_setting('is_superuser') = 'on' THEN",
            *["    " + x for x in superuser_stmts],
            "  ELSE",
            "    -- non-superuser migrator (B2): the roles come from ddl/bootstrap_roles.sql; verify them instead",
            f"    IF EXISTS (SELECT FROM unnest(ARRAY[{names}]) AS r(n) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r.n)) THEN",
            "      RAISE EXCEPTION 'runtime roles missing: run ddl/bootstrap_roles.sql once per cluster as a role administrator';",
            "    END IF;",
            f"    IF EXISTS (SELECT FROM pg_roles WHERE rolname IN ({names})",
            "               AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls OR rolcanlogin)) THEN",
            "      RAISE EXCEPTION 'runtime roles must be NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';",
            "    END IF;",
            "  END IF;",
            "END $do$;"]

def bootstrap_roles_sql():
    """Run ONCE per PostgreSQL cluster, before the first migration, by a role administrator (a login with CREATEROLE;
    not the migration owner, not a superuser). New roles are NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    NOBYPASSRLS by default, so no ALTER ROLE is needed."""
    L = ["-- bootstrap_roles.sql (B2, D-50): create the Brain runtime roles. Run ONCE per cluster, before `alembic upgrade`,",
         "-- as a role administrator with CREATEROLE (not the migration owner). Safe to re-run: existing roles are skipped.",
         "-- Migrations never create or alter roles when the migrator is not a superuser; they only verify these.",
         "DO $do$ BEGIN"]
    L += [f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{r}') THEN CREATE ROLE {r} NOLOGIN; END IF;" for r in RUNTIME_ROLES]
    L += ["END $do$;",
          "-- Login users are created per environment and granted ONE of these roles (never brain_app and brain_worker together)."]
    return "\n".join(L) + "\n"

def handover_ownership_sql():
    """For a database built BEFORE D-50 by a superuser migrator: hand the Brain objects to the migration owner once, so
    later upgrades (0008 and on) run without a superuser. Not needed for databases built on the bootstrap path."""
    S = "('ingest','feat','intel','agent','audit')"
    return "\n".join([
        "-- handover_ownership.sql (B2, D-50): ONE-TIME, run by a DBA (superuser) on a database built before D-50 by a",
        "-- superuser migrator. Moves the Brain schemas, tables, views, functions and alembic_version to the migration owner,",
        "-- so every later `alembic upgrade` runs as that non-superuser owner. Runtime grants and data are unchanged.",
        "-- Usage: psql -d <db> -c \"SET bb.migration_owner = '<owner login>'\" -f handover_ownership.sql  (one session)",
        "DO $do$ DECLARE r record; owner_role text := current_setting('bb.migration_owner'); BEGIN",
        "  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = owner_role AND NOT rolsuper) THEN",
        "    RAISE EXCEPTION 'bb.migration_owner must name an existing non-superuser login';",
        "  END IF;",
        "  -- 0007 and later revisions create public.brain_* functions; the owner needs CREATE on public (not ownership).",
        "  EXECUTE 'GRANT USAGE, CREATE ON SCHEMA public TO ' || quote_ident(owner_role);",
        f"  FOR r IN SELECT nspname FROM pg_namespace WHERE nspname IN {S} LOOP",
        "    EXECUTE 'ALTER SCHEMA ' || quote_ident(r.nspname) || ' OWNER TO ' || quote_ident(owner_role);",
        "  END LOOP;",
        "  FOR r IN SELECT n.nspname, c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace",
        f"           WHERE (n.nspname IN {S} AND c.relkind IN ('r', 'p', 'v'))",
        "              OR (n.nspname = 'public' AND c.relname = 'alembic_version') LOOP",
        "    EXECUTE 'ALTER ' || CASE r.relkind WHEN 'v' THEN 'VIEW ' ELSE 'TABLE ' END || quote_ident(r.nspname) || '.'",
        "            || quote_ident(r.relname) || ' OWNER TO ' || quote_ident(owner_role);",
        "  END LOOP;",
        "  FOR r IN SELECT p.oid::regprocedure AS fn FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace",
        f"           WHERE n.nspname IN {S} OR (n.nspname = 'public' AND left(p.proname, 6) = 'brain_') LOOP",
        "    EXECUTE 'ALTER FUNCTION ' || r.fn::text || ' OWNER TO ' || quote_ident(owner_role);",
        "  END LOOP;",
        "END $do$;"]) + "\n"

def grants_sql(tables):
    L = ["-- 0005: roles, grants and seed data",
         "-- D-45: brain_worker (brain-worker jobs) is separate from brain_app (brain-api). It cannot record or change a decision",
         "-- (no INSERT on agent.action_approval) and may only expire proposals or complete executions (guard_proposal_transition).",
         "-- D-50 (B2): a superuser migrator runs the original role statements; any other migrator only verifies the roles.",
         *role_block(["brain_app", "brain_retention", "brain_readonly", "brain_worker"], [
             "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_app')       THEN CREATE ROLE brain_app NOLOGIN; END IF;",
             "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_retention') THEN CREATE ROLE brain_retention NOLOGIN; END IF;",
             "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_readonly')  THEN CREATE ROLE brain_readonly NOLOGIN; END IF;",
             "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_worker')    THEN CREATE ROLE brain_worker NOLOGIN; END IF;",
             "ALTER ROLE brain_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"]),
         "-- Login users are created per environment by DevOps and granted ONE of these roles (never brain_app and brain_worker together).",
         "GRANT USAGE ON SCHEMA ingest, feat, intel, agent, audit TO brain_app, brain_worker, brain_retention, brain_readonly;"]
    mp = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}
    for t in tables:
        privs = ", ".join(mp[c] for c in t.grants)
        L.append(f"GRANT {privs} ON {t.qname} TO brain_app;")
        L.extend(worker_grant_sql(t))
        L.append(f"GRANT SELECT ON {t.qname} TO brain_readonly;")
        if t.purge:
            L.append(f"GRANT SELECT, DELETE ON {t.qname} TO brain_retention;")
    L.append("GRANT SELECT ON intel.v_insight_current, intel.v_alert_open, agent.v_agent_action TO brain_app, brain_readonly;")
    return "\n".join(L) + "\n\n" + SEEDS


VIEWS_INTEL = """-- ---- projections (views, no storage): Insight and Alert are API projections, not tables ----
CREATE VIEW intel.v_insight_current AS
SELECT r.tenant_id, r.id AS insight_id, r.product_id, r.supplier_id, r.risk_type, r.severity, r.confidence,
       r.days_of_cover, r.lead_time_days, r.demand_over_lead_time, r.demand_over_lead_time_upper,
       r.input_available_quantity, r.inventory_as_of, r.rule_version, r.calculated_at, r.last_confirmed_at,
       r.forecast_id, r.anomaly_event_id,
       rec.id AS recommendation_id, rec.recommendation_type, rec.payload AS recommendation_payload,
       rec.expires_at AS recommendation_expires_at
  FROM intel.risk_assessment r
  LEFT JOIN intel.recommendation rec
    ON rec.tenant_id = r.tenant_id AND rec.risk_assessment_id = r.id AND rec.status = 'active'
 WHERE r.superseded_at IS NULL;
COMMENT ON VIEW intel.v_insight_current IS 'Insight projection: current risk assessment plus its active recommendation. insight_id = risk_assessment.id (OD-06).';

CREATE VIEW intel.v_alert_open AS
SELECT a.tenant_id, 'anomaly'::text AS alert_kind, a.id AS source_id, a.product_id, a.severity, a.first_detected_at AS raised_at
  FROM intel.anomaly_event a WHERE a.status = 'open'
UNION ALL
SELECT r.tenant_id, 'risk'::text, r.id, r.product_id, r.severity, r.calculated_at
  FROM intel.risk_assessment r WHERE r.superseded_at IS NULL AND r.severity IN ('medium','high');
COMMENT ON VIEW intel.v_alert_open IS 'Alert projection: open anomaly signals plus current medium/high risks (AlertBadge).';
"""

VIEWS_AGENT = """-- ---- projection: the source-shaped AgentAction (tool_name, arguments, status, requires_approval, approved_by, result) ----
CREATE VIEW agent.v_agent_action AS
SELECT p.tenant_id, p.id AS proposal_id, p.session_id, p.tool_name, p.arguments, p.requires_approval, p.status,
       a.decided_by_actor_id AS approved_by, a.decided_at AS approved_at,
       e.status AS execution_status, e.result, e.external_ref_type, e.external_ref_id, p.created_at, p.expires_at
  FROM agent.action_proposal p
  LEFT JOIN LATERAL (SELECT x.* FROM agent.action_approval x
                      WHERE x.tenant_id = p.tenant_id AND x.proposal_id = p.id AND x.decision = 'approved'
                      ORDER BY x.approval_round DESC LIMIT 1) a ON true
  LEFT JOIN LATERAL (SELECT y.* FROM agent.action_execution y
                      WHERE y.tenant_id = p.tenant_id AND y.proposal_id = p.id
                      ORDER BY y.attempt_no DESC LIMIT 1) e ON true;
COMMENT ON VIEW agent.v_agent_action IS 'Source-shaped AgentAction projection over proposal + latest approval + latest execution.';
"""

TENANT_CONTEXT_FN = """-- N-02: the tenant of the current transaction. Set ONLY with set_config('app.tenant_id', <tenant uuid>, true)
-- (transaction-local, so commit/rollback clears it and a pooled connection never carries it to the next unit of work).
-- Not set (or set to '') -> NULL -> every tenant_isolation policy matches nothing: reads are empty, writes are refused.
-- A value that is not a UUID raises an error instead of matching anything.
CREATE OR REPLACE FUNCTION public.brain_current_tenant() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS $fn$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$fn$;
COMMENT ON FUNCTION public.brain_current_tenant() IS 'Tenant of the current transaction from the transaction-local setting app.tenant_id (N-02). NULL when unset.';
"""

VIEWS = ["intel.v_insight_current", "intel.v_alert_open", "agent.v_agent_action"]

def rls_table_sql(t):
    """ENABLE + FORCE RLS and the tenant_isolation policy for one table (N-02)."""
    return [f"ALTER TABLE {t.qname} ENABLE ROW LEVEL SECURITY;",
            f"ALTER TABLE {t.qname} FORCE ROW LEVEL SECURITY;",
            f"CREATE POLICY pol_tenant_isolation ON {t.qname} AS PERMISSIVE FOR ALL TO PUBLIC "
            f"USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());"]

def provisioner_grant_sql(t):
    mp = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}
    return [f"GRANT {', '.join(mp[c] for c in t.provisioner_grants)} ON {t.qname} TO brain_provisioner;"] if t.provisioner_grants else []

def tenancy_sql():
    """0007: tenant registry (N-01) and row-level security on every tenant table (N-02)."""
    L = ["-- 0007_tenancy_rls: tenant registry (N-01) and PostgreSQL row-level security (N-02)",
         "-- Run as the migration owner. RLS is a SECOND wall: brain-api and brain-worker still filter every statement by tenant (D-34).",
         *role_block(["brain_provisioner"], [
             "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_provisioner') THEN CREATE ROLE brain_provisioner NOLOGIN; END IF;"]),
         "-- brain_provisioner: the provisioning command (N-01). It writes the tenant registry and may seed a tenant's rule sets;",
         "-- it has no access to sales, models, proposals or audit data. Like every runtime role it is subject to RLS.",
         "GRANT USAGE ON SCHEMA ingest, intel TO brain_provisioner;",
         "", TENANT_CONTEXT_FN]
    body, cust = group_sql("tenant registry (N-01)", TABLES_TENANCY)
    L += [body, "", *cust, ""]
    for t in TABLES_TENANCY:
        mp = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}
        L.append(f"GRANT {', '.join(mp[c] for c in t.grants)} ON {t.qname} TO brain_app;")
        L.extend(worker_grant_sql(t))
        L.extend(provisioner_grant_sql(t))
        L.append(f"GRANT SELECT ON {t.qname} TO brain_readonly;")
    for t in ALL_BASE:
        L.extend(provisioner_grant_sql(t))
    L += ["", "-- ---- row-level security on every tenant table (N-02) ----",
          "-- FORCE applies the policies to the table owner too; superusers and BYPASSRLS roles are the only exceptions,",
          "-- and no runtime role or its login may have either attribute (checked by tenancy_rls_checks.py)."]
    for t in ALL:
        if not t.rls: continue
        stmts = rls_table_sql(t)
        if t.scope == "SHOULD":   # 0006 is optional: apply only when the table exists
            L.append(f"DO $do$ BEGIN IF to_regclass('{t.qname}') IS NOT NULL THEN")
            L.extend("  EXECUTE " + "'" + x.rstrip(";").replace("'", "''") + "';" for x in stmts)
            L.append("END IF; END $do$;")
        else:
            L.extend(stmts)
    L += ["-- brain_worker must discover the tenants before it has a tenant context: it may read every registry row",
          "-- (ids, status, credential references; no business data). Permissive policies are OR-ed.",
          "CREATE POLICY pol_worker_list_tenants ON ingest.tenant_registry AS PERMISSIVE FOR SELECT TO brain_worker USING (true);",
          "", "-- Views must run with the caller's rights, otherwise they would read as the owner and skip RLS.",
          *[f"ALTER VIEW {v} SET (security_invoker = true);" for v in VIEWS]]
    return "\n".join(L) + "\n"

def tenancy_down_sql():
    """Reverse of 0007 (executed by the Alembic downgrade). Roles are cluster-level and are left in place, as in 0005."""
    L = ["-- 0007_tenancy_rls downgrade: remove RLS, the registry and brain_provisioner's grants"]
    L += [f"ALTER VIEW {v} RESET (security_invoker);" for v in VIEWS]
    L.append("DROP POLICY IF EXISTS pol_worker_list_tenants ON ingest.tenant_registry;")
    for t in ALL_BASE:
        if not t.rls: continue
        if t.scope == "SHOULD":
            L.append(f"DO $do$ BEGIN IF to_regclass('{t.qname}') IS NOT NULL THEN EXECUTE 'DROP POLICY IF EXISTS pol_tenant_isolation ON {t.qname}'; "
                     f"EXECUTE 'ALTER TABLE {t.qname} NO FORCE ROW LEVEL SECURITY'; EXECUTE 'ALTER TABLE {t.qname} DISABLE ROW LEVEL SECURITY'; END IF; END $do$;")
        else:
            L += [f"DROP POLICY IF EXISTS pol_tenant_isolation ON {t.qname};",
                  f"ALTER TABLE {t.qname} NO FORCE ROW LEVEL SECURITY;", f"ALTER TABLE {t.qname} DISABLE ROW LEVEL SECURITY;"]
    for t in ALL_BASE:
        if t.provisioner_grants:
            L.append(f"REVOKE ALL ON {t.qname} FROM brain_provisioner;")
    L += [f"DROP TABLE IF EXISTS {t.qname};" for t in TABLES_TENANCY]
    L += ["DROP FUNCTION IF EXISTS ingest.guard_tenant_registry();", "DROP FUNCTION IF EXISTS public.brain_current_tenant();",
          "REVOKE USAGE ON SCHEMA ingest, intel FROM brain_provisioner;"]
    return "\n".join(L) + "\n"

MP = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}

RULE_CONFIG_AUDIT_SQL = """-- Every rule-set change is attributed and audited in the same transaction (D-51). The function runs with the caller's
-- rights (no SECURITY DEFINER): the caller needs INSERT on audit.audit_log, and RLS keeps the row in the caller's tenant.
CREATE OR REPLACE FUNCTION intel.audit_rule_config_change() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  actor text := NULLIF(current_setting('app.actor_id', true), '');
  trace text := NULLIF(current_setting('app.trace_id', true), '');
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.is_active IS NOT DISTINCT FROM OLD.is_active THEN
    RETURN NULL;
  END IF;
  IF actor IS NULL THEN
    RAISE EXCEPTION USING MESSAGE = 'rule_config: set app.actor_id (the operator) in this transaction before changing a rule set (D-51)',
                          ERRCODE = 'check_violation';
  END IF;
  INSERT INTO audit.audit_log (tenant_id, event_type, outcome, actor_type, actor_id, subject_type, subject_id, details, trace_id)
  VALUES (NEW.tenant_id,
          CASE WHEN TG_OP = 'INSERT' THEN 'rule_config.version_added'
               WHEN NEW.is_active THEN 'rule_config.activated' ELSE 'rule_config.deactivated' END,
          'success', 'user', actor, 'rule_config', NEW.id,
          jsonb_build_object('rule_set', NEW.rule_set, 'version', NEW.version, 'version_label', NEW.version_label,
                             'is_active', NEW.is_active),
          coalesce(trace, replace(gen_random_uuid()::text, '-', '')));
  RETURN NULL;
END
$fn$;
CREATE TRIGGER trg_rule_config_audit AFTER INSERT OR UPDATE OF is_active ON intel.rule_config
  FOR EACH ROW EXECUTE FUNCTION intel.audit_rule_config_change();

-- An active tenant keeps exactly one active version of every rule set: a switch must deactivate and activate in ONE
-- transaction (checked at commit, so the order inside the transaction does not matter). Mirrors the activation gate (D-46).
CREATE OR REPLACE FUNCTION intel.check_rule_set_still_active() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF NOT NEW.is_active
     AND EXISTS (SELECT 1 FROM ingest.tenant_registry r WHERE r.tenant_id = NEW.tenant_id AND r.status = 'active')
     AND NOT EXISTS (SELECT 1 FROM intel.rule_config c WHERE c.tenant_id = NEW.tenant_id AND c.rule_set = NEW.rule_set AND c.is_active) THEN
    RAISE EXCEPTION USING MESSAGE = 'rule_config: active tenant ' || NEW.tenant_id || ' would have no active ' || NEW.rule_set
                                    || ' rule set; activate the new version in the same transaction (D-51)',
                          ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END
$fn$;
CREATE CONSTRAINT TRIGGER trg_rule_config_keep_active AFTER UPDATE OF is_active ON intel.rule_config
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION intel.check_rule_set_still_active();
"""

def _frozen_app(t):
    return set(t.grants)

def least_privilege_sql():
    """0008 (B1, B7; D-51): additive REVOKE/GRANT from the frozen 0005-0007 grants to spec_privileges, plus the audited
    rule-set change path. 0005 and 0007 are never rewritten."""
    L = ["-- 0008_least_privilege (B1, B7; D-51): brain_app loses every pipeline write; brain_worker gets the calendar;",
         "-- brain_provisioner may switch rule-set versions (is_active only), audited by trigger. Additive: 0005-0007 unchanged."]
    for t in ALL:
        if t.scope == "FUTURE": continue
        target = set(PRIV.APP_TARGET[t.qname])
        drop = [MP[c] for c in "IUD" if c in _frozen_app(t) and c not in target]
        cols = PRIV.APP_UPDATE_COLS.get(t.qname)
        stmts = []
        if drop:
            stmts.append(f"REVOKE {', '.join(drop)} ON {t.qname} FROM brain_app;")
        if cols:
            stmts.append(f"GRANT UPDATE ({', '.join(cols)}) ON {t.qname} TO brain_app;")
        add = PRIV.WORKER_ADD.get(t.qname)
        if add:
            stmts.append(f"GRANT {', '.join(MP[c] for c in add)} ON {t.qname} TO brain_worker;")
        if t.scope == "SHOULD" and stmts:
            L.append(f"DO $do$ BEGIN IF to_regclass('{t.qname}') IS NOT NULL THEN")
            L.extend("  EXECUTE '" + x.rstrip(";").replace("'", "''") + "';" for x in stmts)
            L.append("END IF; END $do$;")
        else:
            L.extend(stmts)
    L.append(f"GRANT USAGE ON SCHEMA {', '.join(PRIV.PROVISIONER_SCHEMAS)} TO brain_provisioner;")
    for q, add in PRIV.PROVISIONER_ADD.items():
        L.append(f"GRANT {', '.join(MP[c] for c in add)} ON {q} TO brain_provisioner;")
    for q, cols in PRIV.PROVISIONER_UPDATE_COLS.items():
        L.append(f"GRANT UPDATE ({', '.join(cols)}) ON {q} TO brain_provisioner;")
    L += ["", RULE_CONFIG_AUDIT_SQL]
    return "\n".join(L)

def least_privilege_down_sql():
    """Exact inverse of 0008: back to the 0005-0007 grants."""
    L = ["-- 0008_least_privilege downgrade: restore the 0005-0007 grants and drop the rule-set audit triggers",
         "DROP TRIGGER IF EXISTS trg_rule_config_keep_active ON intel.rule_config;",
         "DROP TRIGGER IF EXISTS trg_rule_config_audit ON intel.rule_config;",
         "DROP FUNCTION IF EXISTS intel.check_rule_set_still_active();",
         "DROP FUNCTION IF EXISTS intel.audit_rule_config_change();"]
    for q, cols in PRIV.PROVISIONER_UPDATE_COLS.items():
        L.append(f"REVOKE UPDATE ({', '.join(cols)}) ON {q} FROM brain_provisioner;")
    for q, add in PRIV.PROVISIONER_ADD.items():
        L.append(f"REVOKE {', '.join(MP[c] for c in add)} ON {q} FROM brain_provisioner;")
    L.append(f"REVOKE USAGE ON SCHEMA {', '.join(PRIV.PROVISIONER_SCHEMAS)} FROM brain_provisioner;")
    for t in ALL:
        if t.scope == "FUTURE": continue
        target = set(PRIV.APP_TARGET[t.qname])
        back = [MP[c] for c in "IUD" if c in _frozen_app(t) and c not in target]
        cols = PRIV.APP_UPDATE_COLS.get(t.qname)
        stmts = []
        if cols:
            stmts.append(f"REVOKE UPDATE ({', '.join(cols)}) ON {t.qname} FROM brain_app;")
        if back:
            stmts.append(f"GRANT {', '.join(back)} ON {t.qname} TO brain_app;")
        add = PRIV.WORKER_ADD.get(t.qname)
        if add:
            stmts.append(f"REVOKE {', '.join(MP[c] for c in add)} ON {t.qname} FROM brain_worker;")
        if t.scope == "SHOULD" and stmts:
            L.append(f"DO $do$ BEGIN IF to_regclass('{t.qname}') IS NOT NULL THEN")
            L.extend("  EXECUTE '" + x.rstrip(";").replace("'", "''") + "';" for x in stmts)
            L.append("END IF; END $do$;")
        else:
            L.extend(stmts)
    return "\n".join(L) + "\n"

def build_sql():
    sql = {}
    sql["0001_foundation.sql"] = FOUNDATION
    ing = [t for t in TABLES_INGEST]
    body, cust = group_sql("0002_ingest_feat: ingest + feat schemas", ing)
    sql["0002_ingest_feat.sql"] = body + ("\n\n" + "\n".join(cust) if cust else "") + "\n"
    intel = [t for t in TABLES_INTEL if t.scope == "MVP"]
    body, cust = group_sql("0003_intel: intel schema (MVP tables)", intel)
    sql["0003_intel.sql"] = body + ("\n\n" + "\n".join(cust) if cust else "") + "\n\n" + VIEWS_INTEL
    aa = TABLES_AGENT
    body, cust = group_sql("0004_audit_agent: audit + agent schemas", aa)
    sql["0004_audit_agent.sql"] = body + "\n\n-- ---- custom guard triggers (created after all agent tables exist) ----\n" + "\n".join(cust) + "\n\n" + VIEWS_AGENT
    mvp_tables = [t for t in ALL_BASE if t.scope == "MVP"]
    sql["0005_roles_grants_seed.sql"] = grants_sql(mvp_tables)
    br = [t for t in TABLES_INTEL if t.scope == "SHOULD"]
    body, cust = group_sql("0006_optional_briefing: SHOULD-have table, safe to skip", br)
    gr = "\n".join(f"GRANT {', '.join(dict(S='SELECT',I='INSERT',U='UPDATE',D='DELETE')[c] for c in t.grants)} ON {t.qname} TO brain_app;\n" + "".join(x + "\n" for x in worker_grant_sql(t)) + f"GRANT SELECT ON {t.qname} TO brain_readonly;\nGRANT SELECT, DELETE ON {t.qname} TO brain_retention;" for t in br)
    sql["0006_optional_briefing.sql"] = body + "\n\n" + gr + "\n"
    sql["0007_tenancy_rls.sql"] = tenancy_sql()
    sql["0008_least_privilege.sql"] = least_privilege_sql()
    fut = ["-- OPTIONAL / FUTURE ONLY: RAG. Not part of the MVP. Requires the pgvector extension.",
           "CREATE EXTENSION IF NOT EXISTS vector;", "CREATE SCHEMA IF NOT EXISTS rag;"]
    for t in TABLES_FUTURE:
        fut.append(table_ddl(t)); fut.extend(t.custom_triggers)
        fut.append(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t.qname} TO brain_app;\nGRANT USAGE ON SCHEMA rag TO brain_app, brain_readonly;")
    sql["optional_future_rag.sql"] = "\n".join(fut) + "\n"
    full = "\n".join([
        "-- brain_db: complete MVP DDL (concatenation of migrations 0001-0005, optional 0006, 0007 tenancy/RLS, 0008 least privilege).",
        "-- Generated from the same schema definition as models.py. Execute as the migration owner role.",
        "-- Not executed by the author; review and test in a scratch database first.", ""] +
        [f"\n-- ==================== {k} ====================\n{v}" for k, v in sql.items() if k.startswith("000") and not k.endswith(".down.sql")])
    sql["brain_db_mvp.sql"] = full
    sql["0007_tenancy_rls.down.sql"] = tenancy_down_sql()
    sql["0008_least_privilege.down.sql"] = least_privilege_down_sql()
    sql["bootstrap_roles.sql"] = bootstrap_roles_sql()
    sql["handover_ownership.sql"] = handover_ownership_sql()
    for k, v in sql.items():
        assert '%' not in v, f'percent sign in {k}: ' + v[v.index('%')-60:v.index('%')+20]
    return sql

if __name__ == "__main__":
    e = validate()
    print("validation errors:", len(e))
    for x in e: print(" -", x)
