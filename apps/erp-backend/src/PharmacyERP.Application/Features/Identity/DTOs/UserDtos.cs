using System.ComponentModel.DataAnnotations;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Identity.DTOs;

public sealed record CreateUserRequest
{
    public Guid EmployeeId { get; init; }
    [Required, StringLength(80)] public string Username { get; init; } = string.Empty;
    [Required, MinLength(12)] public string Password { get; init; } = string.Empty;
    public UserRole Role { get; init; }
    public BranchScope BranchScope { get; init; } = BranchScope.ASSIGNED;
    public IReadOnlyCollection<Guid> BranchIds { get; init; } = Array.Empty<Guid>();
}

public sealed record UpdateUserRequest
{
    public UserRole Role { get; init; }
    public BranchScope BranchScope { get; init; }
    public IReadOnlyCollection<Guid> BranchIds { get; init; } = Array.Empty<Guid>();
    public bool? IsActive { get; init; }
}

public sealed record ResetPasswordRequest { [Required, MinLength(12)] public string NewPassword { get; init; } = string.Empty; }
public sealed record UserDto(Guid UserId, Guid EmployeeId, Guid OrganizationId, string Username, UserRole Role,
    BranchScope BranchScope, bool IsActive, IReadOnlyCollection<Guid> BranchIds);

public static class UserDtoMapper
{
    public static UserDto From(UserAccount user) => new(user.UserId, user.EmployeeId, user.OrganizationId, user.Username,
        user.Role, user.BranchScope, user.IsActive, user.BranchAccesses.Select(x => x.BranchId).ToArray());
}
