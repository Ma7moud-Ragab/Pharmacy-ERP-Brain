using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Domain.Entities.Integration;

public class OutboxEventCursor
{
    public Guid OrganizationId { get; private set; }
    public long LastEventSequence { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    public Organization Organization { get; private set; } = null!;

    private OutboxEventCursor() { } 

    public OutboxEventCursor(Guid organizationId)
    {
        OrganizationId = organizationId;
        LastEventSequence = 0;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public long AllocateNextSequence(DateTimeOffset now)
    {
        LastEventSequence++;
        UpdatedAt = now;
        return LastEventSequence;
    }
}