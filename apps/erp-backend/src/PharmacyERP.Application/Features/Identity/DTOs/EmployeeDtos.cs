using System.ComponentModel.DataAnnotations;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.DTOs;

public sealed record CreateEmployeeRequest
{
    public Guid BranchId { get; init; }
    [Required, StringLength(30)] public string EmployeeNo { get; init; } = string.Empty;
    [Required, StringLength(150)] public string FullName { get; init; } = string.Empty;
    [EmailAddress, StringLength(254)] public string? Email { get; init; }
    [StringLength(30)] public string? Phone { get; init; }
    [Required, StringLength(80)] public string JobTitle { get; init; } = string.Empty;
    [Required] public AddressDto Address { get; init; } = new();
    public DateOnly HiredOn { get; init; } = DateOnly.FromDateTime(DateTime.UtcNow);
}

public sealed record UpdateEmployeeRequest
{
    [Required, StringLength(150)] public string FullName { get; init; } = string.Empty;
    [EmailAddress, StringLength(254)] public string? Email { get; init; }
    [StringLength(30)] public string? Phone { get; init; }
    [Required, StringLength(80)] public string JobTitle { get; init; } = string.Empty;
    [Required] public AddressDto Address { get; init; } = new();
    public bool? IsActive { get; init; }
}

public sealed record EmployeeDto(Guid EmployeeId, Guid OrganizationId, Guid BranchId, string EmployeeNo,
    string FullName, string? Email, string? Phone, string JobTitle, AddressDto Address, DateOnly HiredOn, bool IsActive);

public static class EmployeeDtoMapper
{
    public static EmployeeDto From(Employee employee) => new(employee.EmployeeId, employee.OrganizationId, employee.BranchId,
        employee.EmployeeNo, employee.FullName, employee.Email, employee.Phone, employee.JobTitle, AddressDto.From(employee.Address), employee.HiredOn, employee.IsActive);
}
