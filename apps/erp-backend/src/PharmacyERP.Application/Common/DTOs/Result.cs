using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Common.DTOs;

public class Result<T>
{
    public bool IsSuccess { get; }
    public T? Value { get; }
    public ErrorCode? ErrorCode { get; }
    public string? ErrorMessage { get; }
    public IReadOnlyList<ApiErrorDetailDto>? ErrorDetails { get; }

    private Result(bool isSuccess, T? value, ErrorCode? errorCode, string? errorMessage, IReadOnlyList<ApiErrorDetailDto>? errorDetails)
    {
        IsSuccess = isSuccess;
        Value = value;
        ErrorCode = errorCode;
        ErrorMessage = errorMessage;
        ErrorDetails = errorDetails;
    }

    public static Result<T> Success(T value) =>
        new Result<T>(true, value, null, null, null);

    public static Result<T> Failure(ErrorCode errorCode, string errorMessage, IReadOnlyList<ApiErrorDetailDto>? errorDetails = null) =>
        new Result<T>(false, default, errorCode, errorMessage, errorDetails);
}

public class Result //for void result
{
    public bool IsSuccess { get; }
    public ErrorCode? ErrorCode { get; }
    public string? ErrorMessage { get; }
    public IReadOnlyList<ApiErrorDetailDto>? ErrorDetails { get; }

    private Result(bool isSuccess, ErrorCode? errorCode, string? errorMessage, IReadOnlyList<ApiErrorDetailDto>? errorDetails)
    {
        IsSuccess = isSuccess;
        ErrorCode = errorCode;
        ErrorMessage = errorMessage;
        ErrorDetails = errorDetails;
    }

    public static Result Success() => new Result(true, null, null, null);

    public static Result Failure(ErrorCode errorCode, string errorMessage, IReadOnlyList<ApiErrorDetailDto>? errorDetails = null) =>
        new Result(false, errorCode, errorMessage, errorDetails);
}