using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Api.Controllers;

[ApiController]
[Route("api/v1/users")]
[Authorize(Policy = "AdminOnly")]
public sealed class UsersController : ControllerBase
{
    private readonly IUserService _service;
    private readonly ICurrentUser _currentUser;
    public UsersController(IUserService service, ICurrentUser currentUser) { _service = service; _currentUser = currentUser; }

    [HttpGet]
    public async Task<IActionResult> GetPaged([FromQuery] Guid? branchId, [FromQuery] UserRole? role, [FromQuery] bool includeInactive = false,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 25, CancellationToken ct = default)
        => ApiResultMapper.ToActionResult(this, await _service.GetPagedAsync(branchId, role, includeInactive, page, pageSize, ct), _currentUser.TraceId);

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.CreateAsync(request, ct), _currentUser.TraceId);

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.GetByIdAsync(id, ct), _currentUser.TraceId);

    [HttpPatch("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateUserRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.UpdateAsync(id, request, ct), _currentUser.TraceId);

    [HttpPost("{id:guid}/password-reset")]
    public async Task<IActionResult> ResetPassword(Guid id, [FromBody] ResetPasswordRequest request, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.ResetPasswordAsync(id, request, ct), _currentUser.TraceId);

    [HttpPost("{id:guid}/revoke-sessions")]
    public async Task<IActionResult> RevokeSessions(Guid id, CancellationToken ct)
        => ApiResultMapper.ToActionResult(this, await _service.RevokeSessionsAsync(id, ct), _currentUser.TraceId);
}
