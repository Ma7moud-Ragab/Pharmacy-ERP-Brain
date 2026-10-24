using PharmacyERP.Domain.ValueObjects;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class Employee
{
    public Guid EmployeeId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid BranchId { get; private set; }
    public string EmployeeNo { get; private set; } = string.Empty;
    public string FullName { get; private set; } = string.Empty;
    public string? Email { get; private set; }
    public string? Phone { get; private set; }
    public string JobTitle { get; private set; } = string.Empty;
    public Address Address { get; private set; } = null!;
    public DateOnly HiredOn { get; private set; }
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Branch Branch { get; private set; } = null!;
    public UserAccount? UserAccount { get; private set; }

    private Employee() { }

    public static Employee Create(Guid organizationId, Guid branchId, string employeeNo, string fullName, string? email, string? phone, string jobTitle, Address address, DateOnly hiredOn)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (branchId == Guid.Empty) throw new ArgumentException("Branch ID is required.", nameof(branchId));
        if (string.IsNullOrWhiteSpace(employeeNo) || employeeNo.Trim().Length > 30) throw new ArgumentException("Employee number is required and cannot exceed 30 characters.", nameof(employeeNo));
        if (string.IsNullOrWhiteSpace(fullName) || fullName.Trim().Length > 150) throw new ArgumentException("Full name is required and cannot exceed 150 characters.", nameof(fullName));
        if (email?.Length > 254) throw new ArgumentException("Email cannot exceed 254 characters.", nameof(email));
        if (phone?.Length > 30) throw new ArgumentException("Phone cannot exceed 30 characters.", nameof(phone));
        if (string.IsNullOrWhiteSpace(jobTitle) || jobTitle.Trim().Length > 80) throw new ArgumentException("Job title is required and cannot exceed 80 characters.", nameof(jobTitle));
        ArgumentNullException.ThrowIfNull(address);
        var now = DateTimeOffset.UtcNow;
        return new Employee { EmployeeId = Guid.NewGuid(), OrganizationId = organizationId, BranchId = branchId, EmployeeNo = employeeNo.Trim(), FullName = fullName.Trim(), Email = string.IsNullOrWhiteSpace(email) ? null : email.Trim(), Phone = string.IsNullOrWhiteSpace(phone) ? null : phone.Trim(), JobTitle = jobTitle.Trim(), Address = address, HiredOn = hiredOn, IsActive = true, CreatedAt = now, UpdatedAt = now };
    }

    public void Deactivate() { IsActive = false; UpdatedAt = DateTimeOffset.UtcNow; }
}
