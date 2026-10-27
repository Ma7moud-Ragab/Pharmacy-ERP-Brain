using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1/employees")]
public sealed class EmployeesController : ControllerBase
{
    private readonly IEmployeeService _service;
    private readonly ICurrentUser _currentUser;
    public EmployeesController(IEmployeeService service, ICurrentUser currentUser) { _service = service; _currentUser = currentUser; }

    [Authorize, HttpGet]
    public async Task<IActionResult> GetPaged([FromQuery] Guid? branchId, [FromQuery] bool includeInactive = false, [FromQuery] string? search = null,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 25, CancellationToken ct = default)
        => ApiResultMapper.ToActionResult(this, await _service.GetPagedAsync(branchId, includeInactive, search, page, pageSize, ct), _currentUser.TraceId);

    [Authorize(Policy = "AdminOnly"), HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateEmployeeRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.CreateAsync(request, ct), _currentUser.TraceId);

    [Authorize, HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.GetByIdAsync(id, ct), _currentUser.TraceId);

    [Authorize(Policy = "AdminOnly"), HttpPatch("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateEmployeeRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.UpdateAsync(id, request, ct), _currentUser.TraceId);
}
