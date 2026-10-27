# Questions to approve the final ERD and database (21 Oct 2026)

**For:** Ibrahim.
**Status (21 Oct, evening):** Q-01 to Q-14 are **answered** and recorded as decisions D-29 to D-42 in `DECISIONS_2026-10-21_ERD.md` (your answers differ from my recommendations on Q-03, Q-10 and Q-11; the table below shows what you decided). They are applied in the generator and regenerated; evidence in `IMPACT_2026-10-21_ERD_DECISIONS.md`. The [A-xx] tags are retired. **Open now: §D, N-03, N-04, N-06, N-07, N-08 and the new N-09 to N-11.** N-01, N-02 and N-05 were answered on 21 Oct (evening) and are decisions D-46, D-47 and D-48.

| Q | Your answer | Decision |
|---|---|---|
| Q-01 | Yes; agent proposals must have session and requester | D-29 |
| Q-02 | Yes; must work under concurrency and retries, complements ERP idempotency | D-30 |
| Q-03 | Yes, but per-product **selection**, not per-SKU training; shared LightGBM, product-specific only if better; registry shows scope | D-31 |
| Q-04 | Yes | D-32 |
| Q-05 | Yes; local artifacts only, SHA-256, never pickle/joblib | D-33 |
| Q-06 | Yes; keep raw values, flag returns > sales, train on validated days only | D-35 |
| Q-07 | Yes, no revenue | D-36 |
| Q-08 | Yes; integrate with ERP Identity (Ahmed Salah); exact scope per endpoint; `brain:admin` grants no job execution | D-37 |
| Q-09 | Yes; CLI only, no UI button, no job API | D-38 |
| Q-10 | **D-02 stays with you; no reassignment to Abdelrahman without your agreement** | D-39 |
| Q-11 | **No. Multi-tenancy is core, not deferred.** RLS is a separate decision (N-02) | D-34 |
| Q-12 | Yes | D-40 |
| Q-13 | Yes; label results synthetic | D-41 |
| Q-14 | You fix it, guided step by step | D-42, BB-05G |

The original questions are kept below for the record.

## A. Changes to the database (need your yes before BB-05)

| Q | Question | Recommended | Why it matters |
|---|---|---|---|
| Q-01 | `agent.action_proposal` only allows `proposed_by='agent'` and needs a `session_id` and a requesting user. D-18 says proposals are built by rules, without the LLM or a chat. Allow `proposed_by IN ('rules','agent')` and make `session_id` and `requested_by_actor_id` nullable when `proposed_by='rules'`? | **Yes** | Without it, the deterministic approval flow (the core of the demo) cannot insert a proposal. **[A-01]** |
| Q-02 | Add a partial unique index: one live proposal (`pending`, `approved`, `executing`) per recommendation? | **Yes** | Stops a double-click from creating two proposals for the same order. **[A-08]** |
| Q-03 | D-20 says one global LightGBM, but `model_registry` picks models per product. Store one registry row per product per model family (with that product's backtest WAPE), all LightGBM rows pointing at the same artifact file? | **Yes** (no schema change) | Keeps per-product winner selection and `forecast.model_id` working without new tables. **[A-05]** |
| Q-04 | Remove `holt_winters` from the `forecast` rule_config seed candidates (BLUEPRINT Q9)? | **Yes** | D-20 names only seasonal-naive and LightGBM. **[A-07]** |
| Q-05 | Narrow `model_registry.artifact_format` to `lightgbm_txt` and `json` (drop `pickle`, `joblib`)? | **Yes** | OD-13 forbids loading pickle; the DB should not even allow it. **[A-04]** |
| Q-06 | A day where returns exceed sales counts as zero demand (`GREATEST(net_units, 0)`), not negative (BLUEPRINT Q6)? | **Yes** | Already how `feature_daily.y_units` is defined. **[A-06]** |
| Q-07 | No revenue in the MVP: `sales_fact` stays without money columns (BLUEPRINT Q7)? | **Yes, no revenue** | Adding it needs a contract change from Yasin first. |

## B. Behaviour and scope (needed by the team, not by the schema)

| Q | Question | Recommended | Why it matters |
|---|---|---|---|
| Q-08 | Add two JWT scopes, `brain:read` (all Brain reads) and `brain:admin` (job status), next to the existing `agent:approve`? | **Yes**, ask Ahmed Salah | brain-api needs to know who may read and who may see admin data. **[A-03]** |
| Q-09 | Is "run now" for the demo OK as a worker command (`brain-worker run end_of_day`), with no button in the UI? | **Yes, command only** | A UI button needs a request table or a new checkpoint status (one more DB change). **[A-09]** |
| Q-10 | Who builds ingestion? `spec_ingest.py` names Abdelrahman; D-02 gives ingestion, features, recommendations and read APIs to you. Is Abdelrahman (or anyone else) available? | **D-02 stays**, but hand BB-14 and BB-15 to a second person if one exists | Your lane is about 23 person-days, twice anyone else's, during midterms. |
| Q-11 | No PostgreSQL row-level security in the MVP: tenant isolation is enforced in code (every query filters `tenant_id`) and documented as post-MVP? | **Yes** | D-16 makes no multi-tenant claim; RLS adds setup and test cost now. **[A-11]** |
| Q-12 | Intraday anomaly checks only spikes; drops are checked only on closed days (BLUEPRINT Q12, Fatma's call)? | **Yes** | A partial day always looks like a drop. **[A-12]** |
| Q-13 | Development and demo data: a synthetic pharmacy dataset (task BB-04) instead of a public dataset such as Favorita? | **Synthetic** | It matches the Canonical contract exactly, can include the Amoxicillin story, Ramadan and gap days, and has no licence questions. **[A-14]** |
| Q-14 | The PL/pgSQL bug in `guard_proposal_transition` (BLUEPRINT Q10): do you want to fix it yourself in BB-05 as planned (learning log), or should I fix it now? | **You fix it in BB-05** | It is a one-line fix and a good first migration exercise. |

## C. For Yasin (send with D-24/D-25, not blocking the ERD)

BLUEPRINT §11 Q3 (`updated_at` at commit time + index), Q4 (when a day is closed), Q5 (`GET /canonical/inventory?updated_since=` as a 1.1 addition), Q11 (adapter serves `updated_since`, outbox not needed by the Brain).

## D. New questions raised while applying your decisions (open)

The team can build everything else now; only the lines tagged **[pending N-xx]** in the contracts and tasks wait for these.

| N | Question | Recommended | Why it matters |
|---|---|---|---|
| N-01 **[answered → D-46]** | How does brain-worker know which tenants exist, and which credentials does it use to call the ERP for each? | A configured tenant list (from the provisioning step in N-08), and one **service token per tenant** issued by ERP Identity, with only the read and draft-PO permissions. Ask Ahmed Salah | D-34 says every job and ERP request is tenant scoped; today the env has one ERP token |
| N-02 **[answered → D-47]** | Add PostgreSQL **row-level security** to `brain_db` in the MVP? | **Yes**, copying the ERP's own pattern: `FORCE ROW LEVEL SECURITY` on tenant tables, policy `tenant_id = current_setting('app.tenant_id', true)::uuid`, set transaction-locally per unit of work, app role is not the table owner, missing setting matches nothing. Risks: about 1 to 2 days of work, a forgotten `SET` shows "no rows" (caught by tests), migrations run as owner. Compensating controls either way: composite FKs, no default tenant, the BB-24 suite | You asked not to treat app filtering as enough without proof. RLS is a second, independent wall; BB-24 is the proof for both |
| N-03 | Days where returns exceed sales (`net_units < 0`): how to flag and use them? | Keep the raw row; in `feature_daily` set `y_units = 0` and `is_outlier = true`; exclude these days from training loss and evaluation; count them in pipeline status | D-35 says "flag", but the schema has no dedicated flag yet; `is_outlier` exists and avoids a schema change |
| N-04 | Which scope may **create** a proposal (`POST /recommendations/{id}/proposal`)? | `agent:approve` | Creating starts the write path; `brain:read` users should only look |
| N-05 **[answered → D-48]** | The ERP tenant is the organization, which has branches with their own databases. Is the Brain's MVP grain the whole organization (branches summed) or per branch? | Organization level for the MVP: sales and stock summed over branches, as OD-20 assumed. Confirm with Yasin and Ahmed Salah | Changes the Canonical API, the forecasts and the risk numbers |
| N-06 | Where does the Brain run? | Next to the cloud ERP, one Brain serving all tenants; the demo still runs on one machine. This amends D-17 (single pharmacy machine) | D-17 predates multi-tenancy (D-34) |
| N-07 | `risk_assessment` requires inventory, lead time and days of cover for every `stockout_risk` row, but the insight contract lists reasons like `INVENTORY_UNAVAILABLE` (C-11). What happens when an input is missing? | Keep the DB strict: write **no** risk row, count the product in `products_not_assessable` with the reason, and show it in pipeline status | Otherwise either the DB check or the contract must change |
| N-08 | How is a new tenant added? | A `brain-worker provision-tenant <organization_id>` command that copies the default `rule_config` rows and creates the model folder; move today's dev-tenant seed out of migration `0005` into a dev-only seed | With no default tenant (D-34), a tenant without `rule_config` cannot run any job |
| N-09 **[answered → D-49]** | How is organization stock represented when the organization has branches? | Ibrahim chose **Option B**: a separate `OrganizationInventory` with no `location_id`, completeness and location count checked against the location register; `InventoryItem.location_id` required and non-null. **Option D** is the fallback: if the ERP cannot supply trustworthy organization totals, inventory-dependent recommendations are blocked for the MVP | A null `location_id` never means organization stock. Canonical contract unsigned until the ERP owners approve |
| N-10 | ERP behaviour for branches (Yasin): sales totals over branches, day close, organization inventory guarantees, location register, draft-PO destination | Questions in §E below; nothing is assumed | Wrong answers give wrong totals, wrong stock or a PO at the wrong branch. Until answered: Option D and `BRANCH_DECISION_REQUIRED` |
| N-11 | Shape of the per-tenant Canonical credential (D-46), Ahmed Salah (EXT-S1) | Questions in §F below; nothing is assumed | Changes `CredentialProvider` and the provisioning validation step, not the registry |

## E. N-10: questions for Yasin (ERP adapter, branches)

Sales totals
1. Is `DailySalesTotal` for a tenant the sum over **all** locations of the organization? Exactly which locations are included: active branches, closed or deactivated branches, central warehouse, online channel?
2. Is the total computed from the central database after branch sync, or live across branch databases at request time?
3. What is the maximum time a branch can lag behind central (normal case, and a branch offline for a day)?
4. When a late branch's sales reach central, does the organization row's `updated_at` move to that commit time, so a poll with `updated_since` sees the change? Is `updated_at` set at commit time (BLUEPRINT §11 Q3)?
5. Do all branches of one organization use the same timezone for `business_date`? If not, whose date wins?
6. When is an organization day `closed`: when every branch has closed it, or at a fixed time? If one branch never closes or never syncs that day, is the organization total sent with `complete = false`?
7. A return at branch X of a sale made at branch Y on another day: which branch and which `business_date` does it count against?
8. Are product ids the same across all branches (one organization-wide catalog)?

Organization inventory (D-49; if the answer to 9 is no, Option D stays for the MVP)
9. Can the adapter serve `GET /inventory/{product_id}` as `OrganizationInventory` exactly as `organization_inventory.schema.json` describes: ERP-computed sums over included locations, **every** location of the organization listed with its status, a per-location `stock_as_of`, and `complete = false` whenever an active location's stock is not current?
10. How does the ERP know a branch's stock is current? Is there a per-branch last-sync time it can put in `stock_as_of`, and what lag should count as unavailable?
11. Can an inactive location still hold stock? Should its stock be excluded from the organization total (the schema assumes yes)?
12. Per location, is `available = on_hand - reserved` exactly, or is it clipped at 0 when reservations exceed stock? Can `on_hand` be negative after an unsynced sale?
13. Does stock include goods in transit between branches (the schema assumes no)? Is `reserved` for customers only, or also for inter-branch transfers?
14. Can the adapter serve `GET /locations` (every location with `active` / `inactive`)? Are `location_id` values stable UUIDs that are never reused? Is a central warehouse a location?

Purchasing
15. Are purchase orders created per branch, centrally, or both? Does `GET /purchase-orders?status=open` return open POs for every branch of the organization?
16. Which location receives a Brain draft PO? Is there a central purchasing location? Must `create_draft_po_request` carry a `delivery_location_id`, and would the ERP reject a draft without one?
17. For an organization with exactly one active location, may the draft PO go to that location implicitly, as the contract currently assumes?
18. Are `preferred_supplier_id`, supplier lead time and pack size organization-wide or per branch?

Tenancy
19. Is the tenant in the service token always the organization, never a branch? Which status code does the adapter return for a token of another organization?

## F. N-11: questions for Ahmed Salah (ERP Identity, per-tenant credential)

1. Can ERP Identity issue a **machine** credential (not tied to a person) per organization for the Brain?
2. In what form: OAuth2 client credentials (client id + secret exchanged for a short-lived access token) or a long-lived bearer token? Which do you recommend for the ERP?
3. What claims will the resulting token carry? Specifically `tenant_id` (= organization id), the `sub` format for a service, and the `scopes` claim format (array or space-separated string)?
4. What are the exact scope names for the Canonical reads (products, inventory, locations, suppliers, sales, purchase orders), and can the credential be limited to those plus `canonical:po:create_draft` and nothing else?
5. What are the lifetimes: access token, client secret or long-lived token? Is there refresh?
6. **Rotation:** can two secrets be valid at the same time during rotation, and for how long? Who triggers the rotation?
7. **Revocation:** how is a compromised credential revoked, and how fast does the adapter start rejecting it?
8. **Delivery:** how does the secret reach the Brain operator without email or chat (e.g. shown once in an admin screen, or written to a secret store)? Who in the ERP may issue one?
9. Is there a cheap endpoint (introspection or "whoami") the provisioning step can call to confirm the credential's organization? If not, which read endpoint should validation use?
10. For a wrong organization, an expired token and a missing scope, which status codes does the adapter return (401 vs 403)? Provisioning must tell these apart.
11. Can a **user** JWT ever carry a branch id instead of the organization id in `tenant_id` (for example, a user who belongs to one branch)? That would break D-34 and D-48.
12. Is the draft PO recorded in the ERP under the service identity, with the human approver taken from the `approval` block (D-11)? Or does Identity expect something else?
