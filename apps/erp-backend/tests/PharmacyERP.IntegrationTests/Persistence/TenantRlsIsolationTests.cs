using Microsoft.EntityFrameworkCore;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Services.Context;
using Xunit;

namespace PharmacyERP.IntegrationTests.Persistence;

public class TenantRlsIsolationTests
{
    [Fact]
    public async Task GlobalQueryFilter_IsolatesOrganizationData_AndBlocksCrossTenantLeakage()
    {
        var dbName = Guid.NewGuid().ToString();
        var orgA = Guid.NewGuid();
        var orgB = Guid.NewGuid();

        var tenantA = new TenantContext();
        tenantA.SetTenant(orgA);

        var optionsA = new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseInMemoryDatabase(dbName)
            .Options;

        await using (var contextA = new PharmacyDbContext(optionsA, tenantA))
        {
            contextA.AuditLogs.Add(new AuditLog(
                orgA, null, Guid.NewGuid(), null, AuditActorType.USER,
                "CREATE", "catalog", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-a", DateTimeOffset.UtcNow));
            await contextA.SaveChangesAsync();
        }

        var tenantB = new TenantContext();
        tenantB.SetTenant(orgB);

        await using (var contextB = new PharmacyDbContext(optionsA, tenantB))
        {
            var logsForB = await contextB.AuditLogs.ToListAsync();
            Assert.Empty(logsForB);

            contextB.AuditLogs.Add(new AuditLog(
                orgB, null, Guid.NewGuid(), null, AuditActorType.USER,
                "CREATE", "catalog", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-b", DateTimeOffset.UtcNow));
            await contextB.SaveChangesAsync();
        }

        await using (var contextAVerify = new PharmacyDbContext(optionsA, tenantA))
        {
            var logsForA = await contextAVerify.AuditLogs.ToListAsync();
            Assert.Single(logsForA);
            Assert.Equal(orgA, logsForA[0].OrganizationId);
        }

        var unboundTenant = new TenantContext();
        await using (var unboundContext = new PharmacyDbContext(optionsA, unboundTenant))
        {
            var leakedLogs = await unboundContext.AuditLogs.ToListAsync();
            Assert.Empty(leakedLogs);
        }
    }
}