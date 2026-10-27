using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Features.Integration.DTOs;
using PharmacyERP.Application.Features.Integration.Services.Interfaces;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1/canonical/capabilities")]
[AllowAnonymous]
public class CanonicalCapabilitiesController : ControllerBase
{
    private readonly ICanonicalCapabilitiesService _capabilitiesService;

    public CanonicalCapabilitiesController(ICanonicalCapabilitiesService capabilitiesService)
    {
        _capabilitiesService = capabilitiesService;
    }

    [HttpGet]
    [ProducesResponseType(typeof(CanonicalCapabilitiesDto), 200)]
    public IActionResult GetCapabilities()
    {
        var capabilities = _capabilitiesService.GetCapabilities();
        return Ok(capabilities);
    }
}