-- brain_db: complete MVP DDL (concatenation of migrations 0001-0005, optional 0006, 0007 tenancy/RLS, 0008 least privilege).
-- Generated from the same schema definition as models.py. Execute as the migration owner role.
-- Not executed by the author; review and test in a scratch database first.


-- ==================== 0001_foundation.sql ====================
-- 0001_foundation: schemas and shared trigger functions (no tables)
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


-- ==================== 0002_ingest_feat.sql ====================
-- 0002_ingest_feat: ingest + feat schemas

-- ---- ingest.sync_checkpoint ----
CREATE TABLE ingest.sync_checkpoint (
    tenant_id UUID NOT NULL,
    resource TEXT NOT NULL,
    high_watermark TIMESTAMPTZ,
    cursor TEXT,
    last_status TEXT NOT NULL DEFAULT 'idle',
    last_started_at TIMESTAMPTZ,
    last_finished_at TIMESTAMPTZ,
    last_error_code TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_sync_checkpoint PRIMARY KEY (tenant_id, resource),
    CONSTRAINT ck_sync_checkpoint__resource_format CHECK (resource ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_sync_checkpoint__last_status CHECK (last_status IN ('idle','running','succeeded','failed')),
    CONSTRAINT ck_sync_checkpoint__failures_nonneg CHECK (consecutive_failures >= 0)
);
COMMENT ON TABLE ingest.sync_checkpoint IS 'Watermark per (tenant, resource) for the short-interval sales poll (`updated_since`), the nightly reconcile and the intraday intelligence window. One row per resource. This table is the poll checkpoint (D-25).';
COMMENT ON COLUMN ingest.sync_checkpoint.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN ingest.sync_checkpoint.resource IS 'Logical job: sales_poll | sales_reconcile | intel_window | feature_nightly_full.';
COMMENT ON COLUMN ingest.sync_checkpoint.high_watermark IS 'sales_poll: the SalesPage `high_watermark` of the last poll whose pages were ALL read (never advanced mid-poll); the next poll sends `updated_since = high_watermark - poll_overlap_seconds`. intel_window: max(sales_fact.updated_at) already processed.';
COMMENT ON COLUMN ingest.sync_checkpoint.cursor IS 'Opaque pagination cursor for an in-progress paged read.';
COMMENT ON COLUMN ingest.sync_checkpoint.last_status IS 'idle | running | succeeded | failed.';
COMMENT ON COLUMN ingest.sync_checkpoint.last_started_at IS 'Start of the most recent run.';
COMMENT ON COLUMN ingest.sync_checkpoint.last_finished_at IS 'End of the most recent run.';
COMMENT ON COLUMN ingest.sync_checkpoint.last_error_code IS 'Short error code of the most recent failure.';
COMMENT ON COLUMN ingest.sync_checkpoint.consecutive_failures IS 'Reset to 0 on success; drives alerting.';
COMMENT ON COLUMN ingest.sync_checkpoint.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.sync_checkpoint.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_sync_checkpoint_set_updated_at BEFORE UPDATE ON ingest.sync_checkpoint FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- ingest.ingest_failure ----
CREATE TABLE ingest.ingest_failure (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    failure_kind TEXT NOT NULL,
    resource TEXT NOT NULL,
    error_code TEXT NOT NULL,
    error_message TEXT,
    payload_excerpt JSONB,
    attempts INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open',
    first_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution TEXT,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_ingest_failure PRIMARY KEY (id),
    CONSTRAINT ck_ingest_failure__kind CHECK (failure_kind IN ('schema_validation','canonical_read_failed','normalization_error','other')),
    CONSTRAINT ck_ingest_failure__resource_format CHECK (resource ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_ingest_failure__status CHECK (status IN ('open','resolved','ignored')),
    CONSTRAINT ck_ingest_failure__attempts CHECK (attempts >= 1),
    CONSTRAINT ck_ingest_failure__message_len CHECK (error_message IS NULL OR char_length(error_message) <= 500),
    CONSTRAINT ck_ingest_failure__resolution CHECK (resolution IS NULL OR resolution IN ('repolled','fixed','ignored_invalid')),
    CONSTRAINT ck_ingest_failure__resolved_consistency CHECK ((status = 'open' AND resolved_at IS NULL) OR (status <> 'open' AND resolved_at IS NOT NULL)),
    CONSTRAINT ck_ingest_failure__payload_excerpt_type CHECK (payload_excerpt IS NULL OR jsonb_typeof(payload_excerpt) = 'object'),
    CONSTRAINT ck_ingest_failure__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$')
);
CREATE UNIQUE INDEX uq_ingest_failure__open_resource_code ON ingest.ingest_failure (tenant_id, resource, error_code) WHERE status = 'open';
CREATE INDEX ix_ingest_failure__tenant_status_failed ON ingest.ingest_failure (tenant_id, status, last_failed_at);
COMMENT ON TABLE ingest.ingest_failure IS 'Record of a Canonical poll or read the Brain could not process after bounded retries. One open row per (resource, error_code); repeats bump `attempts`. Recovery is the next successful poll or the nightly reconcile, never payload replay.';
COMMENT ON COLUMN ingest.ingest_failure.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN ingest.ingest_failure.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN ingest.ingest_failure.failure_kind IS 'schema_validation | canonical_read_failed | normalization_error | other.';
COMMENT ON COLUMN ingest.ingest_failure.resource IS 'Job that failed, e.g. sales_poll, sales_reconcile, inventory_read.';
COMMENT ON COLUMN ingest.ingest_failure.error_code IS 'Stable machine-readable error code.';
COMMENT ON COLUMN ingest.ingest_failure.error_message IS 'Sanitised message (<= 500 chars). Never contains customer data.';
COMMENT ON COLUMN ingest.ingest_failure.payload_excerpt IS 'Allow-listed keys only (schema, version, product_ids, business_dates, http_status). No customer fields.';
COMMENT ON COLUMN ingest.ingest_failure.attempts IS 'Failed attempts folded into this open row.';
COMMENT ON COLUMN ingest.ingest_failure.status IS 'open | resolved | ignored.';
COMMENT ON COLUMN ingest.ingest_failure.first_failed_at IS 'First failure time.';
COMMENT ON COLUMN ingest.ingest_failure.last_failed_at IS 'Most recent failure time.';
COMMENT ON COLUMN ingest.ingest_failure.resolved_at IS 'When closed.';
COMMENT ON COLUMN ingest.ingest_failure.resolved_by IS 'Actor id (JWT sub) or job name that closed it.';
COMMENT ON COLUMN ingest.ingest_failure.resolution IS 'repolled | fixed | ignored_invalid.';
COMMENT ON COLUMN ingest.ingest_failure.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN ingest.ingest_failure.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.ingest_failure.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_ingest_failure_set_updated_at BEFORE UPDATE ON ingest.ingest_failure FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- ingest.canonical_cache ----
CREATE TABLE ingest.canonical_cache (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    source_updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_canonical_cache PRIMARY KEY (id),
    CONSTRAINT uq_canonical_cache__tenant_entity UNIQUE (tenant_id, entity_type, entity_id),
    CONSTRAINT ck_canonical_cache__entity_type CHECK (entity_type IN ('product','inventory_item','supplier','purchase_order')),
    CONSTRAINT ck_canonical_cache__entity_id_len CHECK (char_length(entity_id) BETWEEN 1 AND 200),
    CONSTRAINT ck_canonical_cache__payload_type CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_canonical_cache__payload_sha256_format CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_canonical_cache__tenant_type_synced ON ingest.canonical_cache (tenant_id, entity_type, synced_at);
COMMENT ON TABLE ingest.canonical_cache IS 'Local durable cache of validated Canonical JSON (Product, InventoryItem, Supplier, optionally PurchaseOrder) with `synced_at`. NOT a source of truth: it avoids repeated Canonical reads and holds supplier lead times and product attributes needed by the engines.';
COMMENT ON COLUMN ingest.canonical_cache.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN ingest.canonical_cache.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN ingest.canonical_cache.entity_type IS 'product | inventory_item | supplier | purchase_order.';
COMMENT ON COLUMN ingest.canonical_cache.entity_id IS 'Canonical identifier. product/supplier: UUID string. inventory_item: ''<product_id>|<location_id>''.';
COMMENT ON COLUMN ingest.canonical_cache.schema_name IS 'Canonical schema name, e.g. ''canonical.InventoryItem''.';
COMMENT ON COLUMN ingest.canonical_cache.schema_version IS 'Canonical schema `version`, e.g. ''1.0''.';
COMMENT ON COLUMN ingest.canonical_cache.payload IS 'Validated canonical payload exactly as received (after Pydantic validation).';
COMMENT ON COLUMN ingest.canonical_cache.payload_sha256 IS 'SHA-256 of the canonical-serialised payload; cheap change detection (e.g. supplier lead time changed).';
COMMENT ON COLUMN ingest.canonical_cache.source_updated_at IS 'ERP `updated_at` carried by the payload. Older payloads never overwrite newer ones.';
COMMENT ON COLUMN ingest.canonical_cache.synced_at IS 'When the Brain last fetched/confirmed this payload (UTC).';
COMMENT ON COLUMN ingest.canonical_cache.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.canonical_cache.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_canonical_cache_set_updated_at BEFORE UPDATE ON ingest.canonical_cache FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- ingest.sales_fact ----
CREATE TABLE ingest.sales_fact (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    sales_date DATE NOT NULL,
    units_sold NUMERIC(14,3) NOT NULL DEFAULT 0,
    units_returned NUMERIC(14,3) NOT NULL DEFAULT 0,
    net_units NUMERIC(14,3) NOT NULL DEFAULT 0,
    day_status TEXT NOT NULL,
    is_complete BOOLEAN NOT NULL DEFAULT true,
    source_updated_at TIMESTAMPTZ NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'poll',
    polled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_sales_fact PRIMARY KEY (id),
    CONSTRAINT uq_sales_fact__tenant_product_date UNIQUE (tenant_id, product_id, sales_date),
    CONSTRAINT ck_sales_fact__units_nonneg CHECK (units_sold >= 0),
    CONSTRAINT ck_sales_fact__returned_nonneg CHECK (units_returned >= 0),
    CONSTRAINT ck_sales_fact__net_consistency CHECK (net_units = units_sold - units_returned),
    CONSTRAINT ck_sales_fact__day_status CHECK (day_status IN ('open','closed')),
    CONSTRAINT ck_sales_fact__source_mode CHECK (source_mode IN ('poll','reconcile','backfill'))
);
CREATE INDEX ix_sales_fact__tenant_sales_date ON ingest.sales_fact (tenant_id, sales_date);
CREATE INDEX ix_sales_fact__tenant_updated_at ON ingest.sales_fact (tenant_id, updated_at);
COMMENT ON TABLE ingest.sales_fact IS 'Daily sales per product (product x business day), copied from the polled Canonical `DailySalesTotal`. The only persisted sales data in the Brain; aggregate, not per-sale-line. Every write is an absolute upsert keyed (tenant, product, date) that keeps the newest ERP `updated_at` (D-25), so re-reading a row is always harmless.';
COMMENT ON COLUMN ingest.sales_fact.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN ingest.sales_fact.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN ingest.sales_fact.product_id IS 'Canonical product id (external reference; see OD-02).';
COMMENT ON COLUMN ingest.sales_fact.sales_date IS 'Canonical `business_date`, computed by the ERP in the tenant timezone (D-04, OD-03).';
COMMENT ON COLUMN ingest.sales_fact.units_sold IS 'Gross units sold that day (Canonical `units_sold`).';
COMMENT ON COLUMN ingest.sales_fact.units_returned IS 'Units returned that day (Canonical `units_returned`).';
COMMENT ON COLUMN ingest.sales_fact.net_units IS 'units_sold - units_returned (Canonical `net_units`). Demand = net units (D-06). May be negative only if returns exceed sales that day; the feature label clamps it at 0.';
COMMENT ON COLUMN ingest.sales_fact.day_status IS 'Canonical `day_status`: open (the ERP day is still running) | closed.';
COMMENT ON COLUMN ingest.sales_fact.is_complete IS 'Canonical `complete`. false = the ERP cannot vouch for this total; the day is excluded from training (D-06).';
COMMENT ON COLUMN ingest.sales_fact.source_updated_at IS 'Canonical `updated_at` (ERP clock). The upsert only replaces the row when the incoming value is >= this one.';
COMMENT ON COLUMN ingest.sales_fact.source_mode IS 'poll (short-interval incremental poll) | reconcile (nightly re-read of the last N days) | backfill (manual range).';
COMMENT ON COLUMN ingest.sales_fact.polled_at IS 'When the Brain last read this row from Canonical (UTC).';
COMMENT ON COLUMN ingest.sales_fact.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.sales_fact.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_sales_fact_set_updated_at BEFORE UPDATE ON ingest.sales_fact FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- ingest.sales_day_coverage ----
CREATE TABLE ingest.sales_day_coverage (
    tenant_id UUID NOT NULL,
    business_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    verified_via TEXT,
    verified_at TIMESTAMPTZ,
    gap_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_sales_day_coverage PRIMARY KEY (tenant_id, business_date),
    CONSTRAINT ck_sales_day_coverage__status CHECK (status IN ('open','complete','gap')),
    CONSTRAINT ck_sales_day_coverage__verified_via CHECK (verified_via IS NULL OR verified_via IN ('reconcile','backfill')),
    CONSTRAINT ck_sales_day_coverage__gap_reason CHECK (gap_reason IS NULL OR gap_reason IN ('erp_incomplete','canonical_unavailable','validation_failures','unknown')),
    CONSTRAINT ck_sales_day_coverage__complete_verified CHECK (status <> 'complete' OR (verified_at IS NOT NULL AND verified_via IS NOT NULL)),
    CONSTRAINT ck_sales_day_coverage__gap_reason_required CHECK (status <> 'gap' OR gap_reason IS NOT NULL)
);
CREATE INDEX ix_sales_day_coverage__tenant_status_date ON ingest.sales_day_coverage (tenant_id, status, business_date);
COMMENT ON TABLE ingest.sales_day_coverage IS 'Per tenant-day statement of whether Brain sales data for that day is authoritative. Lets the feature job distinguish a TRUE zero-sales day from a MISSING day (source rule: never treat missing days as zero silently).';
COMMENT ON COLUMN ingest.sales_day_coverage.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN ingest.sales_day_coverage.business_date IS 'Business date (tenant timezone).';
COMMENT ON COLUMN ingest.sales_day_coverage.status IS 'open (ERP day still running) | complete (closed, fully read, ERP vouches for it) | gap (known hole: excluded from training).';
COMMENT ON COLUMN ingest.sales_day_coverage.verified_via IS 'reconcile | backfill. Required when complete.';
COMMENT ON COLUMN ingest.sales_day_coverage.verified_at IS 'When the day was verified against Canonical.';
COMMENT ON COLUMN ingest.sales_day_coverage.gap_reason IS 'erp_incomplete | canonical_unavailable | validation_failures | unknown. Required when gap.';
COMMENT ON COLUMN ingest.sales_day_coverage.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN ingest.sales_day_coverage.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_sales_day_coverage_set_updated_at BEFORE UPDATE ON ingest.sales_day_coverage FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- feat.calendar_day ----
CREATE TABLE feat.calendar_day (
    tenant_id UUID NOT NULL,
    calendar_date DATE NOT NULL,
    is_holiday BOOLEAN NOT NULL DEFAULT false,
    holiday_name TEXT,
    is_ramadan BOOLEAN NOT NULL DEFAULT false,
    is_flu_season BOOLEAN NOT NULL DEFAULT false,
    source TEXT NOT NULL DEFAULT 'seed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_calendar_day PRIMARY KEY (tenant_id, calendar_date),
    CONSTRAINT ck_calendar_day__holiday_name CHECK (holiday_name IS NULL OR is_holiday),
    CONSTRAINT ck_calendar_day__source CHECK (source IN ('seed','manual'))
);
COMMENT ON TABLE feat.calendar_day IS 'Known-in-advance calendar attributes (holiday, Ramadan, flu season) per tenant calendar. Source of the calendar features copied into `feature_daily`.';
COMMENT ON COLUMN feat.calendar_day.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN feat.calendar_day.calendar_date IS 'Calendar date in the tenant business timezone.';
COMMENT ON COLUMN feat.calendar_day.is_holiday IS 'Official holiday.';
COMMENT ON COLUMN feat.calendar_day.holiday_name IS 'Holiday label, when is_holiday.';
COMMENT ON COLUMN feat.calendar_day.is_ramadan IS 'Within Ramadan.';
COMMENT ON COLUMN feat.calendar_day.is_flu_season IS 'Within the configured cold/flu season window.';
COMMENT ON COLUMN feat.calendar_day.source IS 'seed (generated by seed script) | manual (curated override).';
COMMENT ON COLUMN feat.calendar_day.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN feat.calendar_day.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_calendar_day_set_updated_at BEFORE UPDATE ON feat.calendar_day FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

-- ---- feat.feature_daily ----
CREATE TABLE feat.feature_daily (
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    feature_date DATE NOT NULL,
    feature_set_version SMALLINT NOT NULL,
    y_units NUMERIC(14,3),
    y_status TEXT NOT NULL,
    is_outlier BOOLEAN NOT NULL DEFAULT false,
    history_days INTEGER NOT NULL DEFAULT 0,
    n_obs_7 SMALLINT NOT NULL,
    n_obs_28 SMALLINT NOT NULL,
    lag_1 NUMERIC(14,3),
    lag_7 NUMERIC(14,3),
    lag_14 NUMERIC(14,3),
    lag_28 NUMERIC(14,3),
    roll_mean_7 NUMERIC(14,4),
    roll_mean_14 NUMERIC(14,4),
    roll_mean_28 NUMERIC(14,4),
    roll_std_7 NUMERIC(14,4),
    roll_std_28 NUMERIC(14,4),
    dow SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    day_of_month SMALLINT NOT NULL,
    week_of_year SMALLINT NOT NULL,
    is_holiday BOOLEAN NOT NULL DEFAULT false,
    is_ramadan BOOLEAN NOT NULL DEFAULT false,
    is_flu_season BOOLEAN NOT NULL DEFAULT false,
    is_promotion BOOLEAN,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    compute_mode TEXT NOT NULL,
    inputs_max_updated_at TIMESTAMPTZ,
    CONSTRAINT pk_feature_daily PRIMARY KEY (tenant_id, product_id, feature_date),
    CONSTRAINT ck_feature_daily__version CHECK (feature_set_version > 0),
    CONSTRAINT ck_feature_daily__y_status CHECK (y_status IN ('observed','zero_filled','missing','open','future')),
    CONSTRAINT ck_feature_daily__y_consistency CHECK ((y_status IN ('observed','zero_filled')) = (y_units IS NOT NULL)),
    CONSTRAINT ck_feature_daily__zero_filled CHECK (y_status <> 'zero_filled' OR y_units = 0),
    CONSTRAINT ck_feature_daily__y_nonneg CHECK (y_units IS NULL OR y_units >= 0),
    CONSTRAINT ck_feature_daily__history_nonneg CHECK (history_days >= 0),
    CONSTRAINT ck_feature_daily__n_obs_7 CHECK (n_obs_7 BETWEEN 0 AND 7),
    CONSTRAINT ck_feature_daily__n_obs_28 CHECK (n_obs_28 BETWEEN 0 AND 28),
    CONSTRAINT ck_feature_daily__dow CHECK (dow BETWEEN 0 AND 6),
    CONSTRAINT ck_feature_daily__month CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT ck_feature_daily__dom CHECK (day_of_month BETWEEN 1 AND 31),
    CONSTRAINT ck_feature_daily__woy CHECK (week_of_year BETWEEN 1 AND 53),
    CONSTRAINT ck_feature_daily__compute_mode CHECK (compute_mode IN ('incremental','nightly_full','backfill'))
);
CREATE INDEX ix_feature_daily__tenant_date ON feat.feature_daily (tenant_id, feature_date);
COMMENT ON TABLE feat.feature_daily IS 'One wide, typed feature row per (tenant, product, day). Single table serving training, backtesting, anomaly scoring and inference through `FeatureStore.get_features(product_id, date)`. Feature row for day d uses information from days < d only plus known-in-advance calendar data.';
COMMENT ON COLUMN feat.feature_daily.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN feat.feature_daily.product_id IS 'Canonical product id (external reference).';
COMMENT ON COLUMN feat.feature_daily.feature_date IS 'Day the features describe/predict (business date).';
COMMENT ON COLUMN feat.feature_daily.feature_set_version IS 'Version of the feature definition that produced the row. Models record the version they were trained on; inference refuses a mismatch.';
COMMENT ON COLUMN feat.feature_daily.y_units IS 'LABEL: realised demand on feature_date = GREATEST(sales_fact.net_units, 0). NULL unless y_status is observed or zero_filled. Never a model input.';
COMMENT ON COLUMN feat.feature_daily.y_status IS 'observed (sales_fact row on a complete day) | zero_filled (no row on a complete day = true zero) | missing (day not complete) | open (current day) | future.';
COMMENT ON COLUMN feat.feature_daily.is_outlier IS 'Outlier flag (marked, never deleted; training winsorises, anomaly detector still sees it).';
COMMENT ON COLUMN feat.feature_daily.history_days IS 'Count of complete days (observed or zero_filled) before feature_date since the product''s first sale. Drives cold-start routing.';
COMMENT ON COLUMN feat.feature_daily.n_obs_7 IS 'Complete days inside the trailing 7-day window (0..7).';
COMMENT ON COLUMN feat.feature_daily.n_obs_28 IS 'Complete days inside the trailing 28-day window (0..28).';
COMMENT ON COLUMN feat.feature_daily.lag_1 IS 'Units on feature_date - 1; NULL if that day is not complete.';
COMMENT ON COLUMN feat.feature_daily.lag_7 IS 'Units on feature_date - 7.';
COMMENT ON COLUMN feat.feature_daily.lag_14 IS 'Units on feature_date - 14.';
COMMENT ON COLUMN feat.feature_daily.lag_28 IS 'Units on feature_date - 28.';
COMMENT ON COLUMN feat.feature_daily.roll_mean_7 IS 'Trailing 7-day mean over complete days; NULL if n_obs_7 < 5.';
COMMENT ON COLUMN feat.feature_daily.roll_mean_14 IS 'Trailing 14-day mean; NULL if fewer than 10 complete days.';
COMMENT ON COLUMN feat.feature_daily.roll_mean_28 IS 'Trailing 28-day mean; NULL if n_obs_28 < 21.';
COMMENT ON COLUMN feat.feature_daily.roll_std_7 IS 'Trailing 7-day sample std dev.';
COMMENT ON COLUMN feat.feature_daily.roll_std_28 IS 'Trailing 28-day sample std dev.';
COMMENT ON COLUMN feat.feature_daily.dow IS 'Day of week, Monday=0 .. Sunday=6.';
COMMENT ON COLUMN feat.feature_daily.month IS 'Month 1..12.';
COMMENT ON COLUMN feat.feature_daily.day_of_month IS '1..31.';
COMMENT ON COLUMN feat.feature_daily.week_of_year IS 'ISO week 1..53.';
COMMENT ON COLUMN feat.feature_daily.is_holiday IS 'Copied from calendar_day.';
COMMENT ON COLUMN feat.feature_daily.is_ramadan IS 'Copied from calendar_day.';
COMMENT ON COLUMN feat.feature_daily.is_flu_season IS 'Copied from calendar_day.';
COMMENT ON COLUMN feat.feature_daily.is_promotion IS 'NULL = unknown. The Canonical contract has no promotion data in the MVP, so this is always NULL (documented limitation, guide section 7.8).';
COMMENT ON COLUMN feat.feature_daily.computed_at IS 'When this row was (re)computed (UTC).';
COMMENT ON COLUMN feat.feature_daily.compute_mode IS 'incremental | nightly_full | backfill.';
COMMENT ON COLUMN feat.feature_daily.inputs_max_updated_at IS 'max(sales_fact.updated_at) over the rows used. Row is stale if any input row is newer.';


-- ==================== 0003_intel.sql ====================
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


-- ==================== 0004_audit_agent.sql ====================
-- 0004_audit_agent: audit + agent schemas

-- ---- audit.llm_usage ----
CREATE TABLE audit.llm_usage (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_route TEXT,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    tokens_cached_in INTEGER,
    estimated_cost_usd NUMERIC(12,6) NOT NULL,
    pricing_version TEXT,
    latency_ms INTEGER NOT NULL,
    cache_status TEXT NOT NULL DEFAULT 'miss',
    outcome TEXT NOT NULL,
    error_code TEXT,
    schema_valid BOOLEAN,
    prompt_sha256 CHAR(64),
    actor_id TEXT,
    session_id UUID,
    tool_step SMALLINT,
    trace_id CHAR(32) NOT NULL,
    span_id CHAR(16),
    CONSTRAINT pk_llm_usage PRIMARY KEY (id),
    CONSTRAINT uq_llm_usage__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_llm_usage__purpose CHECK (purpose IN ('explanation','assistant_chat','agent_reasoning','briefing','other')),
    CONSTRAINT ck_llm_usage__route CHECK (model_route IS NULL OR model_route IN ('template','small','large')),
    CONSTRAINT ck_llm_usage__tokens CHECK (tokens_in >= 0 AND tokens_out >= 0 AND (tokens_cached_in IS NULL OR (tokens_cached_in >= 0 AND tokens_cached_in <= tokens_in))),
    CONSTRAINT ck_llm_usage__cost CHECK (estimated_cost_usd >= 0),
    CONSTRAINT ck_llm_usage__latency CHECK (latency_ms >= 0),
    CONSTRAINT ck_llm_usage__cache_status CHECK (cache_status IN ('miss','hit','not_cacheable')),
    CONSTRAINT ck_llm_usage__outcome CHECK (outcome IN ('success','error','timeout','invalid_output','refused')),
    CONSTRAINT ck_llm_usage__span_format CHECK (span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'),
    CONSTRAINT ck_llm_usage__prompt_sha256_format CHECK (prompt_sha256 IS NULL OR prompt_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_llm_usage__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_llm_usage__tenant_occurred ON audit.llm_usage (tenant_id, occurred_at);
CREATE INDEX ix_llm_usage__tenant_purpose_occurred ON audit.llm_usage (tenant_id, purpose, occurred_at);
CREATE INDEX ix_llm_usage__trace ON audit.llm_usage (trace_id);
COMMENT ON TABLE audit.llm_usage IS 'One row per LLM layer call (and per cache hit that avoided a call): provider, model, prompt version, tokens, estimated cost, latency, outcome, trace. Feeds `/brain/admin/cost`. Stores NO prompt or completion text.';
COMMENT ON COLUMN audit.llm_usage.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN audit.llm_usage.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN audit.llm_usage.occurred_at IS 'Call time (UTC).';
COMMENT ON COLUMN audit.llm_usage.purpose IS 'explanation | assistant_chat | agent_reasoning | briefing | other.';
COMMENT ON COLUMN audit.llm_usage.provider IS 'LLM provider id (provider is an open decision, OD-18).';
COMMENT ON COLUMN audit.llm_usage.model IS 'Exact model identifier returned/used.';
COMMENT ON COLUMN audit.llm_usage.model_route IS 'template | small | large (model routing decision).';
COMMENT ON COLUMN audit.llm_usage.prompt_name IS 'Prompt file name from `llm/prompts/`.';
COMMENT ON COLUMN audit.llm_usage.prompt_version IS 'Prompt version (git-tracked).';
COMMENT ON COLUMN audit.llm_usage.tokens_in IS 'Input tokens.';
COMMENT ON COLUMN audit.llm_usage.tokens_out IS 'Output tokens.';
COMMENT ON COLUMN audit.llm_usage.tokens_cached_in IS 'Input tokens served from the provider''s prompt cache, if reported.';
COMMENT ON COLUMN audit.llm_usage.estimated_cost_usd IS 'Estimated cost in USD (micro-dollar precision).';
COMMENT ON COLUMN audit.llm_usage.pricing_version IS 'Price table used for the estimate.';
COMMENT ON COLUMN audit.llm_usage.latency_ms IS 'End-to-end latency.';
COMMENT ON COLUMN audit.llm_usage.cache_status IS 'miss | hit (response cache, zero tokens) | not_cacheable.';
COMMENT ON COLUMN audit.llm_usage.outcome IS 'success | error | timeout | invalid_output | refused.';
COMMENT ON COLUMN audit.llm_usage.error_code IS 'Short error code when outcome is not success.';
COMMENT ON COLUMN audit.llm_usage.schema_valid IS 'Whether the structured output validated against its JSON schema.';
COMMENT ON COLUMN audit.llm_usage.prompt_sha256 IS 'Hash of the rendered prompt (dedupe/cache analysis). The text itself is never stored.';
COMMENT ON COLUMN audit.llm_usage.actor_id IS 'JWT sub of the requesting user (pseudonymous), for per-user cost.';
COMMENT ON COLUMN audit.llm_usage.session_id IS 'agent_session id. SOFT reference (no FK): usage rows outlive sessions.';
COMMENT ON COLUMN audit.llm_usage.tool_step IS 'Step number inside an agent run.';
COMMENT ON COLUMN audit.llm_usage.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN audit.llm_usage.span_id IS 'W3C span-id.';
CREATE TRIGGER trg_llm_usage_forbid_update BEFORE UPDATE ON audit.llm_usage FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- audit.audit_log ----
CREATE TABLE audit.audit_log (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    seq BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    tenant_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    on_behalf_of_actor_id TEXT,
    approved_by_actor_id TEXT,
    tool_name TEXT,
    subject_type TEXT,
    subject_id UUID,
    arguments_sha256 CHAR(64),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    trace_id CHAR(32) NOT NULL,
    span_id CHAR(16),
    request_id TEXT,
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT uq_audit_log__seq UNIQUE (seq),
    CONSTRAINT ck_audit_log__event_type CHECK (event_type ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$'),
    CONSTRAINT ck_audit_log__outcome CHECK (outcome IN ('success','failure','denied','info')),
    CONSTRAINT ck_audit_log__actor_type CHECK (actor_type IN ('user','agent','system')),
    CONSTRAINT ck_audit_log__actor_required CHECK (actor_type = 'system' OR actor_id IS NOT NULL),
    CONSTRAINT ck_audit_log__subject_pair CHECK ((subject_type IS NULL) = (subject_id IS NULL)),
    CONSTRAINT ck_audit_log__details_size CHECK (octet_length(details::text) <= 8192),
    CONSTRAINT ck_audit_log__span_format CHECK (span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'),
    CONSTRAINT ck_audit_log__arguments_sha256_format CHECK (arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_audit_log__details_type CHECK (jsonb_typeof(details) = 'object'),
    CONSTRAINT ck_audit_log__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_audit_log__tenant_occurred ON audit.audit_log (tenant_id, occurred_at);
CREATE INDEX ix_audit_log__trace ON audit.audit_log (trace_id);
CREATE INDEX ix_audit_log__tenant_actor_occurred ON audit.audit_log (tenant_id, actor_id, occurred_at);
CREATE INDEX ix_audit_log__subject ON audit.audit_log (tenant_id, subject_type, subject_id, occurred_at);
COMMENT ON TABLE audit.audit_log IS 'Brain audit trail: who proposed, approved/rejected, executed, which tool, which payload fingerprint, outcome, trace. Distinct from `erp_db.AuditLog` (human changes in the ERP). Append-only.';
COMMENT ON COLUMN audit.audit_log.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN audit.audit_log.seq IS 'Monotonic ordering / keyset-pagination key.';
COMMENT ON COLUMN audit.audit_log.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN audit.audit_log.occurred_at IS 'Event time (UTC).';
COMMENT ON COLUMN audit.audit_log.event_type IS 'Dotted lowercase vocabulary, e.g. proposal.created, proposal.approved, proposal.rejected, execution.succeeded, tool.denied, model.status_changed.';
COMMENT ON COLUMN audit.audit_log.outcome IS 'success | failure | denied | info.';
COMMENT ON COLUMN audit.audit_log.actor_type IS 'user | agent | system.';
COMMENT ON COLUMN audit.audit_log.actor_id IS 'JWT sub for users; session id for agent; component name for system.';
COMMENT ON COLUMN audit.audit_log.on_behalf_of_actor_id IS 'User on whose behalf an agent acted.';
COMMENT ON COLUMN audit.audit_log.approved_by_actor_id IS 'Approver (JWT sub) when relevant.';
COMMENT ON COLUMN audit.audit_log.tool_name IS 'Registry tool name when relevant.';
COMMENT ON COLUMN audit.audit_log.subject_type IS 'Kind of Brain object the event concerns (action_proposal, model_registry, ...).';
COMMENT ON COLUMN audit.audit_log.subject_id IS 'Brain object id. SOFT reference (polymorphic, no FK): audit rows must outlive subjects.';
COMMENT ON COLUMN audit.audit_log.arguments_sha256 IS 'Fingerprint of the exact action payload involved.';
COMMENT ON COLUMN audit.audit_log.details IS 'Sanitised allow-listed context (status from/to, model_version, rule_version, result summary).';
COMMENT ON COLUMN audit.audit_log.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN audit.audit_log.span_id IS 'W3C span-id.';
COMMENT ON COLUMN audit.audit_log.request_id IS 'HTTP request id.';
CREATE TRIGGER trg_audit_log_forbid_update_delete BEFORE UPDATE OR DELETE ON audit.audit_log FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update_delete();
CREATE TRIGGER trg_audit_log_forbid_truncate BEFORE TRUNCATE ON audit.audit_log FOR EACH STATEMENT EXECUTE FUNCTION public.brain_forbid_truncate();

-- ---- agent.agent_session ----
CREATE TABLE agent.agent_session (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_actor_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    allowed_tools TEXT[] NOT NULL DEFAULT '{}'::text[],
    max_writes SMALLINT NOT NULL DEFAULT 3,
    write_proposals_count SMALLINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_agent_session PRIMARY KEY (id),
    CONSTRAINT uq_agent_session__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_agent_session__user CHECK (char_length(user_actor_id) BETWEEN 1 AND 128),
    CONSTRAINT ck_agent_session__status CHECK (status IN ('active','closed','expired')),
    CONSTRAINT ck_agent_session__state_size CHECK (octet_length(state::text) <= 16384),
    CONSTRAINT ck_agent_session__max_writes CHECK (max_writes BETWEEN 0 AND 20),
    CONSTRAINT ck_agent_session__write_cap CHECK (write_proposals_count >= 0 AND write_proposals_count <= max_writes),
    CONSTRAINT ck_agent_session__state_type CHECK (jsonb_typeof(state) = 'object'),
    CONSTRAINT ck_agent_session__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_agent_session__user_activity ON agent.agent_session (tenant_id, user_actor_id, last_activity_at);
CREATE INDEX ix_agent_session__active_expiry ON agent.agent_session (tenant_id, expires_at) WHERE status = 'active';
COMMENT ON TABLE agent.agent_session IS 'Conversation/agent session: owner, small working context, tool allow-list, write cap, expiry. Survives a browser refresh. Session-scoped memory only (no cross-session memory in MVP).';
COMMENT ON COLUMN agent.agent_session.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_session.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_session.user_actor_id IS 'JWT `sub` of the user who owns the session.';
COMMENT ON COLUMN agent.agent_session.status IS 'active | closed | expired.';
COMMENT ON COLUMN agent.agent_session.state IS 'Compact working context (focused product ids, last intent). No PII, no raw ERP rows. <= 16 KB.';
COMMENT ON COLUMN agent.agent_session.allowed_tools IS 'Per-session tool allow-list (guardrail).';
COMMENT ON COLUMN agent.agent_session.max_writes IS 'Maximum write proposals per session (source example: 3).';
COMMENT ON COLUMN agent.agent_session.write_proposals_count IS 'Write proposals created so far; the CHECK against max_writes makes the cap a database guarantee.';
COMMENT ON COLUMN agent.agent_session.started_at IS 'Session start (UTC).';
COMMENT ON COLUMN agent.agent_session.last_activity_at IS 'Last turn (UTC).';
COMMENT ON COLUMN agent.agent_session.expires_at IS 'Inactivity expiry (UTC).';
COMMENT ON COLUMN agent.agent_session.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN agent.agent_session.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.agent_session.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN agent.agent_session.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_agent_session_set_updated_at BEFORE UPDATE ON agent.agent_session FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_agent_session_guard_update BEFORE UPDATE ON agent.agent_session FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'state', 'allowed_tools', 'max_writes', 'write_proposals_count', 'last_activity_at', 'expires_at', 'row_version', 'updated_at');

-- ---- agent.agent_message ----
CREATE TABLE agent.agent_message (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    pii_scrubbed BOOLEAN NOT NULL DEFAULT false,
    structured JSONB,
    llm_usage_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_agent_message PRIMARY KEY (id),
    CONSTRAINT uq_agent_message__session_turn UNIQUE (session_id, turn_index),
    CONSTRAINT ck_agent_message__turn CHECK (turn_index >= 0),
    CONSTRAINT ck_agent_message__role CHECK (role IN ('user','assistant','tool')),
    CONSTRAINT ck_agent_message__content_len CHECK (char_length(content) <= 4000),
    CONSTRAINT ck_agent_message__scrubbed CHECK (pii_scrubbed),
    CONSTRAINT ck_agent_message__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_agent_message__structured_type CHECK (structured IS NULL OR jsonb_typeof(structured) = 'object'),
    CONSTRAINT fk_agent_message__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_agent_message__tenant_expires ON agent.agent_message (tenant_id, expires_at);
CREATE INDEX ix_agent_message__tenant_session ON agent.agent_message (tenant_id, session_id);
COMMENT ON TABLE agent.agent_message IS 'Recent conversation turns (the ''last N messages'' memory). Content is PII-scrubbed and size-bounded; rows carry their own expiry and are hard-deleted on schedule.';
COMMENT ON COLUMN agent.agent_message.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_message.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_message.session_id IS 'Owning session.';
COMMENT ON COLUMN agent.agent_message.turn_index IS '0-based turn number within the session.';
COMMENT ON COLUMN agent.agent_message.role IS 'user | assistant | tool.';
COMMENT ON COLUMN agent.agent_message.content IS 'Scrubbed text (<= 4000 chars). Assistant turns hold the human-readable explanation.';
COMMENT ON COLUMN agent.agent_message.pii_scrubbed IS 'Writer''s attestation that the PII scrubber ran. CHECK forces TRUE.';
COMMENT ON COLUMN agent.agent_message.structured IS 'Typed Explanation JSON or compact tool-result summary (never raw ERP rows).';
COMMENT ON COLUMN agent.agent_message.llm_usage_id IS 'audit.llm_usage row for assistant turns (soft reference, no FK).';
COMMENT ON COLUMN agent.agent_message.created_at IS 'Turn time (UTC).';
COMMENT ON COLUMN agent.agent_message.expires_at IS 'Purge time for this turn (UTC).';
CREATE TRIGGER trg_agent_message_forbid_update BEFORE UPDATE ON agent.agent_message FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- agent.action_proposal ----
CREATE TABLE agent.action_proposal (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID,
    requested_by_actor_id TEXT,
    proposed_by TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    arguments JSONB NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT true,
    policy_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    recommendation_id UUID,
    risk_assessment_id UUID,
    llm_usage_id UUID,
    idempotency_key UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_action_proposal PRIMARY KEY (id),
    CONSTRAINT uq_action_proposal__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_action_proposal__tenant_idempotency UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT uq_action_proposal__id_hash UNIQUE (tenant_id, id, arguments_sha256),
    CONSTRAINT uq_action_proposal__id_idem UNIQUE (tenant_id, id, idempotency_key),
    CONSTRAINT ck_action_proposal__proposed_by CHECK (proposed_by IN ('rules','agent')),
    CONSTRAINT ck_action_proposal__agent_context CHECK (proposed_by <> 'agent' OR (session_id IS NOT NULL AND requested_by_actor_id IS NOT NULL)),
    CONSTRAINT ck_action_proposal__requires_approval CHECK (requires_approval),
    CONSTRAINT ck_action_proposal__status CHECK (status IN ('pending','approved','rejected','expired','cancelled','executing','succeeded','failed')),
    CONSTRAINT ck_action_proposal__tool_len CHECK (char_length(tool_name) BETWEEN 1 AND 100),
    CONSTRAINT ck_action_proposal__reason_len CHECK (char_length(reason) BETWEEN 1 AND 500),
    CONSTRAINT ck_action_proposal__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_action_proposal__args_size CHECK (octet_length(arguments::text) <= 32768),
    CONSTRAINT ck_action_proposal__arguments_type CHECK (jsonb_typeof(arguments) = 'object'),
    CONSTRAINT ck_action_proposal__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_proposal__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_proposal__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__recommendation FOREIGN KEY (tenant_id, recommendation_id) REFERENCES intel.recommendation (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__risk_assessment FOREIGN KEY (tenant_id, risk_assessment_id) REFERENCES intel.risk_assessment (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__llm_usage FOREIGN KEY (tenant_id, llm_usage_id) REFERENCES audit.llm_usage (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_action_proposal__pending ON agent.action_proposal (tenant_id, created_at) WHERE status = 'pending';
CREATE INDEX ix_action_proposal__tenant_session ON agent.action_proposal (tenant_id, session_id, created_at);
CREATE INDEX ix_action_proposal__tenant_requester ON agent.action_proposal (tenant_id, requested_by_actor_id, created_at);
CREATE INDEX ix_action_proposal__tenant_recommendation ON agent.action_proposal (tenant_id, recommendation_id);
CREATE UNIQUE INDEX uq_action_proposal__live_per_recommendation ON agent.action_proposal (tenant_id, recommendation_id) WHERE recommendation_id IS NOT NULL AND status IN ('pending','approved','executing');
COMMENT ON TABLE agent.action_proposal IS 'The immutable proposed write (tool + arguments) awaiting a human decision, plus its lifecycle status. Arguments and their SHA-256 can never change after insert; approvals and executions are cryptographically bound to that hash by composite FKs.';
COMMENT ON COLUMN agent.action_proposal.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_proposal.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_proposal.session_id IS 'Session that produced the proposal. Required when proposed_by = ''agent''; NULL allowed for deterministic rule proposals (D-29).';
COMMENT ON COLUMN agent.action_proposal.requested_by_actor_id IS 'JWT sub of the user who asked for the proposal. Required when proposed_by = ''agent''; NULL allowed for rule proposals created by the system (D-29).';
COMMENT ON COLUMN agent.action_proposal.proposed_by IS 'rules (deterministic, built from a recommendation without the LLM, D-18) | agent (conversational path). Set explicitly; no default (D-29).';
COMMENT ON COLUMN agent.action_proposal.tool_name IS 'Registry tool name (e.g. create_purchase_order).';
COMMENT ON COLUMN agent.action_proposal.tool_version IS 'Registry schema version of the tool, e.g. ''create_purchase_order@1''.';
COMMENT ON COLUMN agent.action_proposal.arguments IS 'Validated arguments exactly as they will be sent. Immutable.';
COMMENT ON COLUMN agent.action_proposal.arguments_sha256 IS 'SHA-256 (lowercase hex) of the RFC 8785 (JCS) canonical JSON of `arguments` (D-13; golden vectors in contracts/fixtures/hash). Approvals bind to it.';
COMMENT ON COLUMN agent.action_proposal.requires_approval IS 'Always TRUE in MVP (every write needs a human).';
COMMENT ON COLUMN agent.action_proposal.policy_version IS 'Static policy version that returned require-approval.';
COMMENT ON COLUMN agent.action_proposal.reason IS 'Templated human-readable reason (<= 500 chars), e.g. ''high stockout risk (cover 1.7d < lead time 5d)''. Generated by code, not by the LLM.';
COMMENT ON COLUMN agent.action_proposal.recommendation_id IS 'Recommendation the proposal was built from.';
COMMENT ON COLUMN agent.action_proposal.risk_assessment_id IS 'Risk assessment behind it. This is the API `insight_id` (OD-06).';
COMMENT ON COLUMN agent.action_proposal.llm_usage_id IS 'LLM call that proposed the tool call (which model proposed it).';
COMMENT ON COLUMN agent.action_proposal.idempotency_key IS 'Generated once at proposal creation; sent as `Idempotency-Key` on every execution attempt of this proposal.';
COMMENT ON COLUMN agent.action_proposal.status IS 'pending | approved | rejected | expired | cancelled | executing | succeeded | failed.';
COMMENT ON COLUMN agent.action_proposal.status_changed_at IS 'Last status change (set by trigger).';
COMMENT ON COLUMN agent.action_proposal.expires_at IS 'Approval deadline; after it a pending proposal cannot be approved.';
COMMENT ON COLUMN agent.action_proposal.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN agent.action_proposal.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.action_proposal.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN agent.action_proposal.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_action_proposal_set_updated_at BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_action_proposal_guard_update BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'status_changed_at', 'row_version', 'updated_at');
CREATE TRIGGER trg_action_proposal_forbid_delete BEFORE DELETE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();

-- ---- agent.agent_action ----
CREATE TABLE agent.agent_action (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL,
    turn_index INTEGER,
    tool_name TEXT NOT NULL,
    tool_version TEXT,
    read_only BOOLEAN,
    requires_approval BOOLEAN,
    arguments JSONB,
    arguments_sha256 CHAR(64),
    outcome TEXT NOT NULL,
    proposal_id UUID,
    result_summary JSONB,
    error_code TEXT,
    duration_ms INTEGER,
    llm_usage_id UUID,
    trace_id CHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_agent_action PRIMARY KEY (id),
    CONSTRAINT ck_agent_action__outcome CHECK (outcome IN ('executed','pending_approval','denied_policy','rejected_unknown_tool','rejected_invalid_arguments','rejected_scope','error')),
    CONSTRAINT ck_agent_action__tool_len CHECK (char_length(tool_name) BETWEEN 1 AND 100),
    CONSTRAINT ck_agent_action__pending_has_proposal CHECK ((outcome = 'pending_approval') = (proposal_id IS NOT NULL)),
    CONSTRAINT ck_agent_action__write_args_on_proposal CHECK (proposal_id IS NULL OR arguments IS NULL),
    CONSTRAINT ck_agent_action__unknown_tool CHECK (outcome <> 'rejected_unknown_tool' OR read_only IS NULL),
    CONSTRAINT ck_agent_action__args_size CHECK (arguments IS NULL OR octet_length(arguments::text) <= 8192),
    CONSTRAINT ck_agent_action__duration CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ck_agent_action__arguments_type CHECK (arguments IS NULL OR jsonb_typeof(arguments) = 'object'),
    CONSTRAINT ck_agent_action__arguments_sha256_format CHECK (arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_agent_action__result_summary_type CHECK (result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'),
    CONSTRAINT ck_agent_action__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_agent_action__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_action__action_proposal FOREIGN KEY (tenant_id, proposal_id) REFERENCES agent.action_proposal (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_agent_action__tenant_session_created ON agent.agent_action (tenant_id, session_id, created_at);
CREATE INDEX ix_agent_action__tenant_tool_created ON agent.agent_action (tenant_id, tool_name, created_at);
CREATE INDEX ix_agent_action__trace ON agent.agent_action (trace_id);
CREATE INDEX ix_agent_action__tenant_proposal ON agent.agent_action (tenant_id, proposal_id) WHERE proposal_id IS NOT NULL;
COMMENT ON TABLE agent.agent_action IS 'Log of every tool call the agent attempted, including rejected ones (unknown tool, bad arguments, policy deny). For write tools it only points at the ActionProposal; the authorisation and execution detail live in the proposal/approval/execution tables.';
COMMENT ON COLUMN agent.agent_action.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_action.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_action.session_id IS 'Session.';
COMMENT ON COLUMN agent.agent_action.turn_index IS 'Turn that triggered the call (no FK; messages expire).';
COMMENT ON COLUMN agent.agent_action.tool_name IS 'Tool name as attempted (kept even when not in the registry).';
COMMENT ON COLUMN agent.agent_action.tool_version IS 'Registry version when known.';
COMMENT ON COLUMN agent.agent_action.read_only IS 'Registry flag; NULL for unknown tools.';
COMMENT ON COLUMN agent.agent_action.requires_approval IS 'Registry flag; NULL for unknown tools.';
COMMENT ON COLUMN agent.agent_action.arguments IS 'Arguments for read tools only (<= 8 KB). NULL for write intents - those live on the proposal.';
COMMENT ON COLUMN agent.agent_action.arguments_sha256 IS 'Fingerprint of the arguments.';
COMMENT ON COLUMN agent.agent_action.outcome IS 'executed | pending_approval | denied_policy | rejected_unknown_tool | rejected_invalid_arguments | rejected_scope | error.';
COMMENT ON COLUMN agent.agent_action.proposal_id IS 'Set when outcome is pending_approval.';
COMMENT ON COLUMN agent.agent_action.result_summary IS 'Compact result facts (counts, ids). Never raw rows.';
COMMENT ON COLUMN agent.agent_action.error_code IS 'Short error code.';
COMMENT ON COLUMN agent.agent_action.duration_ms IS 'Tool latency.';
COMMENT ON COLUMN agent.agent_action.llm_usage_id IS 'LLM call that proposed the tool call (soft reference).';
COMMENT ON COLUMN agent.agent_action.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.agent_action.created_at IS 'Call time (UTC).';
CREATE TRIGGER trg_agent_action_forbid_update BEFORE UPDATE ON agent.agent_action FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- agent.action_approval ----
CREATE TABLE agent.action_approval (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_round SMALLINT NOT NULL DEFAULT 1,
    decision TEXT NOT NULL,
    decided_by_actor_id TEXT NOT NULL,
    decider_scopes TEXT[] NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    reason_code TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id CHAR(32) NOT NULL,
    CONSTRAINT pk_action_approval PRIMARY KEY (id),
    CONSTRAINT uq_action_approval__proposal_round UNIQUE (tenant_id, proposal_id, approval_round),
    CONSTRAINT uq_action_approval__id_proposal_hash UNIQUE (tenant_id, id, proposal_id, arguments_sha256),
    CONSTRAINT ck_action_approval__round CHECK (approval_round >= 1),
    CONSTRAINT ck_action_approval__decision CHECK (decision IN ('approved','rejected')),
    CONSTRAINT ck_action_approval__scope CHECK ('agent:approve' = ANY(decider_scopes)),
    CONSTRAINT ck_action_approval__reason_code CHECK (reason_code IS NULL OR reason_code IN ('too_much','wrong_supplier','not_needed','stock_arriving','other')),
    CONSTRAINT ck_action_approval__actor CHECK (char_length(decided_by_actor_id) BETWEEN 1 AND 128),
    CONSTRAINT ck_action_approval__human_actor CHECK (left(decided_by_actor_id, 7) <> 'system:'),
    CONSTRAINT ck_action_approval__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_approval__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_approval__action_proposal FOREIGN KEY (tenant_id, proposal_id, arguments_sha256) REFERENCES agent.action_proposal (tenant_id, id, arguments_sha256) ON DELETE RESTRICT
);
CREATE INDEX ix_action_approval__tenant_actor_decided ON agent.action_approval (tenant_id, decided_by_actor_id, decided_at);
COMMENT ON TABLE agent.action_approval IS 'Immutable human decision (approve or reject) on a specific proposal payload. The composite FK to (proposal id, arguments_sha256) means an approval can only ever exist for the exact payload that was proposed.';
COMMENT ON COLUMN agent.action_approval.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_approval.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_approval.proposal_id IS 'Proposal decided.';
COMMENT ON COLUMN agent.action_approval.approval_round IS '1 for the first decision; 2+ only for a fresh human re-approval after the proposal failed with an unknown outcome (D-43). A round covers the worker''s same-key retries while the proposal is executing; once the proposal is failed, only a new round re-opens it.';
COMMENT ON COLUMN agent.action_approval.decision IS 'approved | rejected.';
COMMENT ON COLUMN agent.action_approval.decided_by_actor_id IS 'Authenticated approver (JWT sub). Never a job actor: CHECK rejects ''system:'' ids (D-45).';
COMMENT ON COLUMN agent.action_approval.decider_scopes IS 'Scopes in the approver''s JWT at decision time (must include agent:approve).';
COMMENT ON COLUMN agent.action_approval.arguments_sha256 IS 'Hash of the payload the approver saw; must equal the proposal''s (composite FK).';
COMMENT ON COLUMN agent.action_approval.reason_code IS 'Optional fixed code for a rejection (no free text, no PII).';
COMMENT ON COLUMN agent.action_approval.decided_at IS 'Decision time (UTC), always the server time of the insert (set by trigger). The approval is valid while now() <= decided_at + 24 h (D-44).';
COMMENT ON COLUMN agent.action_approval.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
CREATE TRIGGER trg_action_approval_forbid_update_delete BEFORE UPDATE OR DELETE ON agent.action_approval FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update_delete();
CREATE TRIGGER trg_action_approval_forbid_truncate BEFORE TRUNCATE ON agent.action_approval FOR EACH STATEMENT EXECUTE FUNCTION public.brain_forbid_truncate();

-- ---- agent.action_execution ----
CREATE TABLE agent.action_execution (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_id UUID NOT NULL,
    attempt_no SMALLINT NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    idempotency_key UUID NOT NULL,
    on_behalf_of_actor_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    outcome_certainty TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    canonical_http_status SMALLINT,
    external_ref_type TEXT,
    external_ref_id TEXT,
    error_code TEXT,
    error_message TEXT,
    result JSONB,
    trace_id CHAR(32) NOT NULL,
    CONSTRAINT pk_action_execution PRIMARY KEY (id),
    CONSTRAINT uq_action_execution__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_action_execution__proposal_attempt UNIQUE (tenant_id, proposal_id, attempt_no),
    CONSTRAINT ck_action_execution__attempt CHECK (attempt_no >= 1),
    CONSTRAINT ck_action_execution__status CHECK (status IN ('started','succeeded','failed')),
    CONSTRAINT ck_action_execution__certainty CHECK (outcome_certainty IS NULL OR outcome_certainty IN ('definitive','unknown')),
    CONSTRAINT ck_action_execution__completion CHECK ((status = 'started') = (completed_at IS NULL)),
    CONSTRAINT ck_action_execution__failed_fields CHECK (status <> 'failed' OR (outcome_certainty IS NOT NULL AND error_code IS NOT NULL)),
    CONSTRAINT ck_action_execution__success_clean CHECK (status <> 'succeeded' OR error_code IS NULL),
    CONSTRAINT ck_action_execution__ref_type CHECK (external_ref_type IS NULL OR external_ref_type IN ('purchase_order')),
    CONSTRAINT ck_action_execution__message_len CHECK (error_message IS NULL OR char_length(error_message) <= 500),
    CONSTRAINT ck_action_execution__duration CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ck_action_execution__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_execution__result_type CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    CONSTRAINT ck_action_execution__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_execution__action_approval FOREIGN KEY (tenant_id, approval_id, proposal_id, arguments_sha256) REFERENCES agent.action_approval (tenant_id, id, proposal_id, arguments_sha256) ON DELETE RESTRICT,
    CONSTRAINT fk_action_execution__action_proposal FOREIGN KEY (tenant_id, proposal_id, idempotency_key) REFERENCES agent.action_proposal (tenant_id, id, idempotency_key) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX uq_action_execution__one_inflight ON agent.action_execution (tenant_id, proposal_id) WHERE status = 'started';
CREATE UNIQUE INDEX uq_action_execution__one_success ON agent.action_execution (tenant_id, proposal_id) WHERE status = 'succeeded';
CREATE INDEX ix_action_execution__tenant_started ON agent.action_execution (tenant_id, started_at);
CREATE INDEX ix_action_execution__trace ON agent.action_execution (trace_id);
COMMENT ON TABLE agent.action_execution IS 'One row per execution attempt of an approved proposal against the Canonical API. Records the ActionResult (success/failed, reason), outcome certainty and the ERP object created. Partial unique indexes make a second concurrent attempt or a second success impossible.';
COMMENT ON COLUMN agent.action_execution.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_execution.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_execution.proposal_id IS 'Proposal executed.';
COMMENT ON COLUMN agent.action_execution.approval_id IS 'Approval that authorised this attempt: always the latest decision round (D-43).';
COMMENT ON COLUMN agent.action_execution.attempt_no IS '1, 2, ... per proposal.';
COMMENT ON COLUMN agent.action_execution.arguments_sha256 IS 'Hash of the payload actually sent; must equal the approved hash (composite FK).';
COMMENT ON COLUMN agent.action_execution.idempotency_key IS 'Same key as the proposal; sent as Idempotency-Key (composite FK).';
COMMENT ON COLUMN agent.action_execution.on_behalf_of_actor_id IS 'User whose JWT scopes were used for the Canonical write.';
COMMENT ON COLUMN agent.action_execution.status IS 'started | succeeded | failed.';
COMMENT ON COLUMN agent.action_execution.outcome_certainty IS 'For failed: definitive (adapter rejected, no ERP write) | unknown (timeout/5xx; the write may have happened).';
COMMENT ON COLUMN agent.action_execution.started_at IS 'Attempt start (UTC).';
COMMENT ON COLUMN agent.action_execution.completed_at IS 'Attempt end (UTC).';
COMMENT ON COLUMN agent.action_execution.duration_ms IS 'Canonical call latency.';
COMMENT ON COLUMN agent.action_execution.canonical_http_status IS 'HTTP status from the Canonical API.';
COMMENT ON COLUMN agent.action_execution.external_ref_type IS 'Kind of ERP object created (purchase_order).';
COMMENT ON COLUMN agent.action_execution.external_ref_id IS 'ERP identifier/number of the created object (e.g. PO #1234).';
COMMENT ON COLUMN agent.action_execution.error_code IS 'Canonical error envelope code.';
COMMENT ON COLUMN agent.action_execution.error_message IS 'Sanitised message (<= 500 chars).';
COMMENT ON COLUMN agent.action_execution.result IS 'ActionResult JSON {status, reason, ...} validated against the ai-output schema.';
COMMENT ON COLUMN agent.action_execution.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
CREATE TRIGGER trg_action_execution_forbid_delete BEFORE DELETE ON agent.action_execution FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();

-- ---- custom guard triggers (created after all agent tables exist) ----
CREATE OR REPLACE FUNCTION agent.guard_proposal_transition() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_latest RECORD;
  v_last RECORD;
  v_ok boolean;
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  -- D-45: a session acting as brain_worker (not superuser) may only expire, or complete an execution.
  IF to_regrole('brain_worker') IS NOT NULL AND pg_has_role(current_user, 'brain_worker', 'MEMBER')
     AND NOT (SELECT r.rolsuper FROM pg_roles r WHERE r.rolname = current_user)
     AND NOT ((OLD.status = 'pending' AND NEW.status = 'expired')
           OR (OLD.status = 'executing' AND NEW.status IN ('succeeded','failed'))) THEN
    RAISE EXCEPTION USING MESSAGE = 'brain_worker may not move action_proposal ' || OLD.status || ' -> ' || NEW.status, ERRCODE = 'insufficient_privilege';
  END IF;
  v_ok := CASE OLD.status
    WHEN 'pending'   THEN NEW.status IN ('approved','rejected','expired','cancelled')
    WHEN 'approved'  THEN NEW.status IN ('executing','cancelled')
    WHEN 'executing' THEN NEW.status IN ('succeeded','failed')
    WHEN 'failed'    THEN NEW.status = 'approved'
    ELSE false END;
  IF NOT v_ok THEN
    RAISE EXCEPTION USING MESSAGE = 'illegal action_proposal transition ' || OLD.status || ' -> ' || NEW.status, ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IN ('approved','rejected') OR (OLD.status = 'approved' AND NEW.status = 'executing') THEN
    SELECT * INTO v_latest FROM agent.action_approval
     WHERE tenant_id = OLD.tenant_id AND proposal_id = OLD.id
     ORDER BY approval_round DESC LIMIT 1;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'status ' || NEW.status || ' requires a decision record', ERRCODE = 'check_violation';
    END IF;
    IF v_latest.decision <> (CASE WHEN NEW.status = 'rejected' THEN 'rejected' ELSE 'approved' END) THEN
      RAISE EXCEPTION USING MESSAGE = 'status ' || NEW.status || ' requires a matching decision record', ERRCODE = 'check_violation';
    END IF;
    -- D-44: an approval is valid while now() <= decided_at + 24 h (decided_at is the server time of that human decision).
    IF NEW.status <> 'rejected' AND now() > v_latest.decided_at + interval '24 hours' THEN
      RAISE EXCEPTION USING MESSAGE = 'approval round ' || v_latest.approval_round || ' expired at ' || (v_latest.decided_at + interval '24 hours')::text, ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF OLD.status = 'pending' AND NEW.status = 'approved' AND now() > OLD.expires_at THEN
    RAISE EXCEPTION USING MESSAGE = 'proposal expired at ' || OLD.expires_at::text, ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'failed' AND NEW.status = 'approved' THEN
    -- Latest attempt and the decision round that authorised it.
    SELECT e.status, e.outcome_certainty, a.approval_round INTO v_last
      FROM agent.action_execution e
      JOIN agent.action_approval a ON a.tenant_id = e.tenant_id AND a.id = e.approval_id
     WHERE e.tenant_id = OLD.tenant_id AND e.proposal_id = OLD.id
     ORDER BY e.attempt_no DESC LIMIT 1;
    IF NOT FOUND OR v_last.status <> 'failed' OR v_last.outcome_certainty IS DISTINCT FROM 'unknown' THEN
      RAISE EXCEPTION 're-approval is only allowed after an attempt with unknown outcome' USING ERRCODE = 'check_violation';
    END IF;
    -- A failed proposal never reuses the approval its last attempt ran under: a new human decision round is required (D-43).
    IF v_latest.approval_round <= v_last.approval_round THEN
      RAISE EXCEPTION USING MESSAGE = 're-approval requires a new decision round after attempt round ' || v_last.approval_round, ERRCODE = 'check_violation';
    END IF;
  END IF;
  NEW.status_changed_at := now();
  RETURN NEW;
END
$fn$;
CREATE TRIGGER trg_action_proposal_transition BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION agent.guard_proposal_transition();
CREATE OR REPLACE FUNCTION agent.guard_approval_insert() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_status text;
  v_expires timestamptz;
BEGIN
  SELECT status, expires_at INTO v_status, v_expires FROM agent.action_proposal
   WHERE tenant_id = NEW.tenant_id AND id = NEW.proposal_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'unknown proposal'; END IF;
  IF NEW.approval_round = 1 AND v_status <> 'pending' THEN
    RAISE EXCEPTION USING MESSAGE = 'first decision requires status pending (is ' || v_status || ')', ERRCODE = 'check_violation';
  END IF;
  IF NEW.approval_round > 1 AND v_status <> 'failed' THEN
    RAISE EXCEPTION USING MESSAGE = 're-approval requires status failed (is ' || v_status || ')', ERRCODE = 'check_violation';
  END IF;
  IF NEW.approval_round = 1 AND NEW.decision = 'approved' AND now() > v_expires THEN
    RAISE EXCEPTION USING MESSAGE = 'proposal expired at ' || v_expires::text, ERRCODE = 'check_violation';
  END IF;
  -- D-44: the 24 h validity window starts at the server time of this decision; a client-supplied value is ignored.
  NEW.decided_at := now();
  RETURN NEW;
END
$fn$;
CREATE TRIGGER trg_action_approval_guard_insert BEFORE INSERT ON agent.action_approval FOR EACH ROW EXECUTE FUNCTION agent.guard_approval_insert();
CREATE OR REPLACE FUNCTION agent.guard_execution() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_mutable text[] := ARRAY['status','outcome_certainty','completed_at','duration_ms','canonical_http_status','external_ref_type','external_ref_id','error_code','error_message','result'];
  v_decided timestamptz;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'started' THEN
      RAISE EXCEPTION 'execution must be inserted as started' USING ERRCODE = 'check_violation';
    END IF;
    SELECT a.decided_at INTO v_decided FROM agent.action_approval a
     WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.approval_id AND a.decision = 'approved';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'execution requires an approved decision' USING ERRCODE = 'check_violation';
    END IF;
    -- D-44: every attempt (first send or worker retry) starts only while its approval is valid.
    IF now() > v_decided + interval '24 hours' THEN
      RAISE EXCEPTION USING MESSAGE = 'approval expired at ' || (v_decided + interval '24 hours')::text, ERRCODE = 'check_violation';
    END IF;
    -- FOR SHARE serialises with guard_approval_insert (FOR UPDATE), so no new round can appear mid-check.
    PERFORM 1 FROM agent.action_proposal p
      WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.proposal_id AND p.status = 'executing' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'execution requires the proposal to be executing' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM agent.action_approval a
                WHERE a.tenant_id = NEW.tenant_id AND a.proposal_id = NEW.proposal_id
                  AND a.approval_round > (SELECT b.approval_round FROM agent.action_approval b
                                           WHERE b.tenant_id = NEW.tenant_id AND b.id = NEW.approval_id)) THEN
      RAISE EXCEPTION 'execution must use the latest decision round' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'started' THEN
    RAISE EXCEPTION 'execution row is final' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status NOT IN ('succeeded','failed') THEN
    RAISE EXCEPTION 'execution may only complete as succeeded or failed' USING ERRCODE = 'check_violation';
  END IF;
  IF (to_jsonb(NEW) - v_mutable) IS DISTINCT FROM (to_jsonb(OLD) - v_mutable) THEN
    RAISE EXCEPTION 'only completion fields of an execution may change' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$fn$;
CREATE TRIGGER trg_action_execution_guard BEFORE INSERT OR UPDATE ON agent.action_execution FOR EACH ROW EXECUTE FUNCTION agent.guard_execution();

-- ---- projection: the source-shaped AgentAction (tool_name, arguments, status, requires_approval, approved_by, result) ----
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


-- ==================== 0005_roles_grants_seed.sql ====================
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


-- ==================== 0006_optional_briefing.sql ====================
-- 0006_optional_briefing: SHOULD-have table, safe to skip

-- ---- intel.briefing ----
CREATE TABLE intel.briefing (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    generated_by TEXT NOT NULL,
    llm_usage_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_briefing PRIMARY KEY (id),
    CONSTRAINT uq_briefing__tenant_date UNIQUE (tenant_id, briefing_date),
    CONSTRAINT ck_briefing__generated_by CHECK (generated_by IN ('template','llm')),
    CONSTRAINT ck_briefing__content_type CHECK (jsonb_typeof(content) = 'object')
);
COMMENT ON TABLE intel.briefing IS 'Cached daily morning briefing (`Explanation` subtype report) built from existing risks and pending proposals. SHOULD-have; the MVP does not depend on it.';
COMMENT ON COLUMN intel.briefing.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.briefing.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.briefing.briefing_date IS 'Business date the briefing is for.';
COMMENT ON COLUMN intel.briefing.content IS 'Structured briefing (top risks, pending approvals, summaries).';
COMMENT ON COLUMN intel.briefing.generated_by IS 'template | llm.';
COMMENT ON COLUMN intel.briefing.llm_usage_id IS 'audit.llm_usage row when an LLM polished the text (soft reference, no FK).';
COMMENT ON COLUMN intel.briefing.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.briefing.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_briefing_set_updated_at BEFORE UPDATE ON intel.briefing FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

GRANT SELECT, INSERT, UPDATE ON intel.briefing TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.briefing TO brain_worker;
GRANT SELECT ON intel.briefing TO brain_readonly;
GRANT SELECT, DELETE ON intel.briefing TO brain_retention;


-- ==================== 0007_tenancy_rls.sql ====================
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


-- ==================== 0008_least_privilege.sql ====================
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
