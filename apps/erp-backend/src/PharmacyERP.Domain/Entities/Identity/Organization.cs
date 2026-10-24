using PharmacyERP.Domain.Exceptions;
using PharmacyERP.Domain.ValueObjects;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class Organization
{
    public Guid OrganizationId { get; private set; }
    public string OrganizationCode { get; private set; } = string.Empty;
    public string Name { get; private set; } = string.Empty;
    public string BaseCurrency { get; private set; } = "EGP";
    public string TimeZoneId { get; private set; } = string.Empty;
    public Address Address { get; private set; } = null!;
    public bool IsActive { get; private set; } = true;
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public ICollection<Branch> Branches { get; private set; } = new List<Branch>();

    private Organization() { }

    public static Organization Create(string organizationCode, string name, string baseCurrency, string timeZoneId, Address address)
    {
        if (string.IsNullOrWhiteSpace(organizationCode) || organizationCode.Trim().Length > 30)
            throw new ArgumentException("Organization code is required and cannot exceed 30 characters.", nameof(organizationCode));
        if (string.IsNullOrWhiteSpace(name) || name.Trim().Length > 150)
            throw new ArgumentException("Organization name is required and cannot exceed 150 characters.", nameof(name));
        if (string.IsNullOrWhiteSpace(baseCurrency) || baseCurrency.Trim().Length != 3)
            throw new ArgumentException("Base currency must contain exactly three characters.", nameof(baseCurrency));
        if (string.IsNullOrWhiteSpace(timeZoneId) || !TimeZoneInfo.TryFindSystemTimeZoneById(timeZoneId, out _))
            throw new PharmacyERP.Domain.Exceptions.InvalidTimeZoneException($"Time zone '{timeZoneId}' is not valid.");
        ArgumentNullException.ThrowIfNull(address);

        var now = DateTimeOffset.UtcNow;
        return new Organization
        {
            OrganizationId = Guid.NewGuid(), OrganizationCode = organizationCode.Trim(), Name = name.Trim(),
            BaseCurrency = baseCurrency.Trim().ToUpperInvariant(), TimeZoneId = timeZoneId.Trim(), Address = address,
            IsActive = true, CreatedAt = now, UpdatedAt = now
        };
    }

    public void Deactivate()
    {
        IsActive = false;
        UpdatedAt = DateTimeOffset.UtcNow;
    }
}
