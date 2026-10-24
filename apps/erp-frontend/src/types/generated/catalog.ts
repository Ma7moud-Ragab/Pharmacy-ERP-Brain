/**
 * Pharmacy ERP — Catalog contract (Stage 1).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * KEY RULES:
 *  - UOM mutation is ADDITIVE / item-level only. No full-list PUT, no hard
 *    delete — deactivate via PATCH is_active=false.
 *  - conversion_to_base and is_base become IMMUTABLE once referenced by a
 *    posted document or stock (server rejects the change, 409).
 *  - For a sellable UOM, sale_unit_price is required/non-null/>=0. That price
 *    (+ PRODUCT.tax_rate) is the AUTHORITATIVE POS pricing source. There is
 *    NO branch price list, promotion, or rule-based pricing in the MVP.
 *  - tax_rate is fractional: "0.1400" == 14%.
 *  - Reorder rules are read/config only — never auto-create POs.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// ProductCategory
export type ProductCategoryDto = Schemas['ProductCategoryDto'];
export type ProductCategoryRequest = Schemas['ProductCategoryRequest'];
export type ProductCategoryPatchRequest =
  Schemas['ProductCategoryPatchRequest'];

// Product / UOM
export type ProductUomDto = Schemas['ProductUomDto'];
export type ProductUomRequest = Schemas['ProductUomRequest'];
export type ProductUomPatchRequest = Schemas['ProductUomPatchRequest'];

/** Representative of { product_id, uom_code, factor, price, is_base, active } */
export type ProductUomListItem = ProductUomDto;

export type ProductDto = Schemas['ProductDto'];
export type CreateProductRequest = Schemas['CreateProductRequest'];
export type ProductPatchRequest = Schemas['ProductPatchRequest'];

// Reorder rule (config only)
export type ReorderRuleDto = Schemas['ReorderRuleDto'];
export type ReorderRuleRequest = Schemas['ReorderRuleRequest'];

/** GET /branches/{branchId}/products/{productId}/reorder-rule */
export interface ReorderRuleWrapper {
  rule: ReorderRuleDto | null; // null when none configured
}
