using System.Net;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Moq;
using PharmacyERP.Api.Middleware;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using Xunit;

namespace PharmacyERP.UnitTests.Api.Middleware;

public class MiddlewareTests
{
    [Fact]
    public async Task TraceparentMiddleware_GeneratesW3CTraceparent_WhenNoHeaderProvided()
    {
        var context = new DefaultHttpContext();
        var middleware = new TraceparentMiddleware(_ => Task.CompletedTask);

        await middleware.InvokeAsync(context);

        Assert.True(context.Items.ContainsKey("TraceId"));
        Assert.True(context.Response.Headers.ContainsKey("traceparent"));
        Assert.True(context.Response.Headers.ContainsKey("X-Trace-Id"));

        var traceId = context.Items["TraceId"]?.ToString();
        Assert.False(string.IsNullOrWhiteSpace(traceId));
        Assert.StartsWith("00-", traceId);
    }

    [Fact]
    public async Task TraceparentMiddleware_PreservesIncomingTraceparentHeader()
    {
        var expectedTraceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01";
        var context = new DefaultHttpContext();
        context.Request.Headers["traceparent"] = expectedTraceparent;

        var middleware = new TraceparentMiddleware(_ => Task.CompletedTask);
        await middleware.InvokeAsync(context);

        Assert.Equal(expectedTraceparent, context.Items["TraceId"]);
        Assert.Equal(expectedTraceparent, context.Response.Headers["traceparent"].ToString());
    }

    [Fact]
    public async Task TenantResolutionMiddleware_SetsTenant_WhenUserIsAuthenticatedAndHasOrganizationClaim()
    {
        var orgId = Guid.NewGuid();
        var context = new DefaultHttpContext();
        var claims = new[] { new Claim("organization_id", orgId.ToString()) };
        context.User = new ClaimsPrincipal(new ClaimsIdentity(claims, "TestAuth"));

        var tenantContextMock = new Mock<ITenantContext>();
        tenantContextMock.SetupGet(x => x.IsTenantBound).Returns(true);

        var middleware = new TenantResolutionMiddleware(_ => Task.CompletedTask);
        await middleware.InvokeAsync(context, tenantContextMock.Object);

        tenantContextMock.Verify(x => x.SetTenant(orgId), Times.Once);
    }

    [Theory]
    [InlineData("/api/v1/auth/login")]
    [InlineData("/api/v1/auth/refresh")]
    [InlineData("/api/v1/branch-enrollment")]
    [InlineData("/api/v1/organizations")]
    public async Task TenantResolutionMiddleware_AllowsSystemBypass_OnAnonymousProvisioningPaths(string path)
    {
        var context = new DefaultHttpContext();
        context.Request.Path = path;
        context.User = new ClaimsPrincipal(new ClaimsIdentity());

        var tenantContextMock = new Mock<ITenantContext>();
        tenantContextMock.SetupGet(x => x.IsTenantBound).Returns(false);

        var middleware = new TenantResolutionMiddleware(_ => Task.CompletedTask);
        await middleware.InvokeAsync(context, tenantContextMock.Object);

        tenantContextMock.Verify(x => x.AllowSystemBypass(), Times.Once);
    }

    [Fact]
    public async Task RuntimeModeGuardMiddleware_BlocksStockAdjustmentsOnCloudMode_Returns404()
    {
        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/inventory/adjustments";
        context.Request.Method = HttpMethods.Post;
        context.Response.Body = new MemoryStream();

        var runtimeModeMock = new Mock<IRuntimeModeProvider>();
        runtimeModeMock.SetupGet(x => x.CurrentMode).Returns(ErpRuntimeMode.Cloud);

        var nextCalled = false;
        var middleware = new RuntimeModeGuardMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });

        await middleware.InvokeAsync(context, runtimeModeMock.Object);

        Assert.False(nextCalled);
        Assert.Equal((int)HttpStatusCode.NotFound, context.Response.StatusCode);
    }

    [Fact]
    public async Task RuntimeModeGuardMiddleware_BlocksOrganizationsOnBranchLocalMode_Returns404()
    {
        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/organizations";
        context.Request.Method = HttpMethods.Post;
        context.Response.Body = new MemoryStream();

        var runtimeModeMock = new Mock<IRuntimeModeProvider>();
        runtimeModeMock.SetupGet(x => x.CurrentMode).Returns(ErpRuntimeMode.BranchLocal);

        var nextCalled = false;
        var middleware = new RuntimeModeGuardMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });

        await middleware.InvokeAsync(context, runtimeModeMock.Object);

        Assert.False(nextCalled);
        Assert.Equal((int)HttpStatusCode.NotFound, context.Response.StatusCode);
    }

    [Fact]
    public async Task ExceptionHandlingMiddleware_CatchesDomainException_Returns422UnprocessableEntity()
    {
        var context = new DefaultHttpContext();
        context.Response.Body = new MemoryStream();
        context.Items["TraceId"] = "test-trace-id";

        var loggerMock = new Mock<ILogger<ExceptionHandlingMiddleware>>();
        var middleware = new ExceptionHandlingMiddleware(
            _ => throw new TestDomainException("Business rule violated."),
            loggerMock.Object
        );

        await middleware.InvokeAsync(context);

        context.Response.Body.Seek(0, SeekOrigin.Begin);
        var responseText = await new StreamReader(context.Response.Body).ReadToEndAsync();
        var errorEnvelope = JsonSerializer.Deserialize<ApiErrorEnvelopeDto>(responseText);

        Assert.Equal((int)HttpStatusCode.UnprocessableEntity, context.Response.StatusCode);
        Assert.NotNull(errorEnvelope);
        Assert.Equal("test-trace-id", errorEnvelope.Error.TraceId);
        Assert.Equal("VALIDATION_ERROR", errorEnvelope.Error.Code);
        Assert.Equal("Business rule violated.", errorEnvelope.Error.Message);
        Assert.Contains("\"trace_id\":\"test-trace-id\"", responseText);
    }

    [Fact]
    public async Task ExceptionHandlingMiddleware_CatchesIdempotencyMismatch_Returns409Conflict()
    {
        var context = new DefaultHttpContext();
        context.Response.Body = new MemoryStream();
        context.Items["TraceId"] = "conflict-trace-id";

        var loggerMock = new Mock<ILogger<ExceptionHandlingMiddleware>>();
        var middleware = new ExceptionHandlingMiddleware(
            _ => throw new IntegrationDomainException("IDEMPOTENCY_MISMATCH"),
            loggerMock.Object
        );

        await middleware.InvokeAsync(context);

        context.Response.Body.Seek(0, SeekOrigin.Begin);
        var responseText = await new StreamReader(context.Response.Body).ReadToEndAsync();
        var errorEnvelope = JsonSerializer.Deserialize<ApiErrorEnvelopeDto>(responseText);

        Assert.Equal((int)HttpStatusCode.Conflict, context.Response.StatusCode);
        Assert.NotNull(errorEnvelope);
        Assert.Equal("IDEMPOTENCY_MISMATCH", errorEnvelope.Error.Code);
        Assert.Equal("conflict-trace-id", errorEnvelope.Error.TraceId);
    }

    [Fact]
    public async Task ExceptionHandlingMiddleware_CatchesGenericException_Returns500InternalServerError()
    {
        var context = new DefaultHttpContext();
        context.Response.Body = new MemoryStream();

        var loggerMock = new Mock<ILogger<ExceptionHandlingMiddleware>>();
        var middleware = new ExceptionHandlingMiddleware(
            _ => throw new Exception("Database connection failed."),
            loggerMock.Object
        );

        await middleware.InvokeAsync(context);

        context.Response.Body.Seek(0, SeekOrigin.Begin);
        var responseText = await new StreamReader(context.Response.Body).ReadToEndAsync();
        var errorEnvelope = JsonSerializer.Deserialize<ApiErrorEnvelopeDto>(responseText);

        Assert.Equal((int)HttpStatusCode.InternalServerError, context.Response.StatusCode);
        Assert.NotNull(errorEnvelope);
        Assert.Equal("INTERNAL_SERVER_ERROR", errorEnvelope.Error.Code);
    }

    private class TestDomainException : DomainException
    {
        public TestDomainException(string message) : base(message) { }
    }
}