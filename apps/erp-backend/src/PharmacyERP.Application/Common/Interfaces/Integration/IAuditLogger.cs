using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Common.Interfaces.Integration
{
    public interface IAuditLogger
    {
        Task LogAsync(string action, string entitySchema, string entityName, Guid entityId, object? beforeData, object? afterData, Guid? branchId = null, AuditActorType? actorTypeOverride = null, string? sourcePromptId = null, CancellationToken ct = default);
    }
}
