using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using PharmacyERP.Application.Common.Utilities;
using PharmacyERP.Infrastructure.Services.Context;
using Xunit;

namespace PharmacyERP.UnitTests.Application.Common;

public class CanonicalJsonHasherTests
{
    [Fact]
    public void ComputeSha256Hex_DifferentPropertyOrder_ProducesIdentical64CharHash()
    {
        var payload1 = new { ZProperty = "Paracetamol Extra", AProperty = 100, Nested = new { B = 2, A = 1 } };
        var payload2 = new { AProperty = 100, Nested = new { A = 1, B = 2 }, ZProperty = "Paracetamol Extra" };

        var hash1 = CanonicalJsonHasher.ComputeSha256Hex(payload1);
        var hash2 = CanonicalJsonHasher.ComputeSha256Hex(payload2);

        Assert.Equal(64, hash1.Length);
        Assert.Equal(hash1, hash2);
    }

    [Fact]
    public void ComputeSha256Hex_DecimalsWithTrailingZeros_ProducesIdenticalHash()
    {
        var payload1 = new { Price = 15.5m, Tax = 0.1400m };
        var payload2 = new { Price = 15.5000m, Tax = 0.140000m };

        var hash1 = CanonicalJsonHasher.ComputeSha256Hex(payload1);
        var hash2 = CanonicalJsonHasher.ComputeSha256Hex(payload2);

        Assert.Equal(hash1, hash2);
    }

    [Fact]
    public void ComputeSha256Hex_NullObject_ProducesValidHashForNullString()
    {
        object? nullPayload = null;

        var hash = CanonicalJsonHasher.ComputeSha256Hex(nullPayload);

        Assert.Equal(64, hash.Length);
    }

    [Fact]
    public void CurrentUser_CanAccessBranch_EnforcesAdminAllAndAssignedBranches()
    {
        var allowedBranchId = Guid.NewGuid();
        var forbiddenBranchId = Guid.NewGuid();

        var assignedClaims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()),
            new Claim(ClaimTypes.Role, "Pharmacist"),
            new Claim("branch_scope", "ASSIGNED"),
            new Claim("branch_ids", allowedBranchId.ToString())
        };
        var httpContext = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity(assignedClaims, "TestAuth"))
        };
        var currentUser = new CurrentUser(new HttpContextAccessor { HttpContext = httpContext });

        Assert.True(currentUser.CanAccessBranch(allowedBranchId));
        Assert.False(currentUser.CanAccessBranch(forbiddenBranchId));

        var adminClaims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()),
            new Claim(ClaimTypes.Role, "Admin"),
            new Claim("branch_scope", "ALL")
        };
        var adminHttpContext = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity(adminClaims, "TestAuth"))
        };
        var adminUser = new CurrentUser(new HttpContextAccessor { HttpContext = adminHttpContext });

        Assert.True(adminUser.CanAccessBranch(forbiddenBranchId));
    }

    [Fact]
    public void CurrentUser_WhenNotAuthenticated_PropertiesReturnNullAndFalse()
    {
        var httpContext = new DefaultHttpContext();
        var currentUser = new CurrentUser(new HttpContextAccessor { HttpContext = httpContext });

        Assert.False(currentUser.IsAuthenticated);
        Assert.Null(currentUser.UserId);
        Assert.False(currentUser.CanAccessBranch(Guid.NewGuid()));
    }

    [Fact]
    public void DateTimeProvider_GetOrganizationBusinessDate_ReturnsValidDateForCairo()
    {
        var provider = new DateTimeProvider();
        var businessDate = provider.GetOrganizationBusinessDate("Africa/Cairo");

        Assert.NotEqual(default, businessDate);
    }

    [Fact]
    public void DateTimeProvider_InvalidTimeZoneId_ThrowsTimeZoneNotFoundException()
    {
        var provider = new DateTimeProvider();

        Assert.Throws<TimeZoneNotFoundException>(() =>
            provider.GetOrganizationBusinessDate("Invalid/Timezone"));
    }
}