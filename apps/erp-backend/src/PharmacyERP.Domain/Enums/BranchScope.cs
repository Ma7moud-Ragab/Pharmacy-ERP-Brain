namespace PharmacyERP.Domain.Enums;

/// <summary>
/// Determines which branches a user may access.
/// Persisted values are expected to use the exact names ALL and ASSIGNED.
/// </summary>
public enum BranchScope
{
    ALL = 1,
    ASSIGNED = 2
}
