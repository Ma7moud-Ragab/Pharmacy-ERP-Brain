using PharmacyERP.Application.Features.Integration.DTOs;

namespace PharmacyERP.Application.Features.Integration.Services.Interfaces;

public interface ICanonicalCapabilitiesService
{
    CanonicalCapabilitiesDto GetCapabilities();
}