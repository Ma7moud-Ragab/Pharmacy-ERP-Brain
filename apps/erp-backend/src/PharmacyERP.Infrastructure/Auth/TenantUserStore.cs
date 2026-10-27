using Microsoft.AspNetCore.Identity;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Auth;

/// <summary>A small Identity store adapter over the existing tenant-aware USER_ACCOUNT table.</summary>
public sealed class TenantUserStore : IUserPasswordStore<UserAccount>
{
    private readonly IUserAccountRepository _users;
    private readonly IUnitOfWork _unitOfWork;
    private readonly ITenantContext _tenant;
    private readonly IDateTimeProvider _clock;

    public TenantUserStore(IUserAccountRepository users, IUnitOfWork unitOfWork, ITenantContext tenant, IDateTimeProvider clock)
    {
        _users = users;
        _unitOfWork = unitOfWork;
        _tenant = tenant;
        _clock = clock;
    }

    public Task<string> GetUserIdAsync(UserAccount user, CancellationToken cancellationToken) => Task.FromResult(user.UserId.ToString());
    public Task<string?> GetUserNameAsync(UserAccount user, CancellationToken cancellationToken) => Task.FromResult<string?>(user.Username);
    public Task<string?> GetNormalizedUserNameAsync(UserAccount user, CancellationToken cancellationToken) => Task.FromResult<string?>(user.NormalizedUsername);
    public Task<string?> GetPasswordHashAsync(UserAccount user, CancellationToken cancellationToken) => Task.FromResult<string?>(user.PasswordHash);
    public Task<bool> HasPasswordAsync(UserAccount user, CancellationToken cancellationToken) => Task.FromResult(!string.IsNullOrEmpty(user.PasswordHash));

    // Account identifiers are immutable after creation in the domain model.
    public Task SetUserNameAsync(UserAccount user, string? userName, CancellationToken cancellationToken)
        => Task.FromException(new NotSupportedException("Usernames are immutable after account creation."));
    public Task SetNormalizedUserNameAsync(UserAccount user, string? normalizedName, CancellationToken cancellationToken)
        => Task.FromException(new NotSupportedException("Normalized usernames are immutable after account creation."));
    public Task SetPasswordHashAsync(UserAccount user, string? passwordHash, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(passwordHash)) return Task.FromException(new ArgumentException("Password hash is required."));
        user.UpdatePasswordHash(passwordHash, _clock.UtcNow);
        return Task.CompletedTask;
    }

    public async Task<IdentityResult> CreateAsync(UserAccount user, CancellationToken cancellationToken)
    {
        await _users.AddAsync(user, cancellationToken);
        await _unitOfWork.SaveChangesAsync(cancellationToken);
        return IdentityResult.Success;
    }

    public async Task<IdentityResult> UpdateAsync(UserAccount user, CancellationToken cancellationToken)
    {
        await _unitOfWork.SaveChangesAsync(cancellationToken);
        return IdentityResult.Success;
    }

    public async Task<IdentityResult> DeleteAsync(UserAccount user, CancellationToken cancellationToken)
    {
        user.Deactivate();
        await _unitOfWork.SaveChangesAsync(cancellationToken);
        return IdentityResult.Success;
    }

    public async Task<UserAccount?> FindByIdAsync(string userId, CancellationToken cancellationToken)
        => _tenant.OrganizationId is Guid organizationId && Guid.TryParse(userId, out var id)
            ? await _users.GetByIdWithAccessAsync(organizationId, id, cancellationToken)
            : null;

    public async Task<UserAccount?> FindByNameAsync(string normalizedUserName, CancellationToken cancellationToken)
        => _tenant.OrganizationId is Guid organizationId
            ? await _users.GetForLoginAsync(organizationId, normalizedUserName, cancellationToken)
            : null;

    public void Dispose() { }
}
