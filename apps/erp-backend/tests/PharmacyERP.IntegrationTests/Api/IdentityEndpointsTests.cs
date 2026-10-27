using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Mvc.Testing;

namespace PharmacyERP.IntegrationTests.Api;

public sealed class IdentityEndpointsTests : IClassFixture<WebApplicationFactory<PharmacyERP.Api.Program>>
{
    private readonly HttpClient _client;

    public IdentityEndpointsTests(WebApplicationFactory<PharmacyERP.Api.Program> factory)
        => _client = factory.WithWebHostBuilder(builder => builder.ConfigureLogging(logging => logging.ClearProviders())).CreateClient();

    [Fact]
    public async Task JwksEndpoint_PublishesPublicSigningKey()
    {
        using var response = await _client.GetAsync("/.well-known/jwks.json");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/jwk-set+json", response.Content.Headers.ContentType?.MediaType);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Contains("\"keys\"", body);
        Assert.Contains("\"alg\":\"RS256\"", body);
        Assert.Contains("\"kid\"", body);
    }

    [Theory]
    [InlineData("/api/v1/auth/me")]
    [InlineData("/api/v1/users")]
    [InlineData("/api/v1/employees")]
    [InlineData("/api/v1/branches")]
    public async Task ProtectedIdentityEndpoints_RejectAnonymousRequests(string path)
    {
        using var response = await _client.GetAsync(path);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task OrganizationProvisioning_RejectsAnonymousRequest()
    {
        using var response = await _client.PostAsync("/api/v1/organizations", JsonContent.Create(new { }));
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }
}
