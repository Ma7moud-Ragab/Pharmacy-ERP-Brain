using System.Text.Json.Serialization;

namespace PharmacyERP.Application.Common.DTOs;

public sealed record ApiErrorBodyDto(
    [property: JsonPropertyName("code")] string Code,
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("details")] IReadOnlyList<ApiErrorDetailDto> Details,
    [property: JsonPropertyName("trace_id")] string TraceId
);