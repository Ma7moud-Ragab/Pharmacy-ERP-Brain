/**
 * Pharmacy ERP — Sales contract (Stage 2, BranchLocal runtime POS).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * ABSOLUTE FE RULES (server authority):
 *  - FE sends ONLY product_id + product_uom_id + entered_qty. Prices, tax,
 *    discounts, totals, and change are server-computed. FE totals are
 *    informational only.
 *  - Drafts do NOT reserve or decrement stock.
 *  - Complete = cash payment in FULL (method CASH only).
 *  - The server allocates stock FEFO; insufficient stock -> 409 OUT_OF_STOCK
 *    with affected line details.
 *  - Returns: FE picks invoice line + quantity + disposition ONLY. Batch and
 *    destination location are derived by the server from the original posted
 *    sale allocation. 14-day window (organization tz), must be at the
 *    invoice branch.
 *  - Invoices are immutable after issue; corrections are NEW returns.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// Closed value sets
export type SalesOrderStatus = Schemas['SalesOrderStatus'];
export type InvoiceStatus = Schemas['SalesInvoiceStatus'];
export type InvoicePaymentStatus = Schemas['SalesInvoicePaymentStatus'];
export type PaymentMethod = 'CASH'; // MVP: cash only
export type ReturnDisposition = Schemas['ReturnDisposition'];
export type SalesReturnStatus = Schemas['SalesReturnStatus'];
export type SalesRefundStatus = Schemas['SalesRefundStatus'];

// Orders (draft cart)
export type SalesOrderLineDto = Schemas['SalesOrderLineDto'];
export type SalesOrderDto = Schemas['SalesOrderDto'];
export type SalesOrderLineRequest = Schemas['SalesOrderLineRequest'];
export type CreateSalesOrderRequest = Schemas['CreateSalesOrderRequest'];
export type SalesOrderLinesRequest = Schemas['SalesOrderLinesRequest'];
export type CompleteSalesOrderRequest = Schemas['CompleteSalesOrderRequest'];
export type SalesPaymentDto = Schemas['SalesPaymentDto'];

// Invoice (immutable snapshots + settlement projection)
export type SalesInvoiceLineDto = Schemas['SalesInvoiceLineDto'];
export type SalesInvoiceDto = Schemas['SalesInvoiceDto'];
export type CompleteSalesOrderResult = Schemas['CompleteSalesOrderResultDto'];

// Returns & refunds
export type SalesReturnLineRequest = Schemas['SalesReturnLineRequest'];
export type SalesReturnRequest = Schemas['SalesReturnRequest'];
export type SalesReturnLineDto = Schemas['SalesReturnLineDto'];
export type SalesRefundDto = Schemas['SalesRefundDto'];
export type SalesReturnDto = Schemas['SalesReturnDto'];

export type { SalesReturnDto as SalesReturnInfo };
