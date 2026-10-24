# Impact analysis and verification: ERD decisions of 21 Oct 2026

**Scope:** applying D-27 to D-42 (`DECISIONS_2026-10-21_ERD.md`). Labels: **Done** = changed in the files. **Passed / Failed** = a check that was run. **Not run** = not executed, with the reason. **Pending** = waits for a new decision (N-xx).

## 1. Affected items and what happened

| Item | Decisions | Change | Status |
|---|---|---|---|
| `brain_db/tools/schema_gen/spec_lib.py` | D-34 | `tenant_id` has no default; tenancy text updated | Done |
| `spec_agent.py` | D-29, D-30, D-39, C-5 | `proposed_by IN ('rules','agent')` with no default; `session_id`, `requested_by_actor_id` nullable + CHECK for agent; partial unique index `uq_action_proposal__live_per_recommendation`; JCS wording for `arguments_sha256`; owner text | Done. **Trigger bug left untouched (D-42)** |
| `spec_intel.py` | D-28, D-31, D-32, D-33 | `scope`, `shared_model_id` (+ composite self FK, CHECKs, index); `holt_winters` removed from families; `artifact_format` narrowed; example rewritten so it does not imply per-SKU training | Done |
| `spec_ingest.py` | D-39 | 5 owner texts Abdelrahman → Ibrahim | Done |
| `gen_core.py` | D-32 | `forecast` seed candidates `["seasonal_naive","lightgbm"]` | Done |
| `tpl/01.md`, `tpl/04.md` | D-39 | owners; banner in the backlog section | Done |
| Regenerated: `ddl/0002`–`0006`, `brain_db_mvp.sql`, `optional_future_rag.sql`, `models.py`, `erd/*.mmd` (3), `docs/01`, `02`, `04` | all | `build_all.py`: 24 + 1 tables, 419 columns, 27 FKs, 191 CHECKs, 35 uniques, 42 indexes, 37 triggers, 3 views | Done |
| `python/brain/db/contracts_jsonb.py` (hand-written) | D-32 | `ForecastRuleParams.candidates` default without `holt_winters` | Done. C-1 (hash) still open → BB-17 |
| `contracts/openapi/brain.openapi.yaml` | D-37, D-38, D-34 | exact scope on every operation; run-now note; tenant rule | Done |
| `contracts/internal/brain_ports.py` | D-31, D-34, D-35, D-40 | tenancy docs, `ModelScope`, `returns_exceed_sales`, anomaly mode text | Done |
| `contracts/internal/BRAIN_CONTRACTS.md` | all | §4 scopes, §7 tenancy rewritten (core, not deferred), §8 registry, §13 conflicts, §14 decisions | Done |
| `contracts/internal/brain.env.example` | D-34 | multi-tenant settings marked pending N-01 | Done |
| `docs/BLUEPRINT_FINAL.md` | all | §6 tenancy, §10 register (D-29…D-42), §11 resolved items | Done |
| `docs/decisions/DECISIONS_v1.md`, `brain_db/docs/MVP_DECISIONS_AND_CONTRACTS.md` | D-34 | banners: D-16 superseded, OD-23 amended | Done |
| `docs/TEAM_TASKS.md` | all | ownership; BB-05 and new BB-05G (guided fix); new BB-24 (cross-tenant isolation); tenancy tests in every task; synthetic labels; milestones with the vertical slice first | Done |
| `Answers/01_how_the_brain_works.md` | D-34 | tenant section rewritten | Done |
| `Answers/02_guided_fix_guard_proposal_transition.md` | D-42 | walkthrough, no solution | Done |
| `Pharmacy-ERP-Brain/infrastructure/docker-compose.yml` | D-27 | still has a `redis` service | **Not changed** (ERP repo is out of scope for this thread): task BB-22 (Ali) |
| ERP outbox (`OutboxEvent`, `IOutboxService`) | D-27 | checked read-only: registered in ERP DI and used by the ERP blueprint for branch sync | **Kept** (other purposes) |
| `contracts/schemas/events/*` | D-08, D-27 | unchanged, post-MVP | Kept |

## 2. Verification on PostgreSQL 16.15 (scratch cluster in the cloud workspace)

| Check | Result |
|---|---|
| Generator validation (`build_all.py`) | **Passed** |
| Generated `brain_db_mvp.sql` loads as is | **Failed, expected:** `syntax error` at `guard_proposal_transition` (the D-42 bug, unchanged on purpose) |
| Same DDL with the one-line fix applied **in a scratch copy only** | **Passed** (25 tables; 0 `tenant_id` columns with a default) |
| Six migration files in order (scratch fix in 0004 only) | **Passed** |
| `alembic upgrade head` (scratch fix) | **Passed** |
| `alembic check` | **Failed:** 888 differences, **all comment-only** (`modify_comment` 838, `remove_table_comment` 50) because `models.py` carries no comments while the DDL does. No table, column, type, index or constraint differences. Existed before today; fix in BB-05 |
| Decision checks (`brain_db/verification/decision_checks_2026-10-21.py`), 20 cases | **Passed 20/20**: rules proposal without session inserts; agent proposal without session rejected; unknown `proposed_by` rejected; second live proposal rejected; new proposal allowed after the first is rejected; `pending → succeeded` rejected by the trigger; insert without `tenant_id` fails; `weekly_full` rejected; shared and product registry rows; product row cannot carry both a shared reference and its own artifact; shared row with a product rejected; **tenant 2 cannot reference tenant 1's shared artifact**; pickle, joblib and `holt_winters` rejected; seed candidates correct; negative `net_units` preserved |
| Concurrency: two simultaneous rule proposals for one recommendation | **Passed**: one commits, the other gets `uq_action_proposal__live_per_recommendation`; one live proposal remains |
| Contracts validator (schemas, 53 fixtures, hash vectors, OpenAPI), `mypy --strict brain_ports.py` | **Passed** (re-run after the edits) |
| PostgreSQL RLS | **Not run**: pending decision N-02 |
| Cross-tenant tests for API, worker, cache, forecast, agent paths | **Not run**: no Brain code yet; specified in BB-24 |
| Anything on the user's machine (Docker, alembic) | **Not run**: no Docker on the device session; done in the cloud scratch cluster instead |

## 3. Contradictions found (need a decision or a task)

| ID | Contradiction | Proposed handling |
|---|---|---|
| C-11 | `risk_assessment` CHECK requires `days_of_cover`, `lead_time_days`, inventory for every `stockout_risk` row, but the insight contract lists `INVENTORY_UNAVAILABLE`, `LEAD_TIME_UNKNOWN`, `FORECAST_MISSING` as reasons, and my 21 Oct contract said "write a low-confidence row" | Question N-07 |
| C-12 | `alembic check` comment drift (above) | BB-05 (generator emits comments into `models.py`, or `include_object` ignores comments; Ibrahim's choice) |
| C-13 | The ERP's tenant is the **organization** with **branches** and branch-local databases (ERP blueprint §2, §5). The Brain's grain is product × day with no branch (OD-20), and D-17 put the whole stack on one pharmacy machine | Questions N-05 and N-06 |
| C-14 | `action_proposal.tool_version` example says `create_purchase_order@1`; the contract fixes `"1.0"` | Contract wins; generator example fixed in BB-05 |
| C-1 | `contracts_jsonb.sha256_hex` ≠ RFC 8785 golden vectors | BB-17 (unchanged) |
