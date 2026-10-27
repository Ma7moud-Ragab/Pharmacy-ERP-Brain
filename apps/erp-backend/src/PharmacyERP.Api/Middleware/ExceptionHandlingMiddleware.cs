using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Exceptions;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Api.Middleware;

public class ExceptionHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ExceptionHandlingMiddleware> _logger;

    public ExceptionHandlingMiddleware(RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An unhandled exception occurred during request processing.");
            await HandleExceptionAsync(context, ex);
        }
    }

    private static async Task HandleExceptionAsync(HttpContext context, Exception exception)
    {
        var (statusCode, errorCode, message, details) = MapException(exception);

        context.Response.ContentType = "application/json";
        context.Response.StatusCode = (int)statusCode;

        var traceId = context.Items["TraceId"]?.ToString() ?? context.TraceIdentifier ?? Guid.NewGuid().ToString();

        var errorBody = new ApiErrorBodyDto(errorCode, message, details, traceId);
        var errorEnvelope = new ApiErrorEnvelopeDto(errorBody);

        var result = JsonSerializer.Serialize(errorEnvelope);
        await context.Response.WriteAsync(result);
    }

    private static (HttpStatusCode StatusCode, string ErrorCode, string Message, IReadOnlyList<ApiErrorDetailDto> Details) MapException(Exception exception)
    {
        IReadOnlyList<ApiErrorDetailDto> emptyDetails = Array.Empty<ApiErrorDetailDto>();

        switch (exception)
        {
            case AppException appEx:
                return (MapErrorCodeToHttpStatus(appEx.ErrorCode), appEx.ErrorCode.ToString(), appEx.Message, appEx.Details);

            case IntegrationDomainException intEx when string.Equals(intEx.Message, "IDEMPOTENCY_MISMATCH", StringComparison.OrdinalIgnoreCase)
                                                    || intEx.GetType().Name.Contains("IdempotencyMismatch", StringComparison.OrdinalIgnoreCase):
                return (HttpStatusCode.Conflict, ErrorCode.IDEMPOTENCY_MISMATCH.ToString(), intEx.Message, emptyDetails);

            case DomainException domainEx:
                return (HttpStatusCode.UnprocessableEntity, ErrorCode.VALIDATION_ERROR.ToString(), domainEx.Message, emptyDetails);

            case JsonException:
                return (HttpStatusCode.BadRequest, ErrorCode.MALFORMED_REQUEST.ToString(), "Malformed JSON request payload.", emptyDetails);

            case UnauthorizedAccessException:
                return (HttpStatusCode.Forbidden, ErrorCode.FORBIDDEN.ToString(), "You do not have permission to perform this action.", emptyDetails);

            case KeyNotFoundException notFoundEx:
                return (HttpStatusCode.NotFound, ErrorCode.NOT_FOUND.ToString(), notFoundEx.Message, emptyDetails);

            case InvalidOperationException invalidOpEx:
                return (HttpStatusCode.BadRequest, ErrorCode.MALFORMED_REQUEST.ToString(), invalidOpEx.Message, emptyDetails);

            default:
                return (HttpStatusCode.InternalServerError, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.", emptyDetails);
        }
    }

    private static HttpStatusCode MapErrorCodeToHttpStatus(ErrorCode code) => code switch
    {
        ErrorCode.MALFORMED_REQUEST => HttpStatusCode.BadRequest,
        ErrorCode.UNAUTHORIZED => HttpStatusCode.Unauthorized,
        ErrorCode.FORBIDDEN => HttpStatusCode.Forbidden,
        ErrorCode.FORBIDDEN_BRANCH => HttpStatusCode.Forbidden,
        ErrorCode.NOT_FOUND => HttpStatusCode.NotFound,
        ErrorCode.CONFLICT => HttpStatusCode.Conflict,
        ErrorCode.INVALID_STATE_TRANSITION => HttpStatusCode.Conflict,
        ErrorCode.OUT_OF_STOCK => HttpStatusCode.Conflict,
        ErrorCode.IDEMPOTENCY_MISMATCH => HttpStatusCode.Conflict,
        ErrorCode.VALIDATION_ERROR => HttpStatusCode.UnprocessableEntity,
        ErrorCode.EXPIRY_POLICY_VIOLATION => HttpStatusCode.UnprocessableEntity,
        _ => HttpStatusCode.InternalServerError
    };
}