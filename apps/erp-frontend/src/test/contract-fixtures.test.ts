// Owner: erp-frontend
import { describe, it, expect } from 'vitest';

import type {
  BranchDto,
  OrganizationDto,
  ProductDto,
  InventoryBalanceDto,
  SalesOrderDto,
  SalesInvoiceDto,
  SalesReturnDto,
  SupplierDto,
  PurchaseOrderDto,
  VendorReturnDto,
  TokenPairResponse,
  CurrentUserContext,
} from '../types/generated';

import branchFixture from '@contracts/fixtures/branch.json';
import organizationFixture from '@contracts/fixtures/organization.json';
import productFixture from '@contracts/fixtures/product.json';
import inventoryBalanceFixture from '@contracts/fixtures/inventory-balance.json';
import salesOrderDraftFixture from '@contracts/fixtures/sales-order-draft.json';
import salesInvoiceCompletedFixture from '@contracts/fixtures/sales-invoice-completed.json';
import salesReturnFixture from '@contracts/fixtures/sales-return.json';
import supplierFixture from '@contracts/fixtures/supplier.json';
import purchaseOrderFixture from '@contracts/fixtures/purchase-order.json';
import vendorReturnFixture from '@contracts/fixtures/vendor-return.json';
import authTokenPairFixture from '@contracts/fixtures/auth-token-pair.json';
import currentUserContextFixture from '@contracts/fixtures/current-user-context.json';

describe('Phase 0 Contract Fixtures Type Conformance', () => {
  it('branch.json conforms to BranchDto', () => {
    const branch: BranchDto = branchFixture;
    expect(branch.branch_id).toBeDefined();
    expect(branch.code).toBe('BR-CAI-01');
  });

  it('organization.json conforms to OrganizationDto', () => {
    const org: OrganizationDto = organizationFixture;
    expect(org.organization_id).toBeDefined();
    expect(org.base_currency).toBe('EGP');
    expect(org.time_zone_id).toBe('Africa/Cairo');
  });

  it('product.json conforms to ProductDto', () => {
    const product: ProductDto = productFixture;
    expect(product.product_id).toBeDefined();
    expect(product.uoms.length).toBeGreaterThan(0);
    const baseUom = product.uoms.find((u) => u.is_base);
    expect(baseUom).toBeDefined();
    expect(baseUom?.conversion_to_base).toBe('1.000000');
  });

  it('inventory-balance.json conforms to InventoryBalanceDto', () => {
    const balance: InventoryBalanceDto = inventoryBalanceFixture;
    expect(balance.product_id).toBeDefined();
    expect(balance.on_hand_qty_base).toBeDefined();
    expect(balance.average_unit_cost).toBeDefined();
  });

  it('sales-order-draft.json conforms to SalesOrderDto', () => {
    const order: SalesOrderDto = salesOrderDraftFixture as SalesOrderDto;
    expect(order.order_status).toBe('DRAFT');
    expect(order.channel).toBe('POS');
    expect(order.lines.length).toBeGreaterThan(0);
  });

  it('sales-invoice-completed.json conforms to SalesInvoiceDto', () => {
    const invoice: SalesInvoiceDto =
      salesInvoiceCompletedFixture as SalesInvoiceDto;
    expect(invoice.status).toBe('ISSUED');
    expect(invoice.payment_status).toBe('PAID');
    expect(invoice.payments?.length).toBeGreaterThan(0);
    expect(invoice.payments?.[0].method).toBe('CASH');
  });

  it('sales-return.json conforms to SalesReturnDto', () => {
    const returnDoc: SalesReturnDto = salesReturnFixture as SalesReturnDto;
    expect(returnDoc.status).toBe('POSTED');
    expect(returnDoc.inventory_txns?.[0]?.transaction_type).toBe(
      'SALES_RETURN_IN'
    );
    expect(returnDoc.refund?.method).toBe('CASH');
  });

  it('supplier.json conforms to SupplierDto', () => {
    const supplier: SupplierDto = supplierFixture;
    expect(supplier.supplier_id).toBeDefined();
    expect(supplier.supplier_code).toBe('SUP-EG-CLX');
  });

  it('purchase-order.json conforms to PurchaseOrderDto', () => {
    const po: PurchaseOrderDto = purchaseOrderFixture as PurchaseOrderDto;
    expect(po.status).toBe('PARTIALLY_RECEIVED');
    expect(po.payment_status).toBe('PARTIALLY_PAID');
    expect(po.lines[0].allocated_additional_cost).toBe('58.29');
    expect(po.lines[1].allocated_additional_cost).toBe('61.71');
  });

  it('vendor-return.json conforms to VendorReturnDto', () => {
    const vr: VendorReturnDto = vendorReturnFixture as VendorReturnDto;
    expect(vr.status).toBe('POSTED');
    expect(vr.inventory_txn?.transaction_type).toBe('VENDOR_RETURN_OUT');
  });

  it('auth-token-pair.json conforms to TokenPairResponse', () => {
    const tokenPair: TokenPairResponse =
      authTokenPairFixture as TokenPairResponse;
    expect(tokenPair.token_type).toBe('Bearer');
    expect(tokenPair.user.role).toBe('Pharmacist');
    expect(tokenPair.key_id).toBe('erp-2026-10-k1');
  });

  it('current-user-context.json conforms to CurrentUserContext', () => {
    const ctx: CurrentUserContext =
      currentUserContextFixture as CurrentUserContext;
    expect(ctx.runtime).toBe('BranchLocal');
    expect(ctx.roles).toContain('Pharmacist');
    expect(ctx.organization_code).toBe('PHARMAPLUS');
  });
});
