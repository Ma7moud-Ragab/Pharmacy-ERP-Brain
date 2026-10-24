using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Integration;

public class OutboxEvent
{
    public Guid EventId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid? BranchId { get; private set; }
    public long EventSequence { get; private set; }
    public string EventType { get; private set; } = null!;
    public string SchemaVersion { get; private set; } = "1.0";
    public string Payload { get; private set; } = null!;
    public DateTimeOffset OccurredAt { get; private set; }
    public DateTimeOffset? PublishedAt { get; private set; }
    public int AttemptCount { get; private set; }
    public string? LastError { get; private set; }
    public string TraceId { get; private set; } = null!;

    public Branch? Branch { get; private set; }

    private OutboxEvent() { }

    public OutboxEvent(Guid eventId, Guid organizationId, Guid? branchId, long eventSequence, string eventType, string payload, string traceId)
    {
        if (eventSequence <= 0) throw new IntegrationDomainException("EventSequence must be greater than zero.");
        if (string.IsNullOrWhiteSpace(eventType)) throw new IntegrationDomainException("EventType is required.");
        if (string.IsNullOrWhiteSpace(payload)) throw new IntegrationDomainException("Payload is required.");
        if (string.IsNullOrWhiteSpace(traceId)) throw new IntegrationDomainException("TraceId is required.");

        EventId = eventId;
        OrganizationId = organizationId;
        BranchId = branchId;
        EventSequence = eventSequence;
        EventType = eventType;
        Payload = payload;
        OccurredAt = DateTimeOffset.UtcNow;
        TraceId = traceId;
        AttemptCount = 0;
    }

    public void MarkPublished(DateTimeOffset publishedAt)
    {
        PublishedAt = publishedAt;
        LastError = null;
    }

    public void RecordPublishFailure(string error, DateTimeOffset failedAt)
    {
        AttemptCount++;
        LastError = error.Length > 500 ? error.Substring(0, 500) : error;
    }
}