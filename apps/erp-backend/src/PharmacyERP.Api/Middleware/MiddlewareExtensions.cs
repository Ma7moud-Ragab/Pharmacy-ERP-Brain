using Microsoft.AspNetCore.Builder;

namespace PharmacyERP.Api.Middleware;

public static class MiddlewareExtensions
{
    public static IApplicationBuilder UsePharmacyErpMiddlewares(this IApplicationBuilder app)
    {
        app.UseMiddleware<ExceptionHandlingMiddleware>();
        app.UseMiddleware<TraceparentMiddleware>();
        app.UseMiddleware<RuntimeModeGuardMiddleware>();
        app.UseHttpsRedirection();
        app.UseAuthentication();
        app.UseMiddleware<TenantResolutionMiddleware>();
        app.UseAuthorization();

        return app;
    }
}