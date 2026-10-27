using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Integration.DTOs;
using PharmacyERP.Application.Features.Integration.Services.Interfaces;

namespace PharmacyERP.Application.Features.Integration.Services.Implementations;

public class CanonicalCapabilitiesService : ICanonicalCapabilitiesService
{
    private readonly IRuntimeModeProvider _runtimeModeProvider;

    public CanonicalCapabilitiesService(IRuntimeModeProvider runtimeModeProvider)
    {
        _runtimeModeProvider = runtimeModeProvider;
    }

    public CanonicalCapabilitiesDto GetCapabilities()
    {
        return new CanonicalCapabilitiesDto(
            Stage: 1,
            RuntimeMode: _runtimeModeProvider.CurrentMode.ToString(),
            SupportedReads: new[] { "products", "inventory" },
            SupportedWrites: new[] { "configuration.products", "configuration.reorder-rules" }
        );
    }
}