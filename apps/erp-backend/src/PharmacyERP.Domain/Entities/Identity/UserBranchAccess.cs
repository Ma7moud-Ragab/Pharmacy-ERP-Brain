namespace PharmacyERP.Domain.Entities.Identity;

public sealed class UserBranchAccess
{
    public Guid OrganizationId { get; private set; }
    public Guid UserId { get; private set; }
    public Guid BranchId { get; private set; }
    public UserAccount UserAccount { get; private set; } = null!;
    public Branch Branch { get; private set; } = null!;

    private UserBranchAccess() { }

    public static UserBranchAccess Create(Guid organizationId, Guid userId, Guid branchId)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (userId == Guid.Empty) throw new ArgumentException("User ID is required.", nameof(userId));
        if (branchId == Guid.Empty) throw new ArgumentException("Branch ID is required.", nameof(branchId));
        return new UserBranchAccess { OrganizationId = organizationId, UserId = userId, BranchId = branchId };
    }
}
