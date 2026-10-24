using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class UserRefreshToken
{
    private byte[] _tokenHash = Array.Empty<byte>();

    public Guid RefreshTokenId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid UserId { get; private set; }
    // Hashes are identifiers for bearer credentials; callers must not be able to mutate them.
    public byte[] TokenHash
    {
        get => _tokenHash.ToArray();
        private set => _tokenHash = value;
    }
    public Guid TokenFamilyId { get; private set; }
    public DateTimeOffset IssuedAt { get; private set; }
    public DateTimeOffset ExpiresAt { get; private set; }
    public DateTimeOffset? ConsumedAt { get; private set; }
    public DateTimeOffset? RevokedAt { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public UserAccount UserAccount { get; private set; } = null!;

    private UserRefreshToken() { }

    public static UserRefreshToken Create(Guid organizationId, Guid userId, byte[] tokenHash, Guid tokenFamilyId, DateTimeOffset issuedAt, DateTimeOffset expiresAt)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (userId == Guid.Empty) throw new ArgumentException("User ID is required.", nameof(userId));
        if (tokenFamilyId == Guid.Empty) throw new ArgumentException("Token family ID is required.", nameof(tokenFamilyId));
        if (tokenHash is null || tokenHash.Length != 32) throw new ArgumentException("Token hash must be a 32-byte SHA-256 hash.", nameof(tokenHash));
        if (expiresAt <= issuedAt) throw new ArgumentException("Refresh token expiry must be after issue time.", nameof(expiresAt));
        return new UserRefreshToken { RefreshTokenId = Guid.NewGuid(), OrganizationId = organizationId, UserId = userId, TokenHash = tokenHash.ToArray(), TokenFamilyId = tokenFamilyId, IssuedAt = issuedAt, ExpiresAt = expiresAt, CreatedAt = issuedAt };
    }

    public bool IsActive(DateTimeOffset now) => !ConsumedAt.HasValue && !RevokedAt.HasValue && ExpiresAt > now;

    public void Consume(DateTimeOffset now)
    {
        if (!IsActive(now)) throw new RefreshTokenExpiredOrRevokedException();
        ConsumedAt = now;
    }

    public void Revoke(DateTimeOffset now)
    {
        if (RevokedAt.HasValue) return;
        RevokedAt = now;
    }
}
