
using PharmacyERP.Api.Middleware;
using PharmacyERP.Application;
using PharmacyERP.Infrastructure;


namespace PharmacyERP.Api
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var builder = WebApplication.CreateBuilder(args);

            builder.Services.AddApplicationServices();
            builder.Services.AddInfrastructureServices(builder.Configuration);
            builder.Services.AddApiServices();

            var app = builder.Build();



            if (app.Environment.IsDevelopment())
            {
                app.UseSwagger();
                app.UseSwaggerUI(options =>
                {
                    options.SwaggerEndpoint("/swagger/v1/swagger.json", "Pharmacy ERP API v1");
                });
            }
            app.UsePharmacyErpMiddlewares();

            app.MapControllers();

            app.Run();
        }
    }
}