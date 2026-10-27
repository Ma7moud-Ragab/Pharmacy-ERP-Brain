using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public interface IUserRefreshTokenRepository
{
    Task<UserRefreshToken?> GetByTokenHashAsync(byte[] tokenHash, CancellationToken ct = default);
    Task RevokeFamilyAsync(Guid organizationId, Guid tokenFamilyId, DateTimeOffset revokedAt, CancellationToken ct = default);
    Task RevokeAllUserTokensAsync(Guid organizationId, Guid userId, DateTimeOffset revokedAt, CancellationToken ct = default);
    Task AddAsync(UserRefreshToken token, CancellationToken ct = default);
}
