/**
 * Pharmacy ERP — Inventory contract (Stage 1).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * KEY RULES:
 *  - The ledger (transactions + lines) is APPEND-ONLY and authoritative;
 *    STOCK_BALANCE is a projection. No user edits balances directly.
 *  - POSTED transactions and their lines are immutable (DB-enforced).
 *    Corrections go through REVERSAL or ADJUSTMENT transactions.
 *  - Ledger lines are always in the product BASE UOM
 *    (entered_qty = |quantity_delta_base|, conversion_snapshot = 1).
 *  - Opening balance is a BRANCH-LOCAL command; the cloud never sends stock.
 *  - Batches are read-only via API (created by ledger workflows).
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// Enums / value sets (closed sets, case-sensitive)
export type LocationType = Schemas['LocationType'];
export type BatchQualityStatus = Schemas['BatchQualityStatus'];
export type InventoryTxnType = Schemas['InventoryTxnType'];
export type InventoryTxnStatus = Schemas['InventoryTxnStatus'];

/** Types permissible on POST /api/v1/inventory/adjustments */
export type AdjustmentsTxnType =
  'OPENING_BALANCE' | 'ADJUSTMENT_IN' | 'ADJUSTMENT_OUT' | 'REVERSAL';

// Locations & batches
export type InventoryLocationDto = Schemas['InventoryLocationDto'];
export type InventoryLocationRequest = Schemas['InventoryLocationRequest'];
export type InventoryLocationPatchRequest =
  Schemas['InventoryLocationPatchRequest'];
export type InventoryBatchDto = Schemas['InventoryBatchDto'];

// Balances (projection; no reserved quantity in MVP)
export type InventoryBalanceDto = Schemas['InventoryBalanceDto'];

// Ledger (authoritative)
export type InventoryTxnLineDto = Schemas['InventoryTxnLineDto'];
export type InventoryTxnDto = Schemas['InventoryTxnDto'];

// Adjustment command (opening balance / corrections)
export type InventoryTxnLineRequest = Schemas['InventoryTxnLineRequest'];
export type InventoryTxnRequest = Schemas['InventoryTxnRequest'];
export type InventoryTxnPatchRequest = Schemas['InventoryTxnPatchRequest'];

// FE list filters
export interface BalanceQuery {
  branchId: Schemas['Uuid']; // required
  productId?: Schemas['Uuid'];
  locationId?: Schemas['Uuid'];
  batchId?: Schemas['Uuid'];
}

export interface TxnHistoryQuery {
  branchId: Schemas['Uuid']; // required
  transactionType?: InventoryTxnType;
  productId?: Schemas['Uuid'];
  from?: Schemas['Timestamp'];
  to?: Schemas['Timestamp'];
}
