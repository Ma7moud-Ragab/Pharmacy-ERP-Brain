using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Common.Constants;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.CrossModule;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Application.Features.Identity.DTOs;
using PharmacyERP.Application.Features.Identity.Interfaces;
using PharmacyERP.Application.Features.Identity.Services.Interfaces;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Identity.Services.Implementations;

public sealed class OrganizationProvisioningService : IOrganizationProvisioningService
{
    private readonly IOrganizationRepository _organizations;
    private readonly IBranchRepository _branches;
    private readonly IEmployeeRepository _employees;
    private readonly IUserAccountRepository _users;
    private readonly IGenericRepository<OutboxEventCursor> _cursors;
    private readonly IPasswordHasherService _passwords;
    private readonly IBranchDefaultLocationSeeder _locationSeeder;
    private readonly IUnitOfWork _unitOfWork;
    private readonly IAuditLogger _audit;
    private readonly IOutboxService _outbox;
    private readonly ITenantContext _tenant;
    private readonly ICurrentUser _currentUser;
    private readonly IDateTimeProvider _clock;

    public OrganizationProvisioningService(IOrganizationRepository organizations, IBranchRepository branches,
        IEmployeeRepository employees, IUserAccountRepository users, IGenericRepository<OutboxEventCursor> cursors,
        IPasswordHasherService passwords, IBranchDefaultLocationSeeder locationSeeder, IUnitOfWork unitOfWork,
        IAuditLogger audit, IOutboxService outbox, ITenantContext tenant, ICurrentUser currentUser, IDateTimeProvider clock)
    {
        _organizations = organizations; _branches = branches; _employees = employees; _users = users; _cursors = cursors;
        _passwords = passwords; _locationSeeder = locationSeeder; _unitOfWork = unitOfWork; _audit = audit;
        _outbox = outbox; _tenant = tenant; _currentUser = currentUser; _clock = clock;
    }

    public async Task<Result<OrganizationDto>> CreateAsync(CreateOrganizationRequest request, CancellationToken ct = default)
    {
        if (!string.Equals(_currentUser.Role, "PlatformProvisioner", StringComparison.Ordinal))
            return IdentityResults.Failure<OrganizationDto>(ErrorCode.FORBIDDEN, "Only a platform provisioner may create organizations.");

        Organization organization;
        Branch branch;
        Employee employee;
        UserAccount admin;
        try
        {
            organization = Organization.Create(request.OrganizationCode, request.Name, request.BaseCurrency, request.TimeZoneId, request.Address.ToValueObject());
            branch = Branch.Create(organization.OrganizationId, request.InitialBranch.BranchCode, request.InitialBranch.Name, request.InitialBranch.Address.ToValueObject());
            employee = Employee.Create(organization.OrganizationId, branch.BranchId,
                request.InitialEmployee.EmployeeNo, request.InitialEmployee.FullName, request.InitialEmployee.Email,
                request.InitialEmployee.Phone, request.InitialEmployee.JobTitle, request.InitialEmployee.Address.ToValueObject(), request.InitialEmployee.HiredOn);
            admin = UserAccount.Create(organization.OrganizationId, employee.EmployeeId,
                request.InitialAdmin.Username, "pending-hash", UserRole.Admin, BranchScope.ALL);
            admin.UpdatePasswordHash(_passwords.HashPassword(admin, request.InitialAdmin.Password), _clock.UtcNow);
        }
        catch (Exception ex) when (ex is ArgumentException or PharmacyERP.Domain.Exceptions.IdentityDomainException)
        {
            return IdentityResults.Failure<OrganizationDto>(ErrorCode.VALIDATION_ERROR, ex.Message);
        }

        try
        {
            // Probe globally under the database's explicit system-bypass setting, then use tenant RLS for writes.
            _tenant.AllowSystemBypass();
            await _unitOfWork.BeginTransactionAsync(ct);
            var exists = await _organizations.ExistsByCodeAsync(request.OrganizationCode, ct);
            await _unitOfWork.RollbackTransactionAsync(ct);
            if (exists)
                return IdentityResults.Failure<OrganizationDto>(ErrorCode.CONFLICT, ErrorMessages.DuplicateOrganizationCode);

            _tenant.SetTenant(organization.OrganizationId);
            await _unitOfWork.BeginTransactionAsync(ct);
            await _organizations.AddAsync(organization, ct);
            await _cursors.AddAsync(new OutboxEventCursor(organization.OrganizationId), ct);
            await _unitOfWork.SaveChangesAsync(ct);

            await _branches.AddAsync(branch, ct);
            await _locationSeeder.SeedDefaultLocationsAsync(organization.OrganizationId, branch.BranchId, ct);
            await _employees.AddAsync(employee, ct);
            await _users.AddAsync(admin, ct);
            await _audit.LogAsync("organization.created", "identity", "ORGANIZATION", organization.OrganizationId,
                null, new { organization.OrganizationCode, organization.Name, branch.BranchId, employee.EmployeeId, admin.UserId },
                branch.BranchId, AuditActorType.SYSTEM, ct: ct);
            await _outbox.EnqueueAsync("identity.organization.created", branch.BranchId,
                new { organization.OrganizationId, organization.OrganizationCode, branch.BranchId }, ct: ct);
            await _unitOfWork.CommitTransactionAsync(ct);

            return Result<OrganizationDto>.Success(new OrganizationDto(organization.OrganizationId, organization.OrganizationCode,
                organization.Name, organization.BaseCurrency, organization.TimeZoneId, branch.BranchId, employee.EmployeeId, admin.UserId));
        }
        catch
        {
            await _unitOfWork.RollbackTransactionAsync(ct);
            throw;
        }
    }
}

internal static class IdentityResults
{
    public static Result<T> Failure<T>(ErrorCode code, string message) => Result<T>.Failure(code, message);
    public static Result Failure(ErrorCode code, string message) => Result.Failure(code, message);
}
