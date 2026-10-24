using System.Reflection;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Moq;
using PharmacyERP.Api.Controllers;
using PharmacyERP.Application.Features.Integration.DTOs;
using PharmacyERP.Application.Features.Integration.Services.Interfaces;
using Xunit;

namespace PharmacyERP.UnitTests.Api.Controllers;

public class CanonicalCapabilitiesControllerTests
{
    [Fact]
    public void GetCapabilities_ReturnsOkObjectResult_WithCorrectDtoType()
    {
        var expectedDto = new CanonicalCapabilitiesDto(
            Stage: 1,
            RuntimeMode: "BranchLocal",
            SupportedReads: new[] { "products" },
            SupportedWrites: new[] { "configuration.products" }
        );

        var serviceMock = new Mock<ICanonicalCapabilitiesService>();
        serviceMock.Setup(x => x.GetCapabilities()).Returns(expectedDto);
        var controller = new CanonicalCapabilitiesController(serviceMock.Object);

        var result = controller.GetCapabilities();

        var okResult = Assert.IsType<OkObjectResult>(result);
        var returnValue = Assert.IsType<CanonicalCapabilitiesDto>(okResult.Value);
        Assert.Equal(1, returnValue.Stage);
        Assert.Equal("BranchLocal", returnValue.RuntimeMode);
    }

    [Fact]
    public void ControllerClass_HasRequiredAttributes()
    {
        var controllerType = typeof(CanonicalCapabilitiesController);

        var apiControllerAttribute = controllerType.GetCustomAttribute<ApiControllerAttribute>();
        Assert.NotNull(apiControllerAttribute);

        var routeAttribute = controllerType.GetCustomAttribute<RouteAttribute>();
        Assert.NotNull(routeAttribute);
        Assert.Equal("api/v1/canonical/capabilities", routeAttribute.Template);

        var allowAnonymousAttribute = controllerType.GetCustomAttribute<AllowAnonymousAttribute>();
        Assert.NotNull(allowAnonymousAttribute);
    }

    [Fact]
    public void GetCapabilitiesMethod_HasRequiredAttributes()
    {
        var controllerType = typeof(CanonicalCapabilitiesController);
        var methodInfo = controllerType.GetMethod(nameof(CanonicalCapabilitiesController.GetCapabilities));

        Assert.NotNull(methodInfo);

        var httpGetAttribute = methodInfo.GetCustomAttribute<HttpGetAttribute>();
        Assert.NotNull(httpGetAttribute);

        var producesResponseTypeAttribute = methodInfo.GetCustomAttribute<ProducesResponseTypeAttribute>();
        Assert.NotNull(producesResponseTypeAttribute);
        Assert.Equal(200, producesResponseTypeAttribute.StatusCode);
        Assert.Equal(typeof(CanonicalCapabilitiesDto), producesResponseTypeAttribute.Type);
    }
}