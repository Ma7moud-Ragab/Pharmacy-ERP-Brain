"""Brain internal contracts: domain types, ports (interfaces) and errors.

Status: v1.0.0-proposed (21 Oct 2026). Owner: Ibrahim (contracts kit owner, D-02).
Prose and rules: contracts/internal/BRAIN_CONTRACTS.md. That file wins if the two disagree.

How to use this file
--------------------
Copy it unchanged into the Brain package as `brain/ports.py` (task BB-01). Every module imports its
types and interfaces from there. Change it only through a contracts pull request (same rule as
contracts/schemas): a new optional field or a new method is minor; renaming, removing or changing the
meaning of anything is major and needs every owner in CODEOWNERS.

Design rules this file encodes (see BRAIN_CONTRACTS.md section 2):
  * Engines are PURE. Feature building, anomaly, risk, recommendation, proposal building and template
    explanations take plain inputs and return plain outputs. No database, no HTTP, no clock, no random.
    That is what lets four people build and test them in parallel before the database exists.
  * Jobs and services do the I/O. They read through repositories and the canonical source, call the
    engines, and write results in one transaction per unit of work.
  * Every call carries a RunContext. tenant_id comes from it, never from a module-level constant.
  * Quantities are Decimal at the domain boundary (brain_db uses NUMERIC). Engines may convert to float
    internally for maths, but must return Decimal.

Python 3.11+, standard library only, so it type-checks before any dependency is installed.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

CONTRACT_VERSION = "1.0"

# =====================================================================================================
# 1. Shared vocabulary
# =====================================================================================================

Severity = Literal["low", "medium", "high"]


class JobName(str, Enum):
    """Every scheduled or on-demand unit of work. The value is also the `ingest.sync_checkpoint.resource`
    row that stores its last status, and the advisory-lock key (BRAIN_CONTRACTS.md section 5)."""

    SALES_POLL = "sales_poll"                      # every platform.sales_poll_interval_seconds
    INTEL_WINDOW = "intel_window"                  # every platform.intel_window_minutes
    END_OF_DAY = "end_of_day"                      # once a day at platform.end_of_day_run_local_time
    # Steps of END_OF_DAY. Each one is also runnable alone (admin "run now", tests).
    SALES_RECONCILE = "sales_reconcile"
    FEATURE_NIGHTLY_FULL = "feature_nightly_full"
    TRAINING = "training"
    FORECAST_INFERENCE = "forecast_inference"
    EVALUATION = "evaluation"
    # Housekeeping (hourly, part of INTEL_WINDOW's tick, not a separate schedule)
    PROPOSAL_EXPIRY = "proposal_expiry"


JobTrigger = Literal["schedule", "run_now", "test"]
JobStatus = Literal["succeeded", "partial", "failed", "skipped_locked"]


@dataclass(frozen=True, slots=True)
class RunContext:
    """Passed into every job, service, repository and port call.

    tenant_id   the ERP organization the work belongs to (D-34). API: taken ONLY from the verified JWT, and
                only if that tenant is active in the registry (N-01). Worker: the TenantEntry the scheduler
                is processing (TenantRegistry.active_tenants). Never a default, never from a request body or
                query string. Every repository call filters on it, and the unit of work sets it as the
                transaction-local app.tenant_id for row-level security (N-02, BRAIN_CONTRACTS.md section 7).
    run_id      new UUID per job run or per API request; becomes forecast.job_run_id etc.
    trace_id    32 lowercase hex chars (W3C trace id); goes into every *.trace_id column and log line.
    now_utc     the run's clock, read ONCE at the start. Engines never call datetime.now().
    business_today  today's date in the tenant timezone (platform.business_timezone), derived from now_utc.
    actor_id    JWT sub for API requests; "system:<job name>" for jobs.
    """

    tenant_id: UUID
    run_id: UUID
    trace_id: str
    now_utc: datetime
    business_today: date
    actor_id: str


# =====================================================================================================
# 2. Domain records read from the ERP (already validated against contracts/schemas/canonical)
#    The canonical source maps wire JSON to these. Engines never see wire JSON.
# =====================================================================================================


@dataclass(frozen=True, slots=True)
class DailySalesRow:
    """One canonical.DailySalesTotal."""

    product_id: UUID
    business_date: date
    units_sold: Decimal
    units_returned: Decimal
    net_units: Decimal               # may be negative; demand label = max(net_units, 0) (D-06, Q6)
    day_status: Literal["open", "closed"]
    complete: bool
    source_updated_at: datetime      # ERP updated_at, UTC


@dataclass(frozen=True, slots=True)
class SalesPage:
    items: Sequence[DailySalesRow]
    next_cursor: str | None
    high_watermark: datetime
    coverage_from: date
    coverage_to: date
    incomplete_dates: Sequence[date]
    rejected_rows: int = 0           # rows that failed schema validation (skipped, see section 6.2)


@dataclass(frozen=True, slots=True)
class ProductInfo:
    product_id: UUID
    sku: str
    name: str
    active: bool
    unit: str
    preferred_supplier_id: UUID | None
    pack_multiple: int | None        # None -> engines use 1 (D-21)
    max_order_qty: int | None        # None -> no cap
    source_updated_at: datetime


InventoryRejection = Literal[
    "inventory_source_disabled",        # rule_config platform.inventory_source = "none" (option D, the default)
    "inventory_incomplete",             # complete = false
    "inventory_count_mismatch",         # locations_included != number of 'included' locations
    "inventory_arithmetic_mismatch",    # available != on_hand - reserved
    "inventory_location_set_mismatch",  # locations differ from the location register (ids or status)
    "inventory_stale_location",         # an included location older than updated_at - inventory_freshness_seconds
    "inventory_unreadable",             # live read or register read failed (no cache fallback for stock)
]


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    """One canonical.OrganizationInventory that PASSED the checks in BRAIN_CONTRACTS.md section 7.13 (D-48, D-49).
    The only stock the risk and recommendation engines ever see. It is never built from location records:
    the Brain does not sum branch stock. If any check fails the product is not assessable (INVENTORY_UNAVAILABLE)
    and the job counts the InventoryRejection."""

    product_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    reorder_point: Decimal | None
    as_of: datetime                  # ERP updated_at
    locations_included: int
    source: Literal["canonical_live"]  # organization stock is read live, never from canonical_cache (D-49)


@dataclass(frozen=True, slots=True)
class LocationInventory:
    """One canonical.InventoryItem (location_id never null). Diagnostics and display only: never summed,
    never passed to an engine (D-48)."""

    product_id: UUID
    location_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    as_of: datetime


@dataclass(frozen=True, slots=True)
class LocationRegister:
    """canonical.LocationList: the expected location set, and the active-location count used for
    BRANCH_DECISION_REQUIRED (D-49)."""

    active_location_ids: frozenset[UUID]
    inactive_location_ids: frozenset[UUID]
    as_of: datetime


@dataclass(frozen=True, slots=True)
class SupplierInfo:
    supplier_id: UUID
    name: str
    active: bool
    lead_time_days: int | None
    source_updated_at: datetime


@dataclass(frozen=True, slots=True)
class OpenPurchaseOrderQty:
    """Sum of open quantity for one product across open POs (draft, submitted, partially_received)."""

    product_id: UUID
    open_qty: Decimal
    purchase_order_ids: Sequence[UUID]


@dataclass(frozen=True, slots=True)
class DraftPurchaseOrderLine:
    product_id: UUID
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    """canonical approval_block (D-11)."""

    proposal_id: UUID
    approved_by: str
    approved_at: datetime
    arguments_sha256: str


@dataclass(frozen=True, slots=True)
class DraftPurchaseOrderRequest:
    """canonical create_draft_po_request. supplier_id and lines are EXACTLY the proposal arguments."""

    supplier_id: UUID
    lines: Sequence[DraftPurchaseOrderLine]
    approval: ApprovalEvidence
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DraftPurchaseOrderResult:
    purchase_order_id: UUID
    http_status: int                 # 201 created, 200 replay of an earlier identical request
    replayed: bool


# =====================================================================================================
# 3. Errors. One hierarchy for the whole Brain. `code` matches contracts/schemas/common/error.schema.json.
# =====================================================================================================

ErrorCode = Literal[
    "VALIDATION_ERROR", "NOT_FOUND", "CONFLICT", "UNAUTHORIZED", "FORBIDDEN",
    "DEPENDENCY_UNAVAILABLE", "IDEMPOTENCY_CONFLICT", "INTERNAL_ERROR",
]


class BrainError(Exception):
    """Base class. `retryable` tells the caller whether the SAME call may be retried (section 6.1)."""

    code: ErrorCode = "INTERNAL_ERROR"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, detail_code: str | None = None,
                 details: Sequence[Mapping[str, str]] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.detail_code = detail_code or self.code      # stable machine code, e.g. FEATURE_SET_MISMATCH
        self.details = tuple(details)


class ValidationFailed(BrainError):
    code, http_status = "VALIDATION_ERROR", 422


class NotFound(BrainError):
    code, http_status = "NOT_FOUND", 404


class Conflict(BrainError):
    """State conflict: hash mismatch, expired proposal, conflicting repeat decision, wrong status."""

    code, http_status = "CONFLICT", 409


class BranchDecisionRequired(Conflict):
    """POST /recommendations/{id}/proposal for a tenant with more than one active location: the draft PO would
    need a destination location and N-10 has not defined it (D-49). detail_code BRANCH_DECISION_REQUIRED."""

    def __init__(self, message: str = "a branch decision is required before a draft purchase order (N-10)") -> None:
        super().__init__(message, detail_code="BRANCH_DECISION_REQUIRED")


class InventoryRejected(ValidationFailed):
    """Organization stock failed a section 7.13 check. Callers record `reason` and treat the product as not
    assessable (INVENTORY_UNAVAILABLE); it never reaches an engine."""

    def __init__(self, message: str, *, reason: InventoryRejection) -> None:
        super().__init__(message, detail_code="INVENTORY_REJECTED")
        self.reason: InventoryRejection = reason


class IdempotencyConflict(BrainError):
    """Same Idempotency-Key with a different body (adapter 409, D-09). Never retry; it is a bug."""

    code, http_status = "IDEMPOTENCY_CONFLICT", 409


class DependencyUnavailable(BrainError):
    """Canonical API / LLM / database unreachable, timed out or 5xx. Retryable with backoff."""

    code, http_status, retryable = "DEPENDENCY_UNAVAILABLE", 503, True


class OutcomeUncertain(DependencyUnavailable):
    """A WRITE timed out: the adapter may or may not have created the draft PO. Resolve only by
    retrying with the SAME Idempotency-Key (D-09) while the proposal is executing; once it is failed, only after
    a new human approval round (D-43). Maps to ActionResult.outcome = 'uncertain'."""


class Unauthorized(BrainError):
    code, http_status = "UNAUTHORIZED", 401


class Forbidden(BrainError):
    code, http_status = "FORBIDDEN", 403


class FeatureSetMismatch(BrainError):
    """Model and feature rows disagree on feature_set_version. Inference fails closed (MVP §3.6)."""

    code, http_status = "CONFLICT", 409


class ConfigInvalid(BrainError):
    """Settings or the active rule_config failed validation. The process must not start."""


# =====================================================================================================
# 4. Ports to the outside world
# =====================================================================================================

# ---- 4.0 Tenants and per-tenant ERP credentials (N-01) ---------------------------------------------------

TenantStatus = Literal["provisioning", "active", "suspended"]


@dataclass(frozen=True, slots=True)
class TenantEntry:
    """One ingest.tenant_registry row. Holds a REFERENCE to the tenant's Canonical credential, never the secret."""

    tenant_id: UUID
    status: TenantStatus
    credential_ref: str              # name in the secret store, e.g. "canonical/<tenant_id>"
    credential_sha256: str           # SHA-256 (lowercase hex) of the credential value that was validated
    credential_version: int


@dataclass(frozen=True, slots=True)
class CanonicalCredential:
    """A loaded secret. Lives only in memory, is never logged, cached on disk or written to the database."""

    tenant_id: UUID
    credential_version: int
    secret: str = field(repr=False)


class TenantRegistry(Protocol):
    """Reads ingest.tenant_registry (N-01). Writes happen only in the provisioning command (brain_provisioner)."""

    def active_tenants(self) -> Sequence[TenantEntry]:
        """brain-worker, at every scheduler tick, before any tenant context exists. Only status='active'."""
        ...

    def is_active(self, tenant_id: UUID) -> bool:
        """brain-api, after JWT verification. False -> 403 FORBIDDEN, detail TENANT_NOT_ACTIVE."""
        ...


class CredentialProvider(Protocol):
    """Loads a tenant's Canonical credential from the secret store (CANONICAL_CREDENTIALS_DIR/<credential_ref>).

    Raises ConfigInvalid (for that tenant only) when the secret is missing or its SHA-256 differs from
    entry.credential_sha256 (rotated without re-validation, or swapped with another tenant's file). The
    message names the tenant and credential_ref, never the secret."""

    def load(self, entry: TenantEntry) -> CanonicalCredential: ...


class CanonicalSourceFactory(Protocol):
    """Builds the Canonical client for ONE tenant. There is no shared, tenant-less client.

    Raises Forbidden when ctx.tenant_id != credential.tenant_id. Each client also checks that tenant_id in
    every Canonical response equals ctx.tenant_id (ValidationFailed, detail TENANT_MISMATCH)."""

    def reader(self, ctx: RunContext, credential: CanonicalCredential) -> CanonicalSource: ...
    def writer(self, ctx: RunContext, credential: CanonicalCredential) -> CanonicalWriter: ...



@runtime_checkable
class CanonicalSource(Protocol):
    """READ side of the ERP adapter (contracts/openapi/canonical.openapi.yaml).

    Implementations: HttpCanonicalSource (real adapter, BB-06) and FixtureCanonicalSource (in-memory,
    for unit tests). The mock Canonical server (BB-04) serves the same HTTP contract for integration
    tests. Every method validates the response against the canonical JSON Schema before mapping it.

    Raises: NotFound (404), DependencyUnavailable (timeout, connection error, 5xx, 429),
            ValidationFailed (the whole response is malformed; single bad sales rows are skipped instead).
    """

    def get_sales_page(self, ctx: RunContext, *, date_from: date, date_to: date,
                       updated_since: datetime | None, cursor: str | None,
                       limit: int = 200, product_id: UUID | None = None) -> SalesPage: ...

    def get_product(self, ctx: RunContext, product_id: UUID) -> ProductInfo: ...

    def get_inventory(self, ctx: RunContext, product_id: UUID) -> InventorySnapshot:
        """GET /inventory/{product_id} (OrganizationInventory), then the section 7.13 checks against
        get_location_register(). Raises InventoryRejected with the reason when a check fails."""
        ...

    def list_location_inventory(self, ctx: RunContext, product_id: UUID) -> Sequence[LocationInventory]:
        """GET /inventory/{product_id}/locations. Display only."""
        ...

    def get_location_register(self, ctx: RunContext) -> LocationRegister: ...

    def get_supplier(self, ctx: RunContext, supplier_id: UUID) -> SupplierInfo: ...

    def get_open_po_qty(self, ctx: RunContext, product_id: UUID) -> OpenPurchaseOrderQty:
        """Reads ALL pages of GET /purchase-orders?status=open&product_id= live (never cached, D-07)."""
        ...


@runtime_checkable
class CanonicalWriter(Protocol):
    """WRITE side of the ERP adapter. The ONLY business write the Brain may make (D-11, OD-21).

    Uses the proposal tenant's own service credential (N-01; scope canonical:po:create_draft), header
    Idempotency-Key = proposal id.
    Raises: IdempotencyConflict (409 IDEMPOTENCY_CONFLICT), ValidationFailed (4xx),
            OutcomeUncertain (timeout / connection dropped after send), DependencyUnavailable (5xx).
    """

    def create_draft_purchase_order(self, ctx: RunContext, request: DraftPurchaseOrderRequest,
                                    idempotency_key: UUID) -> DraftPurchaseOrderResult: ...


@runtime_checkable
class CachedCanonicalReader(Protocol):
    """Read-through cache over CanonicalSource backed by ingest.canonical_cache.
    Freshness limits come from rule_config platform.*_freshness_seconds. If the live read fails and the
    cached row is older than the limit, raise DependencyUnavailable (callers turn that into a reason code).
    Organization stock is NOT here: it is always read live with CanonicalSource.get_inventory (D-49)."""

    def product(self, ctx: RunContext, product_id: UUID) -> ProductInfo: ...
    def supplier(self, ctx: RunContext, supplier_id: UUID) -> SupplierInfo: ...


@runtime_checkable
class LlmClient(Protocol):
    """Provider-neutral LLM client (OD-18). Optional: the Brain must work with NullLlmClient.
    Never logs or stores prompt/completion text (D-14). Records one audit.llm_usage row per call.
    Raises DependencyUnavailable when offline; callers fall back to templates."""

    def is_available(self, ctx: RunContext) -> bool: ...

    def complete(self, ctx: RunContext, *, purpose: Literal["explanation", "assistant_chat", "agent_reasoning"],
                 prompt_name: str, prompt_version: str, variables: Mapping[str, object],
                 max_tokens: int) -> LlmReply: ...


@dataclass(frozen=True, slots=True)
class LlmReply:
    text: str
    llm_usage_id: UUID
    schema_valid: bool = True


# =====================================================================================================
# 5. Pure engines (no I/O). Parameters come from the ACTIVE rule_config version of their rule_set;
#    the caller loads it and passes the parsed Pydantic params object (contracts_jsonb.py) as `params`.
# =====================================================================================================

# ---- 5.1 Features (Ibrahim) --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DailyObservation:
    """One product-day as the feature builder sees it, already joined with sales_day_coverage.
    status: observed (complete day, row present), zero_filled (complete day, no row = true zero),
            missing (gap day), open (day not closed/reconciled yet), future."""

    product_id: UUID
    business_date: date
    y_units: Decimal | None          # max(net_units, 0) for observed, 0 for zero_filled, else None (D-35)
    status: Literal["observed", "zero_filled", "missing", "open", "future"]
    returns_exceed_sales: bool = False  # net_units < 0 in sales_fact (raw value kept there); handling: N-03


@dataclass(frozen=True, slots=True)
class CalendarFlags:
    calendar_date: date
    is_holiday: bool
    is_ramadan: bool
    is_flu_season: bool


class FeatureBuilder(Protocol):
    """Builds feat.feature_daily rows for FEATURE_SET_VERSION (contracts_jsonb.py). Shared by training and
    inference (MVP §3.6). Uses only observations strictly BEFORE feature_date for inputs (no leakage).
    Returns one FeatureVector-compatible mapping per (product, date) requested."""

    feature_set_version: int

    def build(self, history: Sequence[DailyObservation], calendar: Mapping[date, CalendarFlags],
              product_ids: Sequence[UUID], dates: Sequence[date]) -> Sequence[Mapping[str, object]]: ...


# ---- 5.2 Anomaly (Fatma) -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnomalyInput:
    product_id: UUID
    observation_date: date
    observed_units: Decimal                       # today's running total (intraday) or the closed total
    history: Sequence[DailyObservation]           # trailing window, completed days only
    expected_units: Decimal | None                # forecast point for observation_date, if any
    forecast_id: UUID | None


@dataclass(frozen=True, slots=True)
class AnomalyFinding:
    """Maps 1:1 to intel.anomaly_event (natural key product, date, type, method)."""

    product_id: UUID
    observation_date: date
    anomaly_type: Literal["demand_spike", "demand_drop", "pattern_outlier"]
    detection_method: Literal["rule", "zscore", "isolation_forest", "combined"]
    expected_value: Decimal | None
    observed_value: Decimal
    zscore: Decimal | None
    score: Decimal                                # 0..1
    severity: Severity
    reasons: Sequence[Mapping[str, object]]       # contracts_jsonb.AnomalyReason shape


class AnomalyDetector(Protocol):
    """mode='intraday': the day is still open (day_status='open'), so ONLY spikes are checked; a partial
    day always looks like a drop (D-40). mode='closed_day': spikes and drops, only for days whose coverage
    is 'complete'. Missing, gap or open days in `history` are never treated as zero.
    Returns [] when history < params.min_history_days."""

    def detect(self, item: AnomalyInput, params: object,
               mode: Literal["intraday", "closed_day"]) -> Sequence[AnomalyFinding]: ...


# ---- 5.3 Risk (Fatma) --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskInputs:
    product_id: UUID
    supplier_id: UUID | None
    inventory: InventorySnapshot | None           # None -> INVENTORY_UNAVAILABLE
    lead_time_days: int | None                    # None -> LEAD_TIME_UNKNOWN
    forecast_id: UUID | None                      # None -> FORECAST_MISSING
    forecast_confidence: Severity | None
    demand_per_day: Decimal | None                # mean of forecast points over the lead time
    demand_over_lead_time: Decimal | None
    demand_over_lead_time_upper: Decimal | None
    worst_open_anomaly: AnomalyFinding | None     # highest-severity anomaly for the product, if any
    anomaly_event_id: UUID | None
    data_stale: bool                              # sales poll stale beyond threshold (section 7)


@dataclass(frozen=True, slots=True)
class RiskResult:
    """Maps to intel.risk_assessment. Returned only when the inputs the DB requires are present
    (pending N-07, see RiskEngine). unavailable_reasons then carries recommendation-side reasons only."""

    product_id: UUID
    risk_type: Literal["stockout_risk", "unusual_demand"]
    severity: Severity
    confidence: Decimal
    days_of_cover: Decimal | None
    unavailable_reasons: Sequence[str]            # subset of insight.schema.json unavailable_reasons
    factors: Sequence[Mapping[str, str]]          # [{code, text}] for the insight
    calculation: Mapping[str, object]             # contracts_jsonb.RiskCalculation shape


class RiskEngine(Protocol):
    """D-22: high if days_of_cover < lead_time; medium if < lead_time + params.margin_days; else low.
    A high anomaly raises one level when params.upgrade_on_high_anomaly. Deterministic.
    PENDING N-07: brain_db only accepts a stockout_risk row when days_of_cover, lead_time_days and
    inventory are present (ck_risk_assessment__stockout_inputs). Until N-07 is answered, return NO
    stockout_risk result when inventory, lead time or forecast is missing; the job counts the product
    as `products_not_assessable` with its reason codes."""

    def assess(self, inputs: RiskInputs, params: object) -> Sequence[RiskResult]: ...


# ---- 5.4 Recommendation (Ibrahim) --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecommendationInputs:
    risk: RiskResult
    risk_assessment_id: UUID
    product: ProductInfo | None
    supplier: SupplierInfo | None                 # preferred supplier only (D-07)
    inventory: InventorySnapshot | None
    open_po: OpenPurchaseOrderQty | None          # None = live read failed -> OPEN_PO_UNAVAILABLE
    forecast_demand_over_horizon: Decimal | None  # sum of points over lead_time + review_period
    sigma_daily: Decimal | None                   # std of daily demand; None -> 1 day of mean demand


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Either an order (quantity > 0 with full calculation) or no order with reason codes. Never both.
    calculation matches the `calculation` object of contracts/schemas/brain/recommendation.schema.json."""

    product_id: UUID
    recommendation_type: Literal["create_purchase_order", "review_anomaly"] | None
    supplier_id: UUID | None
    suggested_quantity: Decimal | None
    calculation: Mapping[str, object] | None
    unavailable_reasons: Sequence[str]


class RecommendationEngine(Protocol):
    """D-21 formula, rule set rec-rules-v1. Returns recommendation_type=None when no order is needed
    (raw <= 0, reason COVERED_BY_OPEN_PO if open POs cover it) or inputs are missing."""

    def recommend(self, inputs: RecommendationInputs, params: object) -> RecommendationResult: ...


# ---- 5.5 Proposal building and hashing (Ahmed Emad) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProposalDraft:
    tool_name: Literal["create_purchase_order"]
    tool_version: Literal["1.0"]
    arguments: Mapping[str, object]               # create_purchase_order_args.schema.json, exact
    arguments_sha256: str                         # sha256(RFC 8785 JCS(arguments)), lowercase hex (D-13)
    reason: str                                   # templated, <= 500 chars, never from the LLM
    recommendation_id: UUID
    risk_assessment_id: UUID


class ArgumentsHasher(Protocol):
    """MUST reproduce contracts/fixtures/hash/golden_vectors.json byte for byte (RFC 8785)."""

    def canonical_json(self, arguments: Mapping[str, object]) -> str: ...
    def sha256(self, arguments: Mapping[str, object]) -> str: ...


class ProposalBuilder(Protocol):
    """Deterministic, no LLM (D-18). Copies supplier_id and quantity from the recommendation unchanged."""

    def build(self, recommendation_id: UUID, recommendation: RecommendationResult,
              risk_assessment_id: UUID, risk: RiskResult) -> ProposalDraft: ...


# ---- 5.6 Explanation (Ahmed Emad) --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    source: Literal["template", "llm"]


class Explainer(Protocol):
    """Turns numbers that code already computed into text. The template path is pure and always works.
    The LLM path may only rephrase the facts it is given; numbers in its text must equal the inputs
    (checked by test). On any LLM failure, return the template text with source='template'."""

    def explain(self, ctx: RunContext, risk: RiskResult,
                recommendation: RecommendationResult | None) -> Explanation: ...


# =====================================================================================================
# 6. Learning workloads (Mostafa). Training and inference are separate entry points and never run
#    inside an API request (BLUEPRINT §2).
# =====================================================================================================


@dataclass(frozen=True, slots=True)
class TrainingRequest:
    cutoff_date: date                             # last CLOSED + complete business date included
    product_ids: Sequence[UUID] | None            # None = all products with history
    trigger: Literal["nightly", "on_demand", "manual"]


@dataclass(frozen=True, slots=True)
class TrainingResult:
    training_run_id: UUID                         # intel.training_run.id
    status: Literal["succeeded", "partial", "failed"]
    products_requested: int
    products_trained: int
    products_skipped: int
    products_failed: int
    validated_model_ids: Sequence[UUID]


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    target_date: date
    predicted_demand: Decimal
    confidence_low: Decimal
    confidence_high: Decimal


@dataclass(frozen=True, slots=True)
class ForecastOutput:
    """Maps to intel.forecast + forecast_point and to contracts/schemas/brain/forecast.schema.json."""

    product_id: UUID
    model_id: UUID
    model_version: str
    feature_set_version: int
    origin_date: date
    horizon_days: int
    forecast_confidence: Severity
    cold_start: bool
    quality_flags: Sequence[str]
    points: Sequence[ForecastPoint]


ModelScope = Literal["shared", "product"]
"""intel.model_registry.scope (D-31). shared: ONE artifact fitted across many products of ONE tenant
(product_id NULL). product: the model a product is served by. A product row either references a shared
row (shared_model_id, no artifact of its own: NOT a separately trained model), or has its own artifact
(a product-specific model kept only if it beats the shared one on the same backtest), or is artifact-less
(seasonal_naive). Artifacts never cross tenants."""


class ForecastModel(Protocol):
    """One model family (seasonal_naive, lightgbm). Global LightGBM is fitted once over all products (D-20).
    Artifacts: LightGBM native text only, never pickle (OD-13)."""

    family: Literal["seasonal_naive", "lightgbm"]

    def fit(self, training_rows: Sequence[Mapping[str, object]]) -> None: ...
    def predict(self, feature_rows: Sequence[Mapping[str, object]]) -> Sequence[ForecastPoint]: ...
    def save(self, path: str) -> str: ...         # returns sha256 of the written artifact
    @classmethod
    def load(cls, path: str, expected_sha256: str) -> ForecastModel: ...


class Trainer(Protocol):
    """Per tenant. Fits seasonal_naive and ONE shared LightGBM over the tenant's products (product-specific
    LightGBM is optional, D-31), backtests every candidate on the same rolling-origin folds
    (params.backtest_weeks) with WAPE, writes training_run, model_registry (scope shared/product) and
    model_evaluation rows, and marks each product's winner `validated` (BRAIN_CONTRACTS.md section 8)."""

    def train(self, ctx: RunContext, request: TrainingRequest) -> TrainingResult: ...


class Forecaster(Protocol):
    """Loads the latest validated model per product; refuses feature_set_version mismatch
    (FeatureSetMismatch); falls back to seasonal_naive (quality flag fallback_model / cold_start)."""

    def forecast(self, ctx: RunContext, origin_date: date,
                 product_ids: Sequence[UUID] | None) -> Sequence[ForecastOutput]: ...


# =====================================================================================================
# 7. Jobs (Ibrahim owns the runner; each step owner owns its job body)
# =====================================================================================================


@dataclass(frozen=True, slots=True)
class JobRequest:
    """contracts/schemas/brain/job_run_request.schema.json"""

    job: JobName
    trigger: JobTrigger
    business_date: date | None = None             # END_OF_DAY / TRAINING: the day being closed
    product_ids: Sequence[UUID] | None = None     # restrict to these products (tests, demo)


@dataclass(frozen=True, slots=True)
class JobResult:
    """contracts/schemas/brain/job_run.schema.json"""

    run_id: UUID
    job: JobName
    trigger: JobTrigger
    status: JobStatus
    started_at: datetime
    finished_at: datetime
    counts: Mapping[str, int] = field(default_factory=dict)
    error_code: str | None = None
    steps: Sequence[JobResult] = ()


class Job(Protocol):
    """A unit of scheduled work. The runner (BB-16) wraps run() with: advisory lock
    pg_try_advisory_lock(hashtext(tenant_id || job)) -> JobStatus 'skipped_locked' if taken;
    sync_checkpoint last_status/started/finished/consecutive_failures bookkeeping; structured logs;
    a fresh RunContext. A job body must be safe to re-run at any time (section 6.3)."""

    name: JobName

    def run(self, ctx: RunContext, request: JobRequest) -> JobResult: ...


# =====================================================================================================
# 8. Repositories (I/O against brain_db). Only the method names other modules depend on are listed;
#    owners may add more. Every method filters by ctx.tenant_id. Writes happen in the caller's
#    transaction (unit of work), never commit on their own.
# =====================================================================================================


class SalesRepository(Protocol):
    def upsert_sales_rows(self, ctx: RunContext, rows: Sequence[DailySalesRow],
                          source_mode: Literal["poll", "reconcile", "backfill"]) -> int:
        """BLUEPRINT §4.3 upsert; returns rows actually changed (older rows are ignored)."""
        ...

    def dirty_products_since(self, ctx: RunContext, since: datetime | None) -> Sequence[UUID]: ...

    def history(self, ctx: RunContext, product_ids: Sequence[UUID], start: date,
                end: date) -> Sequence[DailyObservation]: ...


class CheckpointRepository(Protocol):
    def get_watermark(self, ctx: RunContext, job: JobName) -> datetime | None: ...
    def set_watermark(self, ctx: RunContext, job: JobName, value: datetime) -> None: ...
    def mark_started(self, ctx: RunContext, job: JobName) -> None: ...
    def mark_finished(self, ctx: RunContext, job: JobName, status: JobStatus,
                      error_code: str | None) -> None: ...


class FailureRepository(Protocol):
    def record(self, ctx: RunContext, *, resource: str, failure_kind: str, error_code: str,
               message: str, excerpt: Mapping[str, object] | None) -> None:
        """One open row per (tenant, resource, error_code); repeats bump attempts (BLUEPRINT §4.5)."""
        ...

    def resolve_open(self, ctx: RunContext, *, resource: str, resolution: str) -> int: ...


class RuleConfigRepository(Protocol):
    def active(self, ctx: RunContext, rule_set: str) -> tuple[UUID, str, object]:
        """Returns (rule_config.id, version_label, parsed params). Raises ConfigInvalid."""
        ...
