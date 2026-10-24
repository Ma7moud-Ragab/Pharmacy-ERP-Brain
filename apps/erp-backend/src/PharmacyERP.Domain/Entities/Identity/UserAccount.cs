using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class UserAccount
{
    public Guid UserId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid EmployeeId { get; private set; }
    public string Username { get; private set; } = string.Empty;
    public string NormalizedUsername { get; private set; } = string.Empty;
    public string PasswordHash { get; private set; } = string.Empty;
    public UserRole Role { get; private set; }
    public BranchScope BranchScope { get; private set; }
    public bool IsActive { get; private set; }
    public int AccessFailedCount { get; private set; }
    public DateTimeOffset? LockoutEnd { get; private set; }
    public DateTimeOffset? LastLoginAt { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Employee Employee { get; private set; } = null!;
    public ICollection<UserBranchAccess> BranchAccesses { get; private set; } = new List<UserBranchAccess>();
    public ICollection<UserRefreshToken> RefreshTokens { get; private set; } = new List<UserRefreshToken>();

    private UserAccount() { }

    public static UserAccount Create(Guid organizationId, Guid employeeId, string username, string passwordHash, UserRole role, BranchScope branchScope)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (employeeId == Guid.Empty) throw new ArgumentException("Employee ID is required.", nameof(employeeId));
        if (string.IsNullOrWhiteSpace(username) || username.Trim().Length > 80) throw new ArgumentException("Username is required and cannot exceed 80 characters.", nameof(username));
        if (string.IsNullOrWhiteSpace(passwordHash) || passwordHash.Length > 500) throw new ArgumentException("Password hash is required and cannot exceed 500 characters.", nameof(passwordHash));
        ValidateRoleAndScope(role, branchScope);
        var now = DateTimeOffset.UtcNow;
        var trimmedUsername = username.Trim();
        return new UserAccount { UserId = Guid.NewGuid(), OrganizationId = organizationId, EmployeeId = employeeId, Username = trimmedUsername, NormalizedUsername = trimmedUsername.ToUpperInvariant(), PasswordHash = passwordHash, Role = role, BranchScope = branchScope, IsActive = true, AccessFailedCount = 0, CreatedAt = now, UpdatedAt = now };
    }

    public void RecordLoginSuccess(DateTimeOffset now)
    {
        AccessFailedCount = 0; LockoutEnd = null; LastLoginAt = now; UpdatedAt = now;
    }

    public void RecordLoginFailure(DateTimeOffset now, int maxAttempts, TimeSpan lockoutDuration)
    {
        if (maxAttempts < 1) throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        if (lockoutDuration < TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(lockoutDuration));
        AccessFailedCount++;
        if (AccessFailedCount >= maxAttempts) LockoutEnd = now.Add(lockoutDuration);
        UpdatedAt = now;
    }

    public void ChangeRoleAndScope(UserRole newRole, BranchScope newScope)
    {
        ValidateRoleAndScope(newRole, newScope); Role = newRole; BranchScope = newScope; UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void UpdatePasswordHash(string newPasswordHash, DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(newPasswordHash) || newPasswordHash.Length > 500) throw new ArgumentException("Password hash is required and cannot exceed 500 characters.", nameof(newPasswordHash));
        PasswordHash = newPasswordHash; AccessFailedCount = 0; LockoutEnd = null; UpdatedAt = now;
    }

    public void Deactivate() { IsActive = false; UpdatedAt = DateTimeOffset.UtcNow; }

    private static void ValidateRoleAndScope(UserRole role, BranchScope scope)
    {
        if (!Enum.IsDefined(role)) throw new ArgumentOutOfRangeException(nameof(role));
        if (!Enum.IsDefined(scope)) throw new ArgumentOutOfRangeException(nameof(scope));
        if (scope == BranchScope.ALL && role != UserRole.Admin) throw new InvalidBranchScopeForRoleException();
    }
}
