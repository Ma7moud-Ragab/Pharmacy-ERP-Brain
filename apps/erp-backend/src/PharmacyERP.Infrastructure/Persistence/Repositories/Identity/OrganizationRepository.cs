using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class OrganizationRepository : IOrganizationRepository
{
    private readonly PharmacyDbContext _db;

    public OrganizationRepository(PharmacyDbContext db) => _db = db;

    public Task<Organization?> GetActiveByCodeAsync(string organizationCode, CancellationToken ct = default)
    {
        var code = organizationCode.Trim();
        return _db.Organizations.IgnoreQueryFilters()
            .FirstOrDefaultAsync(x => x.IsActive && x.OrganizationCode.ToUpper() == code.ToUpper(), ct);
    }

    public Task<bool> ExistsByCodeAsync(string organizationCode, CancellationToken ct = default)
    {
        var code = organizationCode.Trim();
        return _db.Organizations.IgnoreQueryFilters()
            .AnyAsync(x => x.OrganizationCode.ToUpper() == code.ToUpper(), ct);
    }

    public async Task AddAsync(Organization organization, CancellationToken ct = default)
        => await _db.Organizations.AddAsync(organization, ct);
}
