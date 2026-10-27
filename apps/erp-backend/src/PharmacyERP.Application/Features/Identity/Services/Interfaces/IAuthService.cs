using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.DTOs;

namespace PharmacyERP.Application.Features.Identity.Services.Interfaces;

public interface IAuthService
{
    Task<Result<LoginResponse>> LoginAsync(LoginRequest request, CancellationToken ct = default);
    Task<Result<LoginResponse>> RefreshAsync(RefreshTokenRequest request, CancellationToken ct = default);
    Task<Result> LogoutAsync(LogoutRequest request, CancellationToken ct = default);
    Result<CurrentUserDto> GetCurrentUser();
}
