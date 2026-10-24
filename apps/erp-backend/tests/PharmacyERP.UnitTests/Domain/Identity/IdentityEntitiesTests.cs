using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using PharmacyERP.Domain.ValueObjects;

namespace PharmacyERP.UnitTests.Domain.Identity;

public class IdentityEntitiesTests
{
    private static Address Address() => new("1 Main Street", null, "Cairo", null, null, "EG");

    [Theory]
    [InlineData(UserRole.Pharmacist)]
    [InlineData(UserRole.Cashier)]
    public void UserAccount_AllScope_IsRejectedForNonAdmin(UserRole role)
    {
        Assert.Throws<InvalidBranchScopeForRoleException>(() => UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), "user", "hash", role, BranchScope.ALL));
    }

    [Fact]
    public void UserAccount_AllScope_IsAllowedForAdmin()
    {
        var account = UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), " Admin ", "hash", UserRole.Admin, BranchScope.ALL);
        Assert.Equal(UserRole.Admin, account.Role);
        Assert.Equal(BranchScope.ALL, account.BranchScope);
        Assert.Equal("ADMIN", account.NormalizedUsername);
    }

    [Fact]
    public void UserAccount_ChangeRoleAndScope_RejectsInvalidCombination()
    {
        var account = UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), "user", "hash", UserRole.Admin, BranchScope.ALL);
        Assert.Throws<InvalidBranchScopeForRoleException>(() => account.ChangeRoleAndScope(UserRole.Pharmacist, BranchScope.ALL));
    }

    [Fact]
    public void UserAccount_LoginFailuresLockOutAndSuccessResetsFailureState()
    {
        var account = UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), "user", "hash", UserRole.Cashier, BranchScope.ASSIGNED);
        var now = DateTimeOffset.UtcNow;

        account.RecordLoginFailure(now, maxAttempts: 2, lockoutDuration: TimeSpan.FromMinutes(5));
        Assert.Equal(1, account.AccessFailedCount);
        Assert.Null(account.LockoutEnd);

        account.RecordLoginFailure(now.AddSeconds(1), maxAttempts: 2, lockoutDuration: TimeSpan.FromMinutes(5));
        Assert.Equal(2, account.AccessFailedCount);
        Assert.Equal(now.AddSeconds(1).AddMinutes(5), account.LockoutEnd);

        account.RecordLoginSuccess(now.AddMinutes(6));
        Assert.Equal(0, account.AccessFailedCount);
        Assert.Null(account.LockoutEnd);
        Assert.Equal(now.AddMinutes(6), account.LastLoginAt);
    }

    [Fact]
    public void UserAccount_PasswordChangeResetsLockoutAndUpdatesTimestamp()
    {
        var account = UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), "user", "old-hash", UserRole.Cashier, BranchScope.ASSIGNED);
        var now = DateTimeOffset.UtcNow;
        account.RecordLoginFailure(now, maxAttempts: 1, lockoutDuration: TimeSpan.FromMinutes(5));

        var changedAt = now.AddMinutes(1);
        account.UpdatePasswordHash("new-hash", changedAt);

        Assert.Equal("new-hash", account.PasswordHash);
        Assert.Equal(0, account.AccessFailedCount);
        Assert.Null(account.LockoutEnd);
        Assert.Equal(changedAt, account.UpdatedAt);
    }

    [Fact]
    public void Organization_InvalidTimeZone_ThrowsDomainException()
    {
        Assert.Throws<PharmacyERP.Domain.Exceptions.InvalidTimeZoneException>(() => Organization.Create("ORG1", "Org", "EGP", "Not/A_Real_TimeZone", Address()));
    }

    [Fact]
    public void BranchEnrollment_CanBeRedeemedOnlyOnce()
    {
        var now = DateTimeOffset.UtcNow;
        var enrollment = BranchEnrollment.Create(Guid.NewGuid(), Guid.NewGuid(), new byte[32], now.AddMinutes(5), now);
        enrollment.Redeem(now.AddMinutes(1));
        Assert.Equal(now.AddMinutes(1), enrollment.UsedAt);
        Assert.Throws<EnrollmentTokenInvalidOrExpiredException>(() => enrollment.Redeem(now.AddMinutes(2)));
    }

    [Fact]
    public void BranchEnrollment_ExpiredTokenCannotBeRedeemed()
    {
        var now = DateTimeOffset.UtcNow;
        var enrollment = BranchEnrollment.Create(Guid.NewGuid(), Guid.NewGuid(), new byte[32], now.AddMinutes(1), now);
        Assert.Throws<EnrollmentTokenInvalidOrExpiredException>(() => enrollment.Redeem(now.AddMinutes(1)));
    }

    [Fact]
    public void BranchEnrollment_TokenHashCannotBeMutatedThroughInputOrGetter()
    {
        var sourceHash = Enumerable.Range(0, 32).Select(value => (byte)value).ToArray();
        var enrollment = BranchEnrollment.Create(Guid.NewGuid(), Guid.NewGuid(), sourceHash, DateTimeOffset.UtcNow.AddMinutes(5), DateTimeOffset.UtcNow);
        var expected = sourceHash.ToArray();

        sourceHash[0] = 255;
        var exposedHash = enrollment.TokenHash;
        exposedHash[1] = 255;

        Assert.Equal(expected, enrollment.TokenHash);
    }


    [Fact]
    public void UserRefreshToken_IsActiveUntilConsumedRevokedOrExpired()
    {
        var now = DateTimeOffset.UtcNow;
        var token = UserRefreshToken.Create(Guid.NewGuid(), Guid.NewGuid(), new byte[32], Guid.NewGuid(), now, now.AddHours(1));
        Assert.True(token.IsActive(now));
        token.Consume(now.AddMinutes(1));
        Assert.False(token.IsActive(now.AddMinutes(1)));
        Assert.Throws<RefreshTokenExpiredOrRevokedException>(() => token.Consume(now.AddMinutes(2)));

        var revoked = UserRefreshToken.Create(Guid.NewGuid(), Guid.NewGuid(), new byte[32], Guid.NewGuid(), now, now.AddHours(1));
        revoked.Revoke(now.AddMinutes(1));
        Assert.False(revoked.IsActive(now.AddMinutes(1)));

        var expired = UserRefreshToken.Create(Guid.NewGuid(), Guid.NewGuid(), new byte[32], Guid.NewGuid(), now, now.AddMinutes(1));
        Assert.False(expired.IsActive(now.AddMinutes(1)));
    }

    [Fact]
    public void UserRefreshToken_TokenHashCannotBeMutatedThroughInputOrGetter()
    {
        var now = DateTimeOffset.UtcNow;
        var sourceHash = Enumerable.Range(0, 32).Select(value => (byte)value).ToArray();
        var token = UserRefreshToken.Create(Guid.NewGuid(), Guid.NewGuid(), sourceHash, Guid.NewGuid(), now, now.AddHours(1));
        var expected = sourceHash.ToArray();

        sourceHash[0] = 255;
        var exposedHash = token.TokenHash;
        exposedHash[1] = 255;

        Assert.Equal(expected, token.TokenHash);
    }
}
