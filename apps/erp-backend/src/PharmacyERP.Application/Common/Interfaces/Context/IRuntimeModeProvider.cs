using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Common.Interfaces.Context
{
    public interface IRuntimeModeProvider
    {
        ErpRuntimeMode CurrentMode { get; }
        Guid? EnrolledBranchId { get; }
    }
}
