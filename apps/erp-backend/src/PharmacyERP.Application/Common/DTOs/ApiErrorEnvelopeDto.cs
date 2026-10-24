using System.Text.Json.Serialization;

namespace PharmacyERP.Application.Common.DTOs;

public sealed record ApiErrorEnvelopeDto(
    [property: JsonPropertyName("error")] ApiErrorBodyDto Error
);