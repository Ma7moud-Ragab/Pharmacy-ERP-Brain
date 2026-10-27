using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class UserAccountRepository : IUserAccountRepository
{
    private readonly PharmacyDbContext _db;

    public UserAccountRepository(PharmacyDbContext db) => _db = db;

    public Task<UserAccount?> GetForLoginAsync(Guid organizationId, string normalizedUsername, CancellationToken ct = default)
        => _db.UserAccounts.Include(x => x.Employee).Include(x => x.BranchAccesses)
            .FirstOrDefaultAsync(x => x.OrganizationId == organizationId && x.NormalizedUsername == normalizedUsername, ct);

    public Task<UserAccount?> GetByIdWithAccessAsync(Guid organizationId, Guid userId, CancellationToken ct = default)
        => _db.UserAccounts.Include(x => x.Employee).Include(x => x.BranchAccesses)
            .FirstOrDefaultAsync(x => x.OrganizationId == organizationId && x.UserId == userId, ct);

    public Task<bool> ExistsByUsernameAsync(Guid organizationId, string normalizedUsername, CancellationToken ct = default)
        => _db.UserAccounts.AnyAsync(x => x.OrganizationId == organizationId && x.NormalizedUsername == normalizedUsername, ct);

    public Task<bool> ExistsForEmployeeAsync(Guid organizationId, Guid employeeId, CancellationToken ct = default)
        => _db.UserAccounts.AnyAsync(x => x.OrganizationId == organizationId && x.EmployeeId == employeeId, ct);

    public async Task<PagedResult<UserAccount>> GetPagedAsync(Guid organizationId, Guid? branchId, UserRole? role, bool includeInactive, int page, int pageSize, CancellationToken ct = default)
    {
        var query = _db.UserAccounts.AsNoTracking().Include(x => x.BranchAccesses)
            .Where(x => x.OrganizationId == organizationId);
        if (!includeInactive) query = query.Where(x => x.IsActive);
        if (role.HasValue) query = query.Where(x => x.Role == role.Value);
        if (branchId.HasValue)
        {
            var id = branchId.Value;
            query = query.Where(x => (x.Role == UserRole.Admin && x.BranchScope == BranchScope.ALL) || x.BranchAccesses.Any(a => a.BranchId == id));
        }
        var total = await query.CountAsync(ct);
        var items = await query.OrderBy(x => x.Username).ThenBy(x => x.UserId)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<UserAccount>(items, page, pageSize, total);
    }

    public async Task ReplaceBranchAccessAsync(Guid organizationId, Guid userId, IReadOnlyCollection<Guid> branchIds, CancellationToken ct = default)
    {
        var existing = await _db.UserBranchAccesses
            .Where(x => x.OrganizationId == organizationId && x.UserId == userId).ToListAsync(ct);
        _db.UserBranchAccesses.RemoveRange(existing);
        var uniqueIds = branchIds.Distinct().ToArray();
        if (uniqueIds.Length > 0)
            await _db.UserBranchAccesses.AddRangeAsync(uniqueIds.Select(id => UserBranchAccess.Create(organizationId, userId, id)), ct);
    }

    public async Task AddAsync(UserAccount userAccount, CancellationToken ct = default)
        => await _db.UserAccounts.AddAsync(userAccount, ct);
}
