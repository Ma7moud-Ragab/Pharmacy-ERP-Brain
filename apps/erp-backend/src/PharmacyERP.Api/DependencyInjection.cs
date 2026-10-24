using Microsoft.OpenApi;

namespace PharmacyERP.Api;

public static class DependencyInjection
{
    public static IServiceCollection AddApiServices(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddControllers();

        services.AddSwaggerGen(options =>
        {
            options.SwaggerDoc("v1", new OpenApiInfo
            {
                Title = "Pharmacy ERP API",
                Version = "v1"
            });
        });

        return services;
    }
}