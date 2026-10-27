using System.ComponentModel.DataAnnotations;
using PharmacyERP.Domain.ValueObjects;

namespace PharmacyERP.Application.Features.Identity.DTOs;

public sealed record CreateOrganizationRequest
{
    [Required, StringLength(30)] public string OrganizationCode { get; init; } = string.Empty;
    [Required, StringLength(150)] public string Name { get; init; } = string.Empty;
    [StringLength(3, MinimumLength = 3)] public string BaseCurrency { get; init; } = "EGP";
    [Required, StringLength(64)] public string TimeZoneId { get; init; } = "Africa/Cairo";
    [Required] public AddressDto Address { get; init; } = new();
    [Required] public CreateBranchRequest InitialBranch { get; init; } = new();
    [Required] public CreateEmployeeRequest InitialEmployee { get; init; } = new();
    [Required] public CreateUserRequest InitialAdmin { get; init; } = new();
}

public sealed record OrganizationDto(Guid OrganizationId, string OrganizationCode, string Name, string BaseCurrency, string TimeZoneId,
    Guid InitialBranchId, Guid InitialEmployeeId, Guid InitialAdminUserId);

public sealed record AddressDto
{
    [Required, StringLength(200, MinimumLength = 1)] public string Line1 { get; init; } = string.Empty;
    [StringLength(200)] public string? Line2 { get; init; }
    [Required, StringLength(100, MinimumLength = 1)] public string City { get; init; } = string.Empty;
    [StringLength(100)] public string? Region { get; init; }
    [StringLength(20)] public string? PostalCode { get; init; }
    [Required, StringLength(2, MinimumLength = 2)] public string CountryCode { get; init; } = string.Empty;

    public Address ToValueObject() => new(Line1, Line2, City, Region, PostalCode, CountryCode);
    public static AddressDto From(Address address) => new()
    {
        Line1 = address.Line1, Line2 = address.Line2, City = address.City,
        Region = address.Region, PostalCode = address.PostalCode, CountryCode = address.CountryCode
    };
}
