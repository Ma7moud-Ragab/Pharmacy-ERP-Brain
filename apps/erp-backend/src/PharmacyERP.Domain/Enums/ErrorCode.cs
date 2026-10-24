namespace PharmacyERP.Domain.Enums;

public enum ErrorCode
{
    MALFORMED_REQUEST,        // HTTP 400
    UNAUTHORIZED,             // HTTP 401
    FORBIDDEN,                // HTTP 403
    FORBIDDEN_BRANCH,         // HTTP 403
    NOT_FOUND,                // HTTP 404
    CONFLICT,                 // HTTP 409
    INVALID_STATE_TRANSITION, // HTTP 409
    OUT_OF_STOCK,             // HTTP 409
    IDEMPOTENCY_MISMATCH,     // HTTP 409
    VALIDATION_ERROR,         // HTTP 422
    EXPIRY_POLICY_VIOLATION   // HTTP 422
}