namespace PharmacyERP.Application.Features.Integration.DTOs;

public record CanonicalCapabilitiesDto(
    int Stage,
    string RuntimeMode,
    IReadOnlyList<string> SupportedReads,
    IReadOnlyList<string> SupportedWrites
);