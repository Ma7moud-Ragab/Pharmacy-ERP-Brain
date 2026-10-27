using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1")]
public sealed class BranchesController : ControllerBase
{
    private readonly IBranchService _service;
    private readonly ICurrentUser _currentUser;
    public BranchesController(IBranchService service, ICurrentUser currentUser) { _service = service; _currentUser = currentUser; }

    [Authorize, HttpGet("branches")]
    public async Task<IActionResult> GetPaged([FromQuery] bool includeInactive = false, [FromQuery] string? search = null,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 25, CancellationToken ct = default)
        => ApiResultMapper.ToActionResult(this, await _service.GetPagedAsync(includeInactive, search, page, pageSize, ct), _currentUser.TraceId);

    [Authorize(Policy = "AdminOnly"), HttpPost("branches")]
    public async Task<IActionResult> Create([FromBody] CreateBranchRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.CreateAsync(request, ct), _currentUser.TraceId);

    [Authorize, HttpGet("branches/{id:guid}")]
    public async Task<IActionResult> GetById(Guid id, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.GetByIdAsync(id, ct), _currentUser.TraceId);

    [Authorize(Policy = "AdminOnly"), HttpPatch("branches/{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateBranchRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.UpdateAsync(id, request, ct), _currentUser.TraceId);

    [Authorize(Policy = "AdminOnly"), HttpPost("branches/{branchId:guid}/enrollment-tokens")]
    public async Task<IActionResult> IssueEnrollmentToken(Guid branchId, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.IssueEnrollmentTokenAsync(branchId, ct), _currentUser.TraceId);

    [AllowAnonymous, HttpPost("branch-enrollment")]
    public async Task<IActionResult> RedeemEnrollment([FromBody] RedeemBranchEnrollmentRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.RedeemEnrollmentAsync(request, ct), _currentUser.TraceId);
}
