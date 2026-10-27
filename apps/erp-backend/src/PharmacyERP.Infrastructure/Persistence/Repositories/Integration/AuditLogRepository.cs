using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Integration;

public class AuditLogRepository : IAuditLogRepository
{
    private readonly PharmacyDbContext _dbContext;

    public AuditLogRepository(PharmacyDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task AddAsync(AuditLog auditLog, CancellationToken ct = default)
    {
        await _dbContext.AuditLogs.AddAsync(auditLog, ct);
    }
}