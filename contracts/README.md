# Pharmacy ERP — Monorepo Contracts Repository

The single shared source of truth for API contracts, schemas, and test fixtures across the three monorepo services:
- **`erp-frontend`** (POS & Back-office Web Clients)
- **`erp-backend`** (.NET Modular Monolith ERP System of Record)
- **`brain`** (AI Analytics, Forecasting & Recommendation Engine)

---

## Directory Index & Ownership

| Path | Owner | Description | Status |
|---|---|---|---|
| `openapi.erp.yaml` | `erp-frontend` | OpenAPI 3.0.3 contract for the ERP Frontend/POS HTTP surface (Stages 1, 2, 3). Canonical `/api/v1/canonical/*` and internal `/api/v1/sync/*` routes are out of scope and are specified separately. | Active |
| `FRONTEND.md` | `erp-frontend` | Detailed frontend contract slice documentation (runtime split, auth flows, error handling, numeric conventions) | Active |
| `schemas/` | `erp-frontend` | JSON Schema (Draft 2020-12) DTO definitions for frontend domain models (`auth`, `catalog`, `common`, `identity`, `inventory`, `purchasing`, `sales`) | Active |
| `fixtures/` | `erp-frontend` (Shared) | Canonical JSON payload fixtures for mock servers and contract tests | Active |
| `canonical/` | `erp-backend` | Canonical schemas separating ERP System of Record from external consumers (Product, InventoryItem, SalesOrder, etc.) | Placeholder (.gitkeep) |
| `events/` | `erp-backend` | JSON Schemas for outbox event messaging | Placeholder (.gitkeep) |
| `ai-output/` | `brain` | JSON Schemas for AI-generated insights, forecasts, and action proposals | Placeholder (.gitkeep) |

---

## Contract Perimeter

`openapi.erp.yaml` is the ERP Frontend/POS surface only. It intentionally
excludes the Canonical API (`/api/v1/canonical/*`) used by the Brain/external
consumers and the internal branch replication API (`/api/v1/sync/*`). Those
boundaries must be specified in their own contract files; their absence from
this file is not a missing frontend route.

---

## Governance Rules

1. **Single Source of Truth:**
   All services build and validate against this repository root `/contracts` folder. No service may maintain duplicated contract definitions within the same boundary. The frontend/POS, Canonical, and sync boundaries are separate contracts; shared DTO primitives should be referenced rather than duplicated.
2. **Wire Format Invariants:**
   - Numbers (Money, quantities, conversion rates) are serialized as string decimals to avoid IEEE-754 precision loss.
   - Timestamps use UTC ISO-8601 formatting (`...Z`).
   - Mutations require an `Idempotency-Key` header, except login and refresh-token rotation.
   - Lists use cursor-based pagination.
3. **Change Protocol:**
   Any changes to shared schemas or OpenAPI definitions must be reviewed and agreed upon by producer and consumer teams before merging.
4. **Client Type Generation:**
   `contracts/schemas/` is the single source of truth; client type generation (e.g. for frontend DTOs) is currently manual (automation pipeline deferred).
