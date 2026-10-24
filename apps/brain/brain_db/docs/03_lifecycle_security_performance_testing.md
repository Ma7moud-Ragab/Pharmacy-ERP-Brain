# ERP Brain - `brain_db` Design Specification

## Part 3 of 4 - Data Lifecycle, Security and Audit, Performance and Retention, Testing

---

## 1. Data Lifecycle and Event Processing

### 1.1 Where each kind of data lives

| Data | `brain_db` | `erp_db` (never read by the Brain) |
|---|---|---|
| Business truth: sales, stock movements, products, suppliers, purchase orders, customers, employees | | **Yes** (System of Record) |
| ERP `AuditLog` | | **Yes** |
| Poll checkpoints, failures, day coverage | **Yes** | |
| Canonical payload cache | **Yes** | |
| `sales_fact` (daily totals), features, forecasts, models, anomalies, risks, recommendations | **Yes** | |
| Agent sessions, proposals, approvals, executions, audit, LLM usage | **Yes** | |
| Model artifact files | Registry row in `brain_db`; file on the models volume | |

There is no Redis and no event stream in the MVP (D-23). The only way ERP data reaches the Brain is a Canonical HTTP read.

### 1.2 Lifecycle of one day of sales

| Stage | What happens | What is stored, and where | Immutable? | Rebuildable? |
|---|---|---|---|---|
| 0. ERP transaction | Sale, return or void committed in the ERP; the daily total for (product, business_date) changes and its `updated_at` advances | `erp_db` only | ERP-owned | n/a |
| 1. Poll (every `sales_poll_interval_seconds`) | `GET /canonical/sales?from=&to=&updated_since=` page by page; each row validated against `canonical.DailySalesTotal` | Nothing yet (a validation or read failure becomes `ingest_failure`) | | |
| 2. Upsert (one DB transaction per page) | Absolute upsert into `sales_fact`; `sales_day_coverage(open)` inserted if missing; after the LAST page, `sync_checkpoint.high_watermark` = the page's `high_watermark` | `sales_fact`, `sales_day_coverage`, `sync_checkpoint` | No | Yes (Canonical backfill) |
| 3. Intraday intelligence window (every `intel_window_minutes`) | Products whose `sales_fact.updated_at` > the `intel_window` watermark are "dirty"; for them: features (incremental) -> anomaly -> risk -> recommendation, using the latest nightly forecast and a fresh inventory read | `feature_daily`, `anomaly_event`, `risk_assessment`, `recommendation` | Risk inputs immutable | Current yes; history no |
| 4. End of day (`end_of_day_run_local_time`, default 02:00 Cairo) | Reconcile the last `reconcile_lookback_days` (no watermark) -> mark closed days `complete`/`gap` -> nightly full features -> **training** -> forecast inference for every product -> intelligence window for every product | All of the above plus `training_run`, `model_registry`, `model_evaluation`, `forecast`, `forecast_point` | Forecast immutable | Past forecasts no |
| 5. Brain API / UI | Reads views and tables; the LLM, if asked to explain, receives only a compact structured object | Nothing new except `llm_usage`, `agent_*` | | |

No model is trained during the business day (D-26). Intraday work only refreshes facts and re-scores risk with the existing forecast.

### 1.3 The poll transaction (reference sequence)

```sql
-- once per page (pages from one poll share the same high_watermark)
BEGIN;
INSERT INTO ingest.sales_fact AS s
  (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, day_status, is_complete,
   source_updated_at, source_mode, polled_at)
VALUES (:t, :p, :business_date, :sold, :returned, :net, :day_status, :complete, :updated_at, 'poll', now())
ON CONFLICT (tenant_id, product_id, sales_date) DO UPDATE SET
  units_sold = EXCLUDED.units_sold, units_returned = EXCLUDED.units_returned, net_units = EXCLUDED.net_units,
  day_status = EXCLUDED.day_status, is_complete = EXCLUDED.is_complete,
  source_updated_at = EXCLUDED.source_updated_at, source_mode = EXCLUDED.source_mode, polled_at = now()
WHERE EXCLUDED.source_updated_at >= s.source_updated_at;   -- an older row never overwrites a newer one

INSERT INTO ingest.sales_day_coverage (tenant_id, business_date, status)
VALUES (:t, :business_date, 'open') ON CONFLICT DO NOTHING;

-- only in the transaction of the LAST page (next_cursor IS NULL):
UPDATE ingest.sync_checkpoint
   SET high_watermark = :page_high_watermark, cursor = NULL, last_status = 'succeeded',
       last_finished_at = now(), consecutive_failures = 0
 WHERE tenant_id = :t AND resource = 'sales_poll';
COMMIT;
```

The next poll sends `updated_since = high_watermark - poll_overlap_seconds` (default 120 s, D-05).

### 1.4 Failure and edge cases

| Scenario | Behaviour | Why it is safe |
|---|---|---|
| **Same row read twice** (overlap window, retried page, re-run poll) | Upsert writes the same values | Absolute totals: idempotent |
| **Out-of-order rows** (an older `updated_at` arrives after a newer one) | `WHERE EXCLUDED.source_updated_at >= s.source_updated_at` skips it | Newest ERP value always wins |
| **Return, void or edit of any day** | ERP advances that row's `updated_at`; the next poll returns the new absolute total and overwrites | No negative increments ever (D-06) |
| **Crash or timeout in the middle of a multi-page poll** | Watermark not advanced; next poll starts again from the old watermark | Re-reading is harmless |
| **Late ERP commit** (row committed with an `updated_at` older than the watermark the Brain already stored) | The poll can miss it; the nightly reconcile re-reads the last `reconcile_lookback_days` by date with no watermark and overwrites it | Bounded: intraday staleness only, closed days are always re-verified (see 1.4.1) |
| **Canonical down** | Retry with backoff inside the poll; then one open `ingest_failure(canonical_read_failed)` per error code, `attempts` bumped on every failed poll; `consecutive_failures` drives the alert | Next successful poll resolves it (`resolution='repolled'`) |
| **Schema validation failure on a row** | Row skipped; `ingest_failure(schema_validation)` with the product ids/dates in `payload_excerpt`; the rest of the page is applied; watermark still advances | The nightly reconcile marks the affected day `gap (validation_failures)` if it is still invalid |
| **ERP says a day is incomplete** (`complete=false` or the date is in `coverage.incomplete_dates`) | Day marked `gap (erp_incomplete)` at reconcile | Excluded from training; never treated as zero |
| **Correction older than `reconcile_lookback_days`** | Picked up by the normal poll (its `updated_at` advances) | Only a late commit that is ALSO older than the lookback is missed; a manual backfill fixes it |
| **`sync_checkpoint` row lost** | Next poll reads from `poll_history_start_date` | Slow once, but correct |

#### 1.4.1 Checkpoint caveat: `updated_since` versus an outbox sequence

A timestamp watermark can skip a row when the ERP stamps `updated_at` at the start of a transaction that commits later than a poll that already moved the watermark past it. The ERP backend blueprint proposes a gap-free `OutboxEvent.event_sequence` cursor to remove this risk, but that needs an outbox read API and per-sale events, which is the complexity D-23 removes. The MVP accepts the timestamp watermark because (1) the 120 s overlap covers normal commit delays, (2) every write is an absolute total, so re-reading is free, and (3) the nightly reconcile re-reads every recent closed day by date range before training. The worst case is a stale intraday total until the next end-of-day run, never wrong training data. If the ERP can stamp `updated_at` at commit time (for example by computing the daily total in a view over committed rows), the caveat mostly disappears; that is an open question for Yasin.

### 1.5 Backfill and rebuild

Backfill is a job, not a migration. `backfill --from D1 --to D2`: for each day, paged `get_sales(from, to)` without `updated_since`; absolute upsert into `sales_fact` (`source_mode='backfill'`); mark `sales_day_coverage` `complete` (`verified_via='backfill'`); then recompute features for the range. It is idempotent and resumable (`sync_checkpoint.cursor`, `high_watermark`). Rebuild order after a total loss of derived data: `canonical_cache` -> `sales_fact` + `sales_day_coverage` -> `calendar_day` -> `feature_daily` -> retrain -> forecasts -> anomalies -> risks -> recommendations. Audit and agent tables are restored from backup, not rebuilt.

### 1.6 Nightly recompute and incremental updates

The nightly full recompute takes `pg_try_advisory_xact_lock` for `feature_nightly_full` and the incremental job skips while it holds the lock. Both use the same pure function, and the upsert only replaces a row when it is at least as fresh:

```sql
ON CONFLICT (tenant_id, product_id, feature_date) DO UPDATE SET ...
WHERE feat.feature_daily.inputs_max_updated_at IS NULL
   OR EXCLUDED.inputs_max_updated_at >= feat.feature_daily.inputs_max_updated_at;
```

So an older computation can never overwrite a newer one.

### 1.7 Retraining and historical predictions

Retraining inserts new `model_registry` rows (`candidate`), backtests them, and promotes the winner to `validated` only if it beats the baseline by `must_beat_baseline_margin`. The previously validated model for that product becomes `retired`. Forecasts are never rewritten; each keeps its `model_id`. If post-deployment WAPE exceeds `degradation_wape_factor` times the backtest WAPE, the model is set `degraded` and inference falls back to the previous validated model or a baseline.

---

## 2. Security, Tenant Isolation and Audit

### 2.1 Isolation from `erp_db`

- `brain_db` is a separate PostgreSQL database. The Brain's configuration contains no `erp_db` host, user or password; the Brain's network (Compose network policy) has no route to the ERP database port. Isolation is enforced by network and credentials, not convention (G§3.30).
- No `postgres_fdw`, `dblink` or shared schema. CI fails if an ERP connection string or ERP table name appears in the Brain repository.
- All ERP data and writes go through the Canonical client with the user's JWT and `traceparent`.

### 2.2 Tenant isolation

- **Tables with `tenant_id`:** all of them (G§18.4: not optional).
- **Constraints with `tenant_id`:** every unique constraint that identifies a business object, every intra-brain FK (composite), and every lookup index.
- **Query layer:** repositories take `tenant_id` as a required argument and add it to every statement; there is no repository method without it. A lint/CI check searches for SQL on Brain tables without `tenant_id`.
- **JWT to data layer:** a FastAPI dependency verifies the JWT (claims `sub, roles, tenant_id, scopes`), builds an immutable `RequestContext(tenant_id, actor_id, scopes, trace_id)` and passes it to services; services pass `ctx.tenant_id` into repositories. For brain-worker jobs the tenant comes only from the `ingest.tenant_registry` row being processed (N-01). A tenant id in a request body, path or query is never used as the context.
- **Tenant registry (N-01):** `ingest.tenant_registry` lists the tenants this Brain serves. brain-worker runs jobs only for `active` rows; brain-api refuses a token whose tenant is not `active` (403 `TENANT_NOT_ACTIVE`). Each row references the tenant's own Canonical credential (`credential_ref` + `credential_sha256`), and the worker builds a separate Canonical client per tenant from it; the secret never enters the database. Activation is refused until the credential is validated and the rule sets exist.
- **Cross-tenant references are impossible** between Brain tables because composite FKs carry `tenant_id`.

### 2.3 Row-Level Security (N-02, migration 0007)

RLS is a **second, independent wall**. Application scoping stays mandatory: every repository statement filters by `ctx.tenant_id` (BB-24 lint). RLS catches the statement where that filter was forgotten.

```sql
-- every tenant table (26), generated by tools/schema_gen (gen_core.tenancy_sql)
ALTER TABLE intel.forecast ENABLE ROW LEVEL SECURITY;
ALTER TABLE intel.forecast FORCE ROW LEVEL SECURITY;        -- also binds the table owner
CREATE POLICY pol_tenant_isolation ON intel.forecast AS PERMISSIVE FOR ALL TO PUBLIC
  USING      (tenant_id = public.brain_current_tenant())
  WITH CHECK (tenant_id = public.brain_current_tenant());
-- public.brain_current_tenant() = NULLIF(current_setting('app.tenant_id', true), '')::uuid
```

Rules:

1. **Transaction-scoped context only.** Each unit of work runs `SELECT set_config('app.tenant_id', :tenant_id, true)` as its first statement (`true` = transaction-local, the same as `SET LOCAL`). Commit or rollback clears it, so a pooled connection (SQLAlchemy pool, PgBouncer in transaction mode) never carries a tenant to the next unit of work. A session-level `SET app.tenant_id` is forbidden (CI grep), and the engine's pool `checkout` hook discards any connection that still has a value.
2. **Fail closed.** No context means `brain_current_tenant()` is NULL: every table reads as empty and every INSERT/UPDATE is refused. A value that is not a UUID raises an error.
3. **Where the value comes from.** brain-api: only the verified JWT `tenant_id` claim. brain-worker: only the registry row of the tenant being processed, one transaction per tenant. Never from a request field.
4. **No bypass.** No runtime role (`brain_app`, `brain_worker`, `brain_retention`, `brain_readonly`, `brain_provisioner`) and no login granted one may be `SUPERUSER` or `BYPASSRLS`, or own a table. brain-api and brain-worker check `rolsuper` and `rolbypassrls` of `current_user` at startup and refuse to start if either is true. Only the migration owner owns tables, and `FORCE` binds it too; only a superuser bypasses RLS.
5. **Views** run with `security_invoker = true`, so they read with the caller's rights.
6. **Exception:** `pol_worker_list_tenants` lets `brain_worker` read every `tenant_registry` row (ids, status, credential references). It needs the list before it has a tenant context. It gives no access to tenant business data.
7. **What RLS does not do.** It cannot tell whether the application set the right tenant: a compromised or buggy process that sets another tenant's id reads that tenant. The guarantee comes from rule 3 plus BB-24's application tests. Trigger functions run as the caller, so they see only the current tenant's rows (a guard that looks up a proposal of another tenant reports it as unknown).

Evidence: `verification/tenancy_rls_checks.py` (catalog coverage, cross-tenant reads and writes for every runtime role, pooled-connection reset, registry rules). Isolation is claimed only for what those checks and BB-24 show.

### 2.4 Database roles

| Role | Used by | Privileges |
|---|---|---|
| migration owner (login, per environment) | Alembic only | Owns all objects; used in the deploy step |
| `brain_app` (NOLOGIN; granted to the API login) | brain-api (FastAPI) | Since 0008 (B1, D-51): `SELECT` only on every `ingest`/`feat`/`intel` table, `tenant_registry` and `rule_config`; writes only the API's own tables: `SELECT, INSERT, UPDATE` on `agent_session` and `action_execution`, `SELECT, INSERT` on `agent_message`, `agent_action`, `action_approval`, `llm_usage`, `audit_log`, and on `action_proposal` `SELECT, INSERT` plus column-level `UPDATE (status, status_changed_at, row_version, updated_at)`. The only role that can record a decision (`INSERT` on `action_approval`). **No `DELETE`, no DDL, no `TRUNCATE`** |
| `brain_worker` (NOLOGIN; granted to the worker login, D-45) | brain-worker jobs | Writes the ingest/feat/intel tables its jobs own, including `calendar_day` (`SELECT, INSERT, UPDATE` since 0008, B7); `SELECT` on `rule_config`, `action_approval`; `INSERT` on `audit_log`; `SELECT, INSERT, UPDATE` on `action_execution` (retries, completion); on `action_proposal` only `SELECT` and column-level `UPDATE (status, status_changed_at, row_version, updated_at)`, and `guard_proposal_transition` lets it move only `pending -> expired` and `executing -> succeeded/failed`. No `DELETE`, no `TRUNCATE`, no decision insert, not a member of `brain_app` |
| `brain_retention` | Retention job | `SELECT, DELETE` on purgeable tables only, one tenant per transaction (RLS) |
| `brain_readonly` | Humans, BI, support | `SELECT` only, one tenant per transaction (RLS) |
| `brain_provisioner` (NOLOGIN; granted to the provisioning login, N-01) | provisioning command | `SELECT, INSERT, UPDATE` on `ingest.tenant_registry`, `SELECT, INSERT` and column-level `UPDATE (is_active)` on `intel.rule_config` (rule-set version switches, D-51), `INSERT` on `audit.audit_log`; nothing else. Subject to RLS: it works on one tenant at a time |

All runtime roles are subject to RLS (N-02); none is `SUPERUSER` or `BYPASSRLS`.

**Rule-set version changes (D-51).** Only `brain_provisioner` (the `brain-provision` command, BB-25) adds a rule-set version or switches the active one, in the tenant context of that tenant. The command sets `app.actor_id` (the operator) and optionally `app.trace_id` transaction-locally; trigger `trg_rule_config_audit` (caller's rights, no `SECURITY DEFINER`) refuses the change without an actor and writes `rule_config.version_added` / `.activated` / `.deactivated` to `audit.audit_log` in the same transaction. Deferred constraint trigger `trg_rule_config_keep_active` refuses, at commit, any transaction that leaves an active tenant without an active version of a set, so a switch deactivates the old and activates the new version in one transaction. Stored versions are immutable apart from `is_active`.

The LLM never connects as any role: tools call services, services call repositories (G§11.4).

### 2.5 Authorisation of tool calls and writes

1. The tool registry rejects unknown tools and validates arguments against `input_schema` (outcome `rejected_unknown_tool` / `rejected_invalid_arguments` in `agent_action`).
2. The static policy returns `require-approval` for every write; it is recorded as `policy_version`.
3. The proposal is inserted with `arguments_sha256` and `idempotency_key`.
4. Approval requires the JWT scope `agent:approve`; the scopes seen are stored on the approval row.
5. The Canonical write is made with the **approver's** JWT, so the agent cannot exceed that user's permission, and with the proposal's `Idempotency-Key`.
6. Triggers and constraints make 2-5 enforceable even if application code has a bug (Part 2, C.1).

Prompts are never a security boundary: nothing above depends on the LLM obeying instructions.

### 2.6 Keeping secrets and sensitive payloads out of logs and traces

- `audit_log.details` is validated by the `AuditDetails` allow-list model; adding a key needs a code change and review.
- `llm_usage`, `audit_log` and `agent_action` never store prompt text, completions, JWTs, secrets, or raw ERP rows (`prompt_sha256` only).
- `agent_message.content` is PII-scrubbed (CHECK forces the attestation), capped at 4,000 characters and expires.
- Error messages are sanitised and capped at 500 characters.
- Application logs are JSON on stdout with the same allow-list discipline; `trace_id` is the only join key.
- Free text from the ERP (product names) is untrusted: it is never concatenated into prompts as instructions (G§10.5).

### 2.7 Backups and recovery of audit records

| Tier | Schemas | Backup | Restore expectation |
|---|---|---|---|
| A audit-critical | `agent`, `audit` | Daily `pg_dump -n agent -n audit` kept longest; recommend WAL archiving for point-in-time recovery (Ali) | Must be restorable alone and to a point in time |
| H history-bearing | `intel` + models volume | Daily dump; the models volume snapshotted with it | Restore both together so `artifact_sha256` matches |
| R/O rebuildable | `ingest`, `feat` | Optional; rebuilt by backfill | Rebuild procedure in 1.5 |

Restore drills are part of the Definition of Done. Hash-chaining `audit_log` for tamper evidence is a future upgrade, not MVP.

---

## 3. Performance, Indexing, Retention

### 3.1 Core access patterns and the index that serves each

| Access pattern | Index / key |
|---|---|
| `FeatureStore.get_features(product_id, date)` | `pk_feature_daily (tenant, product, date)` |
| Training frame per product | Same PK, range scan |
| Per-day batch scoring | `ix_feature_daily__tenant_date` |
| Changed sales since watermark | `ix_sales_fact__tenant_updated_at` |
| `sales_fact` upsert | `uq_sales_fact__tenant_product_date` |
| Idempotent poll apply | `uq_sales_fact__tenant_product_date` + `source_updated_at` guard |
| Latest eligible forecast | `ix_forecast__tenant_product_generated` + `ix_model_registry__serving` |
| Forecast points | `pk_forecast_point (forecast_id, target_date)` |
| Accuracy over a window | `ix_forecast_point__tenant_target` |
| Current risk for a product | `uq_risk_assessment__current` |
| At-risk dashboard | `ix_risk_assessment__current_severity` (partial) |
| Active recommendation | `uq_recommendation__active` |
| Open anomaly signals | `ix_anomaly_event__open_severity` (partial) |
| Pending approvals | `ix_action_proposal__pending` (partial) |
| Session by id / latest for user | PK / `ix_agent_session__user_activity` |
| Audit by trace / actor / subject | `ix_audit_log__trace`, `__tenant_actor_occurred`, `__subject` |
| Cost by day / purpose | `ix_llm_usage__tenant_occurred`, `__tenant_purpose_occurred` |

Composite index order is equality columns first (`tenant_id`, then the entity), then the range/sort column last. Descending order is not declared: PostgreSQL scans a B-tree backward for `ORDER BY ... DESC LIMIT n`.

### 3.2 Pagination

Keyset (seek) pagination everywhere a list can grow: audit by `(occurred_at, seq)` or `seq`; proposals by `(created_at, id)`; anomalies by `(last_detected_at, id)`. No `OFFSET` on tables that grow.

### 3.3 Transaction boundaries

| Operation | Transaction scope |
|---|---|
| Poll apply | One transaction per page: upsert rows + coverage; the watermark is updated only in the transaction of the last page |
| Feature recompute | One transaction per batch of products (e.g. 100), upsert only |
| Forecast generation | One transaction per product: `forecast` + all `forecast_point`s |
| Risk update | One transaction: insert new version + supersede old (or heartbeat) |
| Recommendation | One transaction: supersede previous active + insert new |
| Approval | One transaction: `SELECT ... FOR UPDATE` on the proposal; insert approval; CAS-update status; insert audit row |
| Execution | Txn 1: insert `started` execution + set `executing`. The Canonical call happens **outside** any open transaction. Txn 2: complete the execution, set proposal status, insert audit row |

### 3.4 Connection pooling

SQLAlchemy async engine, `pool_size` about 10 and `max_overflow` about 10 per API process; a separate small pool for the consumer and jobs; `pool_pre_ping=True`; `statement_timeout` per role (API 5 s, jobs 5 min). Alembic uses a separate migration-owner connection with a synchronous driver. Add PgBouncer in transaction mode only if the process count grows; `set_config(..., true)` is compatible with it.

### 3.5 Growth and partitioning decision

Assumptions: one tenant; a realistic pharmacy has about 5,000 SKUs; the demo has about 200. Forecast horizon 14 days; 1 to 2 forecast generations per product per day.

| Table | Rows per year (5,000 SKUs) | Rows per year (200-SKU demo) |
|---|---|---|
| `sales_fact`, `feature_daily` | ~1.8 M each | ~73 k |
| `forecast` | ~1.8 M to 3.7 M | ~73 k to 146 k |
| `forecast_point` | ~25 M to 51 M | ~1 M to 2 M |
| `audit_log`, `llm_usage`, `agent_action` | proportional to usage; far below the above | |

**Decision: no partitioning in the MVP.** PostgreSQL handles these volumes with the indexes above, and 13-month retention caps `forecast_point`. Revisit when: `forecast_point` exceeds ~100 M rows or the nightly purge exceeds its window (partition by month on `target_date`); `audit_log` exceeds ~50 M rows or a purge policy is set (monthly partitions, then `DROP PARTITION` is the only permitted purge path); `llm_usage` exceeds ~50 M rows. Partitioning would be an expand/contract migration (create partitioned copy, backfill, swap), which the additive-first rule already allows.

### 3.6 Retention

| Table | Retention | Mechanism | Note |
|---|---|---|---|
| `ingest_failure` | resolved 90 days; open kept | Purge | |
| `canonical_cache` | evict if not refreshed for 30 days | Purge by `synced_at` | |
| `sales_fact`, `sales_day_coverage`, `calendar_day`, `sync_checkpoint`, `rule_config` | permanent (sales >= 3 years) | none | Seasonality needs full years |
| `feature_daily` | 30 months | Purge by `feature_date` | |
| `training_run` | 13 months | Purge | |
| `model_registry` | rejected candidates 90 days if unreferenced; others 24 months and while referenced | Purge with `NOT EXISTS` (FK RESTRICT protects the rest) | Artifact files deleted together |
| `model_evaluation` | 24 months | Purge | |
| `forecast` | 24 months | Purge | Must be >= `anomaly_event` retention (FK) |
| `forecast_point` | 13 months | Purge by `target_date` | |
| `anomaly_event` | 24 months | Purge | Reviewed rows are evaluation labels |
| `risk_assessment`, `recommendation` | 13 months; kept while referenced by a proposal | Purge with `NOT EXISTS` | |
| `briefing` | 90 days | Purge | |
| `agent_message` | 30 days (`expires_at`) | Purge | |
| `agent_session` | 30 days after expiry if no proposals | Purge with `NOT EXISTS` | Sessions with proposals are kept; their messages are purged |
| `agent_action` | 180 days | Purge | Audit of writes is `audit_log` + proposal/approval/execution |
| `action_proposal`, `action_approval`, `action_execution`, `audit_log` | **No deletion in MVP** | Triggers + no privilege | OD-12 |
| `llm_usage` | 13 months raw | Purge unless referenced | Keep daily aggregates longer if needed |

Purge jobs run as `brain_retention`, in small batches, outside business hours, and write an `audit_log` row (`retention.purged`) with counts only.

---

## 4. Testing Plan and Definition of Done

### 4.1 Test plan

Tests run against a real PostgreSQL in CI (a disposable container), not SQLite: triggers, partial indexes and `CHECK`s are PostgreSQL behaviour.

| ID | Area | Test | Pass condition |
|---|---|---|---|
| T-MIG-01 | Migrations | `alembic upgrade head` on an empty database | Succeeds; all objects exist |
| T-MIG-02 | Migrations | `alembic check` after upgrade | No model/DB drift (known acceptable: partial-index predicate text normalisation) |
| T-MIG-03 | Migrations | `alembic downgrade base` with the guard variable set, then upgrade again | Succeeds; refuses without the variable |
| T-MIG-04 | Migrations | Additive migration on a populated database | No locks > 1 s on the large tables |
| T-MAP-01 | Models | Import `models`, configure mappers, compile all `CreateTable` for the PostgreSQL dialect | No errors or warnings |
| T-CON-01 | Constraints | Every CHECK has a violating and a valid fixture | Violation raises `check_violation` |
| T-CON-02 | Constraints | Every unique constraint and partial unique index | Duplicate raises `unique_violation`; allowed variants succeed |
| T-CON-03 | Constraints | Every FK, including cross-tenant: insert a child whose parent belongs to another tenant | Fails |
| T-TEN-01 | Tenant isolation | Repository methods called with tenant A never return tenant B rows (property test across all repositories) | Zero leakage |
| T-TEN-02 | Tenant isolation | Static scan for SQL on Brain tables without `tenant_id` | None |
| T-POLL-01 | Polling | Read the same page twice | `sales_fact` identical; no duplicate rows |
| T-POLL-02 | Polling | Two polls overlapping by `poll_overlap_seconds` | Identical final totals |
| T-POLL-03 | Polling | An older `updated_at` arrives after a newer one | Older value never overwrites the newer |
| T-POLL-04 | Polling | Crash after page 1 of 3 | Watermark not advanced; next poll re-reads; final totals equal Canonical |
| T-POLL-05 | Polling | Return or void on a closed day | Next poll overwrites the total; the affected feature window recomputes |
| T-POLL-06 | Polling | Canonical down for 1 hour | One open `ingest_failure` with `attempts` > 1; resolved as `repolled` on the next success |
| T-POLL-07 | Polling | Row committed with an `updated_at` older than the stored watermark | Missed by the poll; fixed by the nightly reconcile |
| T-POLL-08 | Polling | `complete=false` or date in `coverage.incomplete_dates` | Day marked `gap (erp_incomplete)`; excluded from training |
| T-FEAT-01 | Features | Golden sales series with a hand-computed expected feature table | Exact match |
| T-FEAT-02 | Features | Gap days | `missing` vs `zero_filled` per coverage; lags NULL; `n_obs_*` correct |
| T-FEAT-03 | Features | Correct a historical day | Only the affected window is recomputed; `inputs_max_updated_at` advances |
| T-FEAT-04 | Features | Nightly full recompute vs incremental result | Identical rows for the same inputs |
| T-FEAT-05 | Features | Leakage: for every row, no input depends on data at or after `feature_date` (perturb future sales; inputs must not change) | No change |
| T-FEAT-06 | Features | `FeatureVector.model_inputs()` order and `MODEL_INPUT_COLUMNS` | Fixed; labels excluded |
| T-FC-01 | Forecast | Two generations for the same product/model | Both kept; unique `(tenant, product, model, job_run_id)` blocks only a retry |
| T-FC-02 | Forecast | `UPDATE intel.forecast ...` | Rejected by trigger |
| T-FC-03 | Forecast | Latest-eligible-forecast query when the model is `degraded` | Falls back to the previous validated model's forecast |
| T-FC-04 | Forecast | Point CHECKs (`low <= predicted <= high`) | Enforced |
| T-RISK-01 | Risk | Recompute with unchanged inputs | Only `last_confirmed_at` changes |
| T-RISK-02 | Risk | Recompute with changed inventory | New version inserted; old superseded; one current row |
| T-RISK-03 | Risk | Provenance: every `stockout_risk` row has inputs, `forecast_id`, `rule_config_id` | CHECK holds; recomputing from stored inputs reproduces severity |
| T-REC-01 | Recommendation | New recommendation for same product/type | Previous becomes `superseded` in the same transaction |
| T-REC-02 | Recommendation | Recommendation created from a risk | No `agent.*` row is created (recommendation is not a PO) |
| T-AGT-01 | Approval | Approve with a hash different from the proposal | FK violation |
| T-AGT-02 | Approval | `UPDATE action_proposal SET arguments = ...` | Rejected |
| T-AGT-03 | Approval | Approve after `expires_at` | Rejected |
| T-AGT-04 | Approval | Approve without scope `agent:approve` | CHECK violation |
| T-AGT-05 | Approval | Two concurrent approvals of one proposal | One succeeds; one fails (`UNIQUE` round / status CAS) |
| T-AGT-06 | Lifecycle | Every illegal transition pair (full matrix) | Rejected; every legal one succeeds |
| T-AGT-07 | Execution | Insert execution for a rejected approval | Rejected |
| T-AGT-08 | Execution | Two concurrent executions of one proposal | Second fails (`one_inflight`) |
| T-AGT-09 | Execution | Second success for a proposal | Fails (`one_success`) |
| T-AGT-10 | Execution | `unknown` failure then re-approval then retry | Same `idempotency_key`; adapter creates one PO (contract test with Yassin's mock) |
| T-AGT-11 | Execution | `definitive` failure then re-approval | Rejected; new proposal required |
| T-AGT-13 | Execution | `unknown` failure, proposal `failed`, then `failed -> approved` or a new attempt using the previous approval (no new round) | Rejected (D-43) |
| T-AGT-14 | Execution | Worker same-key retry under the same approval while still `executing` | Allowed; same `idempotency_key` (D-43 keeps it) |
| T-AGT-15 | Approval validity | Start executing, insert an attempt (first send or worker retry) or re-open a failed proposal more than 24 h after the decision; exactly 24 h | Rejected after 24 h; allowed at exactly 24 h (D-44) |
| T-AGT-16 | Roles | Worker credentials try to approve, re-approve, move `failed -> approved`, change arguments, disable triggers, `SET ROLE brain_app` | All rejected (D-45) |
| T-AGT-17 | Roles | API credentials try to write any `ingest`/`feat`/`intel` table, delete cache rows, add or switch a rule-set version, or change proposal arguments | All rejected with `permission denied` (D-51) |
| T-AGT-18 | Rule sets | Provisioner switches a rule-set version: without `app.actor_id`; leaving no active version; in one transaction; from another tenant's context; editing `params` | Refused, refused at commit, succeeds with two audit rows, 0 rows / refused, refused (D-51) |
| T-AGT-12 | Session | Create more write proposals than `max_writes` | `check_violation` |
| T-AUD-01 | Audit | UPDATE/DELETE/TRUNCATE on `audit_log`, `action_approval`; DELETE on proposal/execution | Rejected for the app role and the owner |
| T-AUD-02 | Audit completeness | Run propose, approve, execute, reject scenarios | Each produces the expected `audit_log` events, linked by one `trace_id` |
| T-AUD-03 | Audit | Answer the audit questions (who proposed, who approved or rejected, exact payload, what was executed, success or failure, which model, cost, which trace) from stored rows | Section 4.2, Q12 and Q13 |
| T-PII-01 | Privacy | Scan `audit_log.details`, `llm_usage`, `ingest_failure`, logs for customer-field names/regex | None |
| T-BKF-01 | Backfill | Drop derived data, run rebuild | `sales_fact` and features equal the pre-drop values |
| T-BKF-02 | Backfill | Interrupt and resume | Same result; no duplicates |
| T-PERF-01 | Performance | `get_features` p95 on a 5,000-SKU, 2-year dataset | < 10 ms |
| T-PERF-02 | Performance | Latest forecast + points for a product | < 20 ms |
| T-PERF-03 | Performance | Nightly full feature recompute for 5,000 SKUs | Within the agreed window |
| T-PERF-04 | Performance | `EXPLAIN` of each core query | Uses the intended index (no seq scan on large tables) |

### 4.2 Sample SQL proving the access patterns

```sql
-- Q1 FeatureStore.get_features(product_id, date)
SELECT * FROM feat.feature_daily
 WHERE tenant_id = :t AND product_id = :p AND feature_date = :d;

-- Q2 training frame (labels present only)
SELECT * FROM feat.feature_daily
 WHERE tenant_id = :t AND product_id = :p AND feature_date BETWEEN :start AND :cutoff
   AND y_status IN ('observed','zero_filled')
 ORDER BY feature_date;

-- Q3 stale feature rows (any input row changed after the row was computed)
SELECT f.product_id, f.feature_date
  FROM feat.feature_daily f
  JOIN ingest.sales_fact s
    ON s.tenant_id = f.tenant_id AND s.product_id = f.product_id
   AND s.sales_date BETWEEN f.feature_date - 28 AND f.feature_date - 1
 WHERE f.tenant_id = :t AND s.updated_at > COALESCE(f.inputs_max_updated_at, '-infinity')
 GROUP BY f.product_id, f.feature_date;

-- Q4 latest forecast from a currently eligible model, and its points
SELECT f.* FROM intel.forecast f
  JOIN intel.model_registry m ON m.tenant_id = f.tenant_id AND m.id = f.model_id
 WHERE f.tenant_id = :t AND f.product_id = :p AND m.status = 'validated'
 ORDER BY f.generated_at DESC LIMIT 1;

SELECT target_date, predicted_demand, confidence_low, confidence_high
  FROM intel.forecast_point WHERE forecast_id = :fid ORDER BY target_date;

-- Q5 demand over the supplier lead time (lead time rounded up to whole days by the caller)
SELECT SUM(predicted_demand) AS demand_over_lead, SUM(confidence_high) AS demand_over_lead_upper
  FROM (SELECT * FROM intel.forecast_point WHERE forecast_id = :fid ORDER BY target_date LIMIT :lead_days) p;

-- Q6 accuracy by lead time (WAPE), counting only verified-complete days
SELECT (fp.target_date - f.origin_date) AS lead_days,
       SUM(ABS(fp.predicted_demand - COALESCE(s.units_sold, 0))) / NULLIF(SUM(COALESCE(s.units_sold, 0)), 0) AS wape
  FROM intel.forecast f
  JOIN intel.forecast_point fp ON fp.tenant_id = f.tenant_id AND fp.forecast_id = f.id
  JOIN ingest.sales_day_coverage c ON c.tenant_id = f.tenant_id AND c.business_date = fp.target_date AND c.status = 'complete'
  LEFT JOIN ingest.sales_fact s ON s.tenant_id = f.tenant_id AND s.product_id = f.product_id AND s.sales_date = fp.target_date
 WHERE f.tenant_id = :t AND f.model_id = :m AND fp.target_date BETWEEN :a AND :b
 GROUP BY 1 ORDER BY 1;

-- Q7 current high-severity insights (use one query per severity; lists are small)
SELECT * FROM intel.v_insight_current
 WHERE tenant_id = :t AND severity = 'high'
 ORDER BY calculated_at DESC, insight_id LIMIT 50;

-- Q8 open anomaly signals, newest first, keyset pagination
SELECT * FROM intel.anomaly_event
 WHERE tenant_id = :t AND status = 'open' AND severity = :sev
   AND (last_detected_at, id) < (:last_ts, :last_id)
 ORDER BY last_detected_at DESC, id DESC LIMIT 50;

-- Q9 anomaly upsert (re-detection never creates a duplicate and keeps the review state)
INSERT INTO intel.anomaly_event AS a (tenant_id, product_id, observation_date, anomaly_type, detection_method,
       expected_value, observed_value, score, severity, reasons, rule_version, rule_config_id)
VALUES (:t, :p, :d, :type, :method, :exp, :obs, :score, :sev, :reasons, :rv, :rcid)
ON CONFLICT (tenant_id, product_id, observation_date, anomaly_type, detection_method) DO UPDATE SET
  expected_value = EXCLUDED.expected_value, observed_value = EXCLUDED.observed_value, score = EXCLUDED.score,
  severity = EXCLUDED.severity, reasons = EXCLUDED.reasons, rule_version = EXCLUDED.rule_version,
  rule_config_id = EXCLUDED.rule_config_id, last_detected_at = now(),
  detection_count = a.detection_count + 1, row_version = a.row_version + 1;

-- Q10 pending approvals for the ApprovalModal
SELECT id, tool_name, arguments, reason, expires_at
  FROM agent.action_proposal
 WHERE tenant_id = :t AND status = 'pending' AND expires_at > now()
 ORDER BY created_at DESC LIMIT 20;

-- Q11 approval transaction (application supplies :v read earlier)
BEGIN;
SELECT status, arguments_sha256 FROM agent.action_proposal WHERE tenant_id = :t AND id = :pid FOR UPDATE;
INSERT INTO agent.action_approval (tenant_id, proposal_id, approval_round, decision, decided_by_actor_id,
       decider_scopes, arguments_sha256, trace_id)
VALUES (:t, :pid, 1, 'approved', :actor, :scopes, :hash_the_user_saw, :trace);
UPDATE agent.action_proposal SET status = 'approved', row_version = row_version + 1
 WHERE tenant_id = :t AND id = :pid AND status = 'pending' AND row_version = :v;   -- 0 rows => conflict, ROLLBACK
INSERT INTO audit.audit_log (tenant_id, event_type, outcome, actor_type, actor_id, approved_by_actor_id, tool_name,
       subject_type, subject_id, arguments_sha256, details, trace_id)
VALUES (:t, 'proposal.approved', 'success', 'user', :actor, :actor, :tool, 'action_proposal', :pid, :hash,
        '{"status_from":"pending","status_to":"approved"}', :trace);
COMMIT;

-- Q12 the five audit questions for one proposal
SELECT p.requested_by_actor_id AS proposed_for, p.proposed_by,
       a.decided_by_actor_id AS approved_or_rejected_by, a.decision, a.decided_at,
       p.arguments AS exact_payload, a.arguments_sha256 AS approved_hash,
       e.attempt_no, e.status AS execution_status, e.outcome_certainty, e.external_ref_type, e.external_ref_id,
       u.provider, u.model, u.prompt_version, u.estimated_cost_usd,
       p.trace_id
  FROM agent.action_proposal p
  LEFT JOIN agent.action_approval  a ON a.tenant_id = p.tenant_id AND a.proposal_id = p.id
  LEFT JOIN agent.action_execution e ON e.tenant_id = p.tenant_id AND e.proposal_id = p.id
  LEFT JOIN audit.llm_usage        u ON u.tenant_id = p.tenant_id AND u.id = p.llm_usage_id
 WHERE p.tenant_id = :t AND p.id = :pid
 ORDER BY a.approval_round, e.attempt_no;

-- Q13 everything that happened under one trace, and what it cost
SELECT seq, occurred_at, event_type, outcome, actor_type, actor_id, tool_name
  FROM audit.audit_log WHERE trace_id = :trace ORDER BY seq;
SELECT SUM(estimated_cost_usd) AS cost_usd, SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out
  FROM audit.llm_usage WHERE trace_id = :trace;

-- Q14 audit by actor, keyset pagination
SELECT seq, occurred_at, event_type, outcome, subject_type, subject_id
  FROM audit.audit_log
 WHERE tenant_id = :t AND actor_id = :actor AND (occurred_at, seq) < (:last_ts, :last_seq)
 ORDER BY occurred_at DESC, seq DESC LIMIT 50;

-- Q15 token cost per day and purpose (the /brain/admin/cost view)
SELECT date_trunc('day', occurred_at) AS day, purpose, model,
       SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, SUM(estimated_cost_usd) AS cost_usd,
       AVG(latency_ms) AS avg_latency_ms, COUNT(*) FILTER (WHERE cache_status = 'hit') AS cache_hits
  FROM audit.llm_usage WHERE tenant_id = :t AND occurred_at >= now() - interval '30 days'
 GROUP BY 1, 2, 3 ORDER BY 1 DESC;

-- Q16 retention purge (run as brain_retention, in batches)
DELETE FROM intel.forecast_point
 WHERE ctid IN (SELECT ctid FROM intel.forecast_point WHERE target_date < current_date - 400 LIMIT 10000);
```

Expected behaviours that must be tested rather than assumed: `UPDATE agent.action_proposal SET arguments = '{}'::jsonb ...` raises `check_violation`; `UPDATE audit.audit_log ...` raises `insufficient_privilege`; inserting a fourth write proposal into a session with `max_writes = 3` raises `check_violation`.

### 4.3 Definition of Done for the database work

1. `alembic upgrade head` from empty succeeds in CI and on a staging copy; `alembic check` is clean; downgrade is guarded.
2. All tests in 4.1 pass in CI against PostgreSQL; none are skipped.
3. Every table has its constraints, indexes, comments and triggers exactly as in Part 2; `alembic check` is clean, and if the team keeps the generator (OD-24) the generated DDL, models, column tables and ERDs show no diff in CI.
4. The five audit questions (4.2 Q12/Q13) return correct answers on a seeded end-to-end scenario (propose, approve, execute, fail-unknown, re-approve).
5. The poller passes the failure matrix (1.4) against the mock Canonical server with fault injection (timeouts, 5xx, repeated and out-of-order pages).
6. The 200-SKU seed and a 5,000-SKU synthetic load meet the PERF targets.
7. Role grants verified: `brain_app` cannot DDL, TRUNCATE, or modify audit rows; `brain_readonly` cannot write; `brain_worker` cannot record or change a decision, re-open a failed proposal, disable triggers or assume `brain_app`; `brain_app` cannot write any pipeline table or rule set; `brain_provisioner` may switch rule-set versions only with an audited operator id (`verification/role_security_checks.py`, `verification/tenancy_rls_checks.py`, D-45, D-51).
8. Backup and restore drill performed for the `agent`/`audit` tier and for `intel` + models volume.
9. A rebuild of derived data from Canonical reproduces `sales_fact` and `feature_daily`.
10. Open decisions OD-01, OD-02, OD-03, OD-04, OD-06 are closed and reflected in the schema; the rest are recorded as ADRs.
11. The feature-table contract and the proposal/approval schema are merged under `/contracts` with both owners' approval (G§15.2), and Pydantic types are regenerated from them.
12. No PII found by the privacy scan (T-PII-01).
