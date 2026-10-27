using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Repositories;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class EmployeeRepository : GenericRepository<Employee>, IEmployeeRepository
{
    public EmployeeRepository(PharmacyDbContext db) : base(db) { }

    public Task<Employee?> GetByIdAsync(Guid organizationId, Guid employeeId, CancellationToken ct = default)
        => _dbSet.FirstOrDefaultAsync(x => x.OrganizationId == organizationId && x.EmployeeId == employeeId, ct);

    public Task<bool> ExistsByEmployeeNoAsync(Guid organizationId, Guid branchId, string employeeNo, CancellationToken ct = default)
        => _dbSet.AnyAsync(x => x.OrganizationId == organizationId && x.BranchId == branchId && x.EmployeeNo.ToUpper() == employeeNo.Trim().ToUpper(), ct);

    public async Task<PagedResult<Employee>> GetPagedAsync(Guid organizationId, Guid? branchId, bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default)
    {
        var query = _dbSet.AsNoTracking().Where(x => x.OrganizationId == organizationId);
        if (branchId.HasValue) query = query.Where(x => x.BranchId == branchId.Value);
        if (!includeInactive) query = query.Where(x => x.IsActive);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var term = search.Trim();
            query = query.Where(x => x.FullName.Contains(term) || x.EmployeeNo.Contains(term) || (x.Email != null && x.Email.Contains(term)));
        }
        var total = await query.CountAsync(ct);
        var items = await query.OrderBy(x => x.FullName).ThenBy(x => x.EmployeeId)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<Employee>(items, page, pageSize, total);
    }
}
