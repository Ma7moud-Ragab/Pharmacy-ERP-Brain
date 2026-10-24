using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.ValueObjects;

/// <summary>
/// An immutable address value object shared by identity-domain entities.
/// </summary>
public sealed record Address
{
    public string Line1 { get; private init; } = string.Empty;
    public string? Line2 { get; private init; }
    public string City { get; private init; } = string.Empty;
    public string? Region { get; private init; }
    public string? PostalCode { get; private init; }
    public string CountryCode { get; private init; } = string.Empty;

    // Required by Entity Framework Core when materializing the owned value object.
    private Address() { }

    public Address(
        string line1,
        string? line2,
        string city,
        string? region,
        string? postalCode,
        string countryCode)
    {
        if (string.IsNullOrWhiteSpace(line1))
            throw new InvalidAddressException("Address Line1 is required.");
        if (line1.Length > 200)
            throw new InvalidAddressException("Address Line1 cannot exceed 200 characters.");

        if (line2?.Length > 200)
            throw new InvalidAddressException("Address Line2 cannot exceed 200 characters.");

        if (string.IsNullOrWhiteSpace(city))
            throw new InvalidAddressException("Address City is required.");
        if (city.Length > 100)
            throw new InvalidAddressException("Address City cannot exceed 100 characters.");

        if (region?.Length > 100)
            throw new InvalidAddressException("Address Region cannot exceed 100 characters.");

        if (postalCode?.Length > 20)
            throw new InvalidAddressException("Address PostalCode cannot exceed 20 characters.");

        if (string.IsNullOrWhiteSpace(countryCode))
            throw new InvalidAddressException("Address CountryCode is required and must contain exactly two characters.");

        var normalizedCountryCode = countryCode.Trim().ToUpperInvariant();
        if (normalizedCountryCode.Length != 2 || !normalizedCountryCode.All(char.IsAsciiLetter))
            throw new InvalidAddressException("Address CountryCode must contain exactly two ASCII letters.");

        Line1 = line1;
        Line2 = line2;
        City = city;
        Region = region;
        PostalCode = postalCode;
        CountryCode = normalizedCountryCode;
    }
}
