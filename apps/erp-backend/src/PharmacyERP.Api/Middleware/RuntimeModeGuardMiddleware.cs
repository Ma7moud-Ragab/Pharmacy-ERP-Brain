using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Http;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Api.Middleware;

public class RuntimeModeGuardMiddleware
{
    private readonly RequestDelegate _next;

    public RuntimeModeGuardMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, IRuntimeModeProvider runtimeModeProvider)
    {
        var path = context.Request.Path.Value ?? string.Empty;
        var method = context.Request.Method;
        var currentMode = runtimeModeProvider.CurrentMode;

        if (!path.StartsWith("/api/v1/canonical/capabilities", StringComparison.OrdinalIgnoreCase))
        {
            if (currentMode == ErpRuntimeMode.Cloud && IsBranchLocalOnlyMutation(path, method))
            {
                await WriteRouteNotAvailableAsync(context, "Branch-local stock mutations are forbidden on the Cloud runtime.");
                return;
            }

            if (currentMode == ErpRuntimeMode.BranchLocal && IsCloudOnlyEndpoint(path))
            {
                await WriteRouteNotAvailableAsync(context, "Cloud-only endpoints are not available on the BranchLocal runtime.");
                return;
            }
        }

        await _next(context);
    }

    private static bool IsBranchLocalOnlyMutation(string path, string method)
    {
        if (HttpMethods.IsGet(method) || HttpMethods.IsHead(method) || HttpMethods.IsOptions(method))
        {
            return false;
        }

        return path.StartsWith("/api/v1/inventory/adjustments", StringComparison.OrdinalIgnoreCase) ||
               path.StartsWith("/api/v1/inventory/opening-balances", StringComparison.OrdinalIgnoreCase) ||
               path.StartsWith("/api/v1/inventory/transfers", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsCloudOnlyEndpoint(string path)
    {
        return path.StartsWith("/api/v1/organizations", StringComparison.OrdinalIgnoreCase) ||
               path.StartsWith("/api/v1/canonical/", StringComparison.OrdinalIgnoreCase);
    }

    private static async Task WriteRouteNotAvailableAsync(HttpContext context, string message)
    {
        context.Response.StatusCode = (int)HttpStatusCode.NotFound;
        context.Response.ContentType = "application/json";

        var traceId = context.Items["TraceId"]?.ToString() ?? context.TraceIdentifier ?? Guid.NewGuid().ToString();
        var errorBody = new ApiErrorBodyDto(ErrorCode.NOT_FOUND.ToString(), message, Array.Empty<ApiErrorDetailDto>(), traceId);
        var envelope = new ApiErrorEnvelopeDto(errorBody);

        var json = JsonSerializer.Serialize(envelope);
        await context.Response.WriteAsync(json);
    }
}