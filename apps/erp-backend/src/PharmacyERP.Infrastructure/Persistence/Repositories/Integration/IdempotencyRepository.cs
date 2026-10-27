using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Integration;

public class IdempotencyRepository : IIdempotencyRepository
{
    private readonly PharmacyDbContext _dbContext;

    public IdempotencyRepository(PharmacyDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public Task<IdempotencyRecord?> GetAsync(Guid organizationId, Guid? branchId, string operationScope, string idempotencyKey, CancellationToken ct = default)
    {
        return _dbContext.IdempotencyRecords
            .FirstOrDefaultAsync(x => x.OrganizationId == organizationId
                                   && x.BranchId == branchId
                                   && x.OperationScope == operationScope
                                   && x.IdempotencyKey == idempotencyKey, ct);
    }

    public async Task AddAsync(IdempotencyRecord record, CancellationToken ct = default)
    {
        await _dbContext.IdempotencyRecords.AddAsync(record, ct);
    }
}