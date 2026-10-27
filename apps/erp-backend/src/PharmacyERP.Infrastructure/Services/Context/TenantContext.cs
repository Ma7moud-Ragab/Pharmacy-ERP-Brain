using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Infrastructure.Services.Context;

public class TenantContext : ITenantContext
{
    public Guid? OrganizationId { get; private set; }
    public bool IsTenantBound => OrganizationId.HasValue;
    public bool IsSystemBypassAllowed { get; private set; }
    public bool IsSystemBypassEnabled => IsSystemBypassAllowed;

    public void SetTenant(Guid organizationId)
    {
        if (organizationId == Guid.Empty)
        {
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));
        }

        OrganizationId = organizationId;
    }

    public void AllowSystemBypass()
    {
        IsSystemBypassAllowed = true;
    }
}