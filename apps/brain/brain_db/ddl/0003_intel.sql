-- 0003_intel: intel schema (MVP tables)

-- ---- intel.rule_config ----
CREATE TABLE intel.rule_config (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    rule_set TEXT NOT NULL,
    version INTEGER NOT NULL,
    version_label TEXT NOT NULL,
    params JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT 'migration',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_rule_config PRIMARY KEY (id),
    CONSTRAINT uq_rule_config__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_rule_config__tenant_set_version UNIQUE (tenant_id, rule_set, version),
    CONSTRAINT uq_rule_config__tenant_set_label UNIQUE (tenant_id, rule_set, version_label),
    CONSTRAINT ck_rule_config__rule_set CHECK (rule_set IN ('platform','anomaly','risk','recommendation','forecast')),
    CONSTRAINT ck_rule_config__version_pos CHECK (version > 0),
    CONSTRAINT ck_rule_config__params_type CHECK (jsonb_typeof(params) = 'object')
);
CREATE UNIQUE INDEX uq_rule_config__one_active_per_set ON intel.rule_config (tenant_id, rule_set) WHERE is_active;
COMMENT ON TABLE intel.rule_config IS 'Immutable, versioned parameter sets for the deterministic engines (anomaly thresholds, risk margins, safety stock, forecast selection rules, platform settings such as business timezone and cache freshness). Every assessment/recommendation points at the exact version it used.';
COMMENT ON COLUMN intel.rule_config.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.rule_config.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.rule_config.rule_set IS 'platform | anomaly | risk | recommendation | forecast.';
COMMENT ON COLUMN intel.rule_config.version IS 'Monotonic integer per (tenant, rule_set).';
COMMENT ON COLUMN intel.rule_config.version_label IS 'Human label copied into `rule_version` columns, e.g. ''risk-rules@1.0.0''.';
COMMENT ON COLUMN intel.rule_config.params IS 'Parameter object validated by the Pydantic model for the rule_set. Immutable after insert.';
COMMENT ON COLUMN intel.rule_config.is_active IS 'Exactly one active row per (tenant, rule_set).';
COMMENT ON COLUMN intel.rule_config.effective_from IS 'When this version became/becomes effective.';
COMMENT ON COLUMN intel.rule_config.created_by IS 'Actor (JWT sub), ''migration'' for seeds, or script name.';
COMMENT ON COLUMN intel.rule_config.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.rule_config.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_rule_config_set_updated_at BEFORE UPDATE ON intel.rule_config FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_rule_config_guard_update BEFORE UPDATE ON intel.rule_config FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('is_active', 'updated_at');

-- ---- intel.training_run ----
CREATE TABLE intel.training_run (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'forecast',
    trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    products_requested INTEGER NOT NULL DEFAULT 0,
    products_trained INTEGER NOT NULL DEFAULT 0,
    products_skipped INTEGER NOT NULL DEFAULT 0,
    products_failed INTEGER NOT NULL DEFAULT 0,
    feature_set_version SMALLINT,
    rule_config_id UUID,
    code_version TEXT,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_summary TEXT,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_training_run PRIMARY KEY (id),
    CONSTRAINT uq_training_run__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_training_run__purpose CHECK (purpose IN ('forecast','anomaly')),
    CONSTRAINT ck_training_run__trigger CHECK (trigger IN ('nightly','on_demand','manual')),
    CONSTRAINT ck_training_run__status CHECK (status IN ('running','succeeded','partial','failed')),
    CONSTRAINT ck_training_run__finished_consistency CHECK ((status = 'running') = (finished_at IS NULL)),
    CONSTRAINT ck_training_run__counts CHECK (products_requested >= 0 AND products_trained >= 0 AND products_skipped >= 0 AND products_failed >= 0),
    CONSTRAINT ck_training_run__error_len CHECK (error_summary IS NULL OR char_length(error_summary) <= 1000),
    CONSTRAINT ck_training_run__config_snapshot_type CHECK (jsonb_typeof(config_snapshot) = 'object'),
    CONSTRAINT ck_training_run__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_training_run__rule_config FOREIGN KEY (tenant_id, rule_config_id) REFERENCES intel.rule_config (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_training_run__tenant_started ON intel.training_run (tenant_id, started_at);
COMMENT ON TABLE intel.training_run IS 'One execution of a training job (nightly end-of-day retrain, D-26; or on-demand). Groups the candidate models it produced and records counts, configuration and outcome.';
COMMENT ON COLUMN intel.training_run.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.training_run.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.training_run.purpose IS 'forecast | anomaly.';
COMMENT ON COLUMN intel.training_run.trigger IS 'nightly | on_demand | manual. Nightly = the 02:00 end-of-day run (D-26); there is no weekly retrain.';
COMMENT ON COLUMN intel.training_run.status IS 'running | succeeded | partial | failed.';
COMMENT ON COLUMN intel.training_run.started_at IS 'Job start (UTC).';
COMMENT ON COLUMN intel.training_run.finished_at IS 'Job end (UTC).';
COMMENT ON COLUMN intel.training_run.products_requested IS 'SKUs selected for training.';
COMMENT ON COLUMN intel.training_run.products_trained IS 'SKUs with a registered winner.';
COMMENT ON COLUMN intel.training_run.products_skipped IS 'SKUs skipped (insufficient history / gaps).';
COMMENT ON COLUMN intel.training_run.products_failed IS 'SKUs that errored.';
COMMENT ON COLUMN intel.training_run.feature_set_version IS 'Feature definition version used.';
COMMENT ON COLUMN intel.training_run.rule_config_id IS 'rule_config(forecast) version used for selection rules.';
COMMENT ON COLUMN intel.training_run.code_version IS 'Git SHA of the training code.';
COMMENT ON COLUMN intel.training_run.config_snapshot IS 'Candidates, backtest window, min-history thresholds actually applied.';
COMMENT ON COLUMN intel.training_run.error_summary IS 'Short failure summary (<= 1000 chars).';
COMMENT ON COLUMN intel.training_run.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN intel.training_run.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.training_run.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_training_run_set_updated_at BEFORE UPDATE ON intel.training_run FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_training_run_guard_update BEFORE UPDATE ON intel.training_run FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'finished_at', 'products_requested', 'products_trained', 'products_skipped', 'products_failed', 'error_summary', 'updated_at');

-- ---- intel.model_registry ----
CREATE TABLE intel.model_registry (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID,
    scope TEXT NOT NULL,
    shared_model_id UUID,
    purpose TEXT NOT NULL DEFAULT 'forecast',
    model_family TEXT NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    training_run_id UUID NOT NULL,
    feature_set_version SMALLINT,
    trained_at TIMESTAMPTZ NOT NULL,
    train_data_start DATE,
    train_data_end DATE,
    hyperparameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    backtest_wape NUMERIC(8,5),
    baseline_wape NUMERIC(8,5),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifact_path TEXT,
    artifact_format TEXT,
    artifact_sha256 CHAR(64),
    artifact_size_bytes BIGINT,
    code_version TEXT,
    validated_at TIMESTAMPTZ,
    degraded_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    status_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_model_registry PRIMARY KEY (id),
    CONSTRAINT uq_model_registry__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_model_registry__tenant_model_version UNIQUE (tenant_id, model_version),
    CONSTRAINT ck_model_registry__purpose CHECK (purpose IN ('forecast','anomaly')),
    CONSTRAINT ck_model_registry__family CHECK (model_family IN ('naive','seasonal_naive','moving_average','category_mean','lightgbm','zscore_residual','isolation_forest')),
    CONSTRAINT ck_model_registry__scope CHECK (scope IN ('shared','product') AND (scope = 'shared') = (product_id IS NULL)),
    CONSTRAINT ck_model_registry__shared_ref CHECK (shared_model_id IS NULL OR (scope = 'product' AND artifact_path IS NULL AND shared_model_id <> id)),
    CONSTRAINT ck_model_registry__status CHECK (status IN ('candidate','validated','degraded','retired','rejected')),
    CONSTRAINT ck_model_registry__train_window CHECK ((train_data_start IS NULL) = (train_data_end IS NULL) AND (train_data_start IS NULL OR train_data_start <= train_data_end)),
    CONSTRAINT ck_model_registry__wape_nonneg CHECK ((backtest_wape IS NULL OR backtest_wape >= 0) AND (baseline_wape IS NULL OR baseline_wape >= 0)),
    CONSTRAINT ck_model_registry__artifact_pair CHECK ((artifact_path IS NULL) = (artifact_sha256 IS NULL)),
    CONSTRAINT ck_model_registry__artifact_path_relative CHECK (artifact_path IS NULL OR (artifact_path !~ '^(/|[A-Za-z]:)' AND artifact_path !~ '[.][.]')),
    CONSTRAINT ck_model_registry__artifact_format CHECK (artifact_format IS NULL OR artifact_format IN ('lightgbm_txt','json')),
    CONSTRAINT ck_model_registry__validated_has_ts CHECK (status <> 'validated' OR validated_at IS NOT NULL),
    CONSTRAINT ck_model_registry__trained_family_artifact CHECK (status <> 'validated' OR model_family NOT IN ('lightgbm','isolation_forest') OR artifact_path IS NOT NULL OR shared_model_id IS NOT NULL),
    CONSTRAINT ck_model_registry__category_mean_scope CHECK (model_family <> 'category_mean' OR product_id IS NULL),
    CONSTRAINT ck_model_registry__reason_len CHECK (status_reason IS NULL OR char_length(status_reason) <= 500),
    CONSTRAINT ck_model_registry__hyperparameters_type CHECK (jsonb_typeof(hyperparameters) = 'object'),
    CONSTRAINT ck_model_registry__metrics_type CHECK (jsonb_typeof(metrics) = 'object'),
    CONSTRAINT ck_model_registry__artifact_sha256_format CHECK (artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_model_registry__training_run FOREIGN KEY (tenant_id, training_run_id) REFERENCES intel.training_run (tenant_id, id) ON DELETE RESTRICT
);
ALTER TABLE intel.model_registry ADD CONSTRAINT fk_model_registry__shared_model FOREIGN KEY (tenant_id, shared_model_id) REFERENCES intel.model_registry (tenant_id, id) ON DELETE RESTRICT;
CREATE INDEX ix_model_registry__serving ON intel.model_registry (tenant_id, product_id, purpose, validated_at) WHERE status = 'validated';
CREATE INDEX ix_model_registry__tenant_run ON intel.model_registry (tenant_id, training_run_id);
CREATE INDEX ix_model_registry__tenant_shared ON intel.model_registry (tenant_id, shared_model_id) WHERE shared_model_id IS NOT NULL;
COMMENT ON TABLE intel.model_registry IS 'Registry of trained or fitted models/methods. A row is either SHARED (scope=shared, product_id NULL: one artifact fitted across many products of the tenant, e.g. the global LightGBM) or PRODUCT (scope=product, product_id set: the model a product is served by, with that product''s own backtest WAPE). A product row either points at a shared row through `shared_model_id` (it uses the shared artifact and has no artifact of its own, so it does NOT mean a separately trained model) or carries its own artifact (a product-specific model, allowed only when it beats the shared one) or is an artifact-less method such as seasonal_naive (D-31). Inference reads the latest `validated` product row.';
COMMENT ON COLUMN intel.model_registry.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.model_registry.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.model_registry.product_id IS 'Canonical product id for scope=product rows; NULL for scope=shared rows.';
COMMENT ON COLUMN intel.model_registry.scope IS 'shared | product (D-31). shared = fitted across products; product = the model selection for one product.';
COMMENT ON COLUMN intel.model_registry.shared_model_id IS 'scope=product rows that use a shared artifact: the shared row. NULL when the product row has its own artifact or uses an artifact-less method.';
COMMENT ON COLUMN intel.model_registry.purpose IS 'forecast | anomaly.';
COMMENT ON COLUMN intel.model_registry.model_family IS 'naive | seasonal_naive | moving_average | category_mean | lightgbm | zscore_residual | isolation_forest. MVP forecasting uses seasonal_naive and lightgbm only (D-20, D-32).';
COMMENT ON COLUMN intel.model_registry.model_version IS 'Unique label per tenant, e.g. ''lgbm-amox-v3'' (the `model_version` of the source key).';
COMMENT ON COLUMN intel.model_registry.status IS 'candidate | validated | degraded | retired | rejected.';
COMMENT ON COLUMN intel.model_registry.training_run_id IS 'Run that produced the row.';
COMMENT ON COLUMN intel.model_registry.feature_set_version IS 'Feature definition version; NULL for methods that do not use features.';
COMMENT ON COLUMN intel.model_registry.trained_at IS 'Training/fit completion (UTC).';
COMMENT ON COLUMN intel.model_registry.train_data_start IS 'First day of training data (leakage audit).';
COMMENT ON COLUMN intel.model_registry.train_data_end IS 'Last day of training data.';
COMMENT ON COLUMN intel.model_registry.hyperparameters IS 'Hyperparameters / fitted parameters.';
COMMENT ON COLUMN intel.model_registry.backtest_wape IS 'WAPE on the rolling-origin backtest (fraction, 0.14 = 14 percent).';
COMMENT ON COLUMN intel.model_registry.baseline_wape IS 'WAPE of the best baseline on the same folds (winner must beat it).';
COMMENT ON COLUMN intel.model_registry.metrics IS 'Other backtest metrics snapshot (mape, bias, n_folds, backtest_weeks).';
COMMENT ON COLUMN intel.model_registry.artifact_path IS 'Path RELATIVE to the models volume root; NULL for methods without an artifact.';
COMMENT ON COLUMN intel.model_registry.artifact_format IS 'lightgbm_txt | json. Executable formats (pickle, joblib) are not allowed (OD-13, D-33).';
COMMENT ON COLUMN intel.model_registry.artifact_sha256 IS 'Checksum verified before load.';
COMMENT ON COLUMN intel.model_registry.artifact_size_bytes IS 'File size.';
COMMENT ON COLUMN intel.model_registry.code_version IS 'Git SHA of the training code.';
COMMENT ON COLUMN intel.model_registry.validated_at IS 'When promoted to validated.';
COMMENT ON COLUMN intel.model_registry.degraded_at IS 'When flagged degraded (post-deployment WAPE jump).';
COMMENT ON COLUMN intel.model_registry.retired_at IS 'When superseded/retired.';
COMMENT ON COLUMN intel.model_registry.status_reason IS 'Why the status last changed (<= 500 chars).';
COMMENT ON COLUMN intel.model_registry.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.model_registry.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_model_registry_set_updated_at BEFORE UPDATE ON intel.model_registry FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_model_registry_guard_update BEFORE UPDATE ON intel.model_registry FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'validated_at', 'degraded_at', 'retired_at', 'status_reason', 'artifact_path', 'artifact_sha256', 'artifact_size_bytes', 'artifact_format', 'updated_at');

-- ---- intel.model_evaluation ----
CREATE TABLE intel.model_evaluation (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id UUID NOT NULL,
    evaluation_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC(14,6) NOT NULL,
    baseline_value NUMERIC(14,6),
    n_obs INTEGER NOT NULL,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT pk_model_evaluation PRIMARY KEY (id),
    CONSTRAINT uq_model_evaluation__window_metric UNIQUE (tenant_id, model_id, evaluation_type, metric_name, window_start, window_end),
    CONSTRAINT ck_model_evaluation__type CHECK (evaluation_type IN ('backtest','post_deploy_weekly','holdout','golden_set')),
    CONSTRAINT ck_model_evaluation__metric CHECK (metric_name IN ('wape','mape','smape','mae','bias','precision','recall','f1')),
    CONSTRAINT ck_model_evaluation__window CHECK (window_end >= window_start),
    CONSTRAINT ck_model_evaluation__n_obs CHECK (n_obs >= 0),
    CONSTRAINT ck_model_evaluation__details_type CHECK (jsonb_typeof(details) = 'object'),
    CONSTRAINT fk_model_evaluation__model_registry FOREIGN KEY (tenant_id, model_id) REFERENCES intel.model_registry (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_model_evaluation__model_evaluated ON intel.model_evaluation (tenant_id, model_id, evaluated_at);
COMMENT ON TABLE intel.model_evaluation IS 'Append-only evaluation results over time (backtests, weekly post-deployment predicted-vs-actual, golden-set precision/recall). Supports degradation detection and model comparison without overwriting history.';
COMMENT ON COLUMN intel.model_evaluation.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.model_evaluation.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.model_evaluation.model_id IS 'Model evaluated.';
COMMENT ON COLUMN intel.model_evaluation.evaluation_type IS 'backtest | post_deploy_weekly | holdout | golden_set.';
COMMENT ON COLUMN intel.model_evaluation.metric_name IS 'wape | mape | smape | mae | bias | precision | recall | f1.';
COMMENT ON COLUMN intel.model_evaluation.metric_value IS 'Metric value (WAPE as a fraction).';
COMMENT ON COLUMN intel.model_evaluation.baseline_value IS 'Same metric for the baseline on the same window.';
COMMENT ON COLUMN intel.model_evaluation.n_obs IS 'Observations (product-days) behind the metric.';
COMMENT ON COLUMN intel.model_evaluation.window_start IS 'First evaluated day.';
COMMENT ON COLUMN intel.model_evaluation.window_end IS 'Last evaluated day.';
COMMENT ON COLUMN intel.model_evaluation.evaluated_at IS 'When computed (UTC).';
COMMENT ON COLUMN intel.model_evaluation.details IS 'Per-fold values or confusion counts.';
CREATE TRIGGER trg_model_evaluation_forbid_update BEFORE UPDATE ON intel.model_evaluation FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- intel.forecast ----
CREATE TABLE intel.forecast (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    model_id UUID NOT NULL,
    job_run_id UUID NOT NULL,
    origin_date DATE NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_days SMALLINT NOT NULL,
    trigger TEXT NOT NULL,
    forecast_confidence TEXT NOT NULL,
    cold_start BOOLEAN NOT NULL DEFAULT false,
    history_days INTEGER NOT NULL,
    interval_method TEXT NOT NULL DEFAULT 'none',
    interval_coverage NUMERIC(4,3),
    feature_set_version SMALLINT,
    inputs_max_updated_at TIMESTAMPTZ,
    quality_flags TEXT[] NOT NULL DEFAULT '{}'::text[],
    factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_forecast PRIMARY KEY (id),
    CONSTRAINT uq_forecast__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_forecast__run_product_model UNIQUE (tenant_id, product_id, model_id, job_run_id),
    CONSTRAINT ck_forecast__horizon CHECK (horizon_days BETWEEN 1 AND 90),
    CONSTRAINT ck_forecast__trigger CHECK (trigger IN ('nightly','on_demand','backfill')),
    CONSTRAINT ck_forecast__confidence CHECK (forecast_confidence IN ('low','medium','high')),
    CONSTRAINT ck_forecast__history_nonneg CHECK (history_days >= 0),
    CONSTRAINT ck_forecast__interval_method CHECK (interval_method IN ('quantile','backtest_residual','none')),
    CONSTRAINT ck_forecast__interval_coverage CHECK (interval_coverage IS NULL OR (interval_coverage > 0 AND interval_coverage < 1)),
    CONSTRAINT ck_forecast__interval_consistency CHECK ((interval_method = 'none') = (interval_coverage IS NULL)),
    CONSTRAINT ck_forecast__factors_type CHECK (jsonb_typeof(factors) = 'array'),
    CONSTRAINT ck_forecast__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_forecast__model_registry FOREIGN KEY (tenant_id, model_id) REFERENCES intel.model_registry (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_forecast__tenant_product_generated ON intel.forecast (tenant_id, product_id, generated_at);
CREATE INDEX ix_forecast__tenant_model_generated ON intel.forecast (tenant_id, model_id, generated_at);
COMMENT ON TABLE intel.forecast IS 'Header of ONE forecast generation for one product by one model at one origin date. Daily values are in `forecast_point`. Never overwritten: each generation is kept so accuracy can be evaluated by lead time and audited.';
COMMENT ON COLUMN intel.forecast.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.forecast.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.forecast.product_id IS 'Canonical product id.';
COMMENT ON COLUMN intel.forecast.model_id IS 'Model/method that produced the forecast.';
COMMENT ON COLUMN intel.forecast.job_run_id IS 'Correlation id of the batch/job (training_run id, nightly job id or on-demand request id). Makes retries idempotent.';
COMMENT ON COLUMN intel.forecast.origin_date IS 'Last day of observed data used (the forecast covers origin_date + 1 ...).';
COMMENT ON COLUMN intel.forecast.generated_at IS 'Generation time (UTC).';
COMMENT ON COLUMN intel.forecast.horizon_days IS 'Number of forecast days (1..90).';
COMMENT ON COLUMN intel.forecast.trigger IS 'nightly | on_demand | backfill.';
COMMENT ON COLUMN intel.forecast.forecast_confidence IS 'Qualitative confidence: low (cold start) | medium | high (from backtest).';
COMMENT ON COLUMN intel.forecast.cold_start IS 'True when a cold-start fallback was used.';
COMMENT ON COLUMN intel.forecast.history_days IS 'Complete days of history available at origin.';
COMMENT ON COLUMN intel.forecast.interval_method IS 'How bounds were produced: quantile | backtest_residual | none.';
COMMENT ON COLUMN intel.forecast.interval_coverage IS 'Nominal coverage of [lower, upper], e.g. 0.800 for P10-P90.';
COMMENT ON COLUMN intel.forecast.feature_set_version IS 'Feature definition version used.';
COMMENT ON COLUMN intel.forecast.inputs_max_updated_at IS 'max(sales_fact.updated_at) of the inputs (reproducibility fingerprint).';
COMMENT ON COLUMN intel.forecast.quality_flags IS 'Data-quality flags, e.g. gap_filled, sparse_history, outlier_winsorised.';
COMMENT ON COLUMN intel.forecast.factors IS 'Explainability factors[] (e.g. ''7-day mean 22 percent above 28-day mean'').';
COMMENT ON COLUMN intel.forecast.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN intel.forecast.created_at IS 'Row creation time (UTC).';
CREATE TRIGGER trg_forecast_forbid_update BEFORE UPDATE ON intel.forecast FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- intel.forecast_point ----
CREATE TABLE intel.forecast_point (
    forecast_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    target_date DATE NOT NULL,
    predicted_demand NUMERIC(14,3) NOT NULL,
    confidence_low NUMERIC(14,3),
    confidence_high NUMERIC(14,3),
    CONSTRAINT pk_forecast_point PRIMARY KEY (forecast_id, target_date),
    CONSTRAINT ck_forecast_point__predicted_nonneg CHECK (predicted_demand >= 0),
    CONSTRAINT ck_forecast_point__bounds_pair CHECK ((confidence_low IS NULL) = (confidence_high IS NULL)),
    CONSTRAINT ck_forecast_point__bounds_order CHECK (confidence_low IS NULL OR (confidence_low >= 0 AND confidence_low <= predicted_demand AND confidence_high >= predicted_demand)),
    CONSTRAINT fk_forecast_point__forecast FOREIGN KEY (tenant_id, forecast_id) REFERENCES intel.forecast (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_forecast_point__tenant_target ON intel.forecast_point (tenant_id, target_date);
COMMENT ON TABLE intel.forecast_point IS 'Daily predicted demand with confidence bounds for one forecast generation.';
COMMENT ON COLUMN intel.forecast_point.forecast_id IS 'Parent forecast.';
COMMENT ON COLUMN intel.forecast_point.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.forecast_point.target_date IS 'Business date being predicted.';
COMMENT ON COLUMN intel.forecast_point.predicted_demand IS 'Point prediction (median/expected demand).';
COMMENT ON COLUMN intel.forecast_point.confidence_low IS 'Lower confidence bound (see parent interval_method/coverage).';
COMMENT ON COLUMN intel.forecast_point.confidence_high IS 'Upper confidence bound.';
CREATE TRIGGER trg_forecast_point_forbid_update BEFORE UPDATE ON intel.forecast_point FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- intel.anomaly_event ----
CREATE TABLE intel.anomaly_event (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    observation_date DATE NOT NULL,
    anomaly_type TEXT NOT NULL,
    detection_method TEXT NOT NULL,
    expected_value NUMERIC(14,3),
    observed_value NUMERIC(14,3) NOT NULL,
    zscore NUMERIC(10,4),
    score NUMERIC(5,4) NOT NULL,
    severity TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    rule_version TEXT NOT NULL,
    rule_config_id UUID NOT NULL,
    model_id UUID,
    forecast_id UUID,
    status TEXT NOT NULL DEFAULT 'open',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    detection_count INTEGER NOT NULL DEFAULT 1,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_anomaly_event PRIMARY KEY (id),
    CONSTRAINT uq_anomaly_event__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_anomaly_event__natural_key UNIQUE (tenant_id, product_id, observation_date, anomaly_type, detection_method),
    CONSTRAINT ck_anomaly_event__type CHECK (anomaly_type IN ('demand_spike','demand_drop','pattern_outlier')),
    CONSTRAINT ck_anomaly_event__method CHECK (detection_method IN ('rule','zscore','isolation_forest','combined')),
    CONSTRAINT ck_anomaly_event__score CHECK (score BETWEEN 0 AND 1),
    CONSTRAINT ck_anomaly_event__severity CHECK (severity IN ('low','medium','high')),
    CONSTRAINT ck_anomaly_event__status CHECK (status IN ('open','acknowledged','dismissed','confirmed','retracted')),
    CONSTRAINT ck_anomaly_event__observed_nonneg CHECK (observed_value >= 0),
    CONSTRAINT ck_anomaly_event__review_pair CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL)),
    CONSTRAINT ck_anomaly_event__review_required CHECK (status NOT IN ('acknowledged','dismissed','confirmed') OR reviewed_by IS NOT NULL),
    CONSTRAINT ck_anomaly_event__count CHECK (detection_count >= 1),
    CONSTRAINT ck_anomaly_event__detect_order CHECK (last_detected_at >= first_detected_at),
    CONSTRAINT ck_anomaly_event__reasons_type CHECK (jsonb_typeof(reasons) = 'array'),
    CONSTRAINT ck_anomaly_event__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_anomaly_event__rule_config FOREIGN KEY (tenant_id, rule_config_id) REFERENCES intel.rule_config (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_event__model_registry FOREIGN KEY (tenant_id, model_id) REFERENCES intel.model_registry (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_anomaly_event__forecast FOREIGN KEY (tenant_id, forecast_id) REFERENCES intel.forecast (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_anomaly_event__tenant_product_date ON intel.anomaly_event (tenant_id, product_id, observation_date);
CREATE INDEX ix_anomaly_event__open_severity ON intel.anomaly_event (tenant_id, severity, last_detected_at) WHERE status = 'open';
COMMENT ON TABLE intel.anomaly_event IS 'A detected unusual observation (an unexplained deviation, NOT a confirmed incident) for a product-day, with expected vs observed, score, severity, structured reasons and provenance. Re-detection updates the same row.';
COMMENT ON COLUMN intel.anomaly_event.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.anomaly_event.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.anomaly_event.product_id IS 'Canonical product id. (MVP anomalies are sales anomalies per product-day.)';
COMMENT ON COLUMN intel.anomaly_event.observation_date IS 'Business date of the observation.';
COMMENT ON COLUMN intel.anomaly_event.anomaly_type IS 'demand_spike | demand_drop | pattern_outlier. (single_line_outlier removed: daily totals carry no line detail.)';
COMMENT ON COLUMN intel.anomaly_event.detection_method IS 'rule | zscore | isolation_forest | combined.';
COMMENT ON COLUMN intel.anomaly_event.expected_value IS 'Expected units (from forecast or rolling mean); NULL if none available.';
COMMENT ON COLUMN intel.anomaly_event.observed_value IS 'Observed net units for the day.';
COMMENT ON COLUMN intel.anomaly_event.zscore IS 'Residual z-score when computed.';
COMMENT ON COLUMN intel.anomaly_event.score IS 'Anomaly score in [0, 1].';
COMMENT ON COLUMN intel.anomaly_event.severity IS 'low | medium | high (thresholds from rule_config).';
COMMENT ON COLUMN intel.anomaly_event.reasons IS 'Structured reasons array: [{code, value, threshold}].';
COMMENT ON COLUMN intel.anomaly_event.rule_version IS 'Rule set label used (copy of rule_config.version_label).';
COMMENT ON COLUMN intel.anomaly_event.rule_config_id IS 'Exact parameter set used.';
COMMENT ON COLUMN intel.anomaly_event.model_id IS 'Isolation Forest / statistical model used, when any.';
COMMENT ON COLUMN intel.anomaly_event.forecast_id IS 'Forecast the expected value came from, when any.';
COMMENT ON COLUMN intel.anomaly_event.status IS 'open (unreviewed signal) | acknowledged | dismissed | confirmed | retracted (no longer anomalous after correction).';
COMMENT ON COLUMN intel.anomaly_event.reviewed_by IS 'Reviewer actor id (JWT sub).';
COMMENT ON COLUMN intel.anomaly_event.reviewed_at IS 'Review time.';
COMMENT ON COLUMN intel.anomaly_event.first_detected_at IS 'First detection (API `detected_at`).';
COMMENT ON COLUMN intel.anomaly_event.last_detected_at IS 'Most recent re-detection.';
COMMENT ON COLUMN intel.anomaly_event.detection_count IS 'Number of detections folded into this row.';
COMMENT ON COLUMN intel.anomaly_event.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN intel.anomaly_event.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN intel.anomaly_event.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.anomaly_event.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_anomaly_event_set_updated_at BEFORE UPDATE ON intel.anomaly_event FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_anomaly_event_guard_update BEFORE UPDATE ON intel.anomaly_event FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('expected_value', 'observed_value', 'zscore', 'score', 'severity', 'reasons', 'rule_version', 'rule_config_id', 'model_id', 'forecast_id', 'status', 'reviewed_by', 'reviewed_at', 'last_detected_at', 'detection_count', 'row_version', 'trace_id', 'updated_at');

-- ---- intel.risk_assessment ----
CREATE TABLE intel.risk_assessment (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    supplier_id UUID,
    risk_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence NUMERIC(4,3),
    input_available_quantity NUMERIC(14,3),
    inventory_as_of TIMESTAMPTZ,
    inventory_source TEXT,
    demand_per_day NUMERIC(14,4),
    demand_over_lead_time NUMERIC(14,3),
    demand_over_lead_time_upper NUMERIC(14,3),
    days_of_cover NUMERIC(8,2),
    lead_time_days NUMERIC(6,2),
    supplier_as_of TIMESTAMPTZ,
    forecast_id UUID,
    anomaly_event_id UUID,
    rule_version TEXT NOT NULL,
    rule_config_id UUID NOT NULL,
    calculation JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,
    superseded_by_id UUID,
    trace_id CHAR(32),
    CONSTRAINT pk_risk_assessment PRIMARY KEY (id),
    CONSTRAINT uq_risk_assessment__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_risk_assessment__type CHECK (risk_type IN ('stockout_risk','unusual_demand')),
    CONSTRAINT ck_risk_assessment__severity CHECK (severity IN ('low','medium','high')),
    CONSTRAINT ck_risk_assessment__confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_risk_assessment__inventory_source CHECK (inventory_source IS NULL OR inventory_source IN ('canonical_live','canonical_cache')),
    CONSTRAINT ck_risk_assessment__numbers_nonneg CHECK ((demand_per_day IS NULL OR demand_per_day >= 0) AND (demand_over_lead_time IS NULL OR demand_over_lead_time >= 0) AND (days_of_cover IS NULL OR days_of_cover >= 0) AND (lead_time_days IS NULL OR lead_time_days >= 0)),
    CONSTRAINT ck_risk_assessment__stockout_inputs CHECK (risk_type <> 'stockout_risk' OR (days_of_cover IS NOT NULL AND lead_time_days IS NOT NULL AND input_available_quantity IS NOT NULL AND inventory_as_of IS NOT NULL)),
    CONSTRAINT ck_risk_assessment__unusual_anomaly CHECK (risk_type <> 'unusual_demand' OR anomaly_event_id IS NOT NULL),
    CONSTRAINT ck_risk_assessment__supersede_pair CHECK ((superseded_at IS NULL) = (superseded_by_id IS NULL)),
    CONSTRAINT ck_risk_assessment__calculation_type CHECK (jsonb_typeof(calculation) = 'object'),
    CONSTRAINT ck_risk_assessment__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_risk_assessment__forecast FOREIGN KEY (tenant_id, forecast_id) REFERENCES intel.forecast (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_risk_assessment__anomaly_event FOREIGN KEY (tenant_id, anomaly_event_id) REFERENCES intel.anomaly_event (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_risk_assessment__rule_config FOREIGN KEY (tenant_id, rule_config_id) REFERENCES intel.rule_config (tenant_id, id) ON DELETE RESTRICT
);
ALTER TABLE intel.risk_assessment ADD CONSTRAINT fk_risk_assessment__superseded_by FOREIGN KEY (tenant_id, superseded_by_id) REFERENCES intel.risk_assessment (tenant_id, id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_risk_assessment__current ON intel.risk_assessment (tenant_id, product_id, risk_type) WHERE superseded_at IS NULL;
CREATE INDEX ix_risk_assessment__current_severity ON intel.risk_assessment (tenant_id, severity, calculated_at) WHERE superseded_at IS NULL;
CREATE INDEX ix_risk_assessment__product_history ON intel.risk_assessment (tenant_id, product_id, calculated_at);
COMMENT ON TABLE intel.risk_assessment IS 'Deterministic risk result per product and risk type (stockout_risk, unusual_demand) with the exact inputs and rule version used. Versions are kept: a changed outcome inserts a new row and supersedes the old one, so recommendations keep pointing at the calculation they were based on.';
COMMENT ON COLUMN intel.risk_assessment.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.risk_assessment.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.risk_assessment.product_id IS 'Canonical product id.';
COMMENT ON COLUMN intel.risk_assessment.supplier_id IS 'Canonical supplier id whose lead time was used (external; see OD-04).';
COMMENT ON COLUMN intel.risk_assessment.risk_type IS 'stockout_risk | unusual_demand.';
COMMENT ON COLUMN intel.risk_assessment.severity IS 'low | medium | high.';
COMMENT ON COLUMN intel.risk_assessment.confidence IS '0..1 where meaningful (stockout_risk); NULL for unusual_demand.';
COMMENT ON COLUMN intel.risk_assessment.input_available_quantity IS 'INPUT SNAPSHOT of ERP available_quantity used in the calculation. Provenance, not an inventory copy.';
COMMENT ON COLUMN intel.risk_assessment.inventory_as_of IS 'Time the inventory value was read from Canonical.';
COMMENT ON COLUMN intel.risk_assessment.inventory_source IS 'canonical_live | canonical_cache.';
COMMENT ON COLUMN intel.risk_assessment.demand_per_day IS 'Forecast demand per day used.';
COMMENT ON COLUMN intel.risk_assessment.demand_over_lead_time IS 'Sum of forecast points over the supplier lead time.';
COMMENT ON COLUMN intel.risk_assessment.demand_over_lead_time_upper IS 'Conservative upper estimate (sum of daily confidence_high).';
COMMENT ON COLUMN intel.risk_assessment.days_of_cover IS 'available / demand_per_day.';
COMMENT ON COLUMN intel.risk_assessment.lead_time_days IS 'Supplier lead time used.';
COMMENT ON COLUMN intel.risk_assessment.supplier_as_of IS 'synced_at of the supplier payload used.';
COMMENT ON COLUMN intel.risk_assessment.forecast_id IS 'Forecast used.';
COMMENT ON COLUMN intel.risk_assessment.anomaly_event_id IS 'Driving anomaly (required for unusual_demand; optional escalation source for stockout_risk).';
COMMENT ON COLUMN intel.risk_assessment.rule_version IS 'Rule set label used.';
COMMENT ON COLUMN intel.risk_assessment.rule_config_id IS 'Exact parameter set used.';
COMMENT ON COLUMN intel.risk_assessment.calculation IS 'Rule trace: [{rule, matched, inputs, output}], other anomaly ids, notes.';
COMMENT ON COLUMN intel.risk_assessment.calculated_at IS 'When this version was first calculated (UTC).';
COMMENT ON COLUMN intel.risk_assessment.last_confirmed_at IS 'Last recalculation that produced the same outcome (heartbeat, avoids row churn).';
COMMENT ON COLUMN intel.risk_assessment.superseded_at IS 'Set when a newer version replaces this one.';
COMMENT ON COLUMN intel.risk_assessment.superseded_by_id IS 'The newer version.';
COMMENT ON COLUMN intel.risk_assessment.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
CREATE TRIGGER trg_risk_assessment_guard_update BEFORE UPDATE ON intel.risk_assessment FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('last_confirmed_at', 'superseded_at', 'superseded_by_id');

-- ---- intel.recommendation ----
CREATE TABLE intel.recommendation (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    supplier_id UUID,
    risk_assessment_id UUID NOT NULL,
    forecast_id UUID,
    recommendation_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    calculation JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    superseded_at TIMESTAMPTZ,
    superseded_by_id UUID,
    rule_version TEXT NOT NULL,
    rule_config_id UUID NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_recommendation PRIMARY KEY (id),
    CONSTRAINT uq_recommendation__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_recommendation__type CHECK (recommendation_type IN ('create_purchase_order','review_anomaly')),
    CONSTRAINT ck_recommendation__status CHECK (status IN ('active','dismissed','superseded','expired')),
    CONSTRAINT ck_recommendation__expiry CHECK (expires_at > generated_at),
    CONSTRAINT ck_recommendation__supersede CHECK ((status = 'superseded') = (superseded_at IS NOT NULL AND superseded_by_id IS NOT NULL)),
    CONSTRAINT ck_recommendation__payload_type CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_recommendation__calculation_type CHECK (jsonb_typeof(calculation) = 'object'),
    CONSTRAINT ck_recommendation__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_recommendation__risk_assessment FOREIGN KEY (tenant_id, risk_assessment_id) REFERENCES intel.risk_assessment (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_recommendation__forecast FOREIGN KEY (tenant_id, forecast_id) REFERENCES intel.forecast (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_recommendation__rule_config FOREIGN KEY (tenant_id, rule_config_id) REFERENCES intel.rule_config (tenant_id, id) ON DELETE RESTRICT
);
ALTER TABLE intel.recommendation ADD CONSTRAINT fk_recommendation__superseded_by FOREIGN KEY (tenant_id, superseded_by_id) REFERENCES intel.recommendation (tenant_id, id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_recommendation__active ON intel.recommendation (tenant_id, product_id, recommendation_type) WHERE status = 'active';
CREATE INDEX ix_recommendation__tenant_product_generated ON intel.recommendation (tenant_id, product_id, generated_at);
CREATE INDEX ix_recommendation__tenant_risk ON intel.recommendation (tenant_id, risk_assessment_id);
COMMENT ON TABLE intel.recommendation IS 'Deterministic, structured suggestion derived from a risk (e.g. order 100 units from supplier X). Separate from any ERP transaction: a recommendation is never an executed purchase order.';
COMMENT ON COLUMN intel.recommendation.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.recommendation.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.recommendation.product_id IS 'Canonical product id.';
COMMENT ON COLUMN intel.recommendation.supplier_id IS 'Suggested supplier (external reference).';
COMMENT ON COLUMN intel.recommendation.risk_assessment_id IS 'Risk this recommendation answers (the source `risk_id`).';
COMMENT ON COLUMN intel.recommendation.forecast_id IS 'Forecast used.';
COMMENT ON COLUMN intel.recommendation.recommendation_type IS 'create_purchase_order | review_anomaly.';
COMMENT ON COLUMN intel.recommendation.payload IS 'Structured payload. For create_purchase_order it mirrors the tool input_schema {supplier_id, lines[{product_id, quantity}]} so the agent copies it into the ActionProposal unchanged.';
COMMENT ON COLUMN intel.recommendation.calculation IS 'Formula inputs and constraints checked: demand_over_lead, safety_stock, available, order_qty, bound_used, open-PO check status.';
COMMENT ON COLUMN intel.recommendation.status IS 'active | dismissed | superseded | expired. (''actioned'' is derived from agent.action_proposal, not stored.)';
COMMENT ON COLUMN intel.recommendation.generated_at IS 'Generation time (UTC).';
COMMENT ON COLUMN intel.recommendation.expires_at IS 'After this time the recommendation is no longer offered.';
COMMENT ON COLUMN intel.recommendation.superseded_at IS 'When replaced by a newer recommendation.';
COMMENT ON COLUMN intel.recommendation.superseded_by_id IS 'Replacement recommendation.';
COMMENT ON COLUMN intel.recommendation.rule_version IS 'Rule set label used.';
COMMENT ON COLUMN intel.recommendation.rule_config_id IS 'Exact parameter set used.';
COMMENT ON COLUMN intel.recommendation.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN intel.recommendation.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN intel.recommendation.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.recommendation.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_recommendation_set_updated_at BEFORE UPDATE ON intel.recommendation FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_recommendation_guard_update BEFORE UPDATE ON intel.recommendation FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'superseded_at', 'superseded_by_id', 'expires_at', 'row_version', 'updated_at');

-- ---- projections (views, no storage): Insight and Alert are API projections, not tables ----
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
