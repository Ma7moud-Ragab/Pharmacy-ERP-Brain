using System.Reflection;
using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Infrastructure.Persistence.Database;

public partial class PharmacyDbContext : DbContext
{
    private readonly ITenantContext _tenantContext;

    public PharmacyDbContext(DbContextOptions<PharmacyDbContext> options, ITenantContext tenantContext)
        : base(options)
    {
        _tenantContext = tenantContext;
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.ApplyConfigurationsFromAssembly(typeof(PharmacyDbContext).Assembly);

        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            // Apply Global Query Filter dynamically
            var orgIdProperty = entityType.FindProperty("OrganizationId");
            if (orgIdProperty != null && orgIdProperty.ClrType == typeof(Guid))
            {
                var method = typeof(PharmacyDbContext)
                    .GetMethod(nameof(ApplyTenantFilter), BindingFlags.NonPublic | BindingFlags.Instance)!
                    .MakeGenericMethod(entityType.ClrType);

                method.Invoke(this, new object[] { modelBuilder });
            }

            // Enforce Restrict Delete Behavior
            foreach (var foreignKey in entityType.GetForeignKeys())
            {
                foreignKey.DeleteBehavior = DeleteBehavior.Restrict;
            }
        }
    }

    private void ApplyTenantFilter<T>(ModelBuilder modelBuilder) where T : class
    {
        modelBuilder.Entity<T>().HasQueryFilter(e =>
            _tenantContext.IsSystemBypassEnabled ||
            EF.Property<Guid>(e, "OrganizationId") == _tenantContext.OrganizationId);
    }
}