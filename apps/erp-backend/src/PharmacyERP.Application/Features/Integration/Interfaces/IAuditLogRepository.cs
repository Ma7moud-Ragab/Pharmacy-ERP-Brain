using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Application.Features.Integration.Interfaces;

public interface IAuditLogRepository
{
    Task AddAsync(AuditLog auditLog, CancellationToken ct = default);
}