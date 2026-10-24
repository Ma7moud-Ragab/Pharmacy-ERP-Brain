using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Integration.DTOs;

public sealed record AuditEntryRequest(
    string Action,
    string EntitySchema,
    string EntityName,
    Guid EntityId,
    object? BeforeData = null,
    object? AfterData = null,
    Guid? BranchId = null,
    AuditActorType? ActorTypeOverride = null,
    string? SourcePromptId = null
);