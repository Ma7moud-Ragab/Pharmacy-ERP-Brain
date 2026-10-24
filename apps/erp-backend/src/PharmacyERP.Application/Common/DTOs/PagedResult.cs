namespace PharmacyERP.Application.Common.DTOs;

public sealed record PagedResult<T>(
    IReadOnlyList<T> Items,
    int Page,
    int PageSize,
    int TotalCount,
    string? NextCursor = null
);