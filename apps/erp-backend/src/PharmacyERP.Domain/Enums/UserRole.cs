namespace PharmacyERP.Domain.Enums;

/// <summary>
/// Roles supported by the MVP. Names are persisted and emitted case-sensitively.
/// </summary>
public enum UserRole
{
    Admin = 1,
    Pharmacist = 2,
    Cashier = 3
}
