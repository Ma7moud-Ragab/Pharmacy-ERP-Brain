/**
 * Pharmacy ERP — Shared Contract Primitives.
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 * These type aliases are derived from the generated OpenAPI types so the FE
 * can never drift from the contract. Re-run `npm run codegen:paths` after any
 * contract change.
 *
 * CRITICAL NOTE ON NUMBERS:
 *   Money / quantities / costs / tax rates / conversion factors are serialized
 *   as fixed-decimal STRINGS, not IEEE-754 floats. Do NOT convert them to
 *   `number` for arithmetic you submit back to the server — the server is
 *   authoritative for all totals. Parse to decimal lib (e.g. decimal.js) only
 *   for display.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// ---------------------------------------------------------------------------
// Scalar conventions
// ---------------------------------------------------------------------------

export type Uuid = Schemas['Uuid'];
/** numeric(18,2) — fixed-2 decimal string (non-negative) */
export type Money = Schemas['Money'];
/** numeric(18,4) — fixed-4 decimal string (quantities, unit costs) */
export type Numeric4 = Schemas['Numeric4'];
/** numeric(18,6) — fixed-6 decimal string (conversion factors) */
export type Numeric6 = Schemas['Numeric6'];
/** numeric(9,4) fractional rate: "0.1400" = 14% (NOT 14) */
export type TaxRate = Schemas['TaxRate'];
/** UTC ISO-8601 timestamptz */
export type Timestamp = Schemas['Timestamp'];
/** Business date, organization-timezone-derived */
export type BusinessDate = string; // "YYYY-MM-DD"

// ---------------------------------------------------------------------------
// Shared value objects
// ---------------------------------------------------------------------------

export type AddressDto = Schemas['AddressDto'];

// ---------------------------------------------------------------------------
// Auth vocabulary (case-sensitive closed sets)
// ---------------------------------------------------------------------------

export type Role = Schemas['Role'];
export type BranchScope = Schemas['BranchScope'];
export type RuntimeMode = Schemas['RuntimeMode'];
export type PermissionScope = Schemas['PermissionScope'];

/** JWT claims shape (verified payload) — §8.5 */
export interface JwtClaims {
  sub: Uuid;
  roles: Role[];
  organization_id: Uuid;
  branch_scope: BranchScope;
  branch_ids: Uuid[];
  scopes: PermissionScope[];
  iat: number;
  exp: number;
}

// ---------------------------------------------------------------------------
// Error envelope — every code maps to exactly ONE HTTP status
// ---------------------------------------------------------------------------

export type ApiErrorCode =
  | 'MALFORMED_REQUEST' // 400
  | 'UNAUTHORIZED' // 401
  | 'FORBIDDEN' // 403
  | 'FORBIDDEN_BRANCH'; // 403 (branch scope failure)

export type ApiErrorCodeConflicts =
  | 'NOT_FOUND' // 404
  | 'CONFLICT' // 409
  | 'INVALID_STATE_TRANSITION' // 409
  | 'OUT_OF_STOCK' // 409
  | 'IDEMPOTENCY_MISMATCH' // 409
  | 'GONE'; // 410 (expired/consumed enrollment token)

export type ApiErrorCodeValidations =
  | 'VALIDATION_ERROR' // 422
  | 'EXPIRY_POLICY_VIOLATION'; // 422

export type ApiErrorCodeAll =
  | ApiErrorCode
  | ApiErrorCodeConflicts
  | ApiErrorCodeValidations
  | 'INTERNAL_ERROR'; // 500

export interface ApiErrorDetail {
  field: string; // JSON path, e.g. "lines[0].quantity"
  issue: string;
}

export type ApiError = Schemas['ApiError'];

/** 409 with per-line stock detail on checkout */
export interface OutOfStockError extends ApiError {
  error: {
    code: 'OUT_OF_STOCK';
    message: string;
    details: ApiErrorDetail[]; // which lines were short
    trace_id: string;
  };
}

// ---------------------------------------------------------------------------
// Pagination — one shape for every list endpoint
// ---------------------------------------------------------------------------

export interface PagedResult<T> {
  items: T[];
  /** Opaque cursor; null means end of results */
  nextCursor: string | null;
}

// ---------------------------------------------------------------------------
// HTTP contract helpers
// ---------------------------------------------------------------------------

/** Attach to every mutating request */
export interface MutationHeaders {
  'Idempotency-Key': string; // stable per logical operation; min 16, max 100 chars
  traceparent?: string; // W3C trace context
}

export interface AuthHeaders extends MutationHeaders {
  Authorization: `Bearer ${string}`;
}

/** Server-issued JWT metadata to keep alongside tokens */
export interface AuthMetadata {
  issuer: string; // iss
  audience: string; // aud
  key_id: string; // kid -> validate via GET /.well-known/jwks.json
}
