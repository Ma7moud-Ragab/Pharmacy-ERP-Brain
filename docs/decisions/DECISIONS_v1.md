# ERP Brain: decision record v1 (20 Oct 2026)

**Status:** recommended by mentor review. Becomes binding once you (Ibrahim) accept it and Yasin signs off on the ERP-facing rows (D-04 to D-09, D-11).
**Precedence:** this file adds to `brain_db/docs/MVP_DECISIONS_AND_CONTRACTS.md`. If they conflict, this file wins, and the conflict register reference (F-xx) comes from `docs/decisions/CROSS_DOCUMENT_CONSISTENCY_AUDIT.md`.

> **Update 21 Oct 2026:** `docs/BLUEPRINT_FINAL.md` is now the top document and adds D-23 to D-26 (no Redis Streams or ERP events in the MVP; sales are polled as daily totals by date and product; poll idempotency by absolute upsert; training only in the end-of-day run). Here, **D-08 is superseded**, and **D-04, D-06, D-17 and D-19 are amended**. The rows below are kept unchanged for history, and the final register is BLUEPRINT_FINAL §10.

> **Update 21 Oct 2026 (evening):** Ibrahim's ERD decisions D-29 to D-42 (`docs/decisions/DECISIONS_2026-10-21_ERD.md`). **D-16 (one tenant, no isolation claim) is superseded by D-34: multi-tenancy is a core requirement.** D-20 is clarified by D-31/D-32.

**Rule used for every decision:** pick the option that is simplest to build, is safe by default (fail closed), and can be demoed in a graduation timeline. Anything clever goes after the MVP.

---

## A. Scope and ownership

| ID | Decision | Why |
|---|---|---|
| D-01 | **Database = the generated `brain_db` package** (5 schemas, 25 mandatory + 1 optional table, 6 migrations). The 41-table / 12-migration / pgvector design in `AI_BRAIN_TEAM_EXECUTION_BLUEPRINT.md` is **withdrawn**. You can change the schema only through `tools/schema_gen` with a regenerate step, and only when a real problem shows up. (F-02) | You already confirmed this. It also has the strongest evidence: the generator validates it and the models match. |
| D-02 | **AI-team ownership = execution blueprint §1.4.** Ibrahim: `brain_db`, ingestion, reconciliation, features, recommendation, insights, pipeline runner, read APIs, **contracts kit owner**. Fatma: anomaly + risk. Ahmed Emad: LLM, agent, approval, audit. Mostafa: forecasting + model registry. ERP-side counterpart for all canonical/event contracts: **Yasin** (adapter + outbox). Tables follow the same split, with Ibrahim as the DDL owner and each person owning the logic for their own tables. (C-09, F-16) | You confirmed Fatma and Ahmed. Having one owner for each contract and each table removes the biggest blocker. |
| D-03 | **Insight = a read-only projection** (a view), and its `id` = the `risk_assessment` UUID. No `ins_insight` table. (F-13) | The final DB has no such table. A view cannot drift from its source. |

## B. Data contracts with the ERP (Yasin signs off)

| ID | Decision | Why |
|---|---|---|
| D-04 | **[Amended 21 Oct: no `occurred_at` check without events; see BLUEPRINT_FINAL §10]** **The ERP computes `business_date`** (tenant timezone `Africa/Cairo`) and sends it in events and in canonical sales. The Brain only *checks* that it fits `occurred_at`, give or take one day, and rejects it otherwise. (F-03) | Only one system decides which day a sale belongs to. The ERP already knows the store's day, including a sale at 23:59 that gets edited at 00:01. |
| D-05 | **Sales sync API returns daily totals**, one row per `(product_id, business_date)` with `units_sold`, `units_returned`, `net_units`, `day_status` and `updated_at`. `from`/`to` are **inclusive** business dates. `updated_since` is an **exclusive** UTC watermark. Ordering is `(updated_at, product_id, business_date)`, and the cursor is opaque. Each response carries `high_watermark` = the server time when the first page was served. The client stores it only after the last page, and the next sync re-reads with **a 120-second overlap** (`updated_since = high_watermark − 120 s`). Duplicates are harmless because rows upsert by `(product_id, business_date)` and keep the newest `updated_at`. (F-04) | This is the standard way to get no gaps even when commits arrive late. The overlap plus idempotent upsert is simpler than snapshot isolation. |
| D-06 | **[Amended 21 Oct: no `SaleCorrected` event; a correction advances the row's `updated_at` and the poll picks it up (D-25)]** **Returns, voids and edits:** the ERP emits `SaleCorrected` (with the `sale_id` and its `business_date`). The Brain **never applies negative increments**. It marks that day dirty and reloads the **absolute daily totals** from canonical sales. Demand = **net units** (sold − returned) per closed day. A day the ERP cannot total is marked `incomplete` and left out of training. (F-05, OD-09) | One correction path for every case. Totals are self-healing, while increments add up errors. |
| D-07 | **Supplier and open orders:** use `Product.preferred_supplier_id` only, with no fallback. Open POs come from a **live** canonical read at recommendation time. If either is missing or the read fails, there is no order recommendation, and reason code `NO_SUPPLIER` / `OPEN_PO_UNAVAILABLE` applies. (F-06) | Never guess when the result could double-order stock. Locally (see D-17) the live read is cheap. |
| D-08 | **[Superseded 21 Oct by D-23: no events in the MVP]** **Event envelope:** add `traceparent` (W3C string, optional) and keep `version` as `"major.minor"`. The Brain accepts the **same major** and ignores unknown fields on events (tolerant reader). It rejects a different major and sends that event to dead-letter. Dedupe key = `(tenant_id, event_id)`. Event types in v1: `SaleCreated`, `SaleCorrected`, `InventoryChanged`, `PurchaseOrderChanged`, `ProductChanged`. (F-09) | Minor additions do not break consumers. A new major is an explicit migration. |
| D-09 | **Idempotency:** `Idempotency-Key` = the proposal UUID. The adapter keeps keys **≥ 30 days**. Same key with the same body gives the original response. Same key with a different body gives `409 IDEMPOTENCY_CONFLICT`. | 30 days is longer than the 24 h TTL plus any retries. |

## C. Agent, approval and security

| ID | Decision | Why |
|---|---|---|
| D-10 | **Proposal TTL = 24 h**, session idle = 4 h, messages = 30 days. These are the MVP values. Any 4 h proposal TTL elsewhere is replaced. (F-08) | Already agreed in OD-11. A pharmacist may approve the next morning. |
| D-11 | **Approval identity:** the user approves in the browser using their own JWT, which must have the `agent:approve` scope (roles Admin, Pharmacist). The Brain then calls the adapter with a **service token** (scope `canonical:po:create_draft`) and sends an `approval` block `{proposal_id, approved_by, approved_at, arguments_sha256}`, which the adapter stores on the draft PO. No on-behalf-of token exchange in the MVP. (F-07) | The write only creates a **draft** PO, which a human still confirms inside the ERP, so the risk is bounded. OBO is real complexity with little demo value. |
| D-12 | **Self-approval:** proposals are created by the system, not by a person, so four-eyes rules do not apply. Any user with `agent:approve` can approve. (U-34) | Nobody is approving their own request. |
| D-13 | **Hash:** `arguments_sha256` = SHA-256 of the **RFC 8785 (JCS) canonical JSON** of `arguments`, lowercase hex. Golden vectors are in `contracts/fixtures/hash/`. (F-08) | Both C# and Python have JCS libraries, so the bytes are identical in both languages. |
| D-14 | **LLM privacy:** never store prompt or completion text. `LLM_LOG_PAYLOADS` is removed. Only provider, model, tokens, latency and cost are stored. (F-12) | The agreed privacy rule beats a deployment flag. |
| D-15 | **Audit hash chain:** out of MVP. (F-14) | Not in the final DB. Add it after the MVP if the examiners ask. |
| D-16 | **Tenancy:** one seeded tenant. Every row and request carries `tenant_id`. Make **no** claim of multi-tenant isolation. (F-15) | Honest and enough for the demo. |

## D. Runtime and intelligence

| ID | Decision | Why |
|---|---|---|
| D-17 | **[Amended 21 Oct: no Redis in the stack (D-23)]** **NEW: local-first, offline-capable deployment.** The whole stack (ERP, Brain, Postgres, Redis, frontend) runs on **one machine in the pharmacy via Docker Compose**. A second user uses it from a browser on the **local network** (`http://<host-LAN-IP>`, optionally `https://` with a locally generated certificate). **No feature of the ERP may need the internet.** The Brain keeps working offline for ingestion, features, forecasts, risk, recommendations and approval → draft PO. Only the **LLM assistant/explanations** need internet. When the internet is down they show "Assistant offline" and fall back to template explanations. Images are pre-pulled, there are no CDN assets, and Let's Encrypt is used only when the install has a public domain. | Your new requirement. Keeping the LLM optional means the core demo can never be killed by Wi-Fi. |
| D-18 | **Agent without the LLM:** a `create_purchase_order` proposal is built **deterministically from a recommendation** (no LLM needed). The LLM agent is an extra conversational path that produces the same proposal shape. | This makes D-17 true for the approval flow too. It is also safer, because the numbers never come from the LLM. |
| D-19 | **[Amended 21 Oct: the poll marks products dirty (D-24); training only in the end-of-day run (D-26)]** **Cadence:** events only update facts and mark products dirty. The **intelligence window** runs **hourly** for dirty products (features → anomaly → risk → recommendation). Forecast inference runs **nightly at 02:00 Cairo**, and retraining runs **weekly**. An admin "run now" endpoint exists for the demo. (F-10) | Predictable, cheap, and easy to test. Real time is not needed for reorder decisions. |
| D-20 | **Model scope:** seasonal-naive baseline + **one global LightGBM** model across products. For each product, pick whichever has the lower backtest WAPE, and use seasonal-naive as the cold-start fallback. (F-10) | A global model works with short per-product history. Per-product selection matches the MVP baseline. Mostafa owns the details. |
| D-21 | **Order formula** (rule set `rec-rules-v1`, parameters in versioned `rule_config`): `target = ceil(forecast_demand_over(lead_time + review_period) + safety_stock)`, `safety_stock = ceil(z · σ_daily · √lead_time)` with z = 1.65 by default (or 1 day of mean demand when σ is unavailable), `raw = target − available − open_po_qty`, `qty = 0 if raw ≤ 0 else roundup(raw, pack_multiple)`, then capped at `max_order_qty`. Defaults: `review_period = 0` days (orders can be placed any day), `pack_multiple = 1` when unknown. The guide's "100" was an illustration only. (F-11) | Uses open POs and pack size, so it does not over-order, and every input is stored in `calc`. |
| D-22 | **Risk severity:** `high` if days_of_cover < lead_time, `medium` if < lead_time + 2, otherwise `low`. A high anomaly on the same product raises it one level. Values live in `rule_config`. (Guide §9.2) | Already in your guide, so it's simple and explainable. |

---

## Still needs a human (not mine to decide)

1. **Yasin's sign-off** on D-04 to D-09 and D-11. These describe what the ERP must do.
2. **Supervisor (Ali?)** on audit retention before any real deployment (OD-12).
3. **Team lead confirmation** that the execution blueprint's 4-person AI split is official (D-02).
