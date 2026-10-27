using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class BranchEnrollmentRepository : IBranchEnrollmentRepository
{
    private readonly PharmacyDbContext _db;
    public BranchEnrollmentRepository(PharmacyDbContext db) => _db = db;

    public Task<BranchEnrollment?> GetByTokenHashAsync(byte[] tokenHash, CancellationToken ct = default)
    {
        IQueryable<BranchEnrollment> query = _db.BranchEnrollments.IgnoreQueryFilters();
        if (_db.Database.IsRelational())
            query = _db.BranchEnrollments
                .FromSqlInterpolated($"SELECT * FROM identity.\"BRANCH_ENROLLMENT\" WHERE token_hash = {tokenHash} FOR UPDATE")
                .IgnoreQueryFilters();
        return query.Include(x => x.Branch).FirstOrDefaultAsync(x => x.TokenHash == tokenHash, ct);
    }

    public async Task AddAsync(BranchEnrollment enrollment, CancellationToken ct = default)
        => await _db.BranchEnrollments.AddAsync(enrollment, ct);
}
