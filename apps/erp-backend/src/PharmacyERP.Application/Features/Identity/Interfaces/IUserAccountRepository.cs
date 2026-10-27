using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public interface IUserAccountRepository
{
    Task<UserAccount?> GetForLoginAsync(Guid organizationId, string normalizedUsername, CancellationToken ct = default);
    Task<UserAccount?> GetByIdWithAccessAsync(Guid organizationId, Guid userId, CancellationToken ct = default);
    Task<bool> ExistsByUsernameAsync(Guid organizationId, string normalizedUsername, CancellationToken ct = default);
    Task<bool> ExistsForEmployeeAsync(Guid organizationId, Guid employeeId, CancellationToken ct = default);
    Task<PagedResult<UserAccount>> GetPagedAsync(Guid organizationId, Guid? branchId, UserRole? role, bool includeInactive, int page, int pageSize, CancellationToken ct = default);
    Task ReplaceBranchAccessAsync(Guid organizationId, Guid userId, IReadOnlyCollection<Guid> branchIds, CancellationToken ct = default);
    Task AddAsync(UserAccount userAccount, CancellationToken ct = default);
}
