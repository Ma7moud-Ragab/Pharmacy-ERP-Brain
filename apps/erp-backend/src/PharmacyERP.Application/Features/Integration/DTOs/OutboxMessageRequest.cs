namespace PharmacyERP.Application.Features.Integration.DTOs;

public sealed record OutboxMessageRequest<TPayload>(
    string EventType,
    Guid? BranchId,
    TPayload Payload,
    string SchemaVersion = "1.0"
);