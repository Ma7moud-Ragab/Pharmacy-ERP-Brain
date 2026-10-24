/**
 * Pharmacy ERP — Purchasing contract (Stage 3).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * RUNTIME SPLIT (FE must respect):
 *  - Cloud: suppliers CRUD, PO create/approve/order, supplier payments,
 *           vendor-return READS
 *  - BranchLocal: PO receive, PO cancel-remaining, vendor-RETURN create/
 *    cancel/post
 *  A route asked at a runtime that does not own it returns 404/405.
 *
 * FLOWS (server authority):
 *  - PO totals: server computes; additional header costs are allocated
 *    pro-rata to ordered line net at creation and released to accepted units
 *    on receipts. FE never computes totals.
 *  - One-step receiving: accepts/rejects per lot; rejected units never enter
 *    sellable stock; shelf-life policy enforced (EXPIRY_POLICY_VIOLATION 422);
 *    exceptions are role-guarded with a reason.
 *  - Supplier payment is an order-level cash settlement (NOT AP ledger) —
 *    cannot exceed outstanding, currency must match PO.
 *  - Vendor returns never infer supplier credit/refund.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// Closed value sets
export type PurchaseOrderStatus = Schemas['PurchaseOrderStatus'];
export type PurchaseOrderPaymentStatus = Schemas['PurchaseOrderPaymentStatus'];
export type SupplierPaymentMethod = 'CASH';
export type VendorReturnStatus = Schemas['VendorReturnStatus'];

// Supplier (Cloud)
export type SupplierDto = Schemas['SupplierDto'];
export type CreateSupplierRequest = Schemas['CreateSupplierRequest'];
export type SupplierPatchRequest = Schemas['SupplierPatchRequest'];
export type SupplierStatusPatchRequest = Schemas['SupplierStatusPatchRequest'];

// Purchase order
export type PurchaseOrderLineDto = Schemas['PurchaseOrderLineDto'];
export type PurchaseOrderDto = Schemas['PurchaseOrderDto'];
export type PurchaseOrderLineRequest = Schemas['PurchaseOrderLineRequest'];
export type CreatePurchaseOrderRequest = Schemas['CreatePurchaseOrderRequest'];
export type PurchaseOrderPatchRequest = Schemas['PurchaseOrderPatchRequest'];
export type CancelPurchaseOrderRequest = Schemas['CancelPurchaseOrderRequest'];
export type CancelPurchaseOrderRemainingRequest =
  Schemas['CancelPurchaseOrderRemainingRequest'];

/** Empty request body for POST /api/v1/purchasing/orders/{id}/order */
export type OrderPurchaseOrderRequest = Schemas['OrderPurchaseOrderRequest'];

// One-step receiving (BranchLocal)
export type ReceiveLineRequest = Schemas['ReceiveLineRequest'];
export type ReceivePurchaseOrderRequest =
  Schemas['ReceivePurchaseOrderRequest'];
export type PurchaseReceiptResultLine = Schemas['ReceiveLineDto'];
export type PurchaseReceiptResult = Schemas['PurchaseReceiptResultDto'];

// Supplier payments (Cloud)
export type RecordSupplierPaymentRequest =
  Schemas['RecordSupplierPaymentRequest'];
export type SupplierPaymentDto = Schemas['SupplierPaymentDto'];

// Vendor returns (create/post on BranchLocal; reads also on Cloud)
export type VendorReturnLineRequest = Schemas['VendorReturnLineRequest'];
export type CreateVendorReturnRequest = Schemas['CreateVendorReturnRequest'];
export type VendorReturnLineDto = Schemas['VendorReturnLineDto'];
export type VendorReturnDto = Schemas['VendorReturnDto'];

// Role vocabulary re-export (keeps domain imports tidy)
export type { Role, BranchScope } from './common';
