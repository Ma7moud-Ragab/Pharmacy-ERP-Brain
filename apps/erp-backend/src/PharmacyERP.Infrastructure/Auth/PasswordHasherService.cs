using Microsoft.AspNetCore.Identity;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Auth;

public sealed class PasswordHasherService : IPasswordHasherService
{
    private readonly PasswordHasher<UserAccount> _hasher;

    public PasswordHasherService() : this(new PasswordHasher<UserAccount>()) { }

    public PasswordHasherService(PasswordHasher<UserAccount> hasher) => _hasher = hasher;

    public string HashPassword(UserAccount account, string password)
    {
        ArgumentNullException.ThrowIfNull(account);
        ArgumentException.ThrowIfNullOrWhiteSpace(password);
        return _hasher.HashPassword(account, password);
    }

    public bool VerifyPassword(UserAccount account, string hashedPassword, string providedPassword)
    {
        if (account is null || string.IsNullOrEmpty(hashedPassword) || providedPassword is null) return false;
        var result = _hasher.VerifyHashedPassword(account, hashedPassword, providedPassword);
        return result is PasswordVerificationResult.Success or PasswordVerificationResult.SuccessRehashNeeded;
    }
}
