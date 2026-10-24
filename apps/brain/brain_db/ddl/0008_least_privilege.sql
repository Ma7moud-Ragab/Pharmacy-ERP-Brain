-- 0008_least_privilege (B1, B7; D-51): brain_app loses every pipeline write; brain_worker gets the calendar;
-- brain_provisioner may switch rule-set versions (is_active only), audited by trigger. Additive: 0005-0007 unchanged.
REVOKE INSERT, UPDATE ON ingest.sync_checkpoint FROM brain_app;
REVOKE INSERT, UPDATE ON ingest.ingest_failure FROM brain_app;
REVOKE INSERT, UPDATE, DELETE ON ingest.canonical_cache FROM brain_app;
REVOKE INSERT, UPDATE ON ingest.sales_fact FROM brain_app;
REVOKE INSERT, UPDATE ON ingest.sales_day_coverage FROM brain_app;
REVOKE INSERT, UPDATE ON feat.calendar_day FROM brain_app;
GRANT INSERT, UPDATE ON feat.calendar_day TO brain_worker;
REVOKE INSERT, UPDATE ON feat.feature_daily FROM brain_app;
REVOKE INSERT, UPDATE ON intel.rule_config FROM brain_app;
REVOKE INSERT, UPDATE ON intel.training_run FROM brain_app;
REVOKE INSERT, UPDATE ON intel.model_registry FROM brain_app;
REVOKE INSERT ON intel.model_evaluation FROM brain_app;
REVOKE INSERT ON intel.forecast FROM brain_app;
REVOKE INSERT ON intel.forecast_point FROM brain_app;
REVOKE INSERT, UPDATE ON intel.anomaly_event FROM brain_app;
REVOKE INSERT, UPDATE ON intel.risk_assessment FROM brain_app;
REVOKE INSERT, UPDATE ON intel.recommendation FROM brain_app;
DO $do$ BEGIN IF to_regclass('intel.briefing') IS NOT NULL THEN
  EXECUTE 'REVOKE INSERT, UPDATE ON intel.briefing FROM brain_app';
END IF; END $do$;
REVOKE UPDATE ON agent.action_proposal FROM brain_app;
GRANT UPDATE (status, status_changed_at, row_version, updated_at) ON agent.action_proposal TO brain_app;
GRANT USAGE ON SCHEMA audit TO brain_provisioner;
GRANT INSERT ON audit.audit_log TO brain_provisioner;
GRANT UPDATE (is_active) ON intel.rule_config TO brain_provisioner;

-- Every rule-set change is attributed and audited in the same transaction (D-51). The function runs with the caller's
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
