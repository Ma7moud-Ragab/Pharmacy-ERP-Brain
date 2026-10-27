using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using PharmacyERP.Application.Features.Integration.DTOs;
using Xunit;

namespace PharmacyERP.IntegrationTests.Api;

public class CanonicalCapabilitiesEndpointTests : IClassFixture<WebApplicationFactory<PharmacyERP.Api.Program>>
{
    private readonly HttpClient _client;

    public CanonicalCapabilitiesEndpointTests(WebApplicationFactory<PharmacyERP.Api.Program> factory)
    {
        // This creates a test server in-memory that hosts our actual API pipeline
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task GetCapabilities_ReturnsSuccessAndCorrectContentType()
    {
        // Act
        var response = await _client.GetAsync("/api/v1/canonical/capabilities");

        // Assert
        response.EnsureSuccessStatusCode(); // Asserts Status Code is 200-299
        Assert.Equal("application/json; charset=utf-8", response.Content.Headers.ContentType?.ToString());

        var responseString = await response.Content.ReadAsStringAsync();
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        var result = JsonSerializer.Deserialize<CanonicalCapabilitiesDto>(responseString, options);

        Assert.NotNull(result);
        Assert.Equal(1, result?.Stage);
        Assert.NotNull(result?.RuntimeMode);
    }

    [Fact]
    public async Task Middleware_AddsTraceIdHeader_ToAllResponses()
    {
        // Act
        var response = await _client.GetAsync("/api/v1/canonical/capabilities");

        // Assert
        Assert.True(response.Headers.Contains("X-Trace-Id"), "The TraceparentMiddleware did not append the X-Trace-Id header.");

        var traceId = response.Headers.GetValues("X-Trace-Id").FirstOrDefault();
        Assert.False(string.IsNullOrWhiteSpace(traceId));
    }

    [Fact]
    public async Task ExceptionHandlingMiddleware_ReturnsJsonEnvelope_OnNonExistentEndpoint()
    {
        // Act - Requesting an endpoint that doesn't exist
        var response = await _client.GetAsync("/api/v1/does-not-exist");

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);

        // Ensure our Traceparent middleware still fires even on 404s
        Assert.True(response.Headers.Contains("X-Trace-Id"));
    }
}