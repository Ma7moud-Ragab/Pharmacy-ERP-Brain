-- 0005: roles, grants and seed data
-- D-45: brain_worker (brain-worker jobs) is separate from brain_app (brain-api). It cannot record or change a decision
-- (no INSERT on agent.action_approval) and may only expire proposals or complete executions (guard_proposal_transition).
-- D-50 (B2): a superuser migrator runs the original role statements; any other migrator only verifies the roles.
DO $do$ BEGIN
  IF current_setting('is_superuser') = 'on' THEN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_app')       THEN CREATE ROLE brain_app NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_retention') THEN CREATE ROLE brain_retention NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_readonly')  THEN CREATE ROLE brain_readonly NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_worker')    THEN CREATE ROLE brain_worker NOLOGIN; END IF;
    ALTER ROLE brain_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  ELSE
    -- non-superuser migrator (B2): the roles come from ddl/bootstrap_roles.sql; verify them instead
    IF EXISTS (SELECT FROM unnest(ARRAY['brain_app', 'brain_retention', 'brain_readonly', 'brain_worker']) AS r(n) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r.n)) THEN
      RAISE EXCEPTION 'runtime roles missing: run ddl/bootstrap_roles.sql once per cluster as a role administrator';
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname IN ('brain_app', 'brain_retention', 'brain_readonly', 'brain_worker')
               AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls OR rolcanlogin)) THEN
      RAISE EXCEPTION 'runtime roles must be NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
    END IF;
  END IF;
END $do$;
-- Login users are created per environment by DevOps and granted ONE of these roles (never brain_app and brain_worker together).
GRANT USAGE ON SCHEMA ingest, feat, intel, agent, audit TO brain_app, brain_worker, brain_retention, brain_readonly;
GRANT SELECT, INSERT, UPDATE ON ingest.sync_checkpoint TO brain_app;
GRANT SELECT, INSERT, UPDATE ON ingest.sync_checkpoint TO brain_worker;
GRANT SELECT ON ingest.sync_checkpoint TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON ingest.ingest_failure TO brain_app;
GRANT SELECT, INSERT, UPDATE ON ingest.ingest_failure TO brain_worker;
GRANT SELECT ON ingest.ingest_failure TO brain_readonly;
GRANT SELECT, DELETE ON ingest.ingest_failure TO brain_retention;
GRANT SELECT, INSERT, UPDATE, DELETE ON ingest.canonical_cache TO brain_app;
GRANT SELECT, INSERT, UPDATE ON ingest.canonical_cache TO brain_worker;
GRANT SELECT ON ingest.canonical_cache TO brain_readonly;
GRANT SELECT, DELETE ON ingest.canonical_cache TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON ingest.sales_fact TO brain_app;
GRANT SELECT, INSERT, UPDATE ON ingest.sales_fact TO brain_worker;
GRANT SELECT ON ingest.sales_fact TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON ingest.sales_day_coverage TO brain_app;
GRANT SELECT, INSERT, UPDATE ON ingest.sales_day_coverage TO brain_worker;
GRANT SELECT ON ingest.sales_day_coverage TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON feat.calendar_day TO brain_app;
GRANT SELECT ON feat.calendar_day TO brain_worker;
GRANT SELECT ON feat.calendar_day TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON feat.feature_daily TO brain_app;
GRANT SELECT, INSERT, UPDATE ON feat.feature_daily TO brain_worker;
GRANT SELECT ON feat.feature_daily TO brain_readonly;
GRANT SELECT, DELETE ON feat.feature_daily TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON intel.rule_config TO brain_app;
GRANT SELECT ON intel.rule_config TO brain_worker;
GRANT SELECT ON intel.rule_config TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON intel.training_run TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.training_run TO brain_worker;
GRANT SELECT ON intel.training_run TO brain_readonly;
GRANT SELECT, DELETE ON intel.training_run TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON intel.model_registry TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.model_registry TO brain_worker;
GRANT SELECT ON intel.model_registry TO brain_readonly;
GRANT SELECT, DELETE ON intel.model_registry TO brain_retention;
GRANT SELECT, INSERT ON intel.model_evaluation TO brain_app;
GRANT SELECT, INSERT ON intel.model_evaluation TO brain_worker;
GRANT SELECT ON intel.model_evaluation TO brain_readonly;
GRANT SELECT, DELETE ON intel.model_evaluation TO brain_retention;
GRANT SELECT, INSERT ON intel.forecast TO brain_app;
GRANT SELECT, INSERT ON intel.forecast TO brain_worker;
GRANT SELECT ON intel.forecast TO brain_readonly;
GRANT SELECT, DELETE ON intel.forecast TO brain_retention;
GRANT SELECT, INSERT ON intel.forecast_point TO brain_app;
GRANT SELECT, INSERT ON intel.forecast_point TO brain_worker;
GRANT SELECT ON intel.forecast_point TO brain_readonly;
GRANT SELECT, DELETE ON intel.forecast_point TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON intel.anomaly_event TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.anomaly_event TO brain_worker;
GRANT SELECT ON intel.anomaly_event TO brain_readonly;
GRANT SELECT, DELETE ON intel.anomaly_event TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON intel.risk_assessment TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.risk_assessment TO brain_worker;
GRANT SELECT ON intel.risk_assessment TO brain_readonly;
GRANT SELECT, DELETE ON intel.risk_assessment TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON intel.recommendation TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.recommendation TO brain_worker;
GRANT SELECT ON intel.recommendation TO brain_readonly;
GRANT SELECT, DELETE ON intel.recommendation TO brain_retention;
GRANT SELECT, INSERT ON audit.llm_usage TO brain_app;
GRANT SELECT ON audit.llm_usage TO brain_readonly;
GRANT SELECT, DELETE ON audit.llm_usage TO brain_retention;
GRANT SELECT, INSERT ON audit.audit_log TO brain_app;
GRANT INSERT ON audit.audit_log TO brain_worker;
GRANT SELECT ON audit.audit_log TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON agent.agent_session TO brain_app;
GRANT SELECT ON agent.agent_session TO brain_readonly;
GRANT SELECT, DELETE ON agent.agent_session TO brain_retention;
GRANT SELECT, INSERT ON agent.agent_message TO brain_app;
GRANT SELECT ON agent.agent_message TO brain_readonly;
GRANT SELECT, DELETE ON agent.agent_message TO brain_retention;
GRANT SELECT, INSERT, UPDATE ON agent.action_proposal TO brain_app;
GRANT SELECT ON agent.action_proposal TO brain_worker;
GRANT UPDATE (status, status_changed_at, row_version, updated_at) ON agent.action_proposal TO brain_worker;
GRANT SELECT ON agent.action_proposal TO brain_readonly;
GRANT SELECT, INSERT ON agent.agent_action TO brain_app;
GRANT SELECT ON agent.agent_action TO brain_readonly;
GRANT SELECT, DELETE ON agent.agent_action TO brain_retention;
GRANT SELECT, INSERT ON agent.action_approval TO brain_app;
GRANT SELECT ON agent.action_approval TO brain_worker;
GRANT SELECT ON agent.action_approval TO brain_readonly;
GRANT SELECT, INSERT, UPDATE ON agent.action_execution TO brain_app;
GRANT SELECT, INSERT, UPDATE ON agent.action_execution TO brain_worker;
GRANT SELECT ON agent.action_execution TO brain_readonly;
GRANT SELECT ON intel.v_insight_current, intel.v_alert_open, agent.v_agent_action TO brain_app, brain_readonly;

-- Seed: default tenant rule sets (illustrative defaults to be tuned by the AI Lead; see OD-16).
INSERT INTO intel.rule_config (tenant_id, rule_set, version, version_label, params, is_active, created_by) VALUES
 ('00000000-0000-0000-0000-000000000001','platform',1,'platform-config@1.0.0','{"business_timezone":"Africa/Cairo","inventory_freshness_seconds":900,"supplier_freshness_seconds":86400,"product_freshness_seconds":86400,"reconcile_lookback_days":7,"feature_overlap_minutes":5,"sales_poll_interval_seconds":300,"poll_overlap_seconds":120,"poll_history_start_date":"2024-01-01","intel_window_minutes":60,"end_of_day_run_local_time":"02:00"}'::jsonb,true,'migration'),
 ('00000000-0000-0000-0000-000000000001','anomaly',1,'anomaly-rules@1.0.0','{"zscore_threshold":4,"severity_high_score":0.9,"severity_medium_score":0.7,"min_history_days":28,"isolation_forest_enabled":false}'::jsonb,true,'migration'),
 ('00000000-0000-0000-0000-000000000001','risk',1,'risk-rules@1.0.0','{"margin_days":2,"bound_policy":"median","upgrade_on_high_anomaly":true,"confidence_by_forecast":{"low":0.4,"medium":0.7,"high":0.9}}'::jsonb,true,'migration'),
 ('00000000-0000-0000-0000-000000000001','recommendation',1,'recommendation-rules@1.0.0','{"safety_stock_days":1,"recommendation_ttl_hours":24,"quantity_rounding":"ceil","suppress_if_open_po":false}'::jsonb,true,'migration'),
 ('00000000-0000-0000-0000-000000000001','forecast',1,'forecast-rules@1.0.0','{"min_history_weeks_per_sku":8,"backtest_weeks":4,"candidates":["seasonal_naive","lightgbm"],"must_beat_baseline_margin":0.05,"interval_method":"quantile","interval_coverage":0.8,"max_gap_days_ffill":3,"horizon_days":14,"degradation_wape_factor":1.5}'::jsonb,true,'migration')
ON CONFLICT DO NOTHING;
