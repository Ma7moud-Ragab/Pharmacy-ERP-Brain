"""brain_db SQLModel models (generated from the same schema definition as the DDL).

* One metadata, five PostgreSQL schemas: ingest, feat, intel, agent, audit.
* Constraint/index names match ddl/*.sql exactly so `alembic check` can detect drift.
* Relationships are viewonly + lazy="raise": always load explicitly (selectinload) and write via repositories.
* Business logic does NOT live here. JSONB payload shapes live in contracts_jsonb.py (Pydantic).
* The DDL files are the authoritative migration source; triggers, grants and roles exist only there. Table and column
  comments are repeated here from the same definition so `alembic check` compares them (B6).

Not executed by the author - run `alembic upgrade head` + `alembic check` in a scratch database first.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKeyConstraint,
    Identity, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID as PG_UUID
from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel

# keyword arguments shared by all relationships
RO = {"viewonly": True, "lazy": "raise"}


class BrainBase(SQLModel):
    """Shared base. Pydantic v2 reserves the `model_` prefix; columns such as model_id / model_version / model_family
    are deliberate (the source says `model_version`), so the protected-namespace check is disabled."""

    model_config = ConfigDict(protected_namespaces=())

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")  # MVP single seeded tenant (OD-23)



class SyncCheckpoint(BrainBase, table=True):
    """ingest.sync_checkpoint: Watermark per (tenant, resource) for the short-interval sales poll (`updated_since`), the nightly reconcile and the intraday intelligence window."""

    __tablename__ = "sync_checkpoint"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "resource", name="pk_sync_checkpoint"),
        CheckConstraint("resource ~ '^[a-z][a-z0-9_]*$'", name="ck_sync_checkpoint__resource_format"),
        CheckConstraint("last_status IN ('idle','running','succeeded','failed')", name="ck_sync_checkpoint__last_status"),
        CheckConstraint("consecutive_failures >= 0", name="ck_sync_checkpoint__failures_nonneg"),
        {"schema": "ingest", "comment": "Watermark per (tenant, resource) for the short-interval sales poll (`updated_since`), the nightly reconcile and the intraday intelligence window. One row per resource. This table is the poll checkpoint (D-25)."},
    )

    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    resource: str = Field(sa_column=Column("resource", Text, primary_key=True, nullable=False, comment="Logical job: sales_poll | sales_reconcile | intel_window | feature_nightly_full."))
    high_watermark: Optional[datetime] = Field(default=None, sa_column=Column("high_watermark", DateTime(timezone=True), nullable=True, comment="sales_poll: the SalesPage `high_watermark` of the last poll whose pages were ALL read (never advanced mid-poll); the next poll sends `updated_since = high_watermark - poll_overlap_seconds`. intel_window: max(sales_fact.updated_at) already processed."))
    cursor: Optional[str] = Field(default=None, sa_column=Column("cursor", Text, nullable=True, comment="Opaque pagination cursor for an in-progress paged read."))
    last_status: Optional[str] = Field(default=None, sa_column=Column("last_status", Text, nullable=False, server_default=text("'idle'"), comment="idle | running | succeeded | failed."))
    last_started_at: Optional[datetime] = Field(default=None, sa_column=Column("last_started_at", DateTime(timezone=True), nullable=True, comment="Start of the most recent run."))
    last_finished_at: Optional[datetime] = Field(default=None, sa_column=Column("last_finished_at", DateTime(timezone=True), nullable=True, comment="End of the most recent run."))
    last_error_code: Optional[str] = Field(default=None, sa_column=Column("last_error_code", Text, nullable=True, comment="Short error code of the most recent failure."))
    consecutive_failures: Optional[int] = Field(default=None, sa_column=Column("consecutive_failures", Integer, nullable=False, server_default=text("0"), comment="Reset to 0 on success; drives alerting."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class IngestFailure(BrainBase, table=True):
    """ingest.ingest_failure: Record of a Canonical poll or read the Brain could not process after bounded retries."""

    __tablename__ = "ingest_failure"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ingest_failure"),
        CheckConstraint("failure_kind IN ('schema_validation','canonical_read_failed','normalization_error','other')", name="ck_ingest_failure__kind"),
        CheckConstraint("resource ~ '^[a-z][a-z0-9_]*$'", name="ck_ingest_failure__resource_format"),
        CheckConstraint("status IN ('open','resolved','ignored')", name="ck_ingest_failure__status"),
        CheckConstraint("attempts >= 1", name="ck_ingest_failure__attempts"),
        CheckConstraint("error_message IS NULL OR char_length(error_message) <= 500", name="ck_ingest_failure__message_len"),
        CheckConstraint("resolution IS NULL OR resolution IN ('repolled','fixed','ignored_invalid')", name="ck_ingest_failure__resolution"),
        CheckConstraint("(status = 'open' AND resolved_at IS NULL) OR (status <> 'open' AND resolved_at IS NOT NULL)", name="ck_ingest_failure__resolved_consistency"),
        CheckConstraint("payload_excerpt IS NULL OR jsonb_typeof(payload_excerpt) = 'object'", name="ck_ingest_failure__payload_excerpt_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_ingest_failure__trace_id_format"),
        Index("uq_ingest_failure__open_resource_code", "tenant_id", "resource", "error_code", unique=True, postgresql_where=text("status = 'open'")),
        Index("ix_ingest_failure__tenant_status_failed", "tenant_id", "status", "last_failed_at"),
        {"schema": "ingest", "comment": "Record of a Canonical poll or read the Brain could not process after bounded retries. One open row per (resource, error_code); repeats bump `attempts`. Recovery is the next successful poll or the nightly reconcile, never payload replay."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    failure_kind: str = Field(sa_column=Column("failure_kind", Text, nullable=False, comment="schema_validation | canonical_read_failed | normalization_error | other."))
    resource: str = Field(sa_column=Column("resource", Text, nullable=False, comment="Job that failed, e.g. sales_poll, sales_reconcile, inventory_read."))
    error_code: str = Field(sa_column=Column("error_code", Text, nullable=False, comment="Stable machine-readable error code."))
    error_message: Optional[str] = Field(default=None, sa_column=Column("error_message", Text, nullable=True, comment="Sanitised message (<= 500 chars). Never contains customer data."))
    payload_excerpt: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("payload_excerpt", JSONB, nullable=True, comment="Allow-listed keys only (schema, version, product_ids, business_dates, http_status). No customer fields."))
    attempts: Optional[int] = Field(default=None, sa_column=Column("attempts", Integer, nullable=False, server_default=text("1"), comment="Failed attempts folded into this open row."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'open'"), comment="open | resolved | ignored."))
    first_failed_at: Optional[datetime] = Field(default=None, sa_column=Column("first_failed_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="First failure time."))
    last_failed_at: Optional[datetime] = Field(default=None, sa_column=Column("last_failed_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Most recent failure time."))
    resolved_at: Optional[datetime] = Field(default=None, sa_column=Column("resolved_at", DateTime(timezone=True), nullable=True, comment="When closed."))
    resolved_by: Optional[str] = Field(default=None, sa_column=Column("resolved_by", Text, nullable=True, comment="Actor id (JWT sub) or job name that closed it."))
    resolution: Optional[str] = Field(default=None, sa_column=Column("resolution", Text, nullable=True, comment="repolled | fixed | ignored_invalid."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class CanonicalCache(BrainBase, table=True):
    """ingest.canonical_cache: Local durable cache of validated Canonical JSON (Product, InventoryItem, Supplier, optionally PurchaseOrder) with `synced_at`."""

    __tablename__ = "canonical_cache"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_canonical_cache"),
        UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_canonical_cache__tenant_entity"),
        CheckConstraint("entity_type IN ('product','inventory_item','supplier','purchase_order')", name="ck_canonical_cache__entity_type"),
        CheckConstraint("char_length(entity_id) BETWEEN 1 AND 200", name="ck_canonical_cache__entity_id_len"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_canonical_cache__payload_type"),
        CheckConstraint("payload_sha256 ~ '^[0-9a-f]{64}$'", name="ck_canonical_cache__payload_sha256_format"),
        Index("ix_canonical_cache__tenant_type_synced", "tenant_id", "entity_type", "synced_at"),
        {"schema": "ingest", "comment": "Local durable cache of validated Canonical JSON (Product, InventoryItem, Supplier, optionally PurchaseOrder) with `synced_at`. NOT a source of truth: it avoids repeated Canonical reads and holds supplier lead times and product attributes needed by the engines."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    entity_type: str = Field(sa_column=Column("entity_type", Text, nullable=False, comment="product | inventory_item | supplier | purchase_order."))
    entity_id: str = Field(sa_column=Column("entity_id", Text, nullable=False, comment="Canonical identifier. product/supplier: UUID string. inventory_item: '<product_id>|<location_id>'."))
    schema_name: str = Field(sa_column=Column("schema_name", Text, nullable=False, comment="Canonical schema name, e.g. 'canonical.InventoryItem'."))
    schema_version: str = Field(sa_column=Column("schema_version", Text, nullable=False, comment="Canonical schema `version`, e.g. '1.0'."))
    payload: Dict[str, Any] = Field(sa_column=Column("payload", JSONB, nullable=False, comment="Validated canonical payload exactly as received (after Pydantic validation)."))
    payload_sha256: str = Field(sa_column=Column("payload_sha256", CHAR(64), nullable=False, comment="SHA-256 of the canonical-serialised payload; cheap change detection (e.g. supplier lead time changed)."))
    source_updated_at: Optional[datetime] = Field(default=None, sa_column=Column("source_updated_at", DateTime(timezone=True), nullable=True, comment="ERP `updated_at` carried by the payload. Older payloads never overwrite newer ones."))
    synced_at: Optional[datetime] = Field(default=None, sa_column=Column("synced_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When the Brain last fetched/confirmed this payload (UTC)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class SalesFact(BrainBase, table=True):
    """ingest.sales_fact: Daily sales per product (product x business day), copied from the polled Canonical `DailySalesTotal`."""

    __tablename__ = "sales_fact"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_sales_fact"),
        UniqueConstraint("tenant_id", "product_id", "sales_date", name="uq_sales_fact__tenant_product_date"),
        CheckConstraint("units_sold >= 0", name="ck_sales_fact__units_nonneg"),
        CheckConstraint("units_returned >= 0", name="ck_sales_fact__returned_nonneg"),
        CheckConstraint("net_units = units_sold - units_returned", name="ck_sales_fact__net_consistency"),
        CheckConstraint("day_status IN ('open','closed')", name="ck_sales_fact__day_status"),
        CheckConstraint("source_mode IN ('poll','reconcile','backfill')", name="ck_sales_fact__source_mode"),
        Index("ix_sales_fact__tenant_sales_date", "tenant_id", "sales_date"),
        Index("ix_sales_fact__tenant_updated_at", "tenant_id", "updated_at"),
        {"schema": "ingest", "comment": "Daily sales per product (product x business day), copied from the polled Canonical `DailySalesTotal`. The only persisted sales data in the Brain; aggregate, not per-sale-line. Every write is an absolute upsert keyed (tenant, product, date) that keeps the newest ERP `updated_at` (D-25), so re-reading a row is always harmless."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=False, comment="Canonical product id (external reference; see OD-02)."))
    sales_date: date = Field(sa_column=Column("sales_date", Date, nullable=False, comment="Canonical `business_date`, computed by the ERP in the tenant timezone (D-04, OD-03)."))
    units_sold: Optional[Decimal] = Field(default=None, sa_column=Column("units_sold", Numeric(14, 3), nullable=False, server_default=text("0"), comment="Gross units sold that day (Canonical `units_sold`)."))
    units_returned: Optional[Decimal] = Field(default=None, sa_column=Column("units_returned", Numeric(14, 3), nullable=False, server_default=text("0"), comment="Units returned that day (Canonical `units_returned`)."))
    net_units: Optional[Decimal] = Field(default=None, sa_column=Column("net_units", Numeric(14, 3), nullable=False, server_default=text("0"), comment="units_sold - units_returned (Canonical `net_units`). Demand = net units (D-06). May be negative only if returns exceed sales that day; the feature label clamps it at 0."))
    day_status: str = Field(sa_column=Column("day_status", Text, nullable=False, comment="Canonical `day_status`: open (the ERP day is still running) | closed."))
    is_complete: Optional[bool] = Field(default=None, sa_column=Column("is_complete", Boolean, nullable=False, server_default=text("true"), comment="Canonical `complete`. false = the ERP cannot vouch for this total; the day is excluded from training (D-06)."))
    source_updated_at: datetime = Field(sa_column=Column("source_updated_at", DateTime(timezone=True), nullable=False, comment="Canonical `updated_at` (ERP clock). The upsert only replaces the row when the incoming value is >= this one."))
    source_mode: Optional[str] = Field(default=None, sa_column=Column("source_mode", Text, nullable=False, server_default=text("'poll'"), comment="poll (short-interval incremental poll) | reconcile (nightly re-read of the last N days) | backfill (manual range)."))
    polled_at: Optional[datetime] = Field(default=None, sa_column=Column("polled_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When the Brain last read this row from Canonical (UTC)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class SalesDayCoverage(BrainBase, table=True):
    """ingest.sales_day_coverage: Per tenant-day statement of whether Brain sales data for that day is authoritative."""

    __tablename__ = "sales_day_coverage"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "business_date", name="pk_sales_day_coverage"),
        CheckConstraint("status IN ('open','complete','gap')", name="ck_sales_day_coverage__status"),
        CheckConstraint("verified_via IS NULL OR verified_via IN ('reconcile','backfill')", name="ck_sales_day_coverage__verified_via"),
        CheckConstraint("gap_reason IS NULL OR gap_reason IN ('erp_incomplete','canonical_unavailable','validation_failures','unknown')", name="ck_sales_day_coverage__gap_reason"),
        CheckConstraint("status <> 'complete' OR (verified_at IS NOT NULL AND verified_via IS NOT NULL)", name="ck_sales_day_coverage__complete_verified"),
        CheckConstraint("status <> 'gap' OR gap_reason IS NOT NULL", name="ck_sales_day_coverage__gap_reason_required"),
        Index("ix_sales_day_coverage__tenant_status_date", "tenant_id", "status", "business_date"),
        {"schema": "ingest", "comment": "Per tenant-day statement of whether Brain sales data for that day is authoritative. Lets the feature job distinguish a TRUE zero-sales day from a MISSING day (source rule: never treat missing days as zero silently)."},
    )

    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    business_date: date = Field(sa_column=Column("business_date", Date, primary_key=True, nullable=False, comment="Business date (tenant timezone)."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'open'"), comment="open (ERP day still running) | complete (closed, fully read, ERP vouches for it) | gap (known hole: excluded from training)."))
    verified_via: Optional[str] = Field(default=None, sa_column=Column("verified_via", Text, nullable=True, comment="reconcile | backfill. Required when complete."))
    verified_at: Optional[datetime] = Field(default=None, sa_column=Column("verified_at", DateTime(timezone=True), nullable=True, comment="When the day was verified against Canonical."))
    gap_reason: Optional[str] = Field(default=None, sa_column=Column("gap_reason", Text, nullable=True, comment="erp_incomplete | canonical_unavailable | validation_failures | unknown. Required when gap."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class CalendarDay(BrainBase, table=True):
    """feat.calendar_day: Known-in-advance calendar attributes (holiday, Ramadan, flu season) per tenant calendar."""

    __tablename__ = "calendar_day"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "calendar_date", name="pk_calendar_day"),
        CheckConstraint("holiday_name IS NULL OR is_holiday", name="ck_calendar_day__holiday_name"),
        CheckConstraint("source IN ('seed','manual')", name="ck_calendar_day__source"),
        {"schema": "feat", "comment": "Known-in-advance calendar attributes (holiday, Ramadan, flu season) per tenant calendar. Source of the calendar features copied into `feature_daily`."},
    )

    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    calendar_date: date = Field(sa_column=Column("calendar_date", Date, primary_key=True, nullable=False, comment="Calendar date in the tenant business timezone."))
    is_holiday: Optional[bool] = Field(default=None, sa_column=Column("is_holiday", Boolean, nullable=False, server_default=text("false"), comment="Official holiday."))
    holiday_name: Optional[str] = Field(default=None, sa_column=Column("holiday_name", Text, nullable=True, comment="Holiday label, when is_holiday."))
    is_ramadan: Optional[bool] = Field(default=None, sa_column=Column("is_ramadan", Boolean, nullable=False, server_default=text("false"), comment="Within Ramadan."))
    is_flu_season: Optional[bool] = Field(default=None, sa_column=Column("is_flu_season", Boolean, nullable=False, server_default=text("false"), comment="Within the configured cold/flu season window."))
    source: Optional[str] = Field(default=None, sa_column=Column("source", Text, nullable=False, server_default=text("'seed'"), comment="seed (generated by seed script) | manual (curated override)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class FeatureDaily(BrainBase, table=True):
    """feat.feature_daily: One wide, typed feature row per (tenant, product, day)."""

    __tablename__ = "feature_daily"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "product_id", "feature_date", name="pk_feature_daily"),
        CheckConstraint("feature_set_version > 0", name="ck_feature_daily__version"),
        CheckConstraint("y_status IN ('observed','zero_filled','missing','open','future')", name="ck_feature_daily__y_status"),
        CheckConstraint("(y_status IN ('observed','zero_filled')) = (y_units IS NOT NULL)", name="ck_feature_daily__y_consistency"),
        CheckConstraint("y_status <> 'zero_filled' OR y_units = 0", name="ck_feature_daily__zero_filled"),
        CheckConstraint("y_units IS NULL OR y_units >= 0", name="ck_feature_daily__y_nonneg"),
        CheckConstraint("history_days >= 0", name="ck_feature_daily__history_nonneg"),
        CheckConstraint("n_obs_7 BETWEEN 0 AND 7", name="ck_feature_daily__n_obs_7"),
        CheckConstraint("n_obs_28 BETWEEN 0 AND 28", name="ck_feature_daily__n_obs_28"),
        CheckConstraint("dow BETWEEN 0 AND 6", name="ck_feature_daily__dow"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_feature_daily__month"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_feature_daily__dom"),
        CheckConstraint("week_of_year BETWEEN 1 AND 53", name="ck_feature_daily__woy"),
        CheckConstraint("compute_mode IN ('incremental','nightly_full','backfill')", name="ck_feature_daily__compute_mode"),
        Index("ix_feature_daily__tenant_date", "tenant_id", "feature_date"),
        {"schema": "feat", "comment": "One wide, typed feature row per (tenant, product, day). Single table serving training, backtesting, anomaly scoring and inference through `FeatureStore.get_features(product_id, date)`. Feature row for day d uses information from days < d only plus known-in-advance calendar data."},
    )

    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Canonical product id (external reference)."))
    feature_date: date = Field(sa_column=Column("feature_date", Date, primary_key=True, nullable=False, comment="Day the features describe/predict (business date)."))
    feature_set_version: int = Field(sa_column=Column("feature_set_version", SmallInteger, nullable=False, comment="Version of the feature definition that produced the row. Models record the version they were trained on; inference refuses a mismatch."))
    y_units: Optional[Decimal] = Field(default=None, sa_column=Column("y_units", Numeric(14, 3), nullable=True, comment="LABEL: realised demand on feature_date = GREATEST(sales_fact.net_units, 0). NULL unless y_status is observed or zero_filled. Never a model input."))
    y_status: str = Field(sa_column=Column("y_status", Text, nullable=False, comment="observed (sales_fact row on a complete day) | zero_filled (no row on a complete day = true zero) | missing (day not complete) | open (current day) | future."))
    is_outlier: Optional[bool] = Field(default=None, sa_column=Column("is_outlier", Boolean, nullable=False, server_default=text("false"), comment="Outlier flag (marked, never deleted; training winsorises, anomaly detector still sees it)."))
    history_days: Optional[int] = Field(default=None, sa_column=Column("history_days", Integer, nullable=False, server_default=text("0"), comment="Count of complete days (observed or zero_filled) before feature_date since the product's first sale. Drives cold-start routing."))
    n_obs_7: int = Field(sa_column=Column("n_obs_7", SmallInteger, nullable=False, comment="Complete days inside the trailing 7-day window (0..7)."))
    n_obs_28: int = Field(sa_column=Column("n_obs_28", SmallInteger, nullable=False, comment="Complete days inside the trailing 28-day window (0..28)."))
    lag_1: Optional[Decimal] = Field(default=None, sa_column=Column("lag_1", Numeric(14, 3), nullable=True, comment="Units on feature_date - 1; NULL if that day is not complete."))
    lag_7: Optional[Decimal] = Field(default=None, sa_column=Column("lag_7", Numeric(14, 3), nullable=True, comment="Units on feature_date - 7."))
    lag_14: Optional[Decimal] = Field(default=None, sa_column=Column("lag_14", Numeric(14, 3), nullable=True, comment="Units on feature_date - 14."))
    lag_28: Optional[Decimal] = Field(default=None, sa_column=Column("lag_28", Numeric(14, 3), nullable=True, comment="Units on feature_date - 28."))
    roll_mean_7: Optional[Decimal] = Field(default=None, sa_column=Column("roll_mean_7", Numeric(14, 4), nullable=True, comment="Trailing 7-day mean over complete days; NULL if n_obs_7 < 5."))
    roll_mean_14: Optional[Decimal] = Field(default=None, sa_column=Column("roll_mean_14", Numeric(14, 4), nullable=True, comment="Trailing 14-day mean; NULL if fewer than 10 complete days."))
    roll_mean_28: Optional[Decimal] = Field(default=None, sa_column=Column("roll_mean_28", Numeric(14, 4), nullable=True, comment="Trailing 28-day mean; NULL if n_obs_28 < 21."))
    roll_std_7: Optional[Decimal] = Field(default=None, sa_column=Column("roll_std_7", Numeric(14, 4), nullable=True, comment="Trailing 7-day sample std dev."))
    roll_std_28: Optional[Decimal] = Field(default=None, sa_column=Column("roll_std_28", Numeric(14, 4), nullable=True, comment="Trailing 28-day sample std dev."))
    dow: int = Field(sa_column=Column("dow", SmallInteger, nullable=False, comment="Day of week, Monday=0 .. Sunday=6."))
    month: int = Field(sa_column=Column("month", SmallInteger, nullable=False, comment="Month 1..12."))
    day_of_month: int = Field(sa_column=Column("day_of_month", SmallInteger, nullable=False, comment="1..31."))
    week_of_year: int = Field(sa_column=Column("week_of_year", SmallInteger, nullable=False, comment="ISO week 1..53."))
    is_holiday: Optional[bool] = Field(default=None, sa_column=Column("is_holiday", Boolean, nullable=False, server_default=text("false"), comment="Copied from calendar_day."))
    is_ramadan: Optional[bool] = Field(default=None, sa_column=Column("is_ramadan", Boolean, nullable=False, server_default=text("false"), comment="Copied from calendar_day."))
    is_flu_season: Optional[bool] = Field(default=None, sa_column=Column("is_flu_season", Boolean, nullable=False, server_default=text("false"), comment="Copied from calendar_day."))
    is_promotion: Optional[bool] = Field(default=None, sa_column=Column("is_promotion", Boolean, nullable=True, comment="NULL = unknown. The Canonical contract has no promotion data in the MVP, so this is always NULL (documented limitation, guide section 7.8)."))
    computed_at: Optional[datetime] = Field(default=None, sa_column=Column("computed_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When this row was (re)computed (UTC)."))
    compute_mode: str = Field(sa_column=Column("compute_mode", Text, nullable=False, comment="incremental | nightly_full | backfill."))
    inputs_max_updated_at: Optional[datetime] = Field(default=None, sa_column=Column("inputs_max_updated_at", DateTime(timezone=True), nullable=True, comment="max(sales_fact.updated_at) over the rows used. Row is stale if any input row is newer."))

class RuleConfig(BrainBase, table=True):
    """intel.rule_config: Immutable, versioned parameter sets for the deterministic engines (anomaly thresholds, risk margins, safety stock, forecast selection rules, platform settings such as business timezone and cache freshness)."""

    __tablename__ = "rule_config"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_rule_config"),
        UniqueConstraint("tenant_id", "id", name="uq_rule_config__tenant_id_id"),
        UniqueConstraint("tenant_id", "rule_set", "version", name="uq_rule_config__tenant_set_version"),
        UniqueConstraint("tenant_id", "rule_set", "version_label", name="uq_rule_config__tenant_set_label"),
        CheckConstraint("rule_set IN ('platform','anomaly','risk','recommendation','forecast')", name="ck_rule_config__rule_set"),
        CheckConstraint("version > 0", name="ck_rule_config__version_pos"),
        CheckConstraint("jsonb_typeof(params) = 'object'", name="ck_rule_config__params_type"),
        Index("uq_rule_config__one_active_per_set", "tenant_id", "rule_set", unique=True, postgresql_where=text("is_active")),
        {"schema": "intel", "comment": "Immutable, versioned parameter sets for the deterministic engines (anomaly thresholds, risk margins, safety stock, forecast selection rules, platform settings such as business timezone and cache freshness). Every assessment/recommendation points at the exact version it used."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    rule_set: str = Field(sa_column=Column("rule_set", Text, nullable=False, comment="platform | anomaly | risk | recommendation | forecast."))
    version: int = Field(sa_column=Column("version", Integer, nullable=False, comment="Monotonic integer per (tenant, rule_set)."))
    version_label: str = Field(sa_column=Column("version_label", Text, nullable=False, comment="Human label copied into `rule_version` columns, e.g. 'risk-rules@1.0.0'."))
    params: Dict[str, Any] = Field(sa_column=Column("params", JSONB, nullable=False, comment="Parameter object validated by the Pydantic model for the rule_set. Immutable after insert."))
    is_active: Optional[bool] = Field(default=None, sa_column=Column("is_active", Boolean, nullable=False, server_default=text("false"), comment="Exactly one active row per (tenant, rule_set)."))
    effective_from: Optional[datetime] = Field(default=None, sa_column=Column("effective_from", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When this version became/becomes effective."))
    created_by: Optional[str] = Field(default=None, sa_column=Column("created_by", Text, nullable=False, server_default=text("'migration'"), comment="Actor (JWT sub), 'migration' for seeds, or script name."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class TrainingRun(BrainBase, table=True):
    """intel.training_run: One execution of a training job (nightly end-of-day retrain, D-26; or on-demand)."""

    __tablename__ = "training_run"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_training_run"),
        UniqueConstraint("tenant_id", "id", name="uq_training_run__tenant_id_id"),
        CheckConstraint("purpose IN ('forecast','anomaly')", name="ck_training_run__purpose"),
        CheckConstraint("trigger IN ('nightly','on_demand','manual')", name="ck_training_run__trigger"),
        CheckConstraint("status IN ('running','succeeded','partial','failed')", name="ck_training_run__status"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="ck_training_run__finished_consistency"),
        CheckConstraint("products_requested >= 0 AND products_trained >= 0 AND products_skipped >= 0 AND products_failed >= 0", name="ck_training_run__counts"),
        CheckConstraint("error_summary IS NULL OR char_length(error_summary) <= 1000", name="ck_training_run__error_len"),
        CheckConstraint("jsonb_typeof(config_snapshot) = 'object'", name="ck_training_run__config_snapshot_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_training_run__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "rule_config_id"], ["intel.rule_config.tenant_id", "intel.rule_config.id"], name="fk_training_run__rule_config", ondelete="RESTRICT"),
        Index("ix_training_run__tenant_started", "tenant_id", "started_at"),
        {"schema": "intel", "comment": "One execution of a training job (nightly end-of-day retrain, D-26; or on-demand). Groups the candidate models it produced and records counts, configuration and outcome."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    purpose: Optional[str] = Field(default=None, sa_column=Column("purpose", Text, nullable=False, server_default=text("'forecast'"), comment="forecast | anomaly."))
    trigger: str = Field(sa_column=Column("trigger", Text, nullable=False, comment="nightly | on_demand | manual. Nightly = the 02:00 end-of-day run (D-26); there is no weekly retrain."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'running'"), comment="running | succeeded | partial | failed."))
    started_at: Optional[datetime] = Field(default=None, sa_column=Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Job start (UTC)."))
    finished_at: Optional[datetime] = Field(default=None, sa_column=Column("finished_at", DateTime(timezone=True), nullable=True, comment="Job end (UTC)."))
    products_requested: Optional[int] = Field(default=None, sa_column=Column("products_requested", Integer, nullable=False, server_default=text("0"), comment="SKUs selected for training."))
    products_trained: Optional[int] = Field(default=None, sa_column=Column("products_trained", Integer, nullable=False, server_default=text("0"), comment="SKUs with a registered winner."))
    products_skipped: Optional[int] = Field(default=None, sa_column=Column("products_skipped", Integer, nullable=False, server_default=text("0"), comment="SKUs skipped (insufficient history / gaps)."))
    products_failed: Optional[int] = Field(default=None, sa_column=Column("products_failed", Integer, nullable=False, server_default=text("0"), comment="SKUs that errored."))
    feature_set_version: Optional[int] = Field(default=None, sa_column=Column("feature_set_version", SmallInteger, nullable=True, comment="Feature definition version used."))
    rule_config_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("rule_config_id", PG_UUID(as_uuid=True), nullable=True, comment="rule_config(forecast) version used for selection rules."))
    code_version: Optional[str] = Field(default=None, sa_column=Column("code_version", Text, nullable=True, comment="Git SHA of the training code."))
    config_snapshot: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("config_snapshot", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Candidates, backtest window, min-history thresholds actually applied."))
    error_summary: Optional[str] = Field(default=None, sa_column=Column("error_summary", Text, nullable=True, comment="Short failure summary (<= 1000 chars)."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    models: List["ModelRegistry"] = Relationship(sa_relationship_kwargs=RO)

class ModelRegistry(BrainBase, table=True):
    """intel.model_registry: Registry of trained or fitted models/methods."""

    __tablename__ = "model_registry"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_model_registry"),
        UniqueConstraint("tenant_id", "id", name="uq_model_registry__tenant_id_id"),
        UniqueConstraint("tenant_id", "model_version", name="uq_model_registry__tenant_model_version"),
        CheckConstraint("purpose IN ('forecast','anomaly')", name="ck_model_registry__purpose"),
        CheckConstraint("model_family IN ('naive','seasonal_naive','moving_average','category_mean','lightgbm','zscore_residual','isolation_forest')", name="ck_model_registry__family"),
        CheckConstraint("scope IN ('shared','product') AND (scope = 'shared') = (product_id IS NULL)", name="ck_model_registry__scope"),
        CheckConstraint("shared_model_id IS NULL OR (scope = 'product' AND artifact_path IS NULL AND shared_model_id <> id)", name="ck_model_registry__shared_ref"),
        CheckConstraint("status IN ('candidate','validated','degraded','retired','rejected')", name="ck_model_registry__status"),
        CheckConstraint("(train_data_start IS NULL) = (train_data_end IS NULL) AND (train_data_start IS NULL OR train_data_start <= train_data_end)", name="ck_model_registry__train_window"),
        CheckConstraint("(backtest_wape IS NULL OR backtest_wape >= 0) AND (baseline_wape IS NULL OR baseline_wape >= 0)", name="ck_model_registry__wape_nonneg"),
        CheckConstraint("(artifact_path IS NULL) = (artifact_sha256 IS NULL)", name="ck_model_registry__artifact_pair"),
        CheckConstraint("artifact_path IS NULL OR (artifact_path !~ '^(/|[A-Za-z]:)' AND artifact_path !~ '[.][.]')", name="ck_model_registry__artifact_path_relative"),
        CheckConstraint("artifact_format IS NULL OR artifact_format IN ('lightgbm_txt','json')", name="ck_model_registry__artifact_format"),
        CheckConstraint("status <> 'validated' OR validated_at IS NOT NULL", name="ck_model_registry__validated_has_ts"),
        CheckConstraint("status <> 'validated' OR model_family NOT IN ('lightgbm','isolation_forest') OR artifact_path IS NOT NULL OR shared_model_id IS NOT NULL", name="ck_model_registry__trained_family_artifact"),
        CheckConstraint("model_family <> 'category_mean' OR product_id IS NULL", name="ck_model_registry__category_mean_scope"),
        CheckConstraint("status_reason IS NULL OR char_length(status_reason) <= 500", name="ck_model_registry__reason_len"),
        CheckConstraint("jsonb_typeof(hyperparameters) = 'object'", name="ck_model_registry__hyperparameters_type"),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="ck_model_registry__metrics_type"),
        CheckConstraint("artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'", name="ck_model_registry__artifact_sha256_format"),
        ForeignKeyConstraint(["tenant_id", "training_run_id"], ["intel.training_run.tenant_id", "intel.training_run.id"], name="fk_model_registry__training_run", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "shared_model_id"], ["intel.model_registry.tenant_id", "intel.model_registry.id"], name="fk_model_registry__shared_model", ondelete="RESTRICT"),
        Index("ix_model_registry__serving", "tenant_id", "product_id", "purpose", "validated_at", postgresql_where=text("status = 'validated'")),
        Index("ix_model_registry__tenant_run", "tenant_id", "training_run_id"),
        Index("ix_model_registry__tenant_shared", "tenant_id", "shared_model_id", postgresql_where=text("shared_model_id IS NOT NULL")),
        {"schema": "intel", "comment": "Registry of trained or fitted models/methods. A row is either SHARED (scope=shared, product_id NULL: one artifact fitted across many products of the tenant, e.g. the global LightGBM) or PRODUCT (scope=product, product_id set: the model a product is served by, with that product's own backtest WAPE). A product row either points at a shared row through `shared_model_id` (it uses the shared artifact and has no artifact of its own, so it does NOT mean a separately trained model) or carries its own artifact (a product-specific model, allowed only when it beats the shared one) or is an artifact-less method such as seasonal_naive (D-31). Inference reads the latest `validated` product row."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=True, comment="Canonical product id for scope=product rows; NULL for scope=shared rows."))
    scope: str = Field(sa_column=Column("scope", Text, nullable=False, comment="shared | product (D-31). shared = fitted across products; product = the model selection for one product."))
    shared_model_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("shared_model_id", PG_UUID(as_uuid=True), nullable=True, comment="scope=product rows that use a shared artifact: the shared row. NULL when the product row has its own artifact or uses an artifact-less method."))
    purpose: Optional[str] = Field(default=None, sa_column=Column("purpose", Text, nullable=False, server_default=text("'forecast'"), comment="forecast | anomaly."))
    model_family: str = Field(sa_column=Column("model_family", Text, nullable=False, comment="naive | seasonal_naive | moving_average | category_mean | lightgbm | zscore_residual | isolation_forest. MVP forecasting uses seasonal_naive and lightgbm only (D-20, D-32)."))
    model_version: str = Field(sa_column=Column("model_version", Text, nullable=False, comment="Unique label per tenant, e.g. 'lgbm-amox-v3' (the `model_version` of the source key)."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'candidate'"), comment="candidate | validated | degraded | retired | rejected."))
    training_run_id: uuid.UUID = Field(sa_column=Column("training_run_id", PG_UUID(as_uuid=True), nullable=False, comment="Run that produced the row."))
    feature_set_version: Optional[int] = Field(default=None, sa_column=Column("feature_set_version", SmallInteger, nullable=True, comment="Feature definition version; NULL for methods that do not use features."))
    trained_at: datetime = Field(sa_column=Column("trained_at", DateTime(timezone=True), nullable=False, comment="Training/fit completion (UTC)."))
    train_data_start: Optional[date] = Field(default=None, sa_column=Column("train_data_start", Date, nullable=True, comment="First day of training data (leakage audit)."))
    train_data_end: Optional[date] = Field(default=None, sa_column=Column("train_data_end", Date, nullable=True, comment="Last day of training data."))
    hyperparameters: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("hyperparameters", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Hyperparameters / fitted parameters."))
    backtest_wape: Optional[Decimal] = Field(default=None, sa_column=Column("backtest_wape", Numeric(8, 5), nullable=True, comment="WAPE on the rolling-origin backtest (fraction, 0.14 = 14 percent)."))
    baseline_wape: Optional[Decimal] = Field(default=None, sa_column=Column("baseline_wape", Numeric(8, 5), nullable=True, comment="WAPE of the best baseline on the same folds (winner must beat it)."))
    metrics: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("metrics", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Other backtest metrics snapshot (mape, bias, n_folds, backtest_weeks)."))
    artifact_path: Optional[str] = Field(default=None, sa_column=Column("artifact_path", Text, nullable=True, comment="Path RELATIVE to the models volume root; NULL for methods without an artifact."))
    artifact_format: Optional[str] = Field(default=None, sa_column=Column("artifact_format", Text, nullable=True, comment="lightgbm_txt | json. Executable formats (pickle, joblib) are not allowed (OD-13, D-33)."))
    artifact_sha256: Optional[str] = Field(default=None, sa_column=Column("artifact_sha256", CHAR(64), nullable=True, comment="Checksum verified before load."))
    artifact_size_bytes: Optional[int] = Field(default=None, sa_column=Column("artifact_size_bytes", BigInteger, nullable=True, comment="File size."))
    code_version: Optional[str] = Field(default=None, sa_column=Column("code_version", Text, nullable=True, comment="Git SHA of the training code."))
    validated_at: Optional[datetime] = Field(default=None, sa_column=Column("validated_at", DateTime(timezone=True), nullable=True, comment="When promoted to validated."))
    degraded_at: Optional[datetime] = Field(default=None, sa_column=Column("degraded_at", DateTime(timezone=True), nullable=True, comment="When flagged degraded (post-deployment WAPE jump)."))
    retired_at: Optional[datetime] = Field(default=None, sa_column=Column("retired_at", DateTime(timezone=True), nullable=True, comment="When superseded/retired."))
    status_reason: Optional[str] = Field(default=None, sa_column=Column("status_reason", Text, nullable=True, comment="Why the status last changed (<= 500 chars)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    training_run: Optional["TrainingRun"] = Relationship(sa_relationship_kwargs=RO)
    evaluations: List["ModelEvaluation"] = Relationship(sa_relationship_kwargs=RO)

class ModelEvaluation(BrainBase, table=True):
    """intel.model_evaluation: Append-only evaluation results over time (backtests, weekly post-deployment predicted-vs-actual, golden-set precision/recall)."""

    __tablename__ = "model_evaluation"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_model_evaluation"),
        UniqueConstraint("tenant_id", "model_id", "evaluation_type", "metric_name", "window_start", "window_end", name="uq_model_evaluation__window_metric"),
        CheckConstraint("evaluation_type IN ('backtest','post_deploy_weekly','holdout','golden_set')", name="ck_model_evaluation__type"),
        CheckConstraint("metric_name IN ('wape','mape','smape','mae','bias','precision','recall','f1')", name="ck_model_evaluation__metric"),
        CheckConstraint("window_end >= window_start", name="ck_model_evaluation__window"),
        CheckConstraint("n_obs >= 0", name="ck_model_evaluation__n_obs"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_model_evaluation__details_type"),
        ForeignKeyConstraint(["tenant_id", "model_id"], ["intel.model_registry.tenant_id", "intel.model_registry.id"], name="fk_model_evaluation__model_registry", ondelete="CASCADE"),
        Index("ix_model_evaluation__model_evaluated", "tenant_id", "model_id", "evaluated_at"),
        {"schema": "intel", "comment": "Append-only evaluation results over time (backtests, weekly post-deployment predicted-vs-actual, golden-set precision/recall). Supports degradation detection and model comparison without overwriting history."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    model_id: uuid.UUID = Field(sa_column=Column("model_id", PG_UUID(as_uuid=True), nullable=False, comment="Model evaluated."))
    evaluation_type: str = Field(sa_column=Column("evaluation_type", Text, nullable=False, comment="backtest | post_deploy_weekly | holdout | golden_set."))
    metric_name: str = Field(sa_column=Column("metric_name", Text, nullable=False, comment="wape | mape | smape | mae | bias | precision | recall | f1."))
    metric_value: Decimal = Field(sa_column=Column("metric_value", Numeric(14, 6), nullable=False, comment="Metric value (WAPE as a fraction)."))
    baseline_value: Optional[Decimal] = Field(default=None, sa_column=Column("baseline_value", Numeric(14, 6), nullable=True, comment="Same metric for the baseline on the same window."))
    n_obs: int = Field(sa_column=Column("n_obs", Integer, nullable=False, comment="Observations (product-days) behind the metric."))
    window_start: date = Field(sa_column=Column("window_start", Date, nullable=False, comment="First evaluated day."))
    window_end: date = Field(sa_column=Column("window_end", Date, nullable=False, comment="Last evaluated day."))
    evaluated_at: Optional[datetime] = Field(default=None, sa_column=Column("evaluated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When computed (UTC)."))
    details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Per-fold values or confusion counts."))

    # read-only convenience relationships (writes go through repositories)
    model: Optional["ModelRegistry"] = Relationship(sa_relationship_kwargs=RO)

class Forecast(BrainBase, table=True):
    """intel.forecast: Header of ONE forecast generation for one product by one model at one origin date."""

    __tablename__ = "forecast"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_forecast"),
        UniqueConstraint("tenant_id", "id", name="uq_forecast__tenant_id_id"),
        UniqueConstraint("tenant_id", "product_id", "model_id", "job_run_id", name="uq_forecast__run_product_model"),
        CheckConstraint("horizon_days BETWEEN 1 AND 90", name="ck_forecast__horizon"),
        CheckConstraint("trigger IN ('nightly','on_demand','backfill')", name="ck_forecast__trigger"),
        CheckConstraint("forecast_confidence IN ('low','medium','high')", name="ck_forecast__confidence"),
        CheckConstraint("history_days >= 0", name="ck_forecast__history_nonneg"),
        CheckConstraint("interval_method IN ('quantile','backtest_residual','none')", name="ck_forecast__interval_method"),
        CheckConstraint("interval_coverage IS NULL OR (interval_coverage > 0 AND interval_coverage < 1)", name="ck_forecast__interval_coverage"),
        CheckConstraint("(interval_method = 'none') = (interval_coverage IS NULL)", name="ck_forecast__interval_consistency"),
        CheckConstraint("jsonb_typeof(factors) = 'array'", name="ck_forecast__factors_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_forecast__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "model_id"], ["intel.model_registry.tenant_id", "intel.model_registry.id"], name="fk_forecast__model_registry", ondelete="RESTRICT"),
        Index("ix_forecast__tenant_product_generated", "tenant_id", "product_id", "generated_at"),
        Index("ix_forecast__tenant_model_generated", "tenant_id", "model_id", "generated_at"),
        {"schema": "intel", "comment": "Header of ONE forecast generation for one product by one model at one origin date. Daily values are in `forecast_point`. Never overwritten: each generation is kept so accuracy can be evaluated by lead time and audited."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=False, comment="Canonical product id."))
    model_id: uuid.UUID = Field(sa_column=Column("model_id", PG_UUID(as_uuid=True), nullable=False, comment="Model/method that produced the forecast."))
    job_run_id: uuid.UUID = Field(sa_column=Column("job_run_id", PG_UUID(as_uuid=True), nullable=False, comment="Correlation id of the batch/job (training_run id, nightly job id or on-demand request id). Makes retries idempotent."))
    origin_date: date = Field(sa_column=Column("origin_date", Date, nullable=False, comment="Last day of observed data used (the forecast covers origin_date + 1 ...)."))
    generated_at: Optional[datetime] = Field(default=None, sa_column=Column("generated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Generation time (UTC)."))
    horizon_days: int = Field(sa_column=Column("horizon_days", SmallInteger, nullable=False, comment="Number of forecast days (1..90)."))
    trigger: str = Field(sa_column=Column("trigger", Text, nullable=False, comment="nightly | on_demand | backfill."))
    forecast_confidence: str = Field(sa_column=Column("forecast_confidence", Text, nullable=False, comment="Qualitative confidence: low (cold start) | medium | high (from backtest)."))
    cold_start: Optional[bool] = Field(default=None, sa_column=Column("cold_start", Boolean, nullable=False, server_default=text("false"), comment="True when a cold-start fallback was used."))
    history_days: int = Field(sa_column=Column("history_days", Integer, nullable=False, comment="Complete days of history available at origin."))
    interval_method: Optional[str] = Field(default=None, sa_column=Column("interval_method", Text, nullable=False, server_default=text("'none'"), comment="How bounds were produced: quantile | backtest_residual | none."))
    interval_coverage: Optional[Decimal] = Field(default=None, sa_column=Column("interval_coverage", Numeric(4, 3), nullable=True, comment="Nominal coverage of [lower, upper], e.g. 0.800 for P10-P90."))
    feature_set_version: Optional[int] = Field(default=None, sa_column=Column("feature_set_version", SmallInteger, nullable=True, comment="Feature definition version used."))
    inputs_max_updated_at: Optional[datetime] = Field(default=None, sa_column=Column("inputs_max_updated_at", DateTime(timezone=True), nullable=True, comment="max(sales_fact.updated_at) of the inputs (reproducibility fingerprint)."))
    quality_flags: Optional[List[str]] = Field(default=None, sa_column=Column("quality_flags", ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"), comment="Data-quality flags, e.g. gap_filled, sparse_history, outlier_winsorised."))
    factors: Optional[List[Any]] = Field(default=None, sa_column=Column("factors", JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment="Explainability factors[] (e.g. '7-day mean 22 percent above 28-day mean')."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))

    # read-only convenience relationships (writes go through repositories)
    model: Optional["ModelRegistry"] = Relationship(sa_relationship_kwargs=RO)
    points: List["ForecastPoint"] = Relationship(sa_relationship_kwargs=RO)

class ForecastPoint(BrainBase, table=True):
    """intel.forecast_point: Daily predicted demand with confidence bounds for one forecast generation."""

    __tablename__ = "forecast_point"
    __table_args__ = (
        PrimaryKeyConstraint("forecast_id", "target_date", name="pk_forecast_point"),
        CheckConstraint("predicted_demand >= 0", name="ck_forecast_point__predicted_nonneg"),
        CheckConstraint("(confidence_low IS NULL) = (confidence_high IS NULL)", name="ck_forecast_point__bounds_pair"),
        CheckConstraint("confidence_low IS NULL OR (confidence_low >= 0 AND confidence_low <= predicted_demand AND confidence_high >= predicted_demand)", name="ck_forecast_point__bounds_order"),
        ForeignKeyConstraint(["tenant_id", "forecast_id"], ["intel.forecast.tenant_id", "intel.forecast.id"], name="fk_forecast_point__forecast", ondelete="CASCADE"),
        Index("ix_forecast_point__tenant_target", "tenant_id", "target_date"),
        {"schema": "intel", "comment": "Daily predicted demand with confidence bounds for one forecast generation."},
    )

    forecast_id: uuid.UUID = Field(sa_column=Column("forecast_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Parent forecast."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    target_date: date = Field(sa_column=Column("target_date", Date, primary_key=True, nullable=False, comment="Business date being predicted."))
    predicted_demand: Decimal = Field(sa_column=Column("predicted_demand", Numeric(14, 3), nullable=False, comment="Point prediction (median/expected demand)."))
    confidence_low: Optional[Decimal] = Field(default=None, sa_column=Column("confidence_low", Numeric(14, 3), nullable=True, comment="Lower confidence bound (see parent interval_method/coverage)."))
    confidence_high: Optional[Decimal] = Field(default=None, sa_column=Column("confidence_high", Numeric(14, 3), nullable=True, comment="Upper confidence bound."))

    # read-only convenience relationships (writes go through repositories)
    forecast: Optional["Forecast"] = Relationship(sa_relationship_kwargs=RO)

class AnomalyEvent(BrainBase, table=True):
    """intel.anomaly_event: A detected unusual observation (an unexplained deviation, NOT a confirmed incident) for a product-day, with expected vs observed, score, severity, structured reasons and provenance."""

    __tablename__ = "anomaly_event"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_anomaly_event"),
        UniqueConstraint("tenant_id", "id", name="uq_anomaly_event__tenant_id_id"),
        UniqueConstraint("tenant_id", "product_id", "observation_date", "anomaly_type", "detection_method", name="uq_anomaly_event__natural_key"),
        CheckConstraint("anomaly_type IN ('demand_spike','demand_drop','pattern_outlier')", name="ck_anomaly_event__type"),
        CheckConstraint("detection_method IN ('rule','zscore','isolation_forest','combined')", name="ck_anomaly_event__method"),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_anomaly_event__score"),
        CheckConstraint("severity IN ('low','medium','high')", name="ck_anomaly_event__severity"),
        CheckConstraint("status IN ('open','acknowledged','dismissed','confirmed','retracted')", name="ck_anomaly_event__status"),
        CheckConstraint("observed_value >= 0", name="ck_anomaly_event__observed_nonneg"),
        CheckConstraint("(reviewed_by IS NULL) = (reviewed_at IS NULL)", name="ck_anomaly_event__review_pair"),
        CheckConstraint("status NOT IN ('acknowledged','dismissed','confirmed') OR reviewed_by IS NOT NULL", name="ck_anomaly_event__review_required"),
        CheckConstraint("detection_count >= 1", name="ck_anomaly_event__count"),
        CheckConstraint("last_detected_at >= first_detected_at", name="ck_anomaly_event__detect_order"),
        CheckConstraint("jsonb_typeof(reasons) = 'array'", name="ck_anomaly_event__reasons_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_anomaly_event__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "rule_config_id"], ["intel.rule_config.tenant_id", "intel.rule_config.id"], name="fk_anomaly_event__rule_config", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "model_id"], ["intel.model_registry.tenant_id", "intel.model_registry.id"], name="fk_anomaly_event__model_registry", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "forecast_id"], ["intel.forecast.tenant_id", "intel.forecast.id"], name="fk_anomaly_event__forecast", ondelete="RESTRICT"),
        Index("ix_anomaly_event__tenant_product_date", "tenant_id", "product_id", "observation_date"),
        Index("ix_anomaly_event__open_severity", "tenant_id", "severity", "last_detected_at", postgresql_where=text("status = 'open'")),
        {"schema": "intel", "comment": "A detected unusual observation (an unexplained deviation, NOT a confirmed incident) for a product-day, with expected vs observed, score, severity, structured reasons and provenance. Re-detection updates the same row."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=False, comment="Canonical product id. (MVP anomalies are sales anomalies per product-day.)"))
    observation_date: date = Field(sa_column=Column("observation_date", Date, nullable=False, comment="Business date of the observation."))
    anomaly_type: str = Field(sa_column=Column("anomaly_type", Text, nullable=False, comment="demand_spike | demand_drop | pattern_outlier. (single_line_outlier removed: daily totals carry no line detail.)"))
    detection_method: str = Field(sa_column=Column("detection_method", Text, nullable=False, comment="rule | zscore | isolation_forest | combined."))
    expected_value: Optional[Decimal] = Field(default=None, sa_column=Column("expected_value", Numeric(14, 3), nullable=True, comment="Expected units (from forecast or rolling mean); NULL if none available."))
    observed_value: Decimal = Field(sa_column=Column("observed_value", Numeric(14, 3), nullable=False, comment="Observed net units for the day."))
    zscore: Optional[Decimal] = Field(default=None, sa_column=Column("zscore", Numeric(10, 4), nullable=True, comment="Residual z-score when computed."))
    score: Decimal = Field(sa_column=Column("score", Numeric(5, 4), nullable=False, comment="Anomaly score in [0, 1]."))
    severity: str = Field(sa_column=Column("severity", Text, nullable=False, comment="low | medium | high (thresholds from rule_config)."))
    reasons: Optional[List[Any]] = Field(default=None, sa_column=Column("reasons", JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment="Structured reasons array: [{code, value, threshold}]."))
    rule_version: str = Field(sa_column=Column("rule_version", Text, nullable=False, comment="Rule set label used (copy of rule_config.version_label)."))
    rule_config_id: uuid.UUID = Field(sa_column=Column("rule_config_id", PG_UUID(as_uuid=True), nullable=False, comment="Exact parameter set used."))
    model_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("model_id", PG_UUID(as_uuid=True), nullable=True, comment="Isolation Forest / statistical model used, when any."))
    forecast_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("forecast_id", PG_UUID(as_uuid=True), nullable=True, comment="Forecast the expected value came from, when any."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'open'"), comment="open (unreviewed signal) | acknowledged | dismissed | confirmed | retracted (no longer anomalous after correction)."))
    reviewed_by: Optional[str] = Field(default=None, sa_column=Column("reviewed_by", Text, nullable=True, comment="Reviewer actor id (JWT sub)."))
    reviewed_at: Optional[datetime] = Field(default=None, sa_column=Column("reviewed_at", DateTime(timezone=True), nullable=True, comment="Review time."))
    first_detected_at: Optional[datetime] = Field(default=None, sa_column=Column("first_detected_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="First detection (API `detected_at`)."))
    last_detected_at: Optional[datetime] = Field(default=None, sa_column=Column("last_detected_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Most recent re-detection."))
    detection_count: Optional[int] = Field(default=None, sa_column=Column("detection_count", Integer, nullable=False, server_default=text("1"), comment="Number of detections folded into this row."))
    row_version: Optional[int] = Field(default=None, sa_column=Column("row_version", Integer, nullable=False, server_default=text("1"), comment="Optimistic-concurrency counter; incremented on every UPDATE by the application."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    model: Optional["ModelRegistry"] = Relationship(sa_relationship_kwargs=RO)
    forecast: Optional["Forecast"] = Relationship(sa_relationship_kwargs=RO)

class RiskAssessment(BrainBase, table=True):
    """intel.risk_assessment: Deterministic risk result per product and risk type (stockout_risk, unusual_demand) with the exact inputs and rule version used."""

    __tablename__ = "risk_assessment"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_risk_assessment"),
        UniqueConstraint("tenant_id", "id", name="uq_risk_assessment__tenant_id_id"),
        CheckConstraint("risk_type IN ('stockout_risk','unusual_demand')", name="ck_risk_assessment__type"),
        CheckConstraint("severity IN ('low','medium','high')", name="ck_risk_assessment__severity"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_risk_assessment__confidence"),
        CheckConstraint("inventory_source IS NULL OR inventory_source IN ('canonical_live','canonical_cache')", name="ck_risk_assessment__inventory_source"),
        CheckConstraint("(demand_per_day IS NULL OR demand_per_day >= 0) AND (demand_over_lead_time IS NULL OR demand_over_lead_time >= 0) AND (days_of_cover IS NULL OR days_of_cover >= 0) AND (lead_time_days IS NULL OR lead_time_days >= 0)", name="ck_risk_assessment__numbers_nonneg"),
        CheckConstraint("risk_type <> 'stockout_risk' OR (days_of_cover IS NOT NULL AND lead_time_days IS NOT NULL AND input_available_quantity IS NOT NULL AND inventory_as_of IS NOT NULL)", name="ck_risk_assessment__stockout_inputs"),
        CheckConstraint("risk_type <> 'unusual_demand' OR anomaly_event_id IS NOT NULL", name="ck_risk_assessment__unusual_anomaly"),
        CheckConstraint("(superseded_at IS NULL) = (superseded_by_id IS NULL)", name="ck_risk_assessment__supersede_pair"),
        CheckConstraint("jsonb_typeof(calculation) = 'object'", name="ck_risk_assessment__calculation_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_risk_assessment__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "forecast_id"], ["intel.forecast.tenant_id", "intel.forecast.id"], name="fk_risk_assessment__forecast", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "anomaly_event_id"], ["intel.anomaly_event.tenant_id", "intel.anomaly_event.id"], name="fk_risk_assessment__anomaly_event", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "rule_config_id"], ["intel.rule_config.tenant_id", "intel.rule_config.id"], name="fk_risk_assessment__rule_config", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "superseded_by_id"], ["intel.risk_assessment.tenant_id", "intel.risk_assessment.id"], name="fk_risk_assessment__superseded_by", ondelete="RESTRICT"),
        Index("uq_risk_assessment__current", "tenant_id", "product_id", "risk_type", unique=True, postgresql_where=text("superseded_at IS NULL")),
        Index("ix_risk_assessment__current_severity", "tenant_id", "severity", "calculated_at", postgresql_where=text("superseded_at IS NULL")),
        Index("ix_risk_assessment__product_history", "tenant_id", "product_id", "calculated_at"),
        {"schema": "intel", "comment": "Deterministic risk result per product and risk type (stockout_risk, unusual_demand) with the exact inputs and rule version used. Versions are kept: a changed outcome inserts a new row and supersedes the old one, so recommendations keep pointing at the calculation they were based on."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=False, comment="Canonical product id."))
    supplier_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("supplier_id", PG_UUID(as_uuid=True), nullable=True, comment="Canonical supplier id whose lead time was used (external; see OD-04)."))
    risk_type: str = Field(sa_column=Column("risk_type", Text, nullable=False, comment="stockout_risk | unusual_demand."))
    severity: str = Field(sa_column=Column("severity", Text, nullable=False, comment="low | medium | high."))
    confidence: Optional[Decimal] = Field(default=None, sa_column=Column("confidence", Numeric(4, 3), nullable=True, comment="0..1 where meaningful (stockout_risk); NULL for unusual_demand."))
    input_available_quantity: Optional[Decimal] = Field(default=None, sa_column=Column("input_available_quantity", Numeric(14, 3), nullable=True, comment="INPUT SNAPSHOT of ERP available_quantity used in the calculation. Provenance, not an inventory copy."))
    inventory_as_of: Optional[datetime] = Field(default=None, sa_column=Column("inventory_as_of", DateTime(timezone=True), nullable=True, comment="Time the inventory value was read from Canonical."))
    inventory_source: Optional[str] = Field(default=None, sa_column=Column("inventory_source", Text, nullable=True, comment="canonical_live | canonical_cache."))
    demand_per_day: Optional[Decimal] = Field(default=None, sa_column=Column("demand_per_day", Numeric(14, 4), nullable=True, comment="Forecast demand per day used."))
    demand_over_lead_time: Optional[Decimal] = Field(default=None, sa_column=Column("demand_over_lead_time", Numeric(14, 3), nullable=True, comment="Sum of forecast points over the supplier lead time."))
    demand_over_lead_time_upper: Optional[Decimal] = Field(default=None, sa_column=Column("demand_over_lead_time_upper", Numeric(14, 3), nullable=True, comment="Conservative upper estimate (sum of daily confidence_high)."))
    days_of_cover: Optional[Decimal] = Field(default=None, sa_column=Column("days_of_cover", Numeric(8, 2), nullable=True, comment="available / demand_per_day."))
    lead_time_days: Optional[Decimal] = Field(default=None, sa_column=Column("lead_time_days", Numeric(6, 2), nullable=True, comment="Supplier lead time used."))
    supplier_as_of: Optional[datetime] = Field(default=None, sa_column=Column("supplier_as_of", DateTime(timezone=True), nullable=True, comment="synced_at of the supplier payload used."))
    forecast_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("forecast_id", PG_UUID(as_uuid=True), nullable=True, comment="Forecast used."))
    anomaly_event_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("anomaly_event_id", PG_UUID(as_uuid=True), nullable=True, comment="Driving anomaly (required for unusual_demand; optional escalation source for stockout_risk)."))
    rule_version: str = Field(sa_column=Column("rule_version", Text, nullable=False, comment="Rule set label used."))
    rule_config_id: uuid.UUID = Field(sa_column=Column("rule_config_id", PG_UUID(as_uuid=True), nullable=False, comment="Exact parameter set used."))
    calculation: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("calculation", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Rule trace: [{rule, matched, inputs, output}], other anomaly ids, notes."))
    calculated_at: Optional[datetime] = Field(default=None, sa_column=Column("calculated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="When this version was first calculated (UTC)."))
    last_confirmed_at: Optional[datetime] = Field(default=None, sa_column=Column("last_confirmed_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last recalculation that produced the same outcome (heartbeat, avoids row churn)."))
    superseded_at: Optional[datetime] = Field(default=None, sa_column=Column("superseded_at", DateTime(timezone=True), nullable=True, comment="Set when a newer version replaces this one."))
    superseded_by_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("superseded_by_id", PG_UUID(as_uuid=True), nullable=True, comment="The newer version."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))

    # read-only convenience relationships (writes go through repositories)
    forecast: Optional["Forecast"] = Relationship(sa_relationship_kwargs=RO)
    anomaly_event: Optional["AnomalyEvent"] = Relationship(sa_relationship_kwargs=RO)
    recommendations: List["Recommendation"] = Relationship(sa_relationship_kwargs=RO)

class Recommendation(BrainBase, table=True):
    """intel.recommendation: Deterministic, structured suggestion derived from a risk (e.g."""

    __tablename__ = "recommendation"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_recommendation"),
        UniqueConstraint("tenant_id", "id", name="uq_recommendation__tenant_id_id"),
        CheckConstraint("recommendation_type IN ('create_purchase_order','review_anomaly')", name="ck_recommendation__type"),
        CheckConstraint("status IN ('active','dismissed','superseded','expired')", name="ck_recommendation__status"),
        CheckConstraint("expires_at > generated_at", name="ck_recommendation__expiry"),
        CheckConstraint("(status = 'superseded') = (superseded_at IS NOT NULL AND superseded_by_id IS NOT NULL)", name="ck_recommendation__supersede"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_recommendation__payload_type"),
        CheckConstraint("jsonb_typeof(calculation) = 'object'", name="ck_recommendation__calculation_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_recommendation__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "risk_assessment_id"], ["intel.risk_assessment.tenant_id", "intel.risk_assessment.id"], name="fk_recommendation__risk_assessment", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "forecast_id"], ["intel.forecast.tenant_id", "intel.forecast.id"], name="fk_recommendation__forecast", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "rule_config_id"], ["intel.rule_config.tenant_id", "intel.rule_config.id"], name="fk_recommendation__rule_config", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "superseded_by_id"], ["intel.recommendation.tenant_id", "intel.recommendation.id"], name="fk_recommendation__superseded_by", ondelete="RESTRICT"),
        Index("uq_recommendation__active", "tenant_id", "product_id", "recommendation_type", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_recommendation__tenant_product_generated", "tenant_id", "product_id", "generated_at"),
        Index("ix_recommendation__tenant_risk", "tenant_id", "risk_assessment_id"),
        {"schema": "intel", "comment": "Deterministic, structured suggestion derived from a risk (e.g. order 100 units from supplier X). Separate from any ERP transaction: a recommendation is never an executed purchase order."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    product_id: uuid.UUID = Field(sa_column=Column("product_id", PG_UUID(as_uuid=True), nullable=False, comment="Canonical product id."))
    supplier_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("supplier_id", PG_UUID(as_uuid=True), nullable=True, comment="Suggested supplier (external reference)."))
    risk_assessment_id: uuid.UUID = Field(sa_column=Column("risk_assessment_id", PG_UUID(as_uuid=True), nullable=False, comment="Risk this recommendation answers (the source `risk_id`)."))
    forecast_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("forecast_id", PG_UUID(as_uuid=True), nullable=True, comment="Forecast used."))
    recommendation_type: str = Field(sa_column=Column("recommendation_type", Text, nullable=False, comment="create_purchase_order | review_anomaly."))
    payload: Dict[str, Any] = Field(sa_column=Column("payload", JSONB, nullable=False, comment="Structured payload. For create_purchase_order it mirrors the tool input_schema {supplier_id, lines[{product_id, quantity}]} so the agent copies it into the ActionProposal unchanged."))
    calculation: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("calculation", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Formula inputs and constraints checked: demand_over_lead, safety_stock, available, order_qty, bound_used, open-PO check status."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'active'"), comment="active | dismissed | superseded | expired. ('actioned' is derived from agent.action_proposal, not stored.)"))
    generated_at: Optional[datetime] = Field(default=None, sa_column=Column("generated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Generation time (UTC)."))
    expires_at: datetime = Field(sa_column=Column("expires_at", DateTime(timezone=True), nullable=False, comment="After this time the recommendation is no longer offered."))
    superseded_at: Optional[datetime] = Field(default=None, sa_column=Column("superseded_at", DateTime(timezone=True), nullable=True, comment="When replaced by a newer recommendation."))
    superseded_by_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("superseded_by_id", PG_UUID(as_uuid=True), nullable=True, comment="Replacement recommendation."))
    rule_version: str = Field(sa_column=Column("rule_version", Text, nullable=False, comment="Rule set label used."))
    rule_config_id: uuid.UUID = Field(sa_column=Column("rule_config_id", PG_UUID(as_uuid=True), nullable=False, comment="Exact parameter set used."))
    row_version: Optional[int] = Field(default=None, sa_column=Column("row_version", Integer, nullable=False, server_default=text("1"), comment="Optimistic-concurrency counter; incremented on every UPDATE by the application."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    risk_assessment: Optional["RiskAssessment"] = Relationship(sa_relationship_kwargs=RO)
    forecast: Optional["Forecast"] = Relationship(sa_relationship_kwargs=RO)

class Briefing(BrainBase, table=True):
    """intel.briefing: Cached daily morning briefing (`Explanation` subtype report) built from existing risks and pending proposals."""

    __tablename__ = "briefing"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_briefing"),
        UniqueConstraint("tenant_id", "briefing_date", name="uq_briefing__tenant_date"),
        CheckConstraint("generated_by IN ('template','llm')", name="ck_briefing__generated_by"),
        CheckConstraint("jsonb_typeof(content) = 'object'", name="ck_briefing__content_type"),
        {"schema": "intel", "comment": "Cached daily morning briefing (`Explanation` subtype report) built from existing risks and pending proposals. SHOULD-have; the MVP does not depend on it."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    briefing_date: date = Field(sa_column=Column("briefing_date", Date, nullable=False, comment="Business date the briefing is for."))
    content: Dict[str, Any] = Field(sa_column=Column("content", JSONB, nullable=False, comment="Structured briefing (top risks, pending approvals, summaries)."))
    generated_by: str = Field(sa_column=Column("generated_by", Text, nullable=False, comment="template | llm."))
    llm_usage_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("llm_usage_id", PG_UUID(as_uuid=True), nullable=True, comment="audit.llm_usage row when an LLM polished the text (soft reference, no FK)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

class LlmUsage(BrainBase, table=True):
    """audit.llm_usage: One row per LLM layer call (and per cache hit that avoided a call): provider, model, prompt version, tokens, estimated cost, latency, outcome, trace."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_llm_usage"),
        UniqueConstraint("tenant_id", "id", name="uq_llm_usage__tenant_id_id"),
        CheckConstraint("purpose IN ('explanation','assistant_chat','agent_reasoning','briefing','other')", name="ck_llm_usage__purpose"),
        CheckConstraint("model_route IS NULL OR model_route IN ('template','small','large')", name="ck_llm_usage__route"),
        CheckConstraint("tokens_in >= 0 AND tokens_out >= 0 AND (tokens_cached_in IS NULL OR (tokens_cached_in >= 0 AND tokens_cached_in <= tokens_in))", name="ck_llm_usage__tokens"),
        CheckConstraint("estimated_cost_usd >= 0", name="ck_llm_usage__cost"),
        CheckConstraint("latency_ms >= 0", name="ck_llm_usage__latency"),
        CheckConstraint("cache_status IN ('miss','hit','not_cacheable')", name="ck_llm_usage__cache_status"),
        CheckConstraint("outcome IN ('success','error','timeout','invalid_output','refused')", name="ck_llm_usage__outcome"),
        CheckConstraint("span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'", name="ck_llm_usage__span_format"),
        CheckConstraint("prompt_sha256 IS NULL OR prompt_sha256 ~ '^[0-9a-f]{64}$'", name="ck_llm_usage__prompt_sha256_format"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_llm_usage__trace_id_format"),
        Index("ix_llm_usage__tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_llm_usage__tenant_purpose_occurred", "tenant_id", "purpose", "occurred_at"),
        Index("ix_llm_usage__trace", "trace_id"),
        {"schema": "audit", "comment": "One row per LLM layer call (and per cache hit that avoided a call): provider, model, prompt version, tokens, estimated cost, latency, outcome, trace. Feeds `/brain/admin/cost`. Stores NO prompt or completion text."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    occurred_at: Optional[datetime] = Field(default=None, sa_column=Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Call time (UTC)."))
    purpose: str = Field(sa_column=Column("purpose", Text, nullable=False, comment="explanation | assistant_chat | agent_reasoning | briefing | other."))
    provider: str = Field(sa_column=Column("provider", Text, nullable=False, comment="LLM provider id (provider is an open decision, OD-18)."))
    model: str = Field(sa_column=Column("model", Text, nullable=False, comment="Exact model identifier returned/used."))
    model_route: Optional[str] = Field(default=None, sa_column=Column("model_route", Text, nullable=True, comment="template | small | large (model routing decision)."))
    prompt_name: str = Field(sa_column=Column("prompt_name", Text, nullable=False, comment="Prompt file name from `llm/prompts/`."))
    prompt_version: str = Field(sa_column=Column("prompt_version", Text, nullable=False, comment="Prompt version (git-tracked)."))
    tokens_in: int = Field(sa_column=Column("tokens_in", Integer, nullable=False, comment="Input tokens."))
    tokens_out: int = Field(sa_column=Column("tokens_out", Integer, nullable=False, comment="Output tokens."))
    tokens_cached_in: Optional[int] = Field(default=None, sa_column=Column("tokens_cached_in", Integer, nullable=True, comment="Input tokens served from the provider's prompt cache, if reported."))
    estimated_cost_usd: Decimal = Field(sa_column=Column("estimated_cost_usd", Numeric(12, 6), nullable=False, comment="Estimated cost in USD (micro-dollar precision)."))
    pricing_version: Optional[str] = Field(default=None, sa_column=Column("pricing_version", Text, nullable=True, comment="Price table used for the estimate."))
    latency_ms: int = Field(sa_column=Column("latency_ms", Integer, nullable=False, comment="End-to-end latency."))
    cache_status: Optional[str] = Field(default=None, sa_column=Column("cache_status", Text, nullable=False, server_default=text("'miss'"), comment="miss | hit (response cache, zero tokens) | not_cacheable."))
    outcome: str = Field(sa_column=Column("outcome", Text, nullable=False, comment="success | error | timeout | invalid_output | refused."))
    error_code: Optional[str] = Field(default=None, sa_column=Column("error_code", Text, nullable=True, comment="Short error code when outcome is not success."))
    schema_valid: Optional[bool] = Field(default=None, sa_column=Column("schema_valid", Boolean, nullable=True, comment="Whether the structured output validated against its JSON schema."))
    prompt_sha256: Optional[str] = Field(default=None, sa_column=Column("prompt_sha256", CHAR(64), nullable=True, comment="Hash of the rendered prompt (dedupe/cache analysis). The text itself is never stored."))
    actor_id: Optional[str] = Field(default=None, sa_column=Column("actor_id", Text, nullable=True, comment="JWT sub of the requesting user (pseudonymous), for per-user cost."))
    session_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("session_id", PG_UUID(as_uuid=True), nullable=True, comment="agent_session id. SOFT reference (no FK): usage rows outlive sessions."))
    tool_step: Optional[int] = Field(default=None, sa_column=Column("tool_step", SmallInteger, nullable=True, comment="Step number inside an agent run."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    span_id: Optional[str] = Field(default=None, sa_column=Column("span_id", CHAR(16), nullable=True, comment="W3C span-id."))

class AuditLog(BrainBase, table=True):
    """audit.audit_log: Brain audit trail: who proposed, approved/rejected, executed, which tool, which payload fingerprint, outcome, trace."""

    __tablename__ = "audit_log"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_audit_log"),
        UniqueConstraint("seq", name="uq_audit_log__seq"),
        CheckConstraint("event_type ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$'", name="ck_audit_log__event_type"),
        CheckConstraint("outcome IN ('success','failure','denied','info')", name="ck_audit_log__outcome"),
        CheckConstraint("actor_type IN ('user','agent','system')", name="ck_audit_log__actor_type"),
        CheckConstraint("actor_type = 'system' OR actor_id IS NOT NULL", name="ck_audit_log__actor_required"),
        CheckConstraint("(subject_type IS NULL) = (subject_id IS NULL)", name="ck_audit_log__subject_pair"),
        CheckConstraint("octet_length(details::text) <= 8192", name="ck_audit_log__details_size"),
        CheckConstraint("span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'", name="ck_audit_log__span_format"),
        CheckConstraint("arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'", name="ck_audit_log__arguments_sha256_format"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_audit_log__details_type"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_audit_log__trace_id_format"),
        Index("ix_audit_log__tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_log__trace", "trace_id"),
        Index("ix_audit_log__tenant_actor_occurred", "tenant_id", "actor_id", "occurred_at"),
        Index("ix_audit_log__subject", "tenant_id", "subject_type", "subject_id", "occurred_at"),
        {"schema": "audit", "comment": "Brain audit trail: who proposed, approved/rejected, executed, which tool, which payload fingerprint, outcome, trace. Distinct from `erp_db.AuditLog` (human changes in the ERP). Append-only."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    seq: Optional[int] = Field(default=None, sa_column=Column("seq", BigInteger, Identity(always=True), nullable=False, comment="Monotonic ordering / keyset-pagination key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    occurred_at: Optional[datetime] = Field(default=None, sa_column=Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Event time (UTC)."))
    event_type: str = Field(sa_column=Column("event_type", Text, nullable=False, comment="Dotted lowercase vocabulary, e.g. proposal.created, proposal.approved, proposal.rejected, execution.succeeded, tool.denied, model.status_changed."))
    outcome: str = Field(sa_column=Column("outcome", Text, nullable=False, comment="success | failure | denied | info."))
    actor_type: str = Field(sa_column=Column("actor_type", Text, nullable=False, comment="user | agent | system."))
    actor_id: Optional[str] = Field(default=None, sa_column=Column("actor_id", Text, nullable=True, comment="JWT sub for users; session id for agent; component name for system."))
    on_behalf_of_actor_id: Optional[str] = Field(default=None, sa_column=Column("on_behalf_of_actor_id", Text, nullable=True, comment="User on whose behalf an agent acted."))
    approved_by_actor_id: Optional[str] = Field(default=None, sa_column=Column("approved_by_actor_id", Text, nullable=True, comment="Approver (JWT sub) when relevant."))
    tool_name: Optional[str] = Field(default=None, sa_column=Column("tool_name", Text, nullable=True, comment="Registry tool name when relevant."))
    subject_type: Optional[str] = Field(default=None, sa_column=Column("subject_type", Text, nullable=True, comment="Kind of Brain object the event concerns (action_proposal, model_registry, ...)."))
    subject_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("subject_id", PG_UUID(as_uuid=True), nullable=True, comment="Brain object id. SOFT reference (polymorphic, no FK): audit rows must outlive subjects."))
    arguments_sha256: Optional[str] = Field(default=None, sa_column=Column("arguments_sha256", CHAR(64), nullable=True, comment="Fingerprint of the exact action payload involved."))
    details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Sanitised allow-listed context (status from/to, model_version, rule_version, result summary)."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    span_id: Optional[str] = Field(default=None, sa_column=Column("span_id", CHAR(16), nullable=True, comment="W3C span-id."))
    request_id: Optional[str] = Field(default=None, sa_column=Column("request_id", Text, nullable=True, comment="HTTP request id."))

class AgentSession(BrainBase, table=True):
    """agent.agent_session: Conversation/agent session: owner, small working context, tool allow-list, write cap, expiry."""

    __tablename__ = "agent_session"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_agent_session"),
        UniqueConstraint("tenant_id", "id", name="uq_agent_session__tenant_id_id"),
        CheckConstraint("char_length(user_actor_id) BETWEEN 1 AND 128", name="ck_agent_session__user"),
        CheckConstraint("status IN ('active','closed','expired')", name="ck_agent_session__status"),
        CheckConstraint("octet_length(state::text) <= 16384", name="ck_agent_session__state_size"),
        CheckConstraint("max_writes BETWEEN 0 AND 20", name="ck_agent_session__max_writes"),
        CheckConstraint("write_proposals_count >= 0 AND write_proposals_count <= max_writes", name="ck_agent_session__write_cap"),
        CheckConstraint("jsonb_typeof(state) = 'object'", name="ck_agent_session__state_type"),
        CheckConstraint("trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$'", name="ck_agent_session__trace_id_format"),
        Index("ix_agent_session__user_activity", "tenant_id", "user_actor_id", "last_activity_at"),
        Index("ix_agent_session__active_expiry", "tenant_id", "expires_at", postgresql_where=text("status = 'active'")),
        {"schema": "agent", "comment": "Conversation/agent session: owner, small working context, tool allow-list, write cap, expiry. Survives a browser refresh. Session-scoped memory only (no cross-session memory in MVP)."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    user_actor_id: str = Field(sa_column=Column("user_actor_id", Text, nullable=False, comment="JWT `sub` of the user who owns the session."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'active'"), comment="active | closed | expired."))
    state: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("state", JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="Compact working context (focused product ids, last intent). No PII, no raw ERP rows. <= 16 KB."))
    allowed_tools: Optional[List[str]] = Field(default=None, sa_column=Column("allowed_tools", ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"), comment="Per-session tool allow-list (guardrail)."))
    max_writes: Optional[int] = Field(default=None, sa_column=Column("max_writes", SmallInteger, nullable=False, server_default=text("3"), comment="Maximum write proposals per session (source example: 3)."))
    write_proposals_count: Optional[int] = Field(default=None, sa_column=Column("write_proposals_count", SmallInteger, nullable=False, server_default=text("0"), comment="Write proposals created so far; the CHECK against max_writes makes the cap a database guarantee."))
    started_at: Optional[datetime] = Field(default=None, sa_column=Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Session start (UTC)."))
    last_activity_at: Optional[datetime] = Field(default=None, sa_column=Column("last_activity_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last turn (UTC)."))
    expires_at: datetime = Field(sa_column=Column("expires_at", DateTime(timezone=True), nullable=False, comment="Inactivity expiry (UTC)."))
    row_version: Optional[int] = Field(default=None, sa_column=Column("row_version", Integer, nullable=False, server_default=text("1"), comment="Optimistic-concurrency counter; incremented on every UPDATE by the application."))
    trace_id: Optional[str] = Field(default=None, sa_column=Column("trace_id", CHAR(32), nullable=True, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    messages: List["AgentMessage"] = Relationship(sa_relationship_kwargs=RO)
    proposals: List["ActionProposal"] = Relationship(sa_relationship_kwargs=RO)
    actions: List["AgentAction"] = Relationship(sa_relationship_kwargs=RO)

class AgentMessage(BrainBase, table=True):
    """agent.agent_message: Recent conversation turns (the 'last N messages' memory)."""

    __tablename__ = "agent_message"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_agent_message"),
        UniqueConstraint("session_id", "turn_index", name="uq_agent_message__session_turn"),
        CheckConstraint("turn_index >= 0", name="ck_agent_message__turn"),
        CheckConstraint("role IN ('user','assistant','tool')", name="ck_agent_message__role"),
        CheckConstraint("char_length(content) <= 4000", name="ck_agent_message__content_len"),
        CheckConstraint("pii_scrubbed", name="ck_agent_message__scrubbed"),
        CheckConstraint("expires_at > created_at", name="ck_agent_message__expiry"),
        CheckConstraint("structured IS NULL OR jsonb_typeof(structured) = 'object'", name="ck_agent_message__structured_type"),
        ForeignKeyConstraint(["tenant_id", "session_id"], ["agent.agent_session.tenant_id", "agent.agent_session.id"], name="fk_agent_message__agent_session", ondelete="CASCADE"),
        Index("ix_agent_message__tenant_expires", "tenant_id", "expires_at"),
        Index("ix_agent_message__tenant_session", "tenant_id", "session_id"),
        {"schema": "agent", "comment": "Recent conversation turns (the 'last N messages' memory). Content is PII-scrubbed and size-bounded; rows carry their own expiry and are hard-deleted on schedule."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    session_id: uuid.UUID = Field(sa_column=Column("session_id", PG_UUID(as_uuid=True), nullable=False, comment="Owning session."))
    turn_index: int = Field(sa_column=Column("turn_index", Integer, nullable=False, comment="0-based turn number within the session."))
    role: str = Field(sa_column=Column("role", Text, nullable=False, comment="user | assistant | tool."))
    content: str = Field(sa_column=Column("content", Text, nullable=False, comment="Scrubbed text (<= 4000 chars). Assistant turns hold the human-readable explanation."))
    pii_scrubbed: Optional[bool] = Field(default=None, sa_column=Column("pii_scrubbed", Boolean, nullable=False, server_default=text("false"), comment="Writer's attestation that the PII scrubber ran. CHECK forces TRUE."))
    structured: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("structured", JSONB, nullable=True, comment="Typed Explanation JSON or compact tool-result summary (never raw ERP rows)."))
    llm_usage_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("llm_usage_id", PG_UUID(as_uuid=True), nullable=True, comment="audit.llm_usage row for assistant turns (soft reference, no FK)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Turn time (UTC)."))
    expires_at: datetime = Field(sa_column=Column("expires_at", DateTime(timezone=True), nullable=False, comment="Purge time for this turn (UTC)."))

    # read-only convenience relationships (writes go through repositories)
    session: Optional["AgentSession"] = Relationship(sa_relationship_kwargs=RO)

class ActionProposal(BrainBase, table=True):
    """agent.action_proposal: The immutable proposed write (tool + arguments) awaiting a human decision, plus its lifecycle status."""

    __tablename__ = "action_proposal"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_action_proposal"),
        UniqueConstraint("tenant_id", "id", name="uq_action_proposal__tenant_id_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_action_proposal__tenant_idempotency"),
        UniqueConstraint("tenant_id", "id", "arguments_sha256", name="uq_action_proposal__id_hash"),
        UniqueConstraint("tenant_id", "id", "idempotency_key", name="uq_action_proposal__id_idem"),
        CheckConstraint("proposed_by IN ('rules','agent')", name="ck_action_proposal__proposed_by"),
        CheckConstraint("proposed_by <> 'agent' OR (session_id IS NOT NULL AND requested_by_actor_id IS NOT NULL)", name="ck_action_proposal__agent_context"),
        CheckConstraint("requires_approval", name="ck_action_proposal__requires_approval"),
        CheckConstraint("status IN ('pending','approved','rejected','expired','cancelled','executing','succeeded','failed')", name="ck_action_proposal__status"),
        CheckConstraint("char_length(tool_name) BETWEEN 1 AND 100", name="ck_action_proposal__tool_len"),
        CheckConstraint("char_length(reason) BETWEEN 1 AND 500", name="ck_action_proposal__reason_len"),
        CheckConstraint("expires_at > created_at", name="ck_action_proposal__expiry"),
        CheckConstraint("octet_length(arguments::text) <= 32768", name="ck_action_proposal__args_size"),
        CheckConstraint("jsonb_typeof(arguments) = 'object'", name="ck_action_proposal__arguments_type"),
        CheckConstraint("arguments_sha256 ~ '^[0-9a-f]{64}$'", name="ck_action_proposal__arguments_sha256_format"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_action_proposal__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "session_id"], ["agent.agent_session.tenant_id", "agent.agent_session.id"], name="fk_action_proposal__agent_session", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "recommendation_id"], ["intel.recommendation.tenant_id", "intel.recommendation.id"], name="fk_action_proposal__recommendation", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "risk_assessment_id"], ["intel.risk_assessment.tenant_id", "intel.risk_assessment.id"], name="fk_action_proposal__risk_assessment", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "llm_usage_id"], ["audit.llm_usage.tenant_id", "audit.llm_usage.id"], name="fk_action_proposal__llm_usage", ondelete="RESTRICT"),
        Index("ix_action_proposal__pending", "tenant_id", "created_at", postgresql_where=text("status = 'pending'")),
        Index("ix_action_proposal__tenant_session", "tenant_id", "session_id", "created_at"),
        Index("ix_action_proposal__tenant_requester", "tenant_id", "requested_by_actor_id", "created_at"),
        Index("ix_action_proposal__tenant_recommendation", "tenant_id", "recommendation_id"),
        Index("uq_action_proposal__live_per_recommendation", "tenant_id", "recommendation_id", unique=True, postgresql_where=text("recommendation_id IS NOT NULL AND status IN ('pending','approved','executing')")),
        {"schema": "agent", "comment": "The immutable proposed write (tool + arguments) awaiting a human decision, plus its lifecycle status. Arguments and their SHA-256 can never change after insert; approvals and executions are cryptographically bound to that hash by composite FKs."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    session_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("session_id", PG_UUID(as_uuid=True), nullable=True, comment="Session that produced the proposal. Required when proposed_by = 'agent'; NULL allowed for deterministic rule proposals (D-29)."))
    requested_by_actor_id: Optional[str] = Field(default=None, sa_column=Column("requested_by_actor_id", Text, nullable=True, comment="JWT sub of the user who asked for the proposal. Required when proposed_by = 'agent'; NULL allowed for rule proposals created by the system (D-29)."))
    proposed_by: str = Field(sa_column=Column("proposed_by", Text, nullable=False, comment="rules (deterministic, built from a recommendation without the LLM, D-18) | agent (conversational path). Set explicitly; no default (D-29)."))
    tool_name: str = Field(sa_column=Column("tool_name", Text, nullable=False, comment="Registry tool name (e.g. create_purchase_order)."))
    tool_version: str = Field(sa_column=Column("tool_version", Text, nullable=False, comment="Registry schema version of the tool, e.g. 'create_purchase_order@1'."))
    arguments: Dict[str, Any] = Field(sa_column=Column("arguments", JSONB, nullable=False, comment="Validated arguments exactly as they will be sent. Immutable."))
    arguments_sha256: str = Field(sa_column=Column("arguments_sha256", CHAR(64), nullable=False, comment="SHA-256 (lowercase hex) of the RFC 8785 (JCS) canonical JSON of `arguments` (D-13; golden vectors in contracts/fixtures/hash). Approvals bind to it."))
    requires_approval: Optional[bool] = Field(default=None, sa_column=Column("requires_approval", Boolean, nullable=False, server_default=text("true"), comment="Always TRUE in MVP (every write needs a human)."))
    policy_version: str = Field(sa_column=Column("policy_version", Text, nullable=False, comment="Static policy version that returned require-approval."))
    reason: str = Field(sa_column=Column("reason", Text, nullable=False, comment="Templated human-readable reason (<= 500 chars), e.g. 'high stockout risk (cover 1.7d < lead time 5d)'. Generated by code, not by the LLM."))
    recommendation_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("recommendation_id", PG_UUID(as_uuid=True), nullable=True, comment="Recommendation the proposal was built from."))
    risk_assessment_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("risk_assessment_id", PG_UUID(as_uuid=True), nullable=True, comment="Risk assessment behind it. This is the API `insight_id` (OD-06)."))
    llm_usage_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("llm_usage_id", PG_UUID(as_uuid=True), nullable=True, comment="LLM call that proposed the tool call (which model proposed it)."))
    idempotency_key: uuid.UUID = Field(sa_column=Column("idempotency_key", PG_UUID(as_uuid=True), nullable=False, comment="Generated once at proposal creation; sent as `Idempotency-Key` on every execution attempt of this proposal."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'pending'"), comment="pending | approved | rejected | expired | cancelled | executing | succeeded | failed."))
    status_changed_at: Optional[datetime] = Field(default=None, sa_column=Column("status_changed_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last status change (set by trigger)."))
    expires_at: datetime = Field(sa_column=Column("expires_at", DateTime(timezone=True), nullable=False, comment="Approval deadline; after it a pending proposal cannot be approved."))
    row_version: Optional[int] = Field(default=None, sa_column=Column("row_version", Integer, nullable=False, server_default=text("1"), comment="Optimistic-concurrency counter; incremented on every UPDATE by the application."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

    # read-only convenience relationships (writes go through repositories)
    session: Optional["AgentSession"] = Relationship(sa_relationship_kwargs=RO)
    recommendation: Optional["Recommendation"] = Relationship(sa_relationship_kwargs=RO)
    risk_assessment: Optional["RiskAssessment"] = Relationship(sa_relationship_kwargs=RO)
    llm_usage: Optional["LlmUsage"] = Relationship(sa_relationship_kwargs=RO)
    approvals: List["ActionApproval"] = Relationship(sa_relationship_kwargs=RO)
    executions: List["ActionExecution"] = Relationship(sa_relationship_kwargs=RO)

class AgentAction(BrainBase, table=True):
    """agent.agent_action: Log of every tool call the agent attempted, including rejected ones (unknown tool, bad arguments, policy deny)."""

    __tablename__ = "agent_action"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_agent_action"),
        CheckConstraint("outcome IN ('executed','pending_approval','denied_policy','rejected_unknown_tool','rejected_invalid_arguments','rejected_scope','error')", name="ck_agent_action__outcome"),
        CheckConstraint("char_length(tool_name) BETWEEN 1 AND 100", name="ck_agent_action__tool_len"),
        CheckConstraint("(outcome = 'pending_approval') = (proposal_id IS NOT NULL)", name="ck_agent_action__pending_has_proposal"),
        CheckConstraint("proposal_id IS NULL OR arguments IS NULL", name="ck_agent_action__write_args_on_proposal"),
        CheckConstraint("outcome <> 'rejected_unknown_tool' OR read_only IS NULL", name="ck_agent_action__unknown_tool"),
        CheckConstraint("arguments IS NULL OR octet_length(arguments::text) <= 8192", name="ck_agent_action__args_size"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_agent_action__duration"),
        CheckConstraint("arguments IS NULL OR jsonb_typeof(arguments) = 'object'", name="ck_agent_action__arguments_type"),
        CheckConstraint("arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_action__arguments_sha256_format"),
        CheckConstraint("result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'", name="ck_agent_action__result_summary_type"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_agent_action__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "session_id"], ["agent.agent_session.tenant_id", "agent.agent_session.id"], name="fk_agent_action__agent_session", ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "proposal_id"], ["agent.action_proposal.tenant_id", "agent.action_proposal.id"], name="fk_agent_action__action_proposal", ondelete="RESTRICT"),
        Index("ix_agent_action__tenant_session_created", "tenant_id", "session_id", "created_at"),
        Index("ix_agent_action__tenant_tool_created", "tenant_id", "tool_name", "created_at"),
        Index("ix_agent_action__trace", "trace_id"),
        Index("ix_agent_action__tenant_proposal", "tenant_id", "proposal_id", postgresql_where=text("proposal_id IS NOT NULL")),
        {"schema": "agent", "comment": "Log of every tool call the agent attempted, including rejected ones (unknown tool, bad arguments, policy deny). For write tools it only points at the ActionProposal; the authorisation and execution detail live in the proposal/approval/execution tables."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    session_id: uuid.UUID = Field(sa_column=Column("session_id", PG_UUID(as_uuid=True), nullable=False, comment="Session."))
    turn_index: Optional[int] = Field(default=None, sa_column=Column("turn_index", Integer, nullable=True, comment="Turn that triggered the call (no FK; messages expire)."))
    tool_name: str = Field(sa_column=Column("tool_name", Text, nullable=False, comment="Tool name as attempted (kept even when not in the registry)."))
    tool_version: Optional[str] = Field(default=None, sa_column=Column("tool_version", Text, nullable=True, comment="Registry version when known."))
    read_only: Optional[bool] = Field(default=None, sa_column=Column("read_only", Boolean, nullable=True, comment="Registry flag; NULL for unknown tools."))
    requires_approval: Optional[bool] = Field(default=None, sa_column=Column("requires_approval", Boolean, nullable=True, comment="Registry flag; NULL for unknown tools."))
    arguments: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("arguments", JSONB, nullable=True, comment="Arguments for read tools only (<= 8 KB). NULL for write intents - those live on the proposal."))
    arguments_sha256: Optional[str] = Field(default=None, sa_column=Column("arguments_sha256", CHAR(64), nullable=True, comment="Fingerprint of the arguments."))
    outcome: str = Field(sa_column=Column("outcome", Text, nullable=False, comment="executed | pending_approval | denied_policy | rejected_unknown_tool | rejected_invalid_arguments | rejected_scope | error."))
    proposal_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("proposal_id", PG_UUID(as_uuid=True), nullable=True, comment="Set when outcome is pending_approval."))
    result_summary: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("result_summary", JSONB, nullable=True, comment="Compact result facts (counts, ids). Never raw rows."))
    error_code: Optional[str] = Field(default=None, sa_column=Column("error_code", Text, nullable=True, comment="Short error code."))
    duration_ms: Optional[int] = Field(default=None, sa_column=Column("duration_ms", Integer, nullable=True, comment="Tool latency."))
    llm_usage_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("llm_usage_id", PG_UUID(as_uuid=True), nullable=True, comment="LLM call that proposed the tool call (soft reference)."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Call time (UTC)."))

    # read-only convenience relationships (writes go through repositories)
    session: Optional["AgentSession"] = Relationship(sa_relationship_kwargs=RO)
    proposal: Optional["ActionProposal"] = Relationship(sa_relationship_kwargs=RO)

class ActionApproval(BrainBase, table=True):
    """agent.action_approval: Immutable human decision (approve or reject) on a specific proposal payload."""

    __tablename__ = "action_approval"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_action_approval"),
        UniqueConstraint("tenant_id", "proposal_id", "approval_round", name="uq_action_approval__proposal_round"),
        UniqueConstraint("tenant_id", "id", "proposal_id", "arguments_sha256", name="uq_action_approval__id_proposal_hash"),
        CheckConstraint("approval_round >= 1", name="ck_action_approval__round"),
        CheckConstraint("decision IN ('approved','rejected')", name="ck_action_approval__decision"),
        CheckConstraint("'agent:approve' = ANY(decider_scopes)", name="ck_action_approval__scope"),
        CheckConstraint("reason_code IS NULL OR reason_code IN ('too_much','wrong_supplier','not_needed','stock_arriving','other')", name="ck_action_approval__reason_code"),
        CheckConstraint("char_length(decided_by_actor_id) BETWEEN 1 AND 128", name="ck_action_approval__actor"),
        CheckConstraint("left(decided_by_actor_id, 7) <> 'system:'", name="ck_action_approval__human_actor"),
        CheckConstraint("arguments_sha256 ~ '^[0-9a-f]{64}$'", name="ck_action_approval__arguments_sha256_format"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_action_approval__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "proposal_id", "arguments_sha256"], ["agent.action_proposal.tenant_id", "agent.action_proposal.id", "agent.action_proposal.arguments_sha256"], name="fk_action_approval__action_proposal", ondelete="RESTRICT"),
        Index("ix_action_approval__tenant_actor_decided", "tenant_id", "decided_by_actor_id", "decided_at"),
        {"schema": "agent", "comment": "Immutable human decision (approve or reject) on a specific proposal payload. The composite FK to (proposal id, arguments_sha256) means an approval can only ever exist for the exact payload that was proposed."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    proposal_id: uuid.UUID = Field(sa_column=Column("proposal_id", PG_UUID(as_uuid=True), nullable=False, comment="Proposal decided."))
    approval_round: Optional[int] = Field(default=None, sa_column=Column("approval_round", SmallInteger, nullable=False, server_default=text("1"), comment="1 for the first decision; 2+ only for a fresh human re-approval after the proposal failed with an unknown outcome (D-43). A round covers the worker's same-key retries while the proposal is executing; once the proposal is failed, only a new round re-opens it."))
    decision: str = Field(sa_column=Column("decision", Text, nullable=False, comment="approved | rejected."))
    decided_by_actor_id: str = Field(sa_column=Column("decided_by_actor_id", Text, nullable=False, comment="Authenticated approver (JWT sub). Never a job actor: CHECK rejects 'system:' ids (D-45)."))
    decider_scopes: List[str] = Field(sa_column=Column("decider_scopes", ARRAY(Text), nullable=False, comment="Scopes in the approver's JWT at decision time (must include agent:approve)."))
    arguments_sha256: str = Field(sa_column=Column("arguments_sha256", CHAR(64), nullable=False, comment="Hash of the payload the approver saw; must equal the proposal's (composite FK)."))
    reason_code: Optional[str] = Field(default=None, sa_column=Column("reason_code", Text, nullable=True, comment="Optional fixed code for a rejection (no free text, no PII)."))
    decided_at: Optional[datetime] = Field(default=None, sa_column=Column("decided_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Decision time (UTC), always the server time of the insert (set by trigger). The approval is valid while now() <= decided_at + 24 h (D-44)."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))

    # read-only convenience relationships (writes go through repositories)
    proposal: Optional["ActionProposal"] = Relationship(sa_relationship_kwargs=RO)
    executions: List["ActionExecution"] = Relationship(sa_relationship_kwargs=RO)

class ActionExecution(BrainBase, table=True):
    """agent.action_execution: One row per execution attempt of an approved proposal against the Canonical API."""

    __tablename__ = "action_execution"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_action_execution"),
        UniqueConstraint("tenant_id", "id", name="uq_action_execution__tenant_id_id"),
        UniqueConstraint("tenant_id", "proposal_id", "attempt_no", name="uq_action_execution__proposal_attempt"),
        CheckConstraint("attempt_no >= 1", name="ck_action_execution__attempt"),
        CheckConstraint("status IN ('started','succeeded','failed')", name="ck_action_execution__status"),
        CheckConstraint("outcome_certainty IS NULL OR outcome_certainty IN ('definitive','unknown')", name="ck_action_execution__certainty"),
        CheckConstraint("(status = 'started') = (completed_at IS NULL)", name="ck_action_execution__completion"),
        CheckConstraint("status <> 'failed' OR (outcome_certainty IS NOT NULL AND error_code IS NOT NULL)", name="ck_action_execution__failed_fields"),
        CheckConstraint("status <> 'succeeded' OR error_code IS NULL", name="ck_action_execution__success_clean"),
        CheckConstraint("external_ref_type IS NULL OR external_ref_type IN ('purchase_order')", name="ck_action_execution__ref_type"),
        CheckConstraint("error_message IS NULL OR char_length(error_message) <= 500", name="ck_action_execution__message_len"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_action_execution__duration"),
        CheckConstraint("arguments_sha256 ~ '^[0-9a-f]{64}$'", name="ck_action_execution__arguments_sha256_format"),
        CheckConstraint("result IS NULL OR jsonb_typeof(result) = 'object'", name="ck_action_execution__result_type"),
        CheckConstraint("trace_id ~ '^[0-9a-f]{32}$'", name="ck_action_execution__trace_id_format"),
        ForeignKeyConstraint(["tenant_id", "approval_id", "proposal_id", "arguments_sha256"], ["agent.action_approval.tenant_id", "agent.action_approval.id", "agent.action_approval.proposal_id", "agent.action_approval.arguments_sha256"], name="fk_action_execution__action_approval", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "proposal_id", "idempotency_key"], ["agent.action_proposal.tenant_id", "agent.action_proposal.id", "agent.action_proposal.idempotency_key"], name="fk_action_execution__action_proposal", ondelete="RESTRICT"),
        Index("uq_action_execution__one_inflight", "tenant_id", "proposal_id", unique=True, postgresql_where=text("status = 'started'")),
        Index("uq_action_execution__one_success", "tenant_id", "proposal_id", unique=True, postgresql_where=text("status = 'succeeded'")),
        Index("ix_action_execution__tenant_started", "tenant_id", "started_at"),
        Index("ix_action_execution__trace", "trace_id"),
        {"schema": "agent", "comment": "One row per execution attempt of an approved proposal against the Canonical API. Records the ActionResult (success/failed, reason), outcome certainty and the ERP object created. Partial unique indexes make a second concurrent attempt or a second success impossible."},
    )

    id: Optional[uuid.UUID] = Field(default=None, sa_column=Column("id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"), comment="Internal Brain surrogate key."))
    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant."))
    proposal_id: uuid.UUID = Field(sa_column=Column("proposal_id", PG_UUID(as_uuid=True), nullable=False, comment="Proposal executed."))
    approval_id: uuid.UUID = Field(sa_column=Column("approval_id", PG_UUID(as_uuid=True), nullable=False, comment="Approval that authorised this attempt: always the latest decision round (D-43)."))
    attempt_no: int = Field(sa_column=Column("attempt_no", SmallInteger, nullable=False, comment="1, 2, ... per proposal."))
    arguments_sha256: str = Field(sa_column=Column("arguments_sha256", CHAR(64), nullable=False, comment="Hash of the payload actually sent; must equal the approved hash (composite FK)."))
    idempotency_key: uuid.UUID = Field(sa_column=Column("idempotency_key", PG_UUID(as_uuid=True), nullable=False, comment="Same key as the proposal; sent as Idempotency-Key (composite FK)."))
    on_behalf_of_actor_id: str = Field(sa_column=Column("on_behalf_of_actor_id", Text, nullable=False, comment="User whose JWT scopes were used for the Canonical write."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'started'"), comment="started | succeeded | failed."))
    outcome_certainty: Optional[str] = Field(default=None, sa_column=Column("outcome_certainty", Text, nullable=True, comment="For failed: definitive (adapter rejected, no ERP write) | unknown (timeout/5xx; the write may have happened)."))
    started_at: Optional[datetime] = Field(default=None, sa_column=Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Attempt start (UTC)."))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column("completed_at", DateTime(timezone=True), nullable=True, comment="Attempt end (UTC)."))
    duration_ms: Optional[int] = Field(default=None, sa_column=Column("duration_ms", Integer, nullable=True, comment="Canonical call latency."))
    canonical_http_status: Optional[int] = Field(default=None, sa_column=Column("canonical_http_status", SmallInteger, nullable=True, comment="HTTP status from the Canonical API."))
    external_ref_type: Optional[str] = Field(default=None, sa_column=Column("external_ref_type", Text, nullable=True, comment="Kind of ERP object created (purchase_order)."))
    external_ref_id: Optional[str] = Field(default=None, sa_column=Column("external_ref_id", Text, nullable=True, comment="ERP identifier/number of the created object (e.g. PO #1234)."))
    error_code: Optional[str] = Field(default=None, sa_column=Column("error_code", Text, nullable=True, comment="Canonical error envelope code."))
    error_message: Optional[str] = Field(default=None, sa_column=Column("error_message", Text, nullable=True, comment="Sanitised message (<= 500 chars)."))
    result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column("result", JSONB, nullable=True, comment="ActionResult JSON {status, reason, ...} validated against the ai-output schema."))
    trace_id: str = Field(sa_column=Column("trace_id", CHAR(32), nullable=False, comment="W3C trace-id (32 lowercase hex) linking the work to the originating request/job."))

    # read-only convenience relationships (writes go through repositories)
    approval: Optional["ActionApproval"] = Relationship(sa_relationship_kwargs=RO)
    proposal: Optional["ActionProposal"] = Relationship(sa_relationship_kwargs=RO)

class TenantRegistry(BrainBase, table=True):
    """ingest.tenant_registry: Stable registry of the tenants (ERP organizations) this Brain serves, with a REFERENCE to each tenant's Canonical API credential (never the secret)."""

    __tablename__ = "tenant_registry"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", name="pk_tenant_registry"),
        CheckConstraint("status IN ('provisioning','active','suspended')", name="ck_tenant_registry__status"),
        CheckConstraint("display_label IS NULL OR char_length(display_label) BETWEEN 1 AND 100", name="ck_tenant_registry__label_len"),
        CheckConstraint("status_reason IS NULL OR char_length(status_reason) <= 200", name="ck_tenant_registry__reason_len"),
        CheckConstraint("credential_ref IS NULL OR credential_ref ~ '^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_.-]*){0,4}$' AND char_length(credential_ref) <= 200", name="ck_tenant_registry__credential_ref_format"),
        CheckConstraint("credential_version >= 0", name="ck_tenant_registry__credential_version"),
        CheckConstraint("credential_validated_at IS NULL OR (credential_ref IS NOT NULL AND credential_sha256 IS NOT NULL)", name="ck_tenant_registry__validated_needs_credential"),
        CheckConstraint("status <> 'active' OR (credential_validated_at IS NOT NULL AND activated_at IS NOT NULL)", name="ck_tenant_registry__active_requirements"),
        CheckConstraint("status <> 'suspended' OR (suspended_at IS NOT NULL AND status_reason IS NOT NULL)", name="ck_tenant_registry__suspended_requirements"),
        CheckConstraint("credential_sha256 IS NULL OR credential_sha256 ~ '^[0-9a-f]{64}$'", name="ck_tenant_registry__credential_sha256_format"),
        Index("ix_tenant_registry__status", "status"),
        {"schema": "ingest", "comment": "Stable registry of the tenants (ERP organizations) this Brain serves, with a REFERENCE to each tenant's Canonical API credential (never the secret). brain-worker runs jobs only for `active` tenants; brain-api refuses tokens of tenants that are not `active` (N-01). A tenant is created as `provisioning` and becomes `active` only when its credential was validated and its rule sets exist."},
    )

    tenant_id: uuid.UUID = Field(sa_column=Column("tenant_id", PG_UUID(as_uuid=True), primary_key=True, nullable=False, comment="Tenant UUID = ERP organization id (external reference owned by ERP Identity). Primary key: one row per tenant, never reused or renamed."))
    display_label: Optional[str] = Field(default=None, sa_column=Column("display_label", Text, nullable=True, comment="Short non-sensitive label for operators (e.g. 'Demo pharmacy A'). Never used for authorization."))
    status: Optional[str] = Field(default=None, sa_column=Column("status", Text, nullable=False, server_default=text("'provisioning'"), comment="provisioning (created, not yet usable) | active (jobs run, API serves) | suspended (jobs skipped, API refuses; data kept)."))
    status_reason: Optional[str] = Field(default=None, sa_column=Column("status_reason", Text, nullable=True, comment="Why the tenant is suspended (operator text, <= 200 chars, no secrets)."))
    credential_ref: Optional[str] = Field(default=None, sa_column=Column("credential_ref", Text, nullable=True, comment="Name of this tenant's Canonical API credential in the secret store, e.g. 'canonical/<tenant_id>' (a file under CANONICAL_CREDENTIALS_DIR). A reference only: the secret itself never enters the database, source control or logs."))
    credential_sha256: Optional[str] = Field(default=None, sa_column=Column("credential_sha256", CHAR(64), nullable=True, comment="SHA-256 of the credential value that was validated. brain-worker refuses to call Canonical when the loaded secret does not match it (stale or swapped secret). Not reversible to the secret."))
    credential_version: Optional[int] = Field(default=None, sa_column=Column("credential_version", Integer, nullable=False, server_default=text("0"), comment="Incremented by trigger on every credential change (rotation counter)."))
    credential_validated_at: Optional[datetime] = Field(default=None, sa_column=Column("credential_validated_at", DateTime(timezone=True), nullable=True, comment="Server time of the last successful validation: a Canonical read made with this credential returned this tenant_id. Cleared by trigger when the credential changes without a new validation."))
    activated_at: Optional[datetime] = Field(default=None, sa_column=Column("activated_at", DateTime(timezone=True), nullable=True, comment="Server time of the last move to active (set by trigger)."))
    suspended_at: Optional[datetime] = Field(default=None, sa_column=Column("suspended_at", DateTime(timezone=True), nullable=True, comment="Server time of the last move to suspended (set by trigger)."))
    provisioned_by: str = Field(sa_column=Column("provisioned_by", Text, nullable=False, comment="Operator id that ran the provisioning command (audit; no secrets)."))
    created_at: Optional[datetime] = Field(default=None, sa_column=Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Row creation time (UTC)."))
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()"), comment="Last modification time (UTC); maintained by trigger."))

__all__ = ["SyncCheckpoint", "IngestFailure", "CanonicalCache", "SalesFact", "SalesDayCoverage", "CalendarDay", "FeatureDaily", "RuleConfig", "TrainingRun", "ModelRegistry", "ModelEvaluation", "Forecast", "ForecastPoint", "AnomalyEvent", "RiskAssessment", "Recommendation", "Briefing", "LlmUsage", "AuditLog", "AgentSession", "AgentMessage", "ActionProposal", "AgentAction", "ActionApproval", "ActionExecution", "TenantRegistry", "DEFAULT_TENANT_ID"]
