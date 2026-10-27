using System.ComponentModel.DataAnnotations;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.DTOs;

public sealed record CreateBranchRequest
{
    [Required, StringLength(30)] public string BranchCode { get; init; } = string.Empty;
    [Required, StringLength(150)] public string Name { get; init; } = string.Empty;
    [Required] public AddressDto Address { get; init; } = new();
}

public sealed record UpdateBranchRequest
{
    [Required, StringLength(150)] public string Name { get; init; } = string.Empty;
    [Required] public AddressDto Address { get; init; } = new();
    public bool? IsActive { get; init; }
}

public sealed record BranchDto(Guid BranchId, Guid OrganizationId, string BranchCode, string Name, AddressDto Address, bool IsActive);
public sealed record EnrollmentTokenResponse(string Token, DateTimeOffset ExpiresAt);
public sealed record RedeemBranchEnrollmentRequest { [Required] public string Token { get; init; } = string.Empty; }
public sealed record RedeemBranchEnrollmentResponse(Guid OrganizationId, Guid BranchId, string RuntimeCredential,
    long InitialSyncCursor, DateTimeOffset CredentialExpiry);

public static class BranchDtoMapper
{
    public static BranchDto From(Branch branch) => new(branch.BranchId, branch.OrganizationId, branch.BranchCode, branch.Name, AddressDto.From(branch.Address), branch.IsActive);
}
