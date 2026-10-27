using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public interface IEmployeeRepository : IGenericRepository<Employee>
{
    Task<Employee?> GetByIdAsync(Guid organizationId, Guid employeeId, CancellationToken ct = default);
    Task<bool> ExistsByEmployeeNoAsync(Guid organizationId, Guid branchId, string employeeNo, CancellationToken ct = default);
    Task<PagedResult<Employee>> GetPagedAsync(Guid organizationId, Guid? branchId, bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default);
}
