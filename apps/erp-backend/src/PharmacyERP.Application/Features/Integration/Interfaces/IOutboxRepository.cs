using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Application.Features.Integration.Interfaces;

public interface IOutboxRepository
{
    Task<OutboxEventCursor?> LockAndGetCursorAsync(Guid organizationId, CancellationToken ct = default);
    Task AddEventAsync(OutboxEvent outboxEvent, CancellationToken ct = default);
}