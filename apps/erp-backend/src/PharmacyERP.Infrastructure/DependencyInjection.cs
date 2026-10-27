using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Interceptors;
using PharmacyERP.Infrastructure.Persistence.Repositories;
using PharmacyERP.Infrastructure.Persistence.Repositories.Integration;
using PharmacyERP.Infrastructure.Persistence.UoW;
using PharmacyERP.Infrastructure.Services.Context;

namespace PharmacyERP.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructureServices(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddHttpContextAccessor();

        services.AddScoped<ITenantContext, TenantContext>();
        services.AddScoped<ICurrentUser, CurrentUser>();
        services.AddSingleton<IDateTimeProvider, DateTimeProvider>();
        services.AddSingleton<IRuntimeModeProvider, RuntimeModeProvider>();

        services.AddScoped<TenantRlsConnectionInterceptor>();

        var connectionString = configuration.GetConnectionString("DefaultConnection")
            ?? "Host=localhost;Database=pharmacy_erp;Username=postgres;Password=postgres";

        services.AddDbContext<PharmacyDbContext>((sp, options) =>
        {
            var rlsInterceptor = sp.GetRequiredService<TenantRlsConnectionInterceptor>();
            options.UseNpgsql(connectionString)
                   .AddInterceptors(rlsInterceptor);
        });

        services.AddScoped<IUnitOfWork, UnitOfWork>();
        services.AddScoped(typeof(IGenericRepository<>), typeof(GenericRepository<>));

        services.AddScoped<IIdempotencyRepository, IdempotencyRepository>();
        services.AddScoped<IOutboxRepository, OutboxRepository>();
        services.AddScoped<IAuditLogRepository, AuditLogRepository>();

        return services;
    }
}