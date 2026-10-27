# ERP Brain MVP — Final Decisions and Contracts

**Status:** MVP engineering baseline, 17 October 2026  

> **Update 21 Oct 2026:** Redis Streams, the ERP outbox event path and the `processed_event` ledger are **out of the MVP** (D-23 in `docs/BLUEPRINT_FINAL.md`). The Brain polls `GET /canonical/sales` daily totals on a short interval instead (D-24, D-25). The Events row in §1, OD-01, OD-19, §3.3 and the Redis part of §4 are superseded, and are kept below for history only.

> **Update 21 Oct 2026 (evening):** **OD-23 is amended by D-34** (`docs/decisions/DECISIONS_2026-10-21_ERD.md`): the `tenant_id` column default is removed now, not later; multi-tenancy is a core requirement and the tenant comes only from the verified token. OD-13 is tightened by D-33 (artifact formats `lightgbm_txt`/`json` only).

> **Update 21 Oct 2026 (night):** **OD-20 is amended by D-48** (grain = organization and product; the Brain never sums branch stock). Tenants come from `ingest.tenant_registry` with per-tenant Canonical credentials (D-46), and PostgreSQL RLS is added on every tenant table (D-47, migration 0007).

**Applies to:** `ERP-Brain-Architecture-Blueprint.md` and the four-part `brain_db` design  
**Contract source of truth at implementation:** versioned OpenAPI and JSON Schema files in `/contracts`; this document records the agreed v1 behavior and must be kept aligned with those files.

## 1. MVP architecture decisions

| Area | Final MVP decision |
|---|---|
| Deployables | One .NET modular-monolith ERP and one Python/FastAPI Brain, with separate `erp_db` and `brain_db`; no direct Brain access to `erp_db`. |
| Integration | The .NET in-process adapter is the sole bridge to ERP business data and implements the same canonical HTTP contract expected of future adapters. |
| Data ownership | ERP owns business facts. Brain stores normalized inputs, derived features and intelligence, model metadata, agent state, and audit records. |
| Tenant scope | One seeded tenant in MVP. Carry and explicitly set `tenant_id` on all Brain records and requests. Do not expose tenant creation or claim isolation between independently administered tenants yet. |
| Database | PostgreSQL 16; no extensions in the default migration chain. `pgvector` and RAG are out of scope. |
| Events | **[Superseded 21 Oct by D-23/D-24: polling, no events]** ERP transactional outbox publishes to Redis Streams. Brain persists event effects and its dedupe record in one transaction, then acknowledges the stream entry. Canonical reads/backfill repair gaps. |
| Sales grain | One row per tenant, product, and business date; one demo store. Location-level sales are deferred. |
| Business date | `Africa/Cairo` for the seeded tenant. ERP calculates and sends `business_date`; instants remain UTC. The Brain rejects an event whose date is inconsistent with its configured tenant timezone. |
| Forecasting | Deterministic baseline plus one classical model path; train and infer from the same versioned feature contract. Per-product model selection and history-bearing forecasts. No feature platform. |
| LLM | Hosted provider behind a provider-neutral client. Invoke only for explanation/assistant requests after deterministic or classical processing; never send raw business tables or PII. Provider/model are configuration and are recorded with usage. |
| Agent writes | Only `create_purchase_order` is an agent write tool. Every write requires an authenticated human approval bound to the immutable proposal hash; execution uses the same idempotency key and canonical adapter. No direct database or inventory-update tool. |
| Deployment | Docker Compose on one host for the MVP; HTTPS at the edge, secrets from environment/secret storage, backups and restore check for `brain_db` and model artifacts. |
| Out of scope | Multi-tenant administration, external ERP connector, RAG, vector database, dynamic approval scoring, multi-agent execution, inventory mutation by the Agent, anomaly-review workflow, and location-grain forecasting. |

## 2. Closed database and integration decision register

These decisions close OD-01 through OD-24 in `04_migration_backlog_decisions_handoff.md` for MVP implementation. They do not claim that an external ERP capability exists until the adapter and its contract tests implement it.

| ID | Final MVP decision |
|---|---|
| OD-01 | **[Superseded 21 Oct by D-23]** `SaleCreated.event_id` is a UUID. Event payload includes `sale_id`, non-empty `lines[]` with `product_id` UUID and positive quantity, `business_date`, UTC `occurred_at`, and optional price/currency fields. |
| OD-02 | `product_id` UUID is the canonical cross-service identifier. SKU is a display/business attribute, never a key. |
| OD-03 | Business dates use the tenant's IANA timezone, seeded as `Africa/Cairo`; ERP is authoritative for `business_date`, and UTC timestamps are retained for ordering/audit. |
| OD-04 | Canonical `Product` includes nullable `preferred_supplier_id`. If absent, no purchase-order recommendation or proposal is produced for that product. |
| OD-05 | MVP adapter supports a read of open purchase orders by status and product, sufficient to include already ordered quantity in replenishment checks. Until that capability is live, recommendation output must say `skipped_no_capability`; it must not silently assume there are no open orders. |
| OD-06 | `insight_id` is the UUID of the immutable `risk_assessment` version that caused the proposal. Frontend/API projection IDs use that same UUID. |
| OD-07 | PostgreSQL 16; no extension, including `pgvector`, in MVP migrations. |
| OD-08 | Sale `unit_price`, `total_amount`, and `currency_code` are optional and nullable. Demand features use units, not revenue; currency is required only when an amount is supplied. |
| OD-09 | Returns, voids, and edits are represented as canonical corrections and reconciled by absolute `get_sales` totals for closed days. No negative event increment is applied. If the ERP cannot provide corrected totals, affected dates are marked incomplete and excluded from training. |
| OD-10 | MVP does not estimate lost demand during stockouts. Forecast output carries a quality/limitation flag when available stock history indicates censoring; the limitation is visible to users. |
| OD-11 | Proposal approval window is 24 hours; session expires after 4 hours idle; message content is retained for 30 days. Expired proposals cannot execute; audit records remain. |
| OD-12 | No audit-log deletion in MVP. Keep audit rows for the life of the MVP dataset; set an explicit retention policy before production use or legal deployment. |
| OD-13 | Store LightGBM models in native text format where supported; any other format must be a non-executable format or explicitly trusted artifact. Every artifact has SHA-256, tenant/product/model-version path, and write access limited to the Brain training process. Do not load pickle artifacts. |
| OD-14 | Calendar features are generated from a pinned holiday-calendar dependency plus versioned, curated Ramadan and flu-season dates. Persist the resolved dates and source/version in `calendar_day`; changes trigger recomputation. |
| OD-15 | No anomaly acknowledge/dismiss/confirm workflow in MVP. Anomaly records are informational and append/versioned by detection; do not expose review actions. |
| OD-16 | Seed rule values from the documented guide defaults; persist a versioned `rule_config` before processing data. Changes create a new config version and are auditable; no hidden constants for business thresholds. |
| OD-17 | JWT `sub` is a string actor ID; `tenant_id` is a UUID; `scopes` is an array of strings. Approval requires `agent:approve`; service-to-service calls use a distinct service identity/scope. |
| OD-18 | Hosted LLM provider is chosen through deployment configuration and hidden behind `llm/client.py`; no embedding model in MVP. Persist provider, model, token counts, latency, and cost estimate, never prompt/completion text. |
| OD-19 | **[Superseded 21 Oct by D-23]** Redis group is `brain-ingest`; retain stream entries for at least 7 days; after 5 failed deliveries, persist an `ingest_failure`, alert, and acknowledge/quarantine the poison event. Dedupe ledger retention exceeds stream retention. |
| OD-20 | Sales and features are per product per business day for the single demo store. `location_id` may be retained in canonical payloads but is not part of MVP fact keys or model inputs. |
| OD-21 | `update_inventory` is not an agent tool. Human ERP workflows own inventory edits. Agent writes create draft purchase orders only. |
| OD-22 | `created_by`/`updated_by` exist only where a human or service actor is meaningful; immutable/system-generated rows do not receive synthetic actor values. Creation/update timestamps and provenance remain as specified per table. |
| OD-23 | Use the seeded tenant UUID already present in the DDL; every application write passes it explicitly. Remove the database default before enabling a second tenant. |
| OD-24 | Keep `tools/schema_gen` as the schema-definition source for generated DDL, models, and table documentation. Changes go into the definition and regenerate artifacts; do not hand-edit generated copies. CI checks generated diffs and `alembic check`. |

## 3. Wire contracts

### 3.1 Shared rules

- All APIs use `/api/v1/`, UTF-8 JSON, UUID identifiers, ISO-8601 UTC instants, and JSON Schema/OpenAPI validation.
- Every cross-service request carries `Authorization: Bearer <JWT>`, `traceparent`, and the explicit `tenant_id` claim. The service derives the tenant from the verified token; a body/query tenant mismatch is rejected.
- Breaking changes require a new schema/API major version. Additive optional fields are backward-compatible. Unknown fields are rejected on Brain-owned structured outputs and tolerated only where a canonical schema explicitly permits extensions.
- Errors use `{ "error": { "code": "...", "message": "...", "details": [], "trace_id": "..." } }`. Stable codes include `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `UNAUTHORIZED`, `FORBIDDEN`, `DEPENDENCY_UNAVAILABLE`, and `IDEMPOTENCY_CONFLICT`.
- Retry reads with bounded exponential backoff. Retry writes only with the original `Idempotency-Key`; the adapter returns the original status/body for a repeated key and rejects reuse with a different request hash.

### 3.2 Canonical API owned by the ERP adapter

Required MVP operations:

| Operation | Contract |
|---|---|
| `GET /api/v1/canonical/products/{product_id}` | Canonical product including UUID, SKU, name, active flag, unit, and nullable preferred supplier UUID. |
| `GET /api/v1/canonical/inventory/{product_id}` | On-hand, reserved, available quantities, unit, location, reorder point, and `updated_at`. |
| `GET /api/v1/canonical/suppliers/{supplier_id}` | Supplier identity, active status, and nullable lead time in days. |
| `GET /api/v1/canonical/sales?from=&to=&updated_since=&cursor=` | Stable cursor pagination; date bounds are business dates, `updated_since` is an exclusive UTC watermark, and edits/voids advance `updated_at`. Response includes canonical totals per product/business date and coverage metadata. |
| `GET /api/v1/canonical/purchase-orders?status=open&product_id=` | Open/draft quantities by product and supplier, with cursor pagination. |
| `POST /api/v1/canonical/purchase-orders` | Creates a **draft** PO only. Requires `Idempotency-Key`, supplier, non-empty positive-quantity lines, approved actor/session metadata, and returns the same PO on retry. |

Canonical records include `schema` (for example `canonical.Product`), `version` (`1.0`), and `tenant_id`. Quantities use the product's canonical unit. The adapter owns validation and mapping between ERP entities and these records.

### 3.3 ERP outbox event envelope and `SaleCreated` (post-MVP; superseded for the MVP by D-23)

```json
{
  "event_id": "8f2b3c10-0000-4000-8000-000000000001",
  "event_type": "SaleCreated",
  "version": "1.0",
  "occurred_at": "2026-10-17T10:16:32Z",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "source": "erp-backend",
  "payload": {
    "sale_id": "8f2b3c10-0000-4000-8000-000000000002",
    "business_date": "2026-10-17",
    "lines": [
      { "product_id": "b3f1c2a0-4e51-4a2e-9d3e-000000000001", "quantity": 2, "unit_price": 45.5, "currency_code": "EGP" }
    ],
    "total_amount": 91.0,
    "currency_code": "EGP"
  }
}
```

The outbox row is committed with the ERP sale. Event IDs are globally unique UUIDs. Consumers may receive duplicates or out-of-order events. Brain commits `processed_event` and all event effects atomically, then acknowledges Redis. For a late event on a closed business date, Brain reconciles that date from canonical sales instead of incrementing its aggregate. Event payloads are not retained after processing except for bounded diagnostic metadata with sensitive fields removed.

### 3.4 Brain read/output contracts

- `GET /api/v1/brain/insights?entity_type=product&entity_id={uuid}` returns a list of typed, versioned insight projections from risk/recommendation records. Each includes stable `id` (= risk assessment UUID), severity, confidence in `[0,1]`, generated timestamp, freshness, explanation/factors, and source model/rule versions.
- `GET /api/v1/brain/forecasts/{product_id}` returns forecast generation ID, model/feature-set versions, horizon, generated time, quality flags, and daily points (`target_date`, demand estimate, lower/upper interval). Forecast generations are immutable.
- Missing or incomplete sales coverage is explicit (`missing`/quality flag) and never encoded as zero. No recommendation is returned if required inventory, supplier, lead-time, or open-PO inputs are unavailable; include a stable reason code.
- Brain endpoints are read-only with respect to ERP business state. The only business write goes through the approved proposal flow below.

### 3.5 Agent proposal, approval, and execution

1. Brain creates an immutable `ActionProposal` with UUID, `tool_name=create_purchase_order`, schema version, exact arguments, reason, risk/insight UUID, `arguments_sha256`, idempotency key, expiry, and status `pending`.
2. Approval endpoint accepts `proposal_id`, `decision` (`approved` or `rejected`), and `seen_arguments_sha256`. The actor must have `agent:approve`. Hash mismatch, expired proposal, or repeat conflicting decision returns `CONFLICT`.
3. On approval, the server records actor/time and moves the proposal to approved. Execution revalidates the approved hash and sends the exact payload to canonical `POST .../purchase-orders` with the proposal's idempotency key. No model call or user text may alter arguments after approval.
4. `ActionResult` records proposal ID, outcome (`succeeded`, `failed`, `uncertain`), external PO reference when known, and completion time. An uncertain timeout is reconciled by retrying the same idempotency key, never by creating a new request. Once a proposal is `failed`, a retry needs a fresh human approval (new approval round, D-43). Every approval authorises execution only while `now() <= decided_at + 24 h` (server time, D-44), and only brain-api's role can record it; brain-worker uses a separate role that cannot (D-45).
5. Rejection/expiry never calls the adapter. All proposals, decisions, execution attempts, and audit events are attributable and retained.

### 3.6 Feature and model contracts

- Feature grain: `(tenant_id, product_id, feature_date)`; feature-set version is explicit. The `FeatureVector` is strict and ordered; labels are physically excluded from model inputs.
- All demand features use completed business days only. An incomplete day is missing, not zero; only a complete day with no sales is zero-filled.
- Training and inference call the same feature builder and contract version. Inference fails closed on a model/feature-set mismatch.
- Forecast rows are append-only by generation/job run. Every output records model version, rule/config version where applicable, generation time, horizon, and quality flags.

## 4. Delivery acceptance gates

*(21 Oct: read "Redis outbox replay/duplicate tests" as "poll replay/overlap/out-of-order tests", T-POLL-01..08 in `03_lifecycle_security_performance_testing.md`.)* MVP contract completion means: schemas and mock fixtures exist under `/contracts`; .NET and Python validate against the same fixtures; Redis outbox replay/duplicate tests prove exactly-once effects at the Brain database boundary; write contract tests prove approval-hash binding and adapter idempotency; missing-sales coverage cannot leak into training as zero; and migrations are generated from the schema definition and verified against a clean PostgreSQL 16 database. These are acceptance criteria, not claims that implementation has already passed them.

## 5. Document precedence

This file closes MVP decisions and defines wire behavior. The architecture blueprint describes component boundaries and rationale. The `brain_db` specification defines persistence details. Generated `/contracts` schemas are authoritative for machine validation once checked in; if a mismatch appears, update the schema and regenerate/align both prose documents in the same change.
