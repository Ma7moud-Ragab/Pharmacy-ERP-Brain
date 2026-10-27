using Microsoft.EntityFrameworkCore;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.ValueObjects;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Repositories.Identity;
using PharmacyERP.Infrastructure.Services.Context;

namespace PharmacyERP.UnitTests.Infrastructure;

public sealed class IdentityRepositoriesTests
{
    private static Address NewAddress() => new("1 Main St", null, "Cairo", null, null, "EG");

    private static (PharmacyDbContext Db, TenantContext Tenant) CreateDb()
    {
        var tenant = new TenantContext();
        var options = new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString())
            .Options;
        return (new PharmacyDbContext(options, tenant), tenant);
    }

    [Fact]
    public async Task OrganizationRepository_FindsActiveCodeAcrossTenantFilter()
    {
        var (db, tenant) = CreateDb();
        await using (db)
        {
            var organization = Organization.Create("ACME", "Acme", "EGP", "Africa/Cairo", NewAddress());
            db.Organizations.Add(organization);
            await db.SaveChangesAsync();
            tenant.SetTenant(Guid.NewGuid());

            var repository = new OrganizationRepository(db);
            Assert.True(await repository.ExistsByCodeAsync(" acme "));
            Assert.Equal(organization.OrganizationId, (await repository.GetActiveByCodeAsync("ACME"))!.OrganizationId);
        }
    }

    [Fact]
    public async Task UserAccountRepository_FindsLoginAndReplacesBranchAccess()
    {
        var (db, tenant) = CreateDb();
        await using (db)
        {
            var organization = Organization.Create("ACME", "Acme", "EGP", "Africa/Cairo", NewAddress());
            tenant.SetTenant(organization.OrganizationId);
            var branch = Branch.Create(organization.OrganizationId, "MAIN", "Main", NewAddress());
            var employee = Employee.Create(organization.OrganizationId, branch.BranchId, "E-1", "A Person", null, null, "Pharmacist", NewAddress(), DateOnly.FromDateTime(DateTime.UtcNow));
            var user = UserAccount.Create(organization.OrganizationId, employee.EmployeeId, "Alice", "hash", UserRole.Pharmacist, BranchScope.ASSIGNED);
            db.AddRange(organization, branch, employee, user);
            await db.SaveChangesAsync();

            var repository = new UserAccountRepository(db);
            Assert.True(await repository.ExistsByUsernameAsync(organization.OrganizationId, "ALICE"));
            Assert.Equal(user.UserId, (await repository.GetForLoginAsync(organization.OrganizationId, "ALICE"))!.UserId);
            await repository.ReplaceBranchAccessAsync(organization.OrganizationId, user.UserId, new[] { branch.BranchId, branch.BranchId });
            await db.SaveChangesAsync();
            Assert.Single(await db.UserBranchAccesses.ToListAsync());
        }
    }

    [Fact]
    public async Task RefreshTokenRepository_RevokesEntireFamily()
    {
        var (db, tenant) = CreateDb();
        await using (db)
        {
            var organizationId = Guid.NewGuid();
            var userId = Guid.NewGuid();
            var familyId = Guid.NewGuid();
            tenant.SetTenant(organizationId);
            var now = DateTimeOffset.UtcNow;
            var first = UserRefreshToken.Create(organizationId, userId, new byte[32], familyId, now, now.AddDays(1));
            var second = UserRefreshToken.Create(organizationId, userId, Enumerable.Repeat((byte)1, 32).ToArray(), familyId, now, now.AddDays(1));
            db.UserRefreshTokens.AddRange(first, second);
            await db.SaveChangesAsync();

            var repository = new UserRefreshTokenRepository(db);
            Assert.Equal(first.RefreshTokenId, (await repository.GetByTokenHashAsync(new byte[32]))!.RefreshTokenId);
            await repository.RevokeFamilyAsync(organizationId, familyId, now.AddMinutes(1));
            await db.SaveChangesAsync();

            Assert.All(await db.UserRefreshTokens.ToListAsync(), token => Assert.Equal(now.AddMinutes(1), token.RevokedAt));
        }
    }
}
