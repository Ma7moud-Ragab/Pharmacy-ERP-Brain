namespace PharmacyERP.Application.Common.Interfaces.Context
{
    public interface IDateTimeProvider
    {
        DateTimeOffset UtcNow { get; }
        DateOnly GetOrganizationBusinessDate(string ianaTimeZoneId);
    }
}
