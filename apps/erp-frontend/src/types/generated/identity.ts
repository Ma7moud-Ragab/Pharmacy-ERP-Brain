/**
 * Pharmacy ERP — Identity contract (Stage 1).
 *
 * Source of truth: /contracts/openapi.erp.yaml (components.schemas).
 *
 * organization_id is ALWAYS derived from the JWT — FE never submits it.
 * Soft deactivation only (is_active); no hard deletes.
 */
import type { components } from './api-paths';

type Schemas = components['schemas'];

// Organization
export type OrganizationDto = Schemas['OrganizationDto'];
export type CreateOrganizationRequest = Schemas['CreateOrganizationRequest'];
export type OrganizationSetupResult = Schemas['OrganizationSetupResultDto'];

// Branch
export type BranchDto = Schemas['BranchDto'];
export type BranchRequest = Schemas['BranchRequest'];
export type BranchPatchRequest = Schemas['BranchPatchRequest'];

// Branch runtime enrollment (single-use, short-lived token, stored hashed)
export type EnrollmentTokenDto = Schemas['EnrollmentTokenDto'];
export type BranchEnrollmentRequest = Schemas['BranchEnrollmentRequest'];
export type BranchEnrollmentResult = Schemas['BranchEnrollmentResultDto'];

// Employee
export type EmployeeDto = Schemas['EmployeeDto'];
export type EmployeeRequest = Schemas['EmployeeRequest'];
export type EmployeePatchRequest = Schemas['EmployeePatchRequest'];

// User account (Admin-only endpoints)
export type UserDto = Schemas['UserDto'];
export type BranchAccessGrant = Schemas['BranchAccessGrantDto'];
export type CreateUserRequest = Schemas['CreateUserRequest'];
export type UserPatchRequest = Schemas['UserPatchRequest'];
export type PasswordResetRequest = Schemas['PasswordResetRequest'];

export type Customer = never; // There is NO customer entity in the MVP
