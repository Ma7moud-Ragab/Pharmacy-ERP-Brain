using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using PharmacyERP.Infrastructure.Auth;

namespace PharmacyERP.Api.Auth;

public static class JwksEndpointExtensions
{
    public static IServiceCollection AddJwksEndpoint(this IServiceCollection services)
    {
        services.AddTransient<IStartupFilter, JwksEndpointStartupFilter>();
        return services;
    }
}

internal sealed class JwksEndpointStartupFilter : IStartupFilter
{
    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next)
        => app =>
        {
            app.UseMiddleware<JwksEndpointMiddleware>();
            next(app);
        };
}

internal sealed class JwksEndpointMiddleware
{
    private readonly RequestDelegate _next;

    public JwksEndpointMiddleware(RequestDelegate next) => _next = next;

    public async Task InvokeAsync(HttpContext context, JwksKeyProvider keyProvider)
    {
        if (HttpMethods.IsGet(context.Request.Method) &&
            string.Equals(context.Request.Path.Value, "/.well-known/jwks.json", StringComparison.Ordinal))
        {
            context.Response.StatusCode = StatusCodes.Status200OK;
            context.Response.ContentType = "application/jwk-set+json";
            await context.Response.WriteAsync(keyProvider.GetPublicJwksJson(), context.RequestAborted);
            return;
        }

        await _next(context);
    }
}
