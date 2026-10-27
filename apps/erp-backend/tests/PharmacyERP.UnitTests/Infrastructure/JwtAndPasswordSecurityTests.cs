using System.Text.Json;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using Microsoft.Extensions.Configuration;
using Moq;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Infrastructure.Auth;

namespace PharmacyERP.UnitTests.Infrastructure;

public sealed class JwtAndPasswordSecurityTests
{
    private static UserAccount CreateUser(UserRole role = UserRole.Pharmacist, BranchScope scope = BranchScope.ASSIGNED)
        => UserAccount.Create(Guid.NewGuid(), Guid.NewGuid(), "alice", "placeholder", role, scope);

    private static IDateTimeProvider Clock(DateTimeOffset now)
    {
        var mock = new Mock<IDateTimeProvider>();
        mock.SetupGet(x => x.UtcNow).Returns(now);
        return mock.Object;
    }

    private static IConfiguration Configuration() => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["Jwt:Issuer"] = "https://issuer.test",
        ["Jwt:Audience"] = "pharmacy-api"
    }).Build();

    [Fact]
    public void PasswordHasher_HashesAndVerifiesOnlyMatchingPassword()
    {
        var service = new PasswordHasherService();
        var user = CreateUser();
        var hash = service.HashPassword(user, "correct horse battery staple");
        Assert.NotEqual("correct horse battery staple", hash);
        Assert.True(service.VerifyPassword(user, hash, "correct horse battery staple"));
        Assert.False(service.VerifyPassword(user, hash, "wrong password"));
    }

    [Fact]
    public void Jwt_IsRs256SignedAndContainsCurrentUserClaimsAndKid()
    {
        using var keys = new JwksKeyProvider();
        var now = DateTimeOffset.UtcNow;
        var runtime = new Mock<IRuntimeModeProvider>();
        runtime.SetupGet(x => x.CurrentMode).Returns(ErpRuntimeMode.Cloud);
        var generator = new JwtTokenGenerator(keys, runtime.Object, Clock(now), Configuration());
        var user = CreateUser();
        var branchIds = new[] { Guid.NewGuid(), Guid.NewGuid() };
        var generated = generator.GenerateAccessToken(user, branchIds);
        var parts = generated.Token.Split('.');
        using var header = JsonDocument.Parse(JwksKeyProvider.Base64UrlDecode(parts[0]));
        using var payload = JsonDocument.Parse(JwksKeyProvider.Base64UrlDecode(parts[1]));
        var root = payload.RootElement;

        Assert.Equal("RS256", header.RootElement.GetProperty("alg").GetString());
        Assert.Equal(keys.KeyId, header.RootElement.GetProperty("kid").GetString());
        var principal = new JwtSecurityTokenHandler().ValidateToken(generated.Token,
            new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = new RsaSecurityKey(keys.GetPublicKeyParameters()) { KeyId = keys.KeyId },
                ValidAlgorithms = new[] { SecurityAlgorithms.RsaSha256 },
                ValidateIssuer = true,
                ValidIssuer = "https://issuer.test",
                ValidateAudience = true,
                ValidAudience = "pharmacy-api",
                ValidateLifetime = true
            }, out _);
        Assert.True(principal.Identity?.IsAuthenticated);
        Assert.Equal(user.UserId.ToString(), root.GetProperty("sub").GetString());
        Assert.Equal(user.EmployeeId.ToString(), root.GetProperty("employee_id").GetString());
        Assert.Equal("Pharmacist", root.GetProperty("role").GetString());
        Assert.Equal(user.OrganizationId.ToString(), root.GetProperty("organization_id").GetString());
        Assert.Equal("ASSIGNED", root.GetProperty("branch_scope").GetString());
        Assert.Equal(branchIds.Select(x => x.ToString()).Order(), root.GetProperty("branch_ids").EnumerateArray().Select(x => x.GetString()).Order());
        Assert.Contains("inventory:read", root.GetProperty("scope").GetString());
        Assert.Contains("sales:write", root.GetProperty("scope").GetString());
        Assert.Equal("https://issuer.test", root.GetProperty("iss").GetString());
        Assert.Equal("pharmacy-api", root.GetProperty("aud").GetString());
        Assert.Equal(generated.ExpiresAt.ToUnixTimeSeconds(), root.GetProperty("exp").GetInt64());
    }

    [Fact]
    public void Jwt_BranchLocalModeRestrictsBranchAndExpiration()
    {
        using var keys = new JwksKeyProvider();
        var now = DateTimeOffset.UtcNow;
        var enrolledBranch = Guid.NewGuid();
        var runtime = new Mock<IRuntimeModeProvider>();
        runtime.SetupGet(x => x.CurrentMode).Returns(ErpRuntimeMode.BranchLocal);
        runtime.SetupGet(x => x.EnrolledBranchId).Returns(enrolledBranch);
        var generator = new JwtTokenGenerator(keys, runtime.Object, Clock(now), Configuration());
        var generated = generator.GenerateAccessToken(CreateUser(UserRole.Admin, BranchScope.ALL), new[] { Guid.NewGuid(), Guid.NewGuid() });
        using var payload = JsonDocument.Parse(JwksKeyProvider.Base64UrlDecode(generated.Token.Split('.')[1]));
        var root = payload.RootElement;

        Assert.Equal(new[] { enrolledBranch.ToString() }, root.GetProperty("branch_ids").EnumerateArray().Select(x => x.GetString()));
        Assert.Equal("ASSIGNED", root.GetProperty("branch_scope").GetString());
        Assert.True(generated.ExpiresAt - now <= TimeSpan.FromHours(24));
    }
}
