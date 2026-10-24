using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Identity;

public sealed class BranchEnrollment
{
    private byte[] _tokenHash = Array.Empty<byte>();

    public Guid EnrollmentId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid BranchId { get; private set; }
    // Hashes are identifiers for one-time credentials; callers must not be able to mutate them.
    public byte[] TokenHash
    {
        get => _tokenHash.ToArray();
        private set => _tokenHash = value;
    }
    public DateTimeOffset ExpiresAt { get; private set; }
    public DateTimeOffset? UsedAt { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public Branch Branch { get; private set; } = null!;

    private BranchEnrollment() { }

    public static BranchEnrollment Create(Guid organizationId, Guid branchId, byte[] tokenHash, DateTimeOffset expiresAt, DateTimeOffset createdAt)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("Organization ID is required.", nameof(organizationId));
        if (branchId == Guid.Empty) throw new ArgumentException("Branch ID is required.", nameof(branchId));
        if (tokenHash is null || tokenHash.Length != 32) throw new ArgumentException("Token hash must be a 32-byte SHA-256 hash.", nameof(tokenHash));
        if (expiresAt <= createdAt) throw new ArgumentException("Enrollment expiry must be after creation.", nameof(expiresAt));
        return new BranchEnrollment { EnrollmentId = Guid.NewGuid(), OrganizationId = organizationId, BranchId = branchId, TokenHash = tokenHash.ToArray(), ExpiresAt = expiresAt, CreatedAt = createdAt };
    }

    public void Redeem(DateTimeOffset now)
    {
        if (UsedAt.HasValue || ExpiresAt <= now) throw new EnrollmentTokenInvalidOrExpiredException();
        UsedAt = now;
    }
}
