using Microsoft.Extensions.DependencyInjection;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Features.Integration.Services.Implementations;
using PharmacyERP.Application.Features.Integration.Services.Interfaces;

namespace PharmacyERP.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddApplicationServices(this IServiceCollection services)
    {
        services.AddScoped<IIdempotencyService, IdempotencyService>();
        services.AddScoped<IOutboxService, OutboxService>();
        services.AddScoped<IAuditLogger, AuditLogger>();
        services.AddScoped<ICanonicalCapabilitiesService, CanonicalCapabilitiesService>();

        return services;
    }
}