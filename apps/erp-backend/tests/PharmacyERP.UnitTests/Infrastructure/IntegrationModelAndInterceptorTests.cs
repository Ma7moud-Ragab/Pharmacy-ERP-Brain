using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using Moq;
using Moq.Protected;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Interceptors;
using PharmacyERP.Infrastructure.Services.Context;
using Xunit;

namespace PharmacyERP.UnitTests.Infrastructure;

public class IntegrationModelAndInterceptorTests
{
    private static PharmacyDbContext CreateContext(TenantContext tenantContext)
    {
        var options = new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseNpgsql("Host=localhost;Database=dummy_test_db;Username=postgres;Password=postgres")
            .Options;

        return new PharmacyDbContext(options, tenantContext);
    }

    [Fact]
    public void EfModel_HasPartialUniqueIndexesAndJsonbColumnsConfigured()
    {
        var tenantContext = new TenantContext();
        using var context = CreateContext(tenantContext);
        var model = context.Model;

        var idempotencyEntity = model.FindEntityType(typeof(IdempotencyRecord))!;
        Assert.Equal("integration", idempotencyEntity.GetSchema());
        Assert.Equal("IDEMPOTENCY_RECORD", idempotencyEntity.GetTableName());

        var indexes = idempotencyEntity.GetIndexes().ToList();
        Assert.Contains(indexes, i => i.IsUnique && i.GetFilter() == "branch_id IS NOT NULL");
        Assert.Contains(indexes, i => i.IsUnique && i.GetFilter() == "branch_id IS NULL");

        var hashProp = idempotencyEntity.FindProperty(nameof(IdempotencyRecord.PayloadHash))!;
        Assert.Equal("char(64)", hashProp.GetColumnType());

        Assert.NotEmpty(idempotencyEntity.GetDeclaredQueryFilters());

        var auditEntity = model.FindEntityType(typeof(AuditLog))!;
        Assert.NotEmpty(auditEntity.GetDeclaredQueryFilters());
    }

    [Fact]
    public void TenantRlsConnectionInterceptor_WithoutActiveTransaction_ThrowsInvalidOperationException()
    {
        var tenantContext = new TenantContext();
        tenantContext.SetTenant(Guid.NewGuid());

        var interceptor = new TenantRlsConnectionInterceptor(tenantContext);

        var commandMock = new Mock<DbCommand>();
        commandMock.Setup(x => x.CommandText).Returns("SELECT * FROM PRODUCTS");
        commandMock.Protected().Setup<DbTransaction>("DbTransaction").Returns((DbTransaction?)null);

        Assert.Throws<InvalidOperationException>(() =>
            interceptor.ScalarExecuting(commandMock.Object, null!, default));
    }

    [Fact]
    public void TenantRlsConnectionInterceptor_WithoutTenantBound_ThrowsUnauthorizedAccessException()
    {
        var tenantContext = new TenantContext();
        var interceptor = new TenantRlsConnectionInterceptor(tenantContext);

        var transactionMock = new Mock<DbTransaction>();
        var commandMock = new Mock<DbCommand>();
        commandMock.Setup(x => x.CommandText).Returns("SELECT * FROM PRODUCTS");
        commandMock.Protected().Setup<DbTransaction>("DbTransaction").Returns(transactionMock.Object);

        Assert.Throws<UnauthorizedAccessException>(() =>
            interceptor.ScalarExecuting(commandMock.Object, null!, default));
    }

    [Fact]
    public void TenantRlsConnectionInterceptor_WithSystemBypassAllowed_DoesNotThrow()
    {
        var tenantContext = new TenantContext();
        tenantContext.AllowSystemBypass();

        var interceptor = new TenantRlsConnectionInterceptor(tenantContext);

        var commandMock = new Mock<DbCommand>();
        commandMock.Setup(x => x.CommandText).Returns("SELECT * FROM PRODUCTS");

        var result = interceptor.ScalarExecuting(commandMock.Object, null!, default);

        Assert.Equal(default, result);
    }

}