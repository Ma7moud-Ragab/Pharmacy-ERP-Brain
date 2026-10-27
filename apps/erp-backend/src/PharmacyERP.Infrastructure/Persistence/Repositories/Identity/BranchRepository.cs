using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Repositories;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class BranchRepository : GenericRepository<Branch>, IBranchRepository
{
    public BranchRepository(PharmacyDbContext db) : base(db) { }

    public Task<Branch?> GetByIdAsync(Guid organizationId, Guid branchId, CancellationToken ct = default)
        => _dbSet.FirstOrDefaultAsync(x => x.OrganizationId == organizationId && x.BranchId == branchId, ct);

    public Task<bool> ExistsByCodeAsync(Guid organizationId, string branchCode, CancellationToken ct = default)
        => _dbSet.AnyAsync(x => x.OrganizationId == organizationId && x.BranchCode.ToUpper() == branchCode.Trim().ToUpper(), ct);

    public async Task<PagedResult<Branch>> GetPagedAsync(Guid organizationId, bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default)
    {
        var query = _dbSet.AsNoTracking().Where(x => x.OrganizationId == organizationId);
        if (!includeInactive) query = query.Where(x => x.IsActive);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var term = search.Trim();
            query = query.Where(x => x.Name.Contains(term) || x.BranchCode.Contains(term));
        }
        var total = await query.CountAsync(ct);
        var items = await query.OrderBy(x => x.Name).ThenBy(x => x.BranchId)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<Branch>(items, page, pageSize, total);
    }
}
