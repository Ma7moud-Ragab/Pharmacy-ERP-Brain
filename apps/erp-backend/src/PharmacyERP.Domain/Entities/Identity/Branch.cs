using PharmacyERP.Domain.ValueObjects;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class Branch
{
    public Guid BranchId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public string BranchCode { get; private set; } = string.Empty;
    public string Name { get; private set; } = string.Empty;
    public Address Address { get; private set; } = null!;
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Organization Organization { get; private set; } = null!;
    public ICollection<Employee> Employees { get; private set; } = new List<Employee>();
    public ICollection<UserBranchAccess> UserBranchAccesses { get; private set; } = new List<UserBranchAccess>();
    public ICollection<BranchEnrollment> Enrollments { get; private set; } = new List<BranchEnrollment>();

    private Branch() { }

    public static Branch Create(Guid organizationId, string branchCode, string name, Address address)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (string.IsNullOrWhiteSpace(branchCode) || branchCode.Trim().Length > 30) throw new ArgumentException("Branch code is required and cannot exceed 30 characters.", nameof(branchCode));
        ValidateName(name);
        ArgumentNullException.ThrowIfNull(address);
        var now = DateTimeOffset.UtcNow;
        return new Branch { BranchId = Guid.NewGuid(), OrganizationId = organizationId, BranchCode = branchCode.Trim(), Name = name.Trim(), Address = address, IsActive = true, CreatedAt = now, UpdatedAt = now };
    }

    public void UpdateDetails(string name, Address address)
    {
        ValidateName(name); ArgumentNullException.ThrowIfNull(address);
        Name = name.Trim(); Address = address; UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void Deactivate() { IsActive = false; UpdatedAt = DateTimeOffset.UtcNow; }

    private static void ValidateName(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Trim().Length > 150) throw new ArgumentException("Branch name is required and cannot exceed 150 characters.", nameof(name));
    }
}
