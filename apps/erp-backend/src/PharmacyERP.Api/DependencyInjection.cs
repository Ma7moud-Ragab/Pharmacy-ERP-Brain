using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi;
using PharmacyERP.Api.Auth;
using PharmacyERP.Infrastructure.Auth;

namespace PharmacyERP.Api;

public static class DependencyInjection
{
    public static IServiceCollection AddApiServices(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddControllers();
        services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
            .AddJwtBearer();
        services.AddOptions<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme)
            .Configure<JwksKeyProvider, IConfiguration>((options, keys, configuration) =>
            {
                options.MapInboundClaims = false;
                options.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuerSigningKey = true,
                    IssuerSigningKey = new RsaSecurityKey(keys.GetPublicKeyParameters()) { KeyId = keys.KeyId },
                    ValidAlgorithms = new[] { SecurityAlgorithms.RsaSha256 },
                    ValidateIssuer = true,
                    ValidIssuer = configuration["Jwt:Issuer"] ?? "PharmacyERP",
                    ValidateAudience = true,
                    ValidAudience = configuration["Jwt:Audience"] ?? "PharmacyERP.Api",
                    ValidateLifetime = true,
                    RequireExpirationTime = true,
                    RequireSignedTokens = true,
                    ClockSkew = TimeSpan.FromSeconds(30),
                    NameClaimType = "sub",
                    RoleClaimType = "role"
                };
            });
        services.AddIdentityAuthorizationPolicies();
        services.AddJwksEndpoint();

        services.AddSwaggerGen(options =>
        {
            options.SwaggerDoc("v1", new OpenApiInfo { Title = "Pharmacy ERP API", Version = "v1" });
        });
        return services;
    }
}
