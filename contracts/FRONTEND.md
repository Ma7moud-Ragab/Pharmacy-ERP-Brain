<!-- Owner: erp-frontend -->

# Pharmacy ERP — Frontend ↔ Backend API Contracts (v1.0)

Derived from `ERP-Backend-Blueprint-v1.1.md`. This package is the FE-side
counterpart of the backend's Phase-0 "Contracts & Mocks" deliverable.

## Package layout

| Path | Contents |
|---|---|
| `openapi.erp.yaml` | ERP Frontend/POS OpenAPI 3.0.3 — 56 paths / 79 operations, Stages 1+2+3, with `x-runtime` (`Cloud`/`BranchLocal`/`Both`) and `x-stage` (`1`/`2`/`3`) on every operation. Canonical and sync boundaries are separate contracts. |
| `schemas/*.json` | Standalone JSON Schema (draft 2020-12) DTO definitions: `common`, `auth`, `identity`, `catalog`, `inventory`, `sales`, `purchasing` |
| *generated types* | Generated client types are emitted to `apps/erp-frontend/src/types/generated` — **NOT** stored in this package (there is no `contracts/types/`) |

Validation status: OpenAPI 3.0.3 schema validation passes, every `$ref`
resolves, operationIds are unique, and protected operations carry RBAC
metadata plus 401/403 responses.

## Client type generation

Client types are generated from this package and written to
`apps/erp-frontend/src/types/generated` (never `contracts/types/`).

- **Source of truth:** `schemas/*.json` (entity/DTO shapes) + `openapi.erp.yaml`
  (endpoint paths, request/response bodies, parameters).
- **Never hand-write** a DTO type that already exists in these contracts.
- If a shape is missing or wrong, fix it in the contract and regenerate — do not
  patch the generated output.

---

## 1. What the FE talks to — and what it must never touch

### Explicitly NOT in this contract
- `GET /api/v1/canonical/*` — external Brain/AI boundary. **No FE usage.**
- `POST /api/v1/canonical/configuration/*`, `/canonical/purchase-orders/drafts`
  — server approval-gated writes. Never called from FE.
- `/api/v1/sync/operations`, `/sync/bootstrap`, `/sync/changes`,
  `/sync/operations/{id}/retry` — internal runtime↔cloud plumbing
  (branch credentials / sync-admin scope).

### Runtime split (ERP_RUNTIME_MODE)

| Feature area | Cloud | BranchLocal |
|---|---|---|
| Auth, users, employees, branch administration | ✅ | ❌ |
| Catalog/reorder reads | ✅ | ✅ |
| Catalog/reorder writes | ✅ | ❌ |
| Inventory locations/batches/balances/ledger reads | ✅ | ✅ |
| Inventory adjustments/opening balances | ❌ | ✅ |
| Sales orders / invoices / returns (Stage 2) | ❌ | ✅ (POS write path) |
| Supplier/PO reads | ✅ | ✅ |
| Supplier/PO create/approve/order, supplier payments (Stage 3) | ✅ | ❌ |
| PO receive, PO cancel-remaining | ❌ | ✅ |
| Vendor return reads | ✅ | ✅ |
| Vendor returns create/cancel/post | ❌ | ✅ |

> If the FE asks a runtime for a route it does not own, the server answers
> **404/405**. Gate the UI on the declared `runtime` from `/auth/me`.

## 2. Authentication flow

1. `POST /auth/login` with `{organization_code, username, password}`.
   Username uniqueness is **per organization**.
2. Store: `access_token`, `refresh_token`, `expires_in`, `issuer`, `audience`,
   `key_id`, plus the trusted scope (`roles`, `organization_id`,
   `branch_scope`, `branch_ids`).
3. `POST /auth/refresh` **rotates** the refresh token on every use. Submitting
   an already-consumed refresh token revokes the whole family → hard re-login.
4. `POST /auth/logout` revokes the current family.
5. `GET /auth/me` returns the authoritative `CurrentUserContext`.
6. Validate JWTs via `GET /.well-known/jwks.json` (RS256, `kid`-keyed).

**Never derive tenant/branch from any request field** — always from the token.

## 3. Standard request rules

- Base `/api/v1`; all list responses are `PagedResult<T>` with opaque
  `nextCursor` (size: `limit`, default 50 max 200).
- `traceparent` (W3C) may be attached to every call; error `trace_id` echoes it.
- `Idempotency-Key` header is REQUIRED on every mutation (16–100 chars).
  - Same key + same payload → original stored response replayed.
  - Same key + different payload → **409 IDEMPOTENCY_MISMATCH**.
- Master-data lists may pass `includeInactive=true`; historical documents
  always show deactivated references.
- Dates: wire format is UTC ISO-8601 (`...Z`). Business dates (hired_on,
  expected_on, received_on, expiry) are organization-timezone strings.

## 4. Error contract (all errors, one envelope)

```json
{
  "error": {
    "code": "OUT_OF_STOCK",
    "message": "The requested quantity is not currently available.",
    "details": [{ "field": "lines[0].quantity", "issue": "available quantity is 3" }],
    "trace_id": "00-4bf9...-01"
  }
}
```

| Code | HTTP | FE handling hint |
|---|---|---|
| MALFORMED_REQUEST | 400 | bug in request building |
| UNAUTHORIZED | 401 | refresh → retry → re-login |
| FORBIDDEN / FORBIDDEN_BRANCH | 403 | hide/redirect UI; branch picker issue |
| NOT_FOUND | 404 | stale local data; refresh list |
| CONFLICT / INVALID_STATE_TRANSITION | 409 | re-fetch state, surface message |
| GONE | 410 | enrollment token expired/consumed; restart enrollment |
| OUT_OF_STOCK | 409 | show per-line shortages from `details` |
| IDEMPOTENCY_MISMATCH | 409 | regenerate key for new payload |
| VALIDATION_ERROR | 422 | map `details[].field` to form fields |
| EXPIRY_POLICY_VIOLATION | 422 | receiving: lot rejected by shelf-life |
| INTERNAL_ERROR | 500 | keep idempotency key, retry safely |

## 5. Numeric serialization (do not break this)

- Money, quantities, costs, tax rates, conversion factors are **strings**
  (`Money` = 2dp, `Numeric4` = 4dp, `Numeric6` = 6dp, `TaxRate` = 4dp fractional).
- Use a decimal library for display; never float-arithmetic totals on FE.
- **Server authority:** prices, taxes, discounts(0), totals, change due,
  availability, FEFO allocation, state transitions. FE-sent totals are ignored.

## 6. Authorization matrix (hide UI by role)

| Capability | Admin | Pharmacist | Cashier |
|---|---|---|---|
| Org/branch/user administration | ✅ (ALL if `branch_scope=ALL`) | ❌ | ❌ |
| Catalog + UOM + reorder config | ✅ | ✅ | read only |
| Inventory balance/ledger reads | ✅ | ✅ | POS-eligible stock read |
| Inventory adjustments / opening balance | ✅ | ✅ | ❌ |
| POS orders/checkout | read | read | create/complete/cancel own-branch drafts |
| Sales return | approval policy | approval policy | receive only (cannot self-approve) |
| Suppliers / POs / receiving / payments / vendor returns | ✅ | ✅ | ❌ |
| Sync conflict retry (`sync:retry`) | ✅ w/ reason | ❌ | ❌ |

`branch_scope=ASSIGNED` users operate only within `branch_ids[]`.

## 7. Stage gating (cumulative)

| Stage | Ships |
|---|---|
| 1 | Auth, org/branch/user/employee, catalog (+UOM, reorder), inventory locations/batches/balances/ledger/adjustments |
| 2 | POS orders → complete (invoice+cash+stock issue), returns/refunds |
| 3 | Suppliers, POs (one-step partial receiving), supplier payments, vendor returns |

Do not build Stage N UI against Stage N−1 data assumptions; cumulative
contract above is the whole surface.

## 8. Critical FE do-not list (from §8.8 + §8.9)

1. No direct canonical writes; AI recommendations are NOT transactions.
2. POS checkout → branch-local API only.
3. No selecting batch/location on returns — server derives all.
4. No client-side discount/tax edits (send nothing; server sets snapshots).
5. No hard deletes anywhere — deactivation via `is_active:false` PATCH.
6. Refunds/returns never edit posted invoices — new transactions only.
7. Never put `organization_id` in FE requests as an authority.

## 9. Out-of-MVP features (do not design)

Customer entity / e-commerce / delivery / reservations; partial or credit POS
payments; multi-terminal POS; cashier shifts & cash-drawer reconciliation;
promotions/branch price lists; supplier invoice matching; supplier credits from
vendor returns; inter-branch transfer; accounting/GL; subscription billing.
