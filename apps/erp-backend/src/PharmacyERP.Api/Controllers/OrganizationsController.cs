using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1/organizations")]
[Authorize(Policy = "PlatformProvisionerOnly")]
public sealed class OrganizationsController : ControllerBase
{
    private readonly IOrganizationProvisioningService _service;
    private readonly ICurrentUser _currentUser;
    public OrganizationsController(IOrganizationProvisioningService service, ICurrentUser currentUser) { _service = service; _currentUser = currentUser; }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateOrganizationRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.CreateAsync(request, ct), _currentUser.TraceId);
}
