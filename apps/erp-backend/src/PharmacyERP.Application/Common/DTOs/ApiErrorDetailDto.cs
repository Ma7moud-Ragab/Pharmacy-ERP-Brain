using System.Text.Json.Serialization;

namespace PharmacyERP.Application.Common.DTOs;

public sealed record ApiErrorDetailDto(
    [property: JsonPropertyName("field")] string Field,
    [property: JsonPropertyName("issue")] string Issue
);