using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Application.Features.Integration.Interfaces;

public interface IIdempotencyRepository
{
    Task<IdempotencyRecord?> GetAsync(Guid organizationId, Guid? branchId, string operationScope, string idempotencyKey, CancellationToken ct = default);
    Task AddAsync(IdempotencyRecord record, CancellationToken ct = default);
}