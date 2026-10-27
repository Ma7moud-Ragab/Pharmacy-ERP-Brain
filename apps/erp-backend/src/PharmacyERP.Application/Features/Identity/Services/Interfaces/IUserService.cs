using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Identity.Services.Interfaces;

public interface IUserService
{
    Task<Result<PagedResult<UserDto>>> GetPagedAsync(Guid? branchId, UserRole? role, bool includeInactive, int page, int pageSize, CancellationToken ct = default);
    Task<Result<UserDto>> GetByIdAsync(Guid userId, CancellationToken ct = default);
    Task<Result<UserDto>> CreateAsync(CreateUserRequest request, CancellationToken ct = default);
    Task<Result<UserDto>> UpdateAsync(Guid userId, UpdateUserRequest request, CancellationToken ct = default);
    Task<Result> ResetPasswordAsync(Guid userId, ResetPasswordRequest request, CancellationToken ct = default);
    Task<Result> RevokeSessionsAsync(Guid userId, CancellationToken ct = default);
}
