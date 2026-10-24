# BB-24 cross-tenant isolation suite (D-34, D-46, D-47)

Status on 21 Oct 2026: **partial**. Only the parts that can be proven without application code are here. brain-api,
brain-worker, the repositories and the Canonical adapter do not exist yet, so the application halves cannot be tested
and are listed below with what they wait for. BB-24 stays open until all eight groups run in CI.

Fixture (`conftest.py`, `world`): tenants A and B hold the same product, the same dates, the same model version, the
same cache key and the same recommendation type, so a query that forgets `tenant_id` finds a plausible wrong row
rather than nothing. Every row is written through `brain/db/session.py` by the login that owns that write (worker for
the pipeline, app for proposals). `harness.snapshot(B)` gives a row count and an md5 of all rows of every tenant table in B's context, so "B unchanged" assertions catch changed values as well as added or removed rows.
Setup and environment: `tests/integration/README.md` (no superuser anywhere).

| Group | Here now | Waits for |
|---|---|---|
| 1 API: A's token on B's ids -> 404, lists only A's rows | nothing | brain-api routers and JWT auth (BB-15, BB-16) |
| 2 Lint: repository SQL without `tenant_id` | nothing (no repository code to scan) | repositories (BB-06 onwards) |
| 3 Worker: run each job for A, B's snapshot unchanged | `harness.snapshot()` only | jobs runner and jobs (BB-07 to BB-10a) |
| 4 Cache keyed by tenant | `test_g4_cache.py`: same key, own payload; A's upsert leaves B unchanged; A cannot write B's key | the cache reader (BB-07) |
| 5 Forecasts and artifacts | `test_g5_forecast_models.py`: forecasts join only own models; four composite FKs refuse cross-tenant references; absolute and `..` artifact paths refused | artifact store refusing paths outside `models/{tenant_id}/` (BB-12) |
| 6 Agent action | `test_g6_agent_refs.py`: A's proposal, decision or execution cannot reach B's recommendation or proposal (the execution case is differential: the same row is accepted in its own tenant); B's proposal invisible and unchangeable from A | ERP write with A's credential (BB-17, BB-18, BB-25) |
| 7 Pooled connections through session.py | `test_g7_pooled_connections.py`: complete for the database layer | nothing |
| 8 RLS through the application | startup login check (`tests/integration/test_session.py`) | brain-api and brain-worker with the repository filter removed (BB-15, BB-16, BB-18) |

Acceptance still open: "a deliberately removed `tenant_id` filter makes the suite fail" needs repository code. The
database-level equivalent was shown once by hand: with RLS switched off on `ingest.canonical_cache`, group 4's read
test fails.
