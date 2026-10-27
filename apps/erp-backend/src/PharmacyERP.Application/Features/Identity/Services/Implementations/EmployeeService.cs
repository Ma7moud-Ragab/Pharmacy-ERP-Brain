using PharmacyERP.Application.Common.Constants;
using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Application.Features.Identity.Services.Implementations;

public sealed class EmployeeService : IEmployeeService
{
    private readonly IEmployeeRepository _employees;
    private readonly IBranchRepository _branches;
    private readonly IUnitOfWork _unitOfWork;
    private readonly IAuditLogger _audit;
    private readonly IOutboxService _outbox;
    private readonly ITenantContext _tenant;
    private readonly ICurrentUser _currentUser;
    private readonly IDateTimeProvider _clock;

    public EmployeeService(IEmployeeRepository employees, IBranchRepository branches, IUnitOfWork unitOfWork,
        IAuditLogger audit, IOutboxService outbox, ITenantContext tenant, ICurrentUser currentUser, IDateTimeProvider clock)
    { _employees = employees; _branches = branches; _unitOfWork = unitOfWork; _audit = audit; _outbox = outbox; _tenant = tenant; _currentUser = currentUser; _clock = clock; }

    public async Task<Result<PagedResult<EmployeeDto>>> GetPagedAsync(Guid? branchId, bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default)
    {
        if (_tenant.OrganizationId is not Guid organizationId) return IdentityResults.Failure<PagedResult<EmployeeDto>>(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        if (page < 1 || pageSize is < 1 or > 200) return IdentityResults.Failure<PagedResult<EmployeeDto>>(ErrorCode.VALIDATION_ERROR, ErrorMessages.ValidationError);
        if (!branchId.HasValue && !IsAllBranchAdmin())
        {
            if (_currentUser.AuthorizedBranchIds.Count != 1)
                return IdentityResults.Failure<PagedResult<EmployeeDto>>(ErrorCode.FORBIDDEN_BRANCH, ErrorMessages.ForbiddenBranch);
            branchId = _currentUser.AuthorizedBranchIds.Single();
        }
        if (branchId.HasValue && !_currentUser.CanAccessBranch(branchId.Value))
            return IdentityResults.Failure<PagedResult<EmployeeDto>>(ErrorCode.FORBIDDEN_BRANCH, ErrorMessages.ForbiddenBranch);

        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var result = await _employees.GetPagedAsync(organizationId, branchId, includeInactive, search, page, pageSize, ct);
            await _unitOfWork.RollbackTransactionAsync(ct);
            return Result<PagedResult<EmployeeDto>>.Success(new PagedResult<EmployeeDto>(result.Items.Select(EmployeeDtoMapper.From).ToArray(), page, pageSize, result.TotalCount));
        }
        catch { await _unitOfWork.RollbackTransactionAsync(ct); throw; }
    }

    public async Task<Result<EmployeeDto>> GetByIdAsync(Guid employeeId, CancellationToken ct = default)
    {
        if (_tenant.OrganizationId is not Guid organizationId) return IdentityResults.Failure<EmployeeDto>(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var employee = await _employees.GetByIdAsync(organizationId, employeeId, ct);
            await _unitOfWork.RollbackTransactionAsync(ct);
            if (employee is null) return IdentityResults.Failure<EmployeeDto>(ErrorCode.NOT_FOUND, ErrorMessages.NotFound);
            if (!_currentUser.CanAccessBranch(employee.BranchId)) return IdentityResults.Failure<EmployeeDto>(ErrorCode.FORBIDDEN_BRANCH, ErrorMessages.ForbiddenBranch);
            return Result<EmployeeDto>.Success(EmployeeDtoMapper.From(employee));
        }
        catch { await _unitOfWork.RollbackTransactionAsync(ct); throw; }
    }

    public async Task<Result<EmployeeDto>> CreateAsync(CreateEmployeeRequest request, CancellationToken ct = default)
    {
        if (!IsAdmin()) return IdentityResults.Failure<EmployeeDto>(ErrorCode.FORBIDDEN, ErrorMessages.Forbidden);
        if (_tenant.OrganizationId is not Guid organizationId) return IdentityResults.Failure<EmployeeDto>(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        if (!_currentUser.CanAccessBranch(request.BranchId)) return IdentityResults.Failure<EmployeeDto>(ErrorCode.FORBIDDEN_BRANCH, ErrorMessages.ForbiddenBranch);
        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var branch = await _branches.GetByIdAsync(organizationId, request.BranchId, ct);
            if (branch is null || !branch.IsActive)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.NOT_FOUND, ErrorMessages.NotFound);
            }
            if (await _employees.ExistsByEmployeeNoAsync(organizationId, request.BranchId, request.EmployeeNo, ct))
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.CONFLICT, ErrorMessages.DuplicateEmployeeNo);
            }
            Employee employee;
            try { employee = Employee.Create(organizationId, request.BranchId, request.EmployeeNo, request.FullName, request.Email, request.Phone, request.JobTitle, request.Address.ToValueObject(), request.HiredOn); }
            catch (Exception ex) when (ex is ArgumentException or IdentityDomainException)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.VALIDATION_ERROR, ex.Message);
            }
            await _employees.AddAsync(employee, ct);
            await _audit.LogAsync("employee.created", "identity", "EMPLOYEE", employee.EmployeeId, null,
                new { employee.EmployeeNo, employee.FullName }, employee.BranchId, ct: ct);
            await _outbox.EnqueueAsync("identity.employee.created", employee.BranchId, new { employee.EmployeeId, employee.EmployeeNo }, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);
            return Result<EmployeeDto>.Success(EmployeeDtoMapper.From(employee));
        }
        catch { await _unitOfWork.RollbackTransactionAsync(ct); throw; }
    }

    public async Task<Result<EmployeeDto>> UpdateAsync(Guid employeeId, UpdateEmployeeRequest request, CancellationToken ct = default)
    {
        if (!IsAdmin()) return IdentityResults.Failure<EmployeeDto>(ErrorCode.FORBIDDEN, ErrorMessages.Forbidden);
        if (_tenant.OrganizationId is not Guid organizationId) return IdentityResults.Failure<EmployeeDto>(ErrorCode.UNAUTHORIZED, ErrorMessages.Unauthorized);
        await _unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var employee = await _employees.GetByIdAsync(organizationId, employeeId, ct);
            if (employee is null)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.NOT_FOUND, ErrorMessages.NotFound);
            }
            if (!_currentUser.CanAccessBranch(employee.BranchId))
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.FORBIDDEN_BRANCH, ErrorMessages.ForbiddenBranch);
            }
            try { employee.UpdateDetails(request.FullName, request.Email, request.Phone, request.JobTitle, request.Address.ToValueObject()); }
            catch (Exception ex) when (ex is ArgumentException or IdentityDomainException)
            {
                await _unitOfWork.RollbackTransactionAsync(ct);
                return IdentityResults.Failure<EmployeeDto>(ErrorCode.VALIDATION_ERROR, ex.Message);
            }
            if (request.IsActive.HasValue) employee.SetActive(request.IsActive.Value);
            await _audit.LogAsync("employee.updated", "identity", "EMPLOYEE", employee.EmployeeId, null,
                new { employee.FullName, employee.Email, employee.Phone, employee.JobTitle, employee.IsActive }, employee.BranchId, ct: ct);
            await _outbox.EnqueueAsync("identity.employee.updated", employee.BranchId, new { employee.EmployeeId, employee.IsActive }, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);
            return Result<EmployeeDto>.Success(EmployeeDtoMapper.From(employee));
        }
        catch { await _unitOfWork.RollbackTransactionAsync(ct); throw; }
    }

    private bool IsAdmin() => string.Equals(_currentUser.Role, UserRole.Admin.ToString(), StringComparison.Ordinal);
    private bool IsAllBranchAdmin() => IsAdmin() && string.Equals(_currentUser.BranchScope, BranchScope.ALL.ToString(), StringComparison.Ordinal);
}
