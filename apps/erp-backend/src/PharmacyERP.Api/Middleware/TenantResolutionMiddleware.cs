using Microsoft.AspNetCore.Http;
using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Api.Middleware;

public class TenantResolutionMiddleware
{
    private readonly RequestDelegate _next;

    private static readonly string[] SystemBypassPathPrefixes =
    {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/branch-enrollment",
        "/api/v1/organizations",
        "/api/v1/canonical/capabilities"
    };

    public TenantResolutionMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, ITenantContext tenantContext)
    {
        if (context.User.Identity?.IsAuthenticated == true)
        {
            var orgIdClaim = context.User.FindFirst("organization_id")?.Value;
            if (Guid.TryParse(orgIdClaim, out var organizationId) && organizationId != Guid.Empty)
            {
                tenantContext.SetTenant(organizationId);
            }
        }

        if (!tenantContext.IsTenantBound && IsSystemBypassPath(context.Request.Path.Value))
        {
            tenantContext.AllowSystemBypass();
        }

        await _next(context);
    }

    private static bool IsSystemBypassPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return false;
        }

        return SystemBypassPathPrefixes.Any(prefix =>
            path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
    }
}