# ERP Brain - `brain_db` Design Specification

## Part 4 of 4 - Migration Plan, Implementation Backlog, Final Decisions, Developer Handoff

---

## 1. Alembic Migration Plan

### 1.1 Revision order

| Revision | File | Creates | Why in this order |
|---|---|---|---|
| `0001_foundation` | `ddl/0001_foundation.sql` | Five schemas; `brain_*` trigger functions in `public` | Everything else depends on the schemas and the shared functions |
| `0002_ingest_feat` | `ddl/0002_ingest_feat.sql` | `ingest.*` (6 tables), `feat.*` (2 tables), their triggers | No FKs to other schemas; independent of intel/agent |
| `0003_intel` | `ddl/0003_intel.sql` | `intel.*` (9 MVP tables) in FK order: `rule_config` -> `training_run` -> `model_registry` -> `model_evaluation`, `forecast` -> `forecast_point`, `anomaly_event` -> `risk_assessment` -> `recommendation`; guard triggers; views `v_insight_current`, `v_alert_open` | Child tables follow their parents; self-FKs are added with `ALTER TABLE` after creation |
| `0004_audit_agent` | `ddl/0004_audit_agent.sql` | `audit.llm_usage`, `audit.audit_log`, `agent.*` (6 tables); then the custom guard functions and triggers; view `v_agent_action` | `llm_usage` is referenced by `action_proposal`; proposals reference `intel.recommendation` / `risk_assessment` (0003). The proposal/approval/execution guard functions are created **after** all agent tables because they read each other |
| `0005_roles_grants_seed` | `ddl/0005_roles_grants_seed.sql` | Roles `brain_app`, `brain_worker` (D-45), `brain_retention`, `brain_readonly`; grants; seed `rule_config` rows | Grants need all tables to exist; seeds need `rule_config` |
| `0006_optional_briefing` | `ddl/0006_optional_briefing.sql` | `intel.briefing` + grants | SHOULD-have; delete the revision file to skip |
| `0007_tenancy_rls` | `ddl/0007_tenancy_rls.sql` (downgrade: `0007_tenancy_rls.down.sql`) | Role `brain_provisioner`; `public.brain_current_tenant()`; `ingest.tenant_registry` + guard trigger (N-01); `ENABLE`/`FORCE ROW LEVEL SECURITY` and `pol_tenant_isolation` on every tenant table; `pol_worker_list_tenants`; `security_invoker` on the three views (N-02) | Needs every table; applies to `intel.briefing` only if 0006 ran (if 0006 is skipped, point 0007's `down_revision` at 0005). Inserts no tenant |
| `0008_least_privilege` | `ddl/0008_least_privilege.sql` (downgrade: `0008_least_privilege.down.sql`) | Revokes every pipeline write and the table-level `UPDATE` on `action_proposal` from `brain_app` (column-level lifecycle `UPDATE` instead); `INSERT, UPDATE` on `calendar_day` for `brain_worker`; `UPDATE (is_active)` on `rule_config`, `INSERT` on `audit_log` for `brain_provisioner`; triggers `trg_rule_config_audit` and `trg_rule_config_keep_active` (B1, B7; D-51) | Additive: 0005-0007 unchanged; generated from `spec_privileges.py`; the downgrade restores the exact 0007 grants |
| (future) | `ddl/optional_future_rag.sql` | `CREATE EXTENSION vector`, schema `rag`, `rag.embedding` | Not in the MVP chain |

`ddl/brain_db_mvp.sql` is the concatenation of `0001`-`0008` for review and for a one-shot scratch database. Each Alembic revision executes its file through `brain.db.migrations_util.run_ddl`.

### 1.2 Extensions

None in the MVP: `gen_random_uuid()` is built into PostgreSQL 13 and later (OD-07). `pgvector` is created only by `optional_future_rag.sql` when RAG is approved; creating an extension needs elevated privileges, which is another reason to keep it out of the default chain.

### 1.3 Seed and reference data

| Data | How | When |
|---|---|---|
| `rule_config` default tenant: platform, anomaly, risk, recommendation, forecast (values are illustrative defaults, OD-16) | Data statements in `0005` | Migration |
| `calendar_day` (2020-2030) | Seed script from the calendar source decided in OD-14 | Deploy step after `upgrade head`; not a migration |
| `sync_checkpoint` | Created lazily by jobs | Runtime |
| Shared baseline methods in `model_registry` | Registered by the first training run | Runtime |
| Roles' login users | Created per environment by DevOps | Provisioning |

### 1.4 Running migrations during deployment

1. CI builds the image; the deploy pipeline runs `alembic upgrade head` as a **separate step before restarting** the application (G§14.2), using the migration-owner URL (`BRAIN_DB_MIGRATION_URL`, synchronous driver `postgresql+psycopg://`).
2. brain-api then starts with its `brain_app` login and brain-worker with its `brain_worker` login (D-45); each process gets only its own URL. Neither credential can run DDL.
3. Migrations are additive-first, so the previous application version keeps working during the step.
4. The Alembic process needs a synchronous driver because each revision sends a multi-statement script. The application may still use asyncpg.
5. Downgrades are blocked unless `BRAIN_ALLOW_DESTRUCTIVE_DOWNGRADE=1`, intended for development and test databases only.

### 1.5 Additive-first rules for future changes

- New column: nullable or with a default; backfill in a job; add `NOT NULL` in a later release.
- New table / index: new revision; for large tables use `CREATE INDEX CONCURRENTLY` inside `op.get_context().autocommit_block()`.
- Rename or type change: expand (add new), dual-write, migrate, contract (drop old) across at least two releases.
- New enum value: drop and re-add the CHECK `NOT VALID`, then `VALIDATE CONSTRAINT`.
- Feature change: additive column + `feature_set_version` bump + full recompute; models trained on the old version keep working until retired.
- Never edit an applied revision file; never mix data backfills into a schema revision.

### 1.6 Large backfills are not migrations

Backfills (sales history, feature recompute, model retraining) run as resumable jobs with `sync_checkpoint`, rate limits and their own monitoring (Part 3, section 1.5). A migration must finish in seconds; a backfill may take hours and must be restartable.

### 1.7 Keeping models and DDL aligned

`models.py` declares every constraint and index with the same names as the DDL. CI runs `alembic upgrade head` on an empty database and then `alembic check`; a failure means the models and the DDL diverged. Objects that exist only in SQL (triggers, functions, comments, grants, views) are not modelled and are excluded from comparison; partial-index predicates may show cosmetic differences. Treat the first run of `alembic check` as part of BK-07, not as a surprise.

---

## 2. Implementation Backlog

> **Update 21 Oct 2026 (Q-10):** ingestion, features, `brain_db`, recommendations and the Brain read APIs are owned by **Ibrahim** (D-02). Ibrahim is not assigned Brain work unless Ibrahim agrees. The current task list is `docs/TEAM_TASKS.md`; the BK rows below are kept as the database backlog with owners updated.

Ownership follows D-02. Where this plan departs from the guide (G§17, §18.5), the row is marked **(adjustment)**.

| Person | Owns in this plan |
|---|---|
| **Ibrahim** (D-02; this row named Abdelrahman before 21 Oct) | `brain_db` schema and migrations, SQLModel, ingestion (consumer, Canonical client), normalization, backfill, feature tables and `FeatureStore`, retention jobs |
| **Ibrahim** | Forecasting, anomaly, risk, recommendation, model evaluation, the interfaces consumed from the database, and (per G§3.23-3.29) agent/approval/LLM/audit logic |
| **Yassin** | Canonical API / Adapter contracts (including the polled daily sales totals), idempotent write path, ERP integration |
| **Ali** | PostgreSQL provisioning, roles/logins, network isolation, volumes, backups, CI database service, dashboards |

Suggested adjustments: *superseded on 21 Oct 2026.* Ibrahim owns the `brain_db` DDL for all schemas (D-02, confirmed by Ibrahim in Q-10); each lane owner owns the logic of their tables.

| ID | Ticket | Owner | Depends on | Acceptance criteria |
|---|---|---|---|---|
| **Phase 0 - Decisions and contracts** | | | | |
| BK-01 | Record and implement the finalized MVP decisions OD-01 through OD-24 | Ibrahim, Yassin | none | Baseline captured in `MVP_DECISIONS_AND_CONTRACTS.md`; generated schema/contracts and implementation conform |
| BK-02 | ~~Event schemas~~ **Replaced (D-23):** the `DailySalesTotal`/`SalesPage` poll contract in `/contracts/canonical` | Yassin (producer), Ibrahim (consumer) | BK-01 | Contract test green on both sides for `GET /canonical/sales` |
| BK-03 | Feature-table contract PR (`feature_daily` columns and types, `FeatureVector`) | Ibrahim | BK-01 | Both owners approve (CODEOWNERS); fixtures committed |
| BK-04 | Agent write-path contract: `ActionProposal`, `ActionResult`, approval endpoint, `create_purchase_order` tool schema, error format, `insight_id` meaning | Ibrahim, Mahmoud, Yassin | BK-01 | Merged under `/contracts/ai-output`; matches `PurchaseOrderArguments` |
| **Phase 1 - Database foundation** | | | | |
| BK-05 | Provision PostgreSQL, volumes, roles/logins, network isolation from `erp_db`, CI database service | Ali | none | `brain_db` reachable only from Brain containers; no route to `erp_db`; role matrix verified; CI has a disposable PostgreSQL |
| BK-06 | Review and adopt the DDL; apply `0001`-`0005` on an empty database | Ibrahim (review: Ibrahim) | BK-01, BK-05 | T-MIG-01, T-MIG-03 pass; review comments resolved |
| BK-07 | Adopt `models.py`; configure mappers; `alembic check` clean | Ibrahim | BK-06 | T-MAP-01, T-MIG-02 pass |
| BK-08 | Constraint, trigger and lifecycle test suite | Ibrahim (agent tests with Ahmed Emad) | BK-06 | T-CON-01..03, T-AGT-01..09, T-AUD-01 pass |
| BK-09 | Repository layer with mandatory tenant context; SQL lint for missing `tenant_id` | Ibrahim | BK-07 | T-TEN-01, T-TEN-02 pass |
| BK-10 | Generate Pydantic types from `/contracts`; reconcile `contracts_jsonb.py` | Ibrahim | BK-03, BK-04 | No hand-written duplicate of a shared type remains |
| **Phase 2 - Ingestion** | | | | |
| BK-11 | Canonical client (reads, backoff on reads only, JWT, `traceparent`) against the mock server | Ibrahim (contract: Yassin) | BK-02 | Contract tests green; no write retry without an idempotency key |
| BK-12 | Sales poller: short-interval `get_sales(updated_since)` poll, watermark advanced only after the last page, failures recorded in `ingest_failure` | Ibrahim | BK-06, BK-11 | T-POLL-01, 02, 04, 06 pass against the mock server |
| BK-13 | Absolute upsert of polled rows into `sales_fact` (newest `updated_at` wins) and `sales_day_coverage` | Ibrahim | BK-12 | T-POLL-03, 05, 08 pass; totals equal canonical totals after random page reordering |
| BK-14 | Nightly reconcile, scheduled backfill, `sales_day_coverage`, `sync_checkpoint` | Ibrahim | BK-13 | T-BKF-01, T-BKF-02 pass |
| BK-15 | `canonical_cache` upsert with freshness policy and stale-overwrite guard | Ibrahim | BK-11 | Older payload never overwrites newer; freshness read from `rule_config(platform)` |
| BK-16 | ~~Stream retention, consumer group~~ **Replaced (D-23):** poll-failure alerting when `sync_checkpoint.consecutive_failures` passes a threshold | Ali, Ibrahim | BK-12 | Alert fires when the mock server is down for 3 polls in a row |
| BK-17 | Canonical `get_sales(range, updated_since)` paging; PO read capability; supplier lead time and product-to-supplier data | Yassin | BK-01 | Capability contract merged; mock supports it |
| **Phase 3 - Features** | | | | |
| BK-18 | Calendar seed script | Ibrahim | OD-14 | `calendar_day` populated 2020-2030; Ramadan dates verified |
| BK-19 | Feature pipeline: pure function, incremental job, nightly full job, upsert freshness guard | Ibrahim (features reviewed by Ibrahim) | BK-14, BK-18 | T-FEAT-01..05 pass |
| BK-20 | `FeatureStore` implementation (`get_features`, batch, training frame) | Ibrahim | BK-19, BK-03 | T-FEAT-06, T-PERF-01 pass |
| BK-21 | Seed-data generator with injected anomalies and a hidden test window **(adjustment: Ahmed Hassan)** | Ahmed Hassan (spec: Ibrahim) | none | Produces Canonical data (daily sales totals, products, inventory, suppliers) for 200 SKUs, 12 months; deterministic seed |
| **Phase 4 - Intelligence** | | | | |
| BK-22 | Training: baselines, Holt-Winters, LightGBM; backtest; selection; registry; artifact writer (safe format) | Ibrahim | BK-20, OD-13 | Winner registered `validated`; losers `rejected`; artifact checksum verified on load |
| BK-23 | Inference and persistence: `forecast` + `forecast_point`, idempotent by `job_run_id` | Ibrahim | BK-22 | T-FC-01..04 pass |
| BK-24 | Evaluation harness, weekly post-deployment evaluation, degradation handling | Ibrahim (Mahmoud: tooling) | BK-23 | `model_evaluation` rows written; a degraded model is skipped by inference |
| BK-25 | Anomaly engine: rules, z-score, optional Isolation Forest; natural-key upsert | Ibrahim | BK-20, BK-23 | Dedup test passes; precision/recall on injected anomalies reported |
| BK-26 | Risk engine with versioned assessments and provenance | Ibrahim | BK-23, BK-25, BK-15, BK-17 | T-RISK-01..03 pass |
| BK-27 | Recommendation engine with supersession | Ibrahim | BK-26 | T-REC-01, 02 pass; formula inputs stored in `calculation` |
| BK-28 | `rule_config` admin script; tune seed values on the seed data | Ibrahim | BK-21 | Versioned rows inserted through the script only |
| BK-29 | API projections over the views (`insight`, `alert`, `agent action`) | Ibrahim (review: Mostafa) | BK-26, BK-27 | Responses match `/contracts/ai-output` fixtures |
| **Phase 5 - Agent and audit** | | | | |
| BK-30 | Sessions and messages with PII scrubber and expiry | Ibrahim | BK-06 | T-AGT-12 and T-PII-01 pass |
| BK-31 | Tool-call log (`agent_action`) for every call including rejected ones | Ibrahim | BK-30 | Unknown-tool and invalid-argument attempts are recorded |
| BK-32 | Proposal, approval and execution flow; approval endpoint; unknown-outcome re-approval path | Ibrahim (write path: Yassin; scopes: Ahmed Salah) | BK-31, BK-04 | T-AGT-01..11 pass; end-to-end demo creates one PO exactly once |
| BK-33 | Audit writer, `llm_usage` writer, `/brain/admin/cost` | Ibrahim (infra: Ali) | BK-06 | T-AUD-02, T-AUD-03 pass; Q15 powers the page |
| BK-34 | Retention jobs with `brain_retention` and purge audit rows | Ibrahim | BK-06 | Each table's retention from Part 3 3.6 verified on a seeded database |
| **Phase 6 - Operations and acceptance** | | | | |
| BK-35 | Backups for `agent`/`audit` and `intel` + models volume; restore drill | Ali | BK-05 | Drill reproduces audit rows and matches artifact checksums |
| BK-36 | Performance run: 5,000 SKUs, 2 years | Ibrahim | BK-19, BK-23 | T-PERF-01..04 meet targets |
| BK-37 | Definition-of-Done review | AI Lead + Data Engineer | all | All 12 DoD items (Part 3, 4.3) signed off |
| **Optional / future** | | | | |
| BK-38 | Morning briefing (`briefing`) | Ibrahim | BK-29 | SHOULD; migration `0006` applied |
| BK-39 | Anomaly review endpoint (acknowledge / dismiss / confirm) | Ibrahim, Mahmoud, Omar | OD-15 | Writes `reviewed_*`; audited |
| BK-40 | Row-Level Security | Ibrahim | N-02 (decided) | Done in migration 0007 (policies, `security_invoker` views); `tenancy_rls_checks.py` passes. Application side (BB-05 session, BB-24) still open |
| BK-41 | Partitioning of high-volume tables | Ibrahim | thresholds in Part 3 3.5 | Expand/contract migration with zero downtime |
| BK-42 | RAG (`rag.embedding`) | Ibrahim | OD-18 | Separate migration; extension approved |

---

## 3. Decision Register (Closed for MVP)

OD-01 through OD-24 are closed as the MVP engineering baseline in [`MVP_DECISIONS_AND_CONTRACTS.md`](MVP_DECISIONS_AND_CONTRACTS.md). The defaults recorded in the table below are adopted for implementation. This removes design ambiguity; it does not assert that adapter capabilities, contract tests, or database verification are complete. Update the baseline and generated schema/contracts together if implementation evidence requires a change.

| ID | Question | Why it matters | Proposed default (assumed by the DDL) | Close by |
|---|---|---|---|---|
| OD-01 | What exactly does `SaleCreated` carry? | | **Superseded by D-23:** no `SaleCreated` event in the MVP; sales arrive as polled `DailySalesTotal` rows | closed |
| OD-02 | Product identifier: canonical `product_id` (UUID) or `sku`? The guide uses `product_id` (G§14.2, §7.5) and `sku` (G§18.4, §19.3) | Primary keys, artifact paths, every external reference | `product_id UUID`; `sku` stays inside the cached product payload | Yassin + Ibrahim + Ibrahim |
| OD-03 | What is a "day"? G§3.10 says dates are UTC, but product-by-day aggregation needs a business day. Where does the tenant timezone come from? | A pharmacy in Egypt sells around midnight; a UTC day misattributes sales and distorts weekday patterns | Business date in the tenant timezone (`Africa/Cairo` in `rule_config(platform)`); timestamps stay UTC | Ibrahim + Ibrahim |
| OD-04 | Which supplier's `lead_time_days` applies to a product? Does the canonical Product expose a preferred supplier? | Risk needs a lead time per product | Canonical Product carries `preferred_supplier_id` | Yassin |
| OD-05 | How does the Brain see open purchase orders to avoid duplicate suggestions (G§18.5)? | Otherwise it recommends the same order repeatedly | Add `get_purchase_orders(status)`; until then `open_po_check = skipped_no_capability` | Yassin + Ibrahim |
| OD-06 | What is `insight_id`? | `ActionProposal` references it; there is no Insight table | `insight_id = risk_assessment.id`; final shape in `/contracts/ai-output` | Ibrahim + Mahmoud |
| OD-07 | PostgreSQL version and image (with or without pgvector) | Features used: `gen_random_uuid()` (13+), identity columns, partial indexes. Views `security_invoker` needs 15+ later | PostgreSQL 16; extension absent in the MVP | Ali |
| OD-08 | Does the canonical Sale carry price/amount and currency? | `revenue` and `currency_code` are nullable until confirmed | Nullable | Yassin |
| OD-09 | Are returns and voids represented? There is no such event type (G§3.5) | `units_sold >= 0` assumes gross sales | Corrections arrive through reconcile/backfill only | Yassin + Ibrahim |
| OD-10 | Demand is censored when stock runs out; the Brain has no inventory history | Forecasts underestimate demand for frequently stocked-out items | Documented limitation; later add a stockout flag derived from events | Ibrahim |
| OD-11 | TTLs: approval deadline, session inactivity, message lifetime | Security and storage | Proposal 24 h, session 4 h inactivity, messages 30 days | Ibrahim + product owner |
| OD-12 | Audit retention and any legal requirement | Whether `audit_log` may ever be purged | No deletion in the MVP; revisit with partitioning | Team Lead + supervisor, Ali |
| OD-13 | Model artifact format and volume layout (G§3.28 shows `.pkl`) | Pickle loading executes code | LightGBM text format or `joblib` with checksum; relative path `tenants/<tenant>/products/<product>/<model_version>.<ext>` | Ibrahim + Ali |
| OD-14 | Source of holidays, Ramadan and flu-season windows | Reproducible calendar features | A holidays library plus curated Ramadan and flu windows, stored in `calendar_day` | Ibrahim |
| OD-15 | Anomaly review workflow (acknowledge, dismiss, confirm) and its contract | Columns exist; endpoint and UI do not | SHOULD; defer | Ibrahim + Mahmoud + Omar |
| OD-16 | Values for the seeded rule sets | Severity cut-offs, margin days, safety days, selection margin | Defaults from G§8.3 and G§9.2; tuned on seed data | Ibrahim |
| OD-17 | JWT `sub` type and the format of the `scopes` claim | `*_actor_id` is `TEXT`; the scope check assumes an array | `sub` as string; `scopes` array containing `agent:approve` | Ahmed Salah |
| OD-18 | LLM provider and embedding model | `llm_usage.provider/model` values, pricing table, future vector dimension (assumed 1536) | Provider behind `llm/client.py`; vector dimension set when RAG is approved | Ibrahim (by budget) |
| OD-19 | ~~Redis stream retention, consumer group, max delivery attempts~~ | | **Superseded by D-23:** no Redis Streams in the MVP | closed |
| OD-20 | Is sales aggregated per product, or per product and location? | Changing the unique key of `sales_fact` and `feature_daily` later is a breaking migration | **Decided (N-05):** per organization and product, `(tenant_id, product_id, business_date)`; branch-level forecasting deferred; branch stock is never summed by the Brain without a defined, tested rule. ERP confirmation pending (Yasin) | Yassin + Ibrahim |
| OD-21 | Is `update_inventory` an agent tool in the MVP (G§18.5 reads it as no)? | `action_execution.external_ref_type` allows only `purchase_order` | Not an agent tool | Ibrahim + Yassin |
| OD-22 | Are `created_by/updated_by` required on every table (G§14.2) or only where an actor exists (RC-02)? | Column set | Only where an actor exists | AI Lead + Data Engineer |
| OD-23 | The seeded tenant UUID and removal of the database default before a second tenant | Silent writes to the default tenant | **Amended by D-34:** default removed. Tenants come from `ingest.tenant_registry` (N-01); migrations insert none | Team Lead |
| OD-24 | After handoff, keep generating DDL/models/docs from `tools/schema_gen`, or edit DDL and models by hand? | Avoid two sources of truth | Hand-maintained DDL and models, `alembic check` in CI; generator kept as reference | AI Lead + Data Engineer |

---

## 4. Developer Handoff

### 4.1 Files and who uses them

| Path | Use | Primary user |
|---|---|---|
| `ddl/0001..0006_*.sql`, `ddl/brain_db_mvp.sql` | Authoritative schema for migrations and review | Ibrahim (review), Ali |
| `alembic.ini`, `alembic/env.py`, `alembic/versions/*.py` | Migration environment; revisions execute the DDL files | Ibrahim |
| `python/brain/db/models.py` | SQLModel tables (read-only relationships) | Ibrahim |
| `python/brain/db/contracts_jsonb.py` | JSONB shapes, rule parameters, `FeatureVector`, `canonical_json/sha256_hex` | Ibrahim |
| `python/brain/db/migrations_util.py` | `run_ddl` and the downgrade guard | Ibrahim |
| `erd/*.mmd` | Diagram sources | everyone |
| `docs/*.md` | This specification | everyone |
| `tools/schema_gen/` | The schema definition and generator (reference, OD-24) | Ibrahim |

### 4.2 Environment

| Variable | Used by | Meaning |
|---|---|---|
| `BRAIN_DB_MIGRATION_URL` | Alembic | Migration-owner connection, sync driver |
| `BRAIN_DB_URL` | brain-api | `brain_app` login (async driver allowed) |
| `BRAIN_WORKER_DB_URL` | brain-worker | `brain_worker` login (D-45); never the `brain_app` login |
| `BRAIN_DDL_DIR` | `migrations_util` | Override if `ddl/` is not next to `python/` |
| `BRAIN_ALLOW_DESTRUCTIVE_DOWNGRADE` | `migrations_util` | Must be `1` to run a downgrade (dev/test only) |

### 4.3 Day-one checklist

**Data Engineer (Ibrahim, D-02):**
1. Start a scratch PostgreSQL 16; export `BRAIN_DB_MIGRATION_URL`; run `alembic upgrade head`, then `alembic check`; record any drift as BK-07 findings.
2. Read the triggers in `0001`, `0003`, `0004`; write the T-CON and T-AGT constraint tests first.
3. Stand up the consumer against the Canonical mock; implement the transaction in Part 3, section 1.3.
4. Open the feature-table contract PR (BK-03) with Ibrahim.

**AI Engineer (Ibrahim):**
1. Review `feature_daily` and `contracts_jsonb.FeatureVector`; confirm the 20 model inputs and the label split.
2. Read `rule_config` seed values; confirm or change (OD-16).
3. Implement against the repository interfaces below using fixtures, before the pipelines exist.
4. Review the approval lifecycle and the `AuditDetails` allow-list.

**Integration (Yassin) and Infrastructure (Ali):** items in BK-02, BK-04, BK-05, BK-16, BK-17, BK-35.

### 4.4 Interfaces between the teams (signature sketches, not final)

```python
from datetime import date, datetime
from typing import Optional, Protocol, Sequence
from uuid import UUID

class RequestContext:               # built from the JWT or the job parameters; immutable
    tenant_id: UUID; actor_id: str; scopes: frozenset[str]; trace_id: str

# --- Ibrahim provides (ingestion and features) -------------------------------------------------------------------------
class FeatureStore(Protocol):       # contracts_jsonb.FeatureStore
    def get_features(self, product_id: UUID, feature_date: date) -> "FeatureVector": ...
    def get_features_batch(self, product_ids: Sequence[UUID], feature_date: date) -> list["FeatureVector"]: ...
    def get_training_frame(self, product_id: UUID, start: date, end: date) -> list["FeatureVector"]: ...

class CanonicalReader(Protocol):    # contract with Yassin; reads only; retries with backoff
    async def get_inventory(self, ctx: RequestContext, product_id: UUID) -> dict: ...
    async def get_supplier(self, ctx: RequestContext, supplier_id: UUID) -> dict: ...
    async def get_sales(self, ctx: RequestContext, start: date, end: date, updated_since: Optional[datetime]) -> list[dict]: ...

class CanonicalCacheRepo(Protocol):
    def get_fresh(self, ctx: RequestContext, entity_type: str, entity_id: str, max_age_s: int) -> Optional[dict]: ...
    def upsert(self, ctx: RequestContext, entity_type: str, entity_id: str, payload: dict, source_updated_at: Optional[datetime]) -> bool: ...

class SalesFactRepo(Protocol):
    def upsert_totals(self, ctx: RequestContext, rows: list[dict], mode: str) -> int: ...   # absolute; newest source_updated_at wins (D-25)
    def changed_since(self, ctx: RequestContext, watermark: datetime) -> list[tuple[UUID, date]]: ...

# --- Ibrahim provides, persisted through repositories (Ibrahim) ------------------------------
class ModelRegistryRepo(Protocol):
    def register(self, ctx: RequestContext, model) -> UUID: ...
    def promote(self, ctx: RequestContext, model_id: UUID, reason: str) -> None: ...
    def degrade(self, ctx: RequestContext, model_id: UUID, reason: str) -> None: ...
    def latest_validated(self, ctx: RequestContext, product_id: UUID, purpose: str = "forecast"): ...

class ForecastRepo(Protocol):
    def save(self, ctx: RequestContext, forecast, points: Sequence) -> UUID: ...   # idempotent on (product, model, job_run_id)
    def latest_eligible(self, ctx: RequestContext, product_id: UUID): ...
    def points(self, ctx: RequestContext, forecast_id: UUID) -> list: ...

class AnomalyRepo(Protocol):
    def upsert_detection(self, ctx: RequestContext, detection) -> UUID: ...        # natural-key upsert
class RiskRepo(Protocol):
    def upsert_version(self, ctx: RequestContext, assessment) -> tuple[UUID, bool]: ...   # (id, inserted_new_version)
class RecommendationRepo(Protocol):
    def supersede_and_insert(self, ctx: RequestContext, rec) -> UUID: ...
class ProposalRepo(Protocol):
    def create(self, ctx: RequestContext, session_id: UUID, tool_name: str, tool_version: str, arguments: dict,
               reason: str, recommendation_id: Optional[UUID], risk_assessment_id: Optional[UUID],
               llm_usage_id: Optional[UUID], ttl_seconds: int) -> UUID: ...        # computes sha256 and idempotency key
    def decide(self, ctx: RequestContext, proposal_id: UUID, decision: str, seen_arguments_sha256: str, round_: int = 1) -> None: ...
    def begin_execution(self, ctx: RequestContext, proposal_id: UUID, approval_id: UUID) -> UUID: ...
    def complete_execution(self, ctx: RequestContext, execution_id: UUID, status: str, certainty: Optional[str], result: dict) -> None: ...
class AuditWriter(Protocol):
    def write(self, ctx: RequestContext, event_type: str, outcome: str, subject_type: Optional[str], subject_id: Optional[UUID],
              details: "AuditDetails", arguments_sha256: Optional[str] = None, tool_name: Optional[str] = None) -> None: ...
class LlmUsageWriter(Protocol):
    def record(self, ctx: RequestContext, **usage) -> UUID: ...
```

### 4.5 Yassin's implementation acceptance

Implement and contract-test the `DailySalesTotal`/`SalesPage` poll contract (D-24), UUID identifiers and preferred-supplier mapping, stable `get_sales` paging/watermark behavior (including correction timestamps), optional amount/currency fields, open-PO read, idempotent purchase-order writes, and stable error codes. These are delivery gates, not unresolved schema decisions.

### 4.6 What Ali must provide

PostgreSQL 16 with the volumes and roles in Part 3, section 2.4; network policy preventing any route from the Brain to `erp_db`; a disposable PostgreSQL service in CI; nightly dumps for the `agent`/`audit` tier with the longest retention and for `intel` plus the models volume; a quarterly restore drill; dashboards fed by `llm_usage` (Q15).
