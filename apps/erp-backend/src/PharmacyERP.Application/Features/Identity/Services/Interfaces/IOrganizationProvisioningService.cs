using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.DTOs;

namespace PharmacyERP.Application.Features.Identity.Services.Interfaces;

public interface IOrganizationProvisioningService
{
    Task<Result<OrganizationDto>> CreateAsync(CreateOrganizationRequest request, CancellationToken ct = default);
}
