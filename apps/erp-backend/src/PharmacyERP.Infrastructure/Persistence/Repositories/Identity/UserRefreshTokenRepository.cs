using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Identity;

public sealed class UserRefreshTokenRepository : IUserRefreshTokenRepository
{
    private readonly PharmacyDbContext _db;
    public UserRefreshTokenRepository(PharmacyDbContext db) => _db = db;

    public Task<UserRefreshToken?> GetByTokenHashAsync(byte[] tokenHash, CancellationToken ct = default)
    {
        IQueryable<UserRefreshToken> query = _db.UserRefreshTokens.IgnoreQueryFilters();
        if (_db.Database.IsRelational())
            query = _db.UserRefreshTokens
                .FromSqlInterpolated($"SELECT * FROM identity.\"USER_REFRESH_TOKEN\" WHERE token_hash = {tokenHash} FOR UPDATE")
                .IgnoreQueryFilters();
        return query.Include(x => x.UserAccount).ThenInclude(x => x.Employee)
            .Include(x => x.UserAccount).ThenInclude(x => x.BranchAccesses)
            .FirstOrDefaultAsync(x => x.TokenHash == tokenHash, ct);
    }

    public async Task RevokeFamilyAsync(Guid organizationId, Guid tokenFamilyId, DateTimeOffset revokedAt, CancellationToken ct = default)
    {
        var family = await _db.UserRefreshTokens
            .Where(x => x.OrganizationId == organizationId && x.TokenFamilyId == tokenFamilyId && x.RevokedAt == null)
            .ToListAsync(ct);
        foreach (var token in family) token.Revoke(revokedAt);
    }

    public async Task RevokeAllUserTokensAsync(Guid organizationId, Guid userId, DateTimeOffset revokedAt, CancellationToken ct = default)
    {
        var tokens = await _db.UserRefreshTokens
            .Where(x => x.OrganizationId == organizationId && x.UserId == userId && x.RevokedAt == null)
            .ToListAsync(ct);
        foreach (var token in tokens) token.Revoke(revokedAt);
    }

    public async Task AddAsync(UserRefreshToken token, CancellationToken ct = default)
        => await _db.UserRefreshTokens.AddAsync(token, ct);
}
