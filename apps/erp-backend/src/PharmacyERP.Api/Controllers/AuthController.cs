using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1/auth")]
public sealed class AuthController : ControllerBase
{
    private readonly IAuthService _auth;
    private readonly ICurrentUser _currentUser;
    public AuthController(IAuthService auth, ICurrentUser currentUser) { _auth = auth; _currentUser = currentUser; }

    [AllowAnonymous, HttpPost("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _auth.LoginAsync(request, ct), _currentUser.TraceId);

    [AllowAnonymous, HttpPost("refresh")]
    public async Task<IActionResult> Refresh([FromBody] RefreshTokenRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _auth.RefreshAsync(request, ct), _currentUser.TraceId);

    [Authorize, HttpPost("logout")]
    public async Task<IActionResult> Logout([FromBody] LogoutRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _auth.LogoutAsync(request, ct), _currentUser.TraceId);

    [Authorize, HttpGet("me")]
    public IActionResult Me()
        => ApiResultMapper.ToActionResult(this, _auth.GetCurrentUser(), _currentUser.TraceId);
}

internal static class ApiResultMapper
{
    public static IActionResult ToActionResult(ControllerBase controller, Result result, string traceId)
    {
        if (result.IsSuccess) return controller.NoContent();
        var code = result.ErrorCode ?? ErrorCode.VALIDATION_ERROR;
        var status = code switch
        {
            ErrorCode.MALFORMED_REQUEST => 400,
            ErrorCode.UNAUTHORIZED => 401,
            ErrorCode.FORBIDDEN or ErrorCode.FORBIDDEN_BRANCH => 403,
            ErrorCode.NOT_FOUND => 404,
            ErrorCode.CONFLICT or ErrorCode.INVALID_STATE_TRANSITION or ErrorCode.OUT_OF_STOCK or ErrorCode.IDEMPOTENCY_MISMATCH => 409,
            ErrorCode.VALIDATION_ERROR or ErrorCode.EXPIRY_POLICY_VIOLATION => 422,
            _ => 500
        };
        var body = new ApiErrorEnvelopeDto(new ApiErrorBodyDto(code.ToString(), result.ErrorMessage ?? "Request failed.", result.ErrorDetails ?? Array.Empty<ApiErrorDetailDto>(), traceId));
        return controller.StatusCode(status, body);
    }

    public static IActionResult ToActionResult<T>(ControllerBase controller, Result<T> result, string traceId)
    {
        if (result.IsSuccess) return controller.Ok(result.Value);
        var code = result.ErrorCode ?? ErrorCode.VALIDATION_ERROR;
        var status = code switch
        {
            ErrorCode.MALFORMED_REQUEST => 400,
            ErrorCode.UNAUTHORIZED => 401,
            ErrorCode.FORBIDDEN or ErrorCode.FORBIDDEN_BRANCH => 403,
            ErrorCode.NOT_FOUND => 404,
            ErrorCode.CONFLICT or ErrorCode.INVALID_STATE_TRANSITION or ErrorCode.OUT_OF_STOCK or ErrorCode.IDEMPOTENCY_MISMATCH => 409,
            ErrorCode.VALIDATION_ERROR or ErrorCode.EXPIRY_POLICY_VIOLATION => 422,
            _ => 500
        };
        var body = new ApiErrorEnvelopeDto(new ApiErrorBodyDto(code.ToString(), result.ErrorMessage ?? "Request failed.", result.ErrorDetails ?? Array.Empty<ApiErrorDetailDto>(), traceId));
        return controller.StatusCode(status, body);
    }
}
