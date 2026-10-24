/**
 * Pharmacy ERP — Auth contract (Stage 1).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * - Username uniqueness is PER-ORGANIZATION (login resolves organization_code).
 * - Refresh rotates on every use; submitting a consumed refresh token revokes
 *   its whole token family -> FE must force re-login.
 * - Branch-local runtime: access tokens max 24h validity, constrained to the
 *   enrolled branch.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

export type LoginRequest = Schemas['LoginRequest'];
export type TokenPairResponse = Schemas['TokenPairResponse'];
export type RefreshTokenRequest = Schemas['RefreshTokenRequest'];
export type LogoutRequest = Schemas['LogoutRequest'];
export type CurrentUserContext = Schemas['CurrentUserContextDto'];
