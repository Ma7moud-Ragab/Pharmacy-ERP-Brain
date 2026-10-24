namespace PharmacyERP.Application.Common.Interfaces.Context
{
    public interface ICurrentUser
    {
        Guid? UserId { get; }
        Guid? EmployeeId { get; }
        Guid? OrganizationId { get; }
        string? Role { get; }
        string? BranchScope { get; }
        IReadOnlySet<Guid> AuthorizedBranchIds { get; }
        IReadOnlySet<string> Scopes { get; }
        string TraceId { get; }
        bool IsAuthenticated { get; }
        bool CanAccessBranch(Guid branchId);
    }
}
