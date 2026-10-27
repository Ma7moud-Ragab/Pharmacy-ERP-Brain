using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public interface IOrganizationRepository
{
    Task<Organization?> GetActiveByCodeAsync(string organizationCode, CancellationToken ct = default);
    Task<bool> ExistsByCodeAsync(string organizationCode, CancellationToken ct = default);
    Task AddAsync(Organization organization, CancellationToken ct = default);
}
