using Microsoft.Extensions.Configuration;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Infrastructure.Services.Context;

public class RuntimeModeProvider : IRuntimeModeProvider
{
    public ErpRuntimeMode CurrentMode { get; }
    public Guid? EnrolledBranchId { get; }

    public RuntimeModeProvider(IConfiguration configuration)
    {
        var modeString = configuration["ERP_RUNTIME_MODE"];
        CurrentMode = Enum.TryParse<ErpRuntimeMode>(modeString, true, out var mode)
            ? mode
            : ErpRuntimeMode.Cloud;

        var branchIdString = configuration["ENROLLED_BRANCH_ID"];
        EnrolledBranchId = Guid.TryParse(branchIdString, out var id) ? id : null;
    }
}