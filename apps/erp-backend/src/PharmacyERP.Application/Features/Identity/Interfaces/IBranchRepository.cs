using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public interface IBranchRepository : IGenericRepository<Branch>
{
    Task<Branch?> GetByIdAsync(Guid organizationId, Guid branchId, CancellationToken ct = default);
    Task<bool> ExistsByCodeAsync(Guid organizationId, string branchCode, CancellationToken ct = default);
    Task<PagedResult<Branch>> GetPagedAsync(Guid organizationId, bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default);
}
