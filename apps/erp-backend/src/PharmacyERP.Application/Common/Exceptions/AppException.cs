using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Common.Exceptions;

public class AppException : Exception
{
    public ErrorCode ErrorCode { get; }
    public IReadOnlyList<ApiErrorDetailDto> Details { get; }

    public AppException(ErrorCode errorCode, string message, IReadOnlyList<ApiErrorDetailDto>? details = null)
        : base(message)
    {
        ErrorCode = errorCode;
        Details = details ?? Array.Empty<ApiErrorDetailDto>();
    }
}