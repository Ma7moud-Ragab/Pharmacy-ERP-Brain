using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Infrastructure.Services.Context;

public class DateTimeProvider : IDateTimeProvider
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;

    public DateOnly GetOrganizationBusinessDate(string ianaTimeZoneId)
    {
       
        var timeZone = TimeZoneInfo.FindSystemTimeZoneById(ianaTimeZoneId);
        var localDateTime = TimeZoneInfo.ConvertTimeFromUtc(UtcNow.UtcDateTime, timeZone);

        return DateOnly.FromDateTime(localDateTime);
    }
}