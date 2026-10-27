using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Services.Context;

namespace PharmacyERP.UnitTests.Infrastructure;

public class IdentityModelConfigurationTests
{
    private static DbContextOptions<PharmacyDbContext> BuildOptions() =>
        new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseNpgsql("Host=localhost;Database=pharmacy_model_test;Username=test;Password=test")
            .Options;

    private static IModel BuildModel()
    {
        using var context = new PharmacyDbContext(BuildOptions(), new TenantContext());
        return context.Model;
    }

    private static IModel BuildDesignTimeModel()
    {
        using var context = new PharmacyDbContext(BuildOptions(), new TenantContext());
        return context.GetService<IDesignTimeModel>().Model;
    }

    [Fact]
    public void AllIdentityEntities_MapToIdentitySchemaAndExpectedTableNames()
    {
        var model = BuildModel();

        var expected = new Dictionary<Type, string>
        {
            [typeof(Organization)] = "ORGANIZATION",
            [typeof(Branch)] = "BRANCH",
            [typeof(Employee)] = "EMPLOYEE",
            [typeof(UserAccount)] = "USER_ACCOUNT",
            [typeof(UserBranchAccess)] = "USER_BRANCH_ACCESS",
            [typeof(BranchEnrollment)] = "BRANCH_ENROLLMENT",
            [typeof(UserRefreshToken)] = "USER_REFRESH_TOKEN"
        };

        foreach (var (type, table) in expected)
        {
            var entity = model.FindEntityType(type)!;

            Assert.Equal("identity", entity.GetSchema());
            Assert.Equal(table, entity.GetTableName());
            Assert.NotNull(entity.GetDeclaredQueryFilters());
        }
    }

    [Theory]
    [InlineData(typeof(Organization))]
    [InlineData(typeof(Branch))]
    [InlineData(typeof(Employee))]
    public void AddressComplexPropertyUsesRequiredColumnNames(Type ownerType)
    {
        var model = BuildModel();
        var owner = model.FindEntityType(ownerType)!;

        var address = owner.FindComplexProperty("Address");

        Assert.NotNull(address);

        var table = StoreObjectIdentifier.Table(
            owner.GetTableName()!,
            owner.GetSchema());

        var expected = new[]
        {
            "address_line1",
            "address_line2",
            "address_city",
            "address_region",
            "address_postal_code",
            "address_country_code"
        };

        var actualColumnNames = address.ComplexType
            .GetProperties()
            .Select(property => property.GetColumnName(table))
            .ToHashSet();

        foreach (var name in expected)
            Assert.Contains(name, actualColumnNames);
    }

    [Fact]
    public void UserAccountEnumsAreStringsAndHaveRequiredCheckConstraints()
    {
        var model = BuildDesignTimeModel();
        var entity = model.FindEntityType(typeof(UserAccount))!;

        Assert.Equal(
            typeof(string),
            entity.FindProperty(nameof(UserAccount.Role))!
                .GetTypeMapping().Converter!.ProviderClrType);

        Assert.Equal(
            typeof(string),
            entity.FindProperty(nameof(UserAccount.BranchScope))!
                .GetTypeMapping().Converter!.ProviderClrType);

        var checks = entity.GetCheckConstraints()
            .Select(constraint => constraint.Name)
            .ToHashSet();

        Assert.Contains("CK_USER_ACCOUNT_role", checks);
        Assert.Contains("CK_USER_ACCOUNT_branch_scope", checks);
        Assert.Contains("CK_USER_ACCOUNT_scope_admin_only", checks);
    }

    [Fact]
    public void RequiredAlternateKeysAndUniqueIndexesExist()
    {
        var model = BuildModel();

        Assert.Contains(
            model.FindEntityType(typeof(Branch))!.GetKeys(),
            key => key.Properties.Select(property => property.Name)
                .SequenceEqual(new[] { "OrganizationId", "BranchId" }));

        Assert.Contains(
            model.FindEntityType(typeof(Employee))!.GetKeys(),
            key => key.Properties.Select(property => property.Name)
                .SequenceEqual(new[] { "OrganizationId", "BranchId", "EmployeeId" }));

        Assert.Contains(
            model.FindEntityType(typeof(Employee))!.GetKeys(),
            key => key.Properties.Select(property => property.Name)
                .SequenceEqual(new[] { "OrganizationId", "EmployeeId" }));

        Assert.Contains(
            model.FindEntityType(typeof(UserAccount))!.GetKeys(),
            key => key.Properties.Select(property => property.Name)
                .SequenceEqual(new[] { "OrganizationId", "UserId" }));

        Assert.Contains(
            model.FindEntityType(typeof(Organization))!.GetIndexes(),
            index => index.IsUnique &&
                index.Properties.Select(property => property.Name)
                    .SequenceEqual(new[] { "OrganizationCode" }));

        Assert.Contains(
            model.FindEntityType(typeof(UserAccount))!.GetIndexes(),
            index => index.IsUnique &&
                index.Properties.Select(property => property.Name)
                    .SequenceEqual(new[] { "OrganizationId", "NormalizedUsername" }));

        Assert.Contains(
            model.FindEntityType(typeof(UserAccount))!.GetIndexes(),
            index => index.IsUnique &&
                index.Properties.Select(property => property.Name)
                    .SequenceEqual(new[] { "OrganizationId", "EmployeeId" }));

        Assert.Contains(
            model.FindEntityType(typeof(BranchEnrollment))!.GetIndexes(),
            index => index.IsUnique &&
                index.Properties.Select(property => property.Name)
                    .SequenceEqual(new[] { "TokenHash" }));

        Assert.Contains(
            model.FindEntityType(typeof(UserRefreshToken))!.GetIndexes(),
            index => index.IsUnique &&
                index.Properties.Select(property => property.Name)
                    .SequenceEqual(new[] { "TokenHash" }));
    }
}