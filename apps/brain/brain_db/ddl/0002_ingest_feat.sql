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
