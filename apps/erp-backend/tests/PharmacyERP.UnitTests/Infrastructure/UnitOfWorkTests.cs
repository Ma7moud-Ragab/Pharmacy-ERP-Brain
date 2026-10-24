using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Triggers;
using PharmacyERP.Infrastructure.Persistence.UoW;
using PharmacyERP.Infrastructure.Services.Context;
using Xunit;

namespace PharmacyERP.UnitTests.Infrastructure;

public class UnitOfWorkTests
{
    private static PharmacyDbContext CreateInMemoryContext(TenantContext tenantContext)
    {
        var options = new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString())
            .ConfigureWarnings(w => w.Ignore(InMemoryEventId.TransactionIgnoredWarning))
            .Options;

        return new PharmacyDbContext(options, tenantContext);
    }

    [Fact]
    public async Task BeginAndCommitTransaction_ManagesActiveTransactionStateCorrectly()
    {
        var tenantContext = new TenantContext();
        tenantContext.SetTenant(Guid.NewGuid());

        await using var dbContext = CreateInMemoryContext(tenantContext);
        await using var uow = new UnitOfWork(dbContext, tenantContext);

        Assert.False(uow.HasActiveTransaction);

        await uow.BeginTransactionAsync();
        Assert.True(uow.HasActiveTransaction);

        await Assert.ThrowsAsync<InvalidOperationException>(() => uow.BeginTransactionAsync());

        await uow.CommitTransactionAsync();
        Assert.False(uow.HasActiveTransaction);
    }

    [Fact]
    public async Task RollbackTransaction_ClearsActiveTransactionState()
    {
        var tenantContext = new TenantContext();
        tenantContext.SetTenant(Guid.NewGuid());

        await using var dbContext = CreateInMemoryContext(tenantContext);
        await using var uow = new UnitOfWork(dbContext, tenantContext);

        await uow.BeginTransactionAsync();
        Assert.True(uow.HasActiveTransaction);

        await uow.RollbackTransactionAsync();
        Assert.False(uow.HasActiveTransaction);
    }

    [Fact]
    public void RlsAndAuditProtectionSql_GeneratesValidForceRlsAndImmutableAuditSql()
    {
        var sql = RlsAndAuditProtectionSql.GenerateCompleteStage1SecuritySql();

        Assert.Contains("ENABLE ROW LEVEL SECURITY", sql);
        Assert.Contains("FORCE ROW LEVEL SECURITY", sql);
        Assert.Contains("current_setting('app.organization_id', true)", sql);
        Assert.Contains("current_setting('app.system_bypass', true)", sql);
        Assert.Contains("prevent_audit_log_mutation", sql);
    }
}