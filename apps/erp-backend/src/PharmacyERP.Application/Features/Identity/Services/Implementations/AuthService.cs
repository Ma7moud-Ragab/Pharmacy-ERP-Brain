using System.Security.Cryptography;
using System.Text;
using PharmacyERP.Application.Common.Constants;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Identity.Services.Implementations;

public sealed class AuthService : IAuthService
{
    private static readonly TimeSpan RefreshLifetime = TimeSpan.FromDays(30);
    private readonly IOrganizationRepository _organizations;
    private readonly IUserAccountRepository _users;
    private readonly IUserRefreshTokenRepository _tokens;
    private readonly IPasswordHasherService _passwords;
    private readonly IJwtTokenGenerator _jwt;
    private readonly IUnitOfWork _unitOfWork;
    private readonly IAuditLogger _audit;
    private readonly IOutboxService _outbox;
    private readonly ITenantContext _tenant;
    private readonly ICurrentUser _currentUser;
    private readonly IDateTimeProvider _clock;

    public AuthService(IOrganizationRepository organizations, IUserAccountRepository users, IUserRefreshTokenRepository tokens,
        IPasswordHasherService passwords, IJwtTokenGenerator jwt, IUnitOfWork unitOfWork, IAuditLogger audit,
        IOutboxService outbox, ITenantContext tenant, ICurrentUser currentUser, IDateTimeProvider clock)
    {
        _organizations = organizations; _users = users; _tokens = tokens; _passwords = passwords; _jwt = jwt;
        _unitOfWork = unitOfWork; _audit = audit; _outbox = outbox; _tenant = tenant; _currentUser = currentUser; _clock = clock;
    }

    public async Task<Result<LoginResponse>> LoginAsync(LoginRequest request, CancellationToken ct = default)
    {
        _tenant.AllowSystemBypass();
        await _unitOfWork.BeginTransactionAsync(ct);
        var organization = await _organizations.GetActiveByCodeAsync(request.OrganizationCode, ct);
        await _unitOfWork.RollbackTransactionAsync(ct);
        if (organization is null)
            return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidCredentials);

        _tenant.SetTenant(organization.OrganizationId);
        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var normalizedUsername = request.Username.Trim().ToUpperInvariant();
            var user = await _users.GetForLoginAsync(organization.OrganizationId, normalizedUsername, ct);
            if (user is null)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidCredentials);
            }

            var now = _clock.UtcNow;
            if (!user.IsActive || !user.Employee.IsActive)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.FORBIDDEN, ErrorMessages.AccountInactive);
            }
            if (user.LockoutEnd > now)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.FORBIDDEN, ErrorMessages.AccountLocked);
            }

            if (!_passwords.VerifyPassword(user, user.PasswordHash, request.Password))
            {
                user.RecordLoginFailure(now, 5, TimeSpan.FromMinutes(15));
                await _audit.LogAsync("auth.login.failed", "identity", "USER_ACCOUNT", user.UserId,
                    null, new { user.AccessFailedCount, user.LockoutEnd }, branchId: user.Employee.BranchId, ct: ct);
                await _unitOfWork.CommitTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidCredentials);
            }

            user.RecordLoginSuccess(now);
            var response = await IssueTokensAsync(user, Guid.NewGuid(), now, ct);
            await _audit.LogAsync("auth.login.succeeded", "identity", "USER_ACCOUNT", user.UserId, null,
                new { user.LastLoginAt }, user.Employee.BranchId, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);
            return Result<LoginResponse>.Success(response);
        }
        catch
        {
            await _unitOfWork.RollbackTransactionAsync(ct);
            throw;
        }
    }

    public async Task<Result<LoginResponse>> RefreshAsync(RefreshTokenRequest request, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(request.RefreshToken))
            return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);

        var hash = HashToken(request.RefreshToken);
        _tenant.AllowSystemBypass();
        await _unitOfWork.BeginTransactionAsync(ct);
        var discovered = await _tokens.GetByTokenHashAsync(hash, ct);
        await _unitOfWork.RollbackTransactionAsync(ct);
        if (discovered is null)
            return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);

        _tenant.SetTenant(discovered.OrganizationId);
        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var token = await _tokens.GetByTokenHashAsync(hash, ct);
            if (token is null)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);
            }
            var now = _clock.UtcNow;
            if (token.ConsumedAt.HasValue)
            {
                await _tokens.RevokeFamilyAsync(token.OrganizationId, token.TokenFamilyId, now, ct);
                await _audit.LogAsync("auth.refresh.reuse_detected", "identity", "USER_REFRESH_TOKEN", token.RefreshTokenId,
                    null, new { token.TokenFamilyId }, ct: ct);
                await _unitOfWork.CommitTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);
            }
            if (!token.IsActive(now) || !token.UserAccount.IsActive || !token.UserAccount.Employee.IsActive)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<LoginResponse>(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);
            }

            token.Consume(now);
            var response = await IssueTokensAsync(token.UserAccount, token.TokenFamilyId, now, ct);
            await _audit.LogAsync("auth.refresh.succeeded", "identity", "USER_REFRESH_TOKEN", token.RefreshTokenId,
                null, new { token.TokenFamilyId }, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);
            return Result<LoginResponse>.Success(response);
        }
        catch
        {
            await _unitOfWork.RollbackTransactionAsync(ct);
            throw;
        }
    }

    public async Task<Result> LogoutAsync(LogoutRequest request, CancellationToken ct = default)
    {
        if (_tenant.OrganizationId is not Guid organizationId || _currentUser.UserId is not Guid userId)
            return IdentityResults.Failure(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        if (string.IsNullOrWhiteSpace(request.RefreshToken))
            return IdentityResults.Failure(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);

        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var token = await _tokens.GetByTokenHashAsync(HashToken(request.RefreshToken), ct);
            if (token is null || token.OrganizationId != organizationId || token.UserId != userId)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure(ErrorCode.UNAUTHORIZED, ErrorMessages.InvalidRefreshToken);
            }
            await _tokens.RevokeFamilyAsync(organizationId, token.TokenFamilyId, _clock.UtcNow, ct);
            await _audit.LogAsync("auth.logout", "identity", "USER_ACCOUNT", userId, null,
                new { token.TokenFamilyId }, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);
            return Result.Success();
        }
        catch
        {
            await _unitOfWork.RollbackTransactionAsync(ct);
            throw;
        }
    }

    public Result<CurrentUserDto> GetCurrentUser()
    {
        if (!_currentUser.IsAuthenticated || _currentUser.UserId is not Guid userId || _currentUser.EmployeeId is not Guid employeeId || _currentUser.OrganizationId is not Guid organizationId)
            return IdentityResults.Failure<CurrentUserDto>(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        var role = Enum.TryParse<UserRole>(_currentUser.Role, out var parsedRole) ? parsedRole : UserRole.Cashier;
        return Result<CurrentUserDto>.Success(new CurrentUserDto(userId, employeeId, organizationId, string.Empty,
            _currentUser.Role ?? string.Empty, _currentUser.BranchScope ?? BranchScope.ASSIGNED.ToString(),
            _currentUser.AuthorizedBranchIds.ToArray(), _currentUser.Scopes.ToArray()));
    }

    private async Task<LoginResponse> IssueTokensAsync(UserAccount user, Guid familyId, DateTimeOffset now, CancellationToken ct)
    {
        var branchIds = user.BranchAccesses.Select(x => x.BranchId).Distinct().ToArray();
        var access = _jwt.GenerateAccessToken(user, branchIds);
        var refreshText = Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
        var refresh = UserRefreshToken.Create(user.OrganizationId, user.UserId, HashToken(refreshText), familyId, now, now.Add(RefreshLifetime));
        await _tokens.AddAsync(refresh, ct);
        return new LoginResponse(access.Token, access.ExpiresAt, refreshText,
            CurrentUserDtoMapper.From(user, branchIds, ScopeNames(user.Role)));
    }

    private static byte[] HashToken(string value) => SHA256.HashData(Encoding.UTF8.GetBytes(value));
    private static string Base64UrlEncode(byte[] value) => Convert.ToBase64String(value).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static string[] ScopeNames(UserRole role) => role switch
    {
        UserRole.Admin => new[] { "user:admin", "branch:admin", "employee:admin", "inventory:read", "inventory:write", "sales:read", "sales:write" },
        UserRole.Pharmacist => new[] { "inventory:read", "inventory:write", "sales:read", "sales:write" },
        UserRole.Cashier => new[] { "inventory:read", "sales:read", "sales:write" },
        _ => Array.Empty<string>()
    };
}
