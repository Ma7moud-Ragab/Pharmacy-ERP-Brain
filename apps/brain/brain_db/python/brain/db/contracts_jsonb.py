"""Pydantic contracts for every JSONB column, the canonical hash function and the typed feature vector.

These models are the *validation boundary* for flexible payloads stored in brain_db. The database only
enforces `jsonb_typeof` (object/array) and size caps; shape and value rules live here. All models forbid
unknown keys so a typo can never silently become stored data.

Author note: written for Pydantic v2; not executed in the authoring environment (no Pydantic installed).
Run `pytest tests/contracts` before relying on it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Protocol, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    # protected_namespaces=(): fields such as model_version / model_family are deliberate (source naming)
    model_config = ConfigDict(extra="forbid", frozen=False, protected_namespaces=())


# --------------------------------------------------------------------------------------
# 1. Canonical hashing (arguments_sha256, payload_sha256, prompt_sha256)
# --------------------------------------------------------------------------------------
def _norm(obj: Any) -> Any:
    """Normalise numbers to canonical decimal strings so 100, 100.0 and Decimal('100.00') hash identically."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, Decimal)):
        d = Decimal(str(obj)).normalize()
        return format(d, "f")
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _norm(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_norm(v) for v in obj]
    raise TypeError(f"unsupported type for canonical JSON: {type(obj)!r}")


def canonical_json(obj: Any) -> str:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj: Any) -> str:
    """64 lowercase hex chars; matches the CHECK '^[0-9a-f]{64}$' on every *_sha256 column."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# 2. Feature contract (feat.feature_daily) - the stable typed vector behind FeatureStore.get_features
# --------------------------------------------------------------------------------------
FEATURE_SET_VERSION = 1

# Ordered model inputs. Order is part of the contract: models are trained and served with this exact order.
MODEL_INPUT_COLUMNS: tuple = (
    "lag_1", "lag_7", "lag_14", "lag_28",
    "roll_mean_7", "roll_mean_14", "roll_mean_28", "roll_std_7", "roll_std_28",
    "n_obs_7", "n_obs_28", "history_days",
    "dow", "month", "day_of_month", "week_of_year",
    "is_holiday", "is_ramadan", "is_flu_season", "is_promotion",
)
# Label side: derived from the same-day observation. NEVER a model input (leakage).
LABEL_COLUMNS: tuple = ("y_units", "y_status", "is_outlier")


class FeatureVector(_Strict):
    tenant_id: UUID
    product_id: UUID
    feature_date: date
    feature_set_version: int
    # inputs
    lag_1: Optional[float] = None
    lag_7: Optional[float] = None
    lag_14: Optional[float] = None
    lag_28: Optional[float] = None
    roll_mean_7: Optional[float] = None
    roll_mean_14: Optional[float] = None
    roll_mean_28: Optional[float] = None
    roll_std_7: Optional[float] = None
    roll_std_28: Optional[float] = None
    n_obs_7: int = Field(ge=0, le=7)
    n_obs_28: int = Field(ge=0, le=28)
    history_days: int = Field(ge=0)
    dow: int = Field(ge=0, le=6)
    month: int = Field(ge=1, le=12)
    day_of_month: int = Field(ge=1, le=31)
    week_of_year: int = Field(ge=1, le=53)
    is_holiday: bool = False
    is_ramadan: bool = False
    is_flu_season: bool = False
    is_promotion: Optional[bool] = None  # None = unknown (no promotion data in the MVP contract)
    # label side
    y_units: Optional[float] = None
    y_status: Literal["observed", "zero_filled", "missing", "open", "future"]
    is_outlier: bool = False

    def model_inputs(self) -> List[Optional[float]]:
        """Inputs in MODEL_INPUT_COLUMNS order; booleans become 0/1, unknowns stay None (LightGBM handles NaN)."""
        out: List[Optional[float]] = []
        for name in MODEL_INPUT_COLUMNS:
            v = getattr(self, name)
            out.append(None if v is None else float(v))
        return out


class FeatureNotAvailable(Exception):
    """No feature row, or the row is stale/at a different feature_set_version."""


class FeatureStore(Protocol):
    """Documented interface: FeatureStore.get_features(product_id, date). tenant comes from the request context."""

    def get_features(self, product_id: UUID, feature_date: date) -> FeatureVector: ...
    def get_features_batch(self, product_ids: Sequence[UUID], feature_date: date) -> List[FeatureVector]: ...
    def get_training_frame(self, product_id: UUID, start: date, end: date) -> List[FeatureVector]:
        """Rows with y_status in (observed, zero_filled) only; trailing-window features; no row at or after the training cutoff."""
        ...


def _assert_contract() -> None:
    fields = set(FeatureVector.model_fields)
    assert set(MODEL_INPUT_COLUMNS) <= fields, "unknown input column"
    assert set(LABEL_COLUMNS) <= fields, "unknown label column"
    assert set(MODEL_INPUT_COLUMNS).isdisjoint(LABEL_COLUMNS), "label leaked into model inputs"


_assert_contract()


# --------------------------------------------------------------------------------------
# 3. Ingestion
# --------------------------------------------------------------------------------------
class PayloadExcerpt(_Strict):
    """ingest.ingest_failure.payload_excerpt - allow-listed keys of a failed Canonical poll/read; no customer fields."""
    schema_name: Optional[str] = Field(default=None, max_length=100)    # e.g. canonical.SalesPage
    version: Optional[str] = Field(default=None, max_length=20)
    http_status: Optional[int] = Field(default=None, ge=100, le=599)
    product_ids: Optional[List[UUID]] = Field(default=None, max_length=50)
    business_dates: Optional[List[date]] = Field(default=None, max_length=50)


# --------------------------------------------------------------------------------------
# 4. Models, forecasts, anomalies, risk, recommendations
# --------------------------------------------------------------------------------------
class TrainingConfigSnapshot(_Strict):
    candidates: List[str]
    backtest_weeks: int = Field(ge=1)
    min_history_weeks_per_sku: int = Field(ge=1)
    must_beat_baseline_margin: float = Field(ge=0)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ModelMetrics(_Strict):
    """intel.model_registry.metrics (decision metrics wape/baseline_wape are real columns)."""
    mape: Optional[float] = None
    smape: Optional[float] = None
    mae: Optional[float] = None
    bias: Optional[float] = None
    n_folds: int = Field(ge=0)
    backtest_weeks: int = Field(ge=0)
    n_obs: int = Field(ge=0)


class EvaluationDetails(_Strict):
    per_fold: List[Dict[str, float]] = Field(default_factory=list)
    confusion: Optional[Dict[str, int]] = None


class ForecastFactor(_Strict):
    """intel.forecast.factors[] - produced by code from features, never by the LLM."""
    code: str = Field(max_length=60)          # e.g. mean7_vs_mean28, holiday_effect
    value: Optional[float] = None
    direction: Optional[Literal["up", "down", "neutral"]] = None
    text_key: Optional[str] = Field(default=None, max_length=100)  # i18n key rendered by the frontend/template


class AnomalyReason(_Strict):
    """intel.anomaly_event.reasons[]"""
    code: str = Field(max_length=60)          # zscore_gt_4 | isolation_forest_outlier | ...
    value: Optional[float] = None
    threshold: Optional[float] = None


class RuleTrace(_Strict):
    rule: str = Field(max_length=60)
    matched: bool
    inputs: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[str] = None


class RiskCalculation(_Strict):
    """intel.risk_assessment.calculation"""
    rules: List[RuleTrace] = Field(default_factory=list)
    anomaly_event_ids: List[UUID] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list, max_length=20)


class RecommendationCalculation(_Strict):
    """intel.recommendation.calculation (formula inputs and constraints checked)"""
    formula: str = "demand_over_lead + safety_stock - available"
    demand_over_lead: Optional[float] = None
    safety_stock: Optional[float] = None
    available: Optional[float] = None
    order_qty: Optional[float] = None
    bound_used: Literal["median", "upper"] = "median"
    open_po_check: Literal["passed", "blocked", "skipped_no_capability"] = "skipped_no_capability"


class PurchaseOrderLine(_Strict):
    product_id: UUID
    quantity: Decimal = Field(gt=0, le=1_000_000)


class PurchaseOrderArguments(_Strict):
    """Identical to the `create_purchase_order` tool input_schema; used for ActionProposal.arguments."""
    supplier_id: UUID
    lines: List[PurchaseOrderLine] = Field(min_length=1, max_length=50)


class PurchaseOrderRecommendationPayload(PurchaseOrderArguments):
    """Recommendation.payload for type create_purchase_order: copied unchanged into the proposal arguments."""


class ReviewAnomalyPayload(_Strict):
    anomaly_event_id: UUID
    suggestion_key: str = Field(max_length=100)  # e.g. review_invoice


class BriefingContent(_Strict):
    high_risk_count: int = Field(ge=0)
    pending_proposals: int = Field(ge=0)
    top_risks: List[UUID] = Field(default_factory=list, max_length=10)  # risk_assessment ids
    summary_key: Optional[str] = None


# --------------------------------------------------------------------------------------
# 5. Agent / audit
# --------------------------------------------------------------------------------------
class SessionState(_Strict):
    """agent.agent_session.state (<= 16 KB by CHECK). No PII, no raw ERP rows."""
    focus_product_ids: List[UUID] = Field(default_factory=list, max_length=10)
    last_intent: Optional[str] = Field(default=None, max_length=60)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolResultSummary(_Strict):
    """agent_action.result_summary / agent_message.structured: compact facts only."""
    ids: Dict[str, str] = Field(default_factory=dict)
    counts: Dict[str, int] = Field(default_factory=dict)
    note: Optional[str] = Field(default=None, max_length=200)


class ActionResult(_Strict):
    """agent.action_execution.result (ai-output contract ActionResult)."""
    status: Literal["success", "failed"]
    reason: Optional[str] = Field(default=None, max_length=500)
    external_ref_type: Optional[Literal["purchase_order"]] = None
    external_ref_id: Optional[str] = Field(default=None, max_length=100)
    po_status: Optional[str] = Field(default=None, max_length=40)


class AuditDetails(_Strict):
    """audit.audit_log.details - allow-list. Add a key here (code review) before anyone can store it."""
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    model_version: Optional[str] = None
    rule_version: Optional[str] = None
    reason_code: Optional[str] = None
    error_code: Optional[str] = None
    result_status: Optional[str] = None
    attempt_no: Optional[int] = None
    external_ref_type: Optional[str] = None
    external_ref_id: Optional[str] = None
    http_status: Optional[int] = None
    duration_ms: Optional[int] = None


# --------------------------------------------------------------------------------------
# 6. intel.rule_config.params, one model per rule_set
# --------------------------------------------------------------------------------------
class PlatformParams(_Strict):
    business_timezone: str = "Africa/Cairo"          # OD-03
    inventory_freshness_seconds: int = Field(default=900, ge=0)
    supplier_freshness_seconds: int = Field(default=86400, ge=0)
    product_freshness_seconds: int = Field(default=86400, ge=0)
    reconcile_lookback_days: int = Field(default=7, ge=1, le=60)
    feature_overlap_minutes: int = Field(default=5, ge=0)
    sales_poll_interval_seconds: int = Field(default=300, ge=30, le=3600)   # D-24
    poll_overlap_seconds: int = Field(default=120, ge=0)                     # D-05
    poll_history_start_date: date = date(2024, 1, 1)                         # first poll / checkpoint reset
    intel_window_minutes: int = Field(default=60, ge=5)                      # D-19
    end_of_day_run_local_time: str = Field(default="02:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")  # D-26, tenant timezone
    # D-49 (N-09): where the Brain gets organization stock. "none" = Option D: no inventory-dependent recommendation
    # (create_purchase_order) is generated. "organization_inventory" only after the ERP owners confirm the Canonical
    # OrganizationInventory guarantees for this tenant. Absent from the seed on purpose, so every tenant starts on "none".
    inventory_source: Literal["none", "organization_inventory"] = "none"


class AnomalyRuleParams(_Strict):
    zscore_threshold: float = Field(default=4, gt=0)
    severity_high_score: float = Field(default=0.9, ge=0, le=1)
    severity_medium_score: float = Field(default=0.7, ge=0, le=1)
    min_history_days: int = Field(default=28, ge=1)
    isolation_forest_enabled: bool = False


class RiskRuleParams(_Strict):
    margin_days: float = Field(default=2, ge=0)
    bound_policy: Literal["median", "upper"] = "median"
    upgrade_on_high_anomaly: bool = True
    confidence_by_forecast: Dict[Literal["low", "medium", "high"], float] = {"low": 0.4, "medium": 0.7, "high": 0.9}


class RecommendationRuleParams(_Strict):
    safety_stock_days: float = Field(default=1, ge=0)
    recommendation_ttl_hours: int = Field(default=24, ge=1)
    quantity_rounding: Literal["ceil", "round"] = "ceil"
    suppress_if_open_po: bool = False                 # needs a Canonical PO read capability (OD-05)


class ForecastRuleParams(_Strict):
    min_history_weeks_per_sku: int = Field(default=8, ge=1)
    backtest_weeks: int = Field(default=4, ge=1)
    candidates: List[str] = ["seasonal_naive", "lightgbm"]  # D-20, D-32: no holt_winters
    must_beat_baseline_margin: float = Field(default=0.05, ge=0)
    interval_method: Literal["quantile", "backtest_residual", "none"] = "quantile"
    interval_coverage: float = Field(default=0.8, gt=0, lt=1)
    max_gap_days_ffill: int = Field(default=3, ge=0)
    horizon_days: int = Field(default=14, ge=1, le=90)
    degradation_wape_factor: float = Field(default=1.5, gt=1)


RULE_SET_MODELS = {
    "platform": PlatformParams,
    "anomaly": AnomalyRuleParams,
    "risk": RiskRuleParams,
    "recommendation": RecommendationRuleParams,
    "forecast": ForecastRuleParams,
}
