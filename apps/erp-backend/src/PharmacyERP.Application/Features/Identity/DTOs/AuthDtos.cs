using System.ComponentModel.DataAnnotations;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.DTOs;

public sealed record LoginRequest
{
    [Required, StringLength(30)] public string OrganizationCode { get; init; } = string.Empty;
    [Required, StringLength(80)] public string Username { get; init; } = string.Empty;
    [Required] public string Password { get; init; } = string.Empty;
}

public sealed record RefreshTokenRequest { [Required] public string RefreshToken { get; init; } = string.Empty; }
public sealed record LogoutRequest { [Required] public string RefreshToken { get; init; } = string.Empty; }

public sealed record CurrentUserDto(
    Guid UserId, Guid EmployeeId, Guid OrganizationId, string Username, string Role,
    string BranchScope, IReadOnlyCollection<Guid> BranchIds, IReadOnlyCollection<string> Scopes);

public sealed record LoginResponse(string AccessToken, DateTimeOffset AccessTokenExpiresAt, string RefreshToken, CurrentUserDto User);

public static class CurrentUserDtoMapper
{
    public static CurrentUserDto From(UserAccount user, IReadOnlyCollection<Guid> branchIds, IReadOnlyCollection<string> scopes)
        => new(user.UserId, user.EmployeeId, user.OrganizationId, user.Username, user.Role.ToString(), user.BranchScope.ToString(), branchIds, scopes);
}
