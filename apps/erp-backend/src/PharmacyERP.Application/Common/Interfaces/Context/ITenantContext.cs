namespace PharmacyERP.Application.Common.Interfaces.Context;

public interface ITenantContext
{
    Guid? OrganizationId { get; }
    bool IsTenantBound { get; }
    bool IsSystemBypassAllowed { get; }
    bool IsSystemBypassEnabled { get; }
    void SetTenant(Guid organizationId);
    void AllowSystemBypass();
}