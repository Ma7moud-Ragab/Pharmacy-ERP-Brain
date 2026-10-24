-- 0007_tenancy_rls: tenant registry (N-01) and PostgreSQL row-level security (N-02)
-- Run as the migration owner. RLS is a SECOND wall: brain-api and brain-worker still filter every statement by tenant (D-34).
DO $do$ BEGIN
  IF current_setting('is_superuser') = 'on' THEN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_provisioner') THEN CREATE ROLE brain_provisioner NOLOGIN; END IF;
  ELSE
    -- non-superuser migrator (B2): the roles come from ddl/bootstrap_roles.sql; verify them instead
    IF EXISTS (SELECT FROM unnest(ARRAY['brain_provisioner']) AS r(n) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r.n)) THEN
      RAISE EXCEPTION 'runtime roles missing: run ddl/bootstrap_roles.sql once per cluster as a role administrator';
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname IN ('brain_provisioner')
               AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls OR rolcanlogin)) THEN
      RAISE EXCEPTION 'runtime roles must be NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
    END IF;
  END IF;
END $do$;
-- brain_provisioner: the provisioning command (N-01). It writes the tenant registry and may seed a tenant's rule sets;
-- it has no access to sales, models, proposals or audit data. Like every runtime role it is subject to RLS.
GRANT USAGE ON SCHEMA ingest, intel TO brain_provisioner;

-- N-02: the tenant of the current transaction. Set ONLY with set_config('app.tenant_id', <tenant uuid>, true)
-- (transaction-local, so commit/rollback clears it and a pooled connection never carries it to the next unit of work).
-- Not set (or set to '') -> NULL -> every tenant_isolation policy matches nothing: reads are empty, writes are refused.
-- A value that is not a UUID raises an error instead of matching anything.
CREATE OR REPLACE FUNCTION public.brain_current_tenant() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS $fn$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$fn$;
COMMENT ON FUNCTION public.brain_current_tenant() IS 'Tenant of the current transaction from the transaction-local setting app.tenant_id (N-02). NULL when unset.';

-- tenant registry (N-01)

-- ---- ingest.tenant_registry ----
CREATE TABLE ingest.tenant_registry (
    tenant_id UUID NOT NULL,
    display_label TEXT,
    status TEXT NOT NULL DEFAULT 'provisioning',
    status_reason TEXT,
    credential_ref TEXT,
    credential_sha256 CHAR(64),
    credential_version INTEGER NOT NULL DEFAULT 0,
    credential_validated_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    suspended_at TIMESTAMPTZ,
    provisioned_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_tenant_registry PRIMARY KEY (tenant_id),
    CONSTRAINT ck_tenant_registry__status CHECK (status IN ('provisioning','active','suspended')),
    CONSTRAINT ck_tenant_registry__label_len CHECK (display_label IS NULL OR char_length(display_label) BETWEEN 1 AND 100),
    CONSTRAINT ck_tenant_registry__reason_len CHECK (status_reason IS NULL OR char_length(status_reason) <= 200),
    CONSTRAINT ck_tenant_registry__credential_ref_format CHECK (credential_ref IS NULL OR credential_ref ~ '^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_.-]*){0,4}$' AND char_length(credential_ref) <= 200),
    CONSTRAINT ck_tenant_registry__credential_version CHECK (credential_version >= 0),
    CONSTRAINT ck_tenant_registry__validated_needs_credential CHECK (credential_validated_at IS NULL OR (credential_ref IS NOT NULL AND credential_sha256 IS NOT NULL)),
    CONSTRAINT ck_tenant_registry__active_requirements CHECK (status <> 'active' OR (credential_validated_at IS NOT NULL AND activated_at IS NOT NULL)),
    CONSTRAINT ck_tenant_registry__suspended_requirements CHECK (status <> 'suspended' OR (suspended_at IS NOT NULL AND status_reason IS NOT NULL)),
    CONSTRAINT ck_tenant_registry__credential_sha256_format CHECK (credential_sha256 IS NULL OR credential_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_tenant_registry__status ON ingest.tenant_registry (status);
COMMENT ON TABLE ingest.tenant_registry IS 'Stable registry of the tenants (ERP organizations) this Brain serves, with a REFERENCE to each tenant''s Canonical API credential (never the secret). brain-worker runs jobs only for `active` tenants; brain-api refuses tokens of tenants that are not `active` (N-01). A tenant is created as `provisioning` and becomes `active` only when its credential was validated and its rule sets exist.';
COMMENT ON COLUMN ingest.tenant_registry.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity). Primary key: one row per tenant, never reused or renamed.';
COMMENT ON COLUMN ingest.tenant_registry.display_label IS 'Short non-sensitive label for operators (e.g. ''Demo pharmacy A''). Never used for authorization.';
COMMENT ON COLUMN ingest.tenant_registry.status IS 'provisioning (created, not yet usable) | active (jobs run, API serves) | suspended (jobs skipped, API refuses; data kept).';
COMMENT ON COLUMN ingest.tenant_registry.status_reason IS 'Why the tenant is suspended (operator text, <= 200 chars, no secrets).';
COMMENT ON COLUMN ingest.tenant_registry.credential_ref IS 'Name of this tenant''s Canonical API credential in the secret store, e.g. ''canonical/<tenant_id>'' (a file under CANONICAL_CREDENTIALS_DIR). A reference only: the secret itself never enters the database, source control or logs.';
COMMENT ON COLUMN ingest.tenant_registry.credential_sha256 IS 'SHA-256 of the credential value that was validated. brain-worker refuses to call Canonical when the loaded secret does not match it (stale or swapped secret). Not reversible to the secret.';
COMMENT ON COLUMN ingest.tenant_registry.credential_version IS 'Incremented by trigger on every credential change (rotation counter).';
COMMENT ON COLUMN ingest.tenant_registry.credential_validated_at IS 'Server time of the last successful validation: a Canonical read made with this credential returned this tenant_id. Cleared by trigger when the credential changes without a new validation.';
COMMENT ON COLUMN ingest.tenant_registry.activated_at IS 'Server time of the last move to active (set by trigger).';
COMMENT ON COLUMN ingest.tenant_registry.suspended_at IS 'Server time of the last move to suspended (set by trigger).';
COMMENT ON COLUMN ingest.tenant_registry.provisioned_by IS 'Operator id that ran the provisioning command (audit; no secrets).';
COMMENT ON COLUMN ingest.tenant_registry.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.tenant_registry.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_tenant_registry_forbid_delete BEFORE DELETE ON ingest.tenant_registry FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();

CREATE OR REPLACE FUNCTION ingest.guard_tenant_registry() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  missing text;
BEGIN
  -- N-01: a tenant is never activated silently. It is created as 'provisioning' and becomes 'active' only through an
  -- explicit UPDATE that passes the checks below. All times are database server time (client values are ignored).
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'provisioning' THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: a tenant must be created in status provisioning (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.created_at := now(); NEW.updated_at := now();
    NEW.activated_at := NULL; NEW.suspended_at := NULL;
    IF NEW.credential_validated_at IS NOT NULL THEN NEW.credential_validated_at := now(); END IF;
    RETURN NEW;
  END IF;

  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION USING MESSAGE = 'tenant_registry: tenant_id is immutable', ERRCODE = 'check_violation';
  END IF;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := now();

  -- A new or rotated credential counts as validated only when the same UPDATE records a validation.
  IF (NEW.credential_ref IS DISTINCT FROM OLD.credential_ref OR NEW.credential_sha256 IS DISTINCT FROM OLD.credential_sha256)
     AND NEW.credential_validated_at IS NOT DISTINCT FROM OLD.credential_validated_at THEN
    IF NEW.status = 'active' THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: credential of an active tenant changed without a new validation (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.credential_validated_at := NULL;
  ELSIF NEW.credential_validated_at IS DISTINCT FROM OLD.credential_validated_at AND NEW.credential_validated_at IS NOT NULL THEN
    NEW.credential_validated_at := now();
  END IF;
  IF NEW.credential_ref IS DISTINCT FROM OLD.credential_ref OR NEW.credential_sha256 IS DISTINCT FROM OLD.credential_sha256 THEN
    NEW.credential_version := OLD.credential_version + 1;
  ELSE
    NEW.credential_version := OLD.credential_version;
  END IF;

  IF NEW.status = 'active' AND OLD.status <> 'active' THEN
    IF NEW.credential_validated_at IS NULL THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: cannot activate tenant ' || NEW.tenant_id || ': its Canonical credential is not validated (N-01)', ERRCODE = 'check_violation';
    END IF;
    SELECT string_agg(s, ', ' ORDER BY s) INTO missing
      FROM unnest(ARRAY['platform','anomaly','risk','recommendation','forecast']) AS s
     WHERE NOT EXISTS (SELECT 1 FROM intel.rule_config r
                        WHERE r.tenant_id = NEW.tenant_id AND r.rule_set = s AND r.is_active);
    IF missing IS NOT NULL THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: cannot activate tenant ' || NEW.tenant_id || ': no active rule_config for ' || missing || ' (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.activated_at := now();
    NEW.suspended_at := NULL;
  ELSIF NEW.status = 'suspended' AND OLD.status <> 'suspended' THEN
    NEW.suspended_at := now();
    NEW.activated_at := OLD.activated_at;
  ELSE
    NEW.activated_at := OLD.activated_at;
    NEW.suspended_at := OLD.suspended_at;
  END IF;
  RETURN NEW;
END
$fn$;
CREATE TRIGGER trg_tenant_registry_guard BEFORE INSERT OR UPDATE ON ingest.tenant_registry FOR EACH ROW EXECUTE FUNCTION ingest.guard_tenant_registry();

GRANT SELECT ON ingest.tenant_registry TO brain_app;
GRANT SELECT ON ingest.tenant_registry TO brain_worker;
GRANT SELECT, INSERT, UPDATE ON ingest.tenant_registry TO brain_provisioner;
GRANT SELECT ON ingest.tenant_registry TO brain_readonly;
GRANT SELECT, INSERT ON intel.rule_config TO brain_provisioner;

-- ---- row-level security on every tenant table (N-02) ----
-- FORCE applies the policies to the table owner too; superusers and BYPASSRLS roles are the only exceptions,
-- and no runtime role or its login may have either attribute (checked by tenancy_rls_checks.py).
ALTER TABLE ingest.sync_checkpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.sync_checkpoint FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.sync_checkpoint AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE ingest.ingest_failure ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.ingest_failure FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.ingest_failure AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE ingest.canonical_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.canonical_cache FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.canonical_cache AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE ingest.sales_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.sales_fact FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.sales_fact AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE ingest.sales_day_coverage ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.sales_day_coverage FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.sales_day_coverage AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE feat.calendar_day ENABLE ROW LEVEL SECURITY;
ALTER TABLE feat.calendar_day FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON feat.calendar_day AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE feat.feature_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE feat.feature_daily FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON feat.feature_daily AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.rule_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.rule_config FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.rule_config AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.training_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.training_run FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.training_run AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.model_registry FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.model_registry AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.model_evaluation ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.model_evaluation FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.model_evaluation AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.forecast ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.forecast FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.forecast AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.forecast_point ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.forecast_point FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.forecast_point AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.anomaly_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.anomaly_event FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.anomaly_event AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.risk_assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.risk_assessment FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.risk_assessment AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE intel.recommendation ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.recommendation FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON intel.recommendation AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
DO $do$ BEGIN IF to_regclass('intel.briefing') IS NOT NULL THEN
  EXECUTE 'ALTER TABLE intel.briefing ENABLE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE intel.briefing FORCE ROW LEVEL SECURITY';
  EXECUTE 'CREATE POLICY pol_tenant_isolation ON intel.briefing AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant())';
END IF; END $do$;
ALTER TABLE audit.llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.llm_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON audit.llm_usage AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE audit.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON audit.audit_log AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.agent_session ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_session FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.agent_session AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.agent_message ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_message FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.agent_message AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.action_proposal ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.action_proposal FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.action_proposal AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.agent_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_action FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.agent_action AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.action_approval ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.action_approval FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.action_approval AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE agent.action_execution ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.action_execution FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON agent.action_execution AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
ALTER TABLE ingest.tenant_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.tenant_registry FORCE ROW LEVEL SECURITY;
CREATE POLICY pol_tenant_isolation ON ingest.tenant_registry AS PERMISSIVE FOR ALL TO PUBLIC USING (tenant_id = public.brain_current_tenant()) WITH CHECK (tenant_id = public.brain_current_tenant());
-- brain_worker must discover the tenants before it has a tenant context: it may read every registry row
-- (ids, status, credential references; no business data). Permissive policies are OR-ed.
CREATE POLICY pol_worker_list_tenants ON ingest.tenant_registry AS PERMISSIVE FOR SELECT TO brain_worker USING (true);

-- Views must run with the caller's rights, otherwise they would read as the owner and skip RLS.
ALTER VIEW intel.v_insight_current SET (security_invoker = true);
ALTER VIEW intel.v_alert_open SET (security_invoker = true);
ALTER VIEW agent.v_agent_action SET (security_invoker = true);
