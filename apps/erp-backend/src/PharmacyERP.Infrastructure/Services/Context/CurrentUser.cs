using System.Diagnostics;
using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Infrastructure.Services.Context;

public class CurrentUser : ICurrentUser
{
    private readonly IHttpContextAccessor _httpContextAccessor;

    public CurrentUser(IHttpContextAccessor httpContextAccessor)
    {
        _httpContextAccessor = httpContextAccessor;
    }

    private ClaimsPrincipal? Principal => _httpContextAccessor.HttpContext?.User;

    public bool IsAuthenticated => Principal?.Identity?.IsAuthenticated == true;

    public Guid? UserId => TryGetGuidClaim(ClaimTypes.NameIdentifier) ?? TryGetGuidClaim("sub");

    public Guid? EmployeeId => TryGetGuidClaim("employee_id");

    public Guid? OrganizationId => TryGetGuidClaim("organization_id");

    public string? Role => Principal?.FindFirst(ClaimTypes.Role)?.Value ?? Principal?.FindFirst("role")?.Value;

    public string? BranchScope => Principal?.FindFirst("branch_scope")?.Value;

    public IReadOnlySet<Guid> AuthorizedBranchIds
    {
        get
        {
            if (!IsAuthenticated || Principal == null)
            {
                return new HashSet<Guid>();
            }

            var branchClaims = Principal.FindAll("branch_ids").Select(c => c.Value);
            var result = new HashSet<Guid>();

            foreach (var claimValue in branchClaims)
            {
                foreach (var part in claimValue.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                {
                    if (Guid.TryParse(part, out var branchId))
                    {
                        result.Add(branchId);
                    }
                }
            }

            return result;
        }
    }

    public IReadOnlySet<string> Scopes
    {
        get
        {
            if (!IsAuthenticated || Principal == null)
            {
                return new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            }

            var scopeClaims = Principal.FindAll("scope").Concat(Principal.FindAll("scp")).Select(c => c.Value);
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            foreach (var raw in scopeClaims)
            {
                foreach (var item in raw.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                {
                    result.Add(item);
                }
            }

            return result;
        }
    }

    public string TraceId
    {
        get
        {
            var httpContext = _httpContextAccessor.HttpContext;
            if (httpContext != null)
            {
                if (httpContext.Items.TryGetValue("TraceId", out var itemTraceId) && itemTraceId is string s && !string.IsNullOrWhiteSpace(s))
                {
                    return s;
                }

                var traceparent = httpContext.Request.Headers["traceparent"].FirstOrDefault();
                if (!string.IsNullOrWhiteSpace(traceparent))
                {
                    return traceparent;
                }

                var customHeader = httpContext.Request.Headers["X-Trace-Id"].FirstOrDefault();
                if (!string.IsNullOrWhiteSpace(customHeader))
                {
                    return customHeader;
                }

                if (!string.IsNullOrWhiteSpace(httpContext.TraceIdentifier))
                {
                    return httpContext.TraceIdentifier;
                }
            }

            return Activity.Current?.Id ?? $"00-{Guid.NewGuid():N}-{Guid.NewGuid().ToString("N")[..16]}-01";
        }
    }

    public bool CanAccessBranch(Guid branchId)
    {
        if (!IsAuthenticated)
        {
            return false;
        }

        if (string.Equals(BranchScope, "ALL", StringComparison.OrdinalIgnoreCase) &&
            string.Equals(Role, "Admin", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return AuthorizedBranchIds.Contains(branchId);
    }

    private Guid? TryGetGuidClaim(string claimType)
    {
        var value = Principal?.FindFirst(claimType)?.Value;
        return Guid.TryParse(value, out var parsed) ? parsed : null;
    }
}