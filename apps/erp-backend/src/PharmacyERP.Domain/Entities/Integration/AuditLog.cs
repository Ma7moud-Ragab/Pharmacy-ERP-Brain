using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Integration;

public class AuditLog
{
    public Guid AuditLogId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid? BranchId { get; private set; }
    public Guid? ActorUserId { get; private set; }
    public Guid? ActorEmployeeId { get; private set; }
    public AuditActorType ActorType { get; private set; }
    public string Action { get; private set; } = null!;
    public string EntitySchema { get; private set; } = null!;
    public string EntityName { get; private set; } = null!;
    public Guid EntityId { get; private set; }
    public string? SourcePromptId { get; private set; }
    public string? BeforeData { get; private set; }
    public string? AfterData { get; private set; }
    public string TraceId { get; private set; } = null!;
    public DateTimeOffset CreatedAt { get; private set; }

    public Branch? Branch { get; private set; }
    public UserAccount? ActorUser { get; private set; }
    public Employee? ActorEmployee { get; private set; }

    private AuditLog() { }

    public AuditLog(Guid organizationId, Guid? branchId, Guid? actorUserId, Guid? actorEmployeeId, AuditActorType actorType,
                    string action, string entitySchema, string entityName, Guid entityId,
                    string? beforeData, string? afterData, string traceId, DateTimeOffset createdAt, string? sourcePromptId = null)
    {
        if (actorType == AuditActorType.AI_ASSISTED && (actorUserId == null || string.IsNullOrWhiteSpace(sourcePromptId)))
            throw new MissingSourcePromptIdException();

        if (string.IsNullOrWhiteSpace(action)) throw new IntegrationDomainException("Action is required.");
        if (string.IsNullOrWhiteSpace(entitySchema)) throw new IntegrationDomainException("EntitySchema is required.");
        if (string.IsNullOrWhiteSpace(entityName)) throw new IntegrationDomainException("EntityName is required.");
        if (string.IsNullOrWhiteSpace(traceId)) throw new IntegrationDomainException("TraceId is required.");

        AuditLogId = Guid.NewGuid();
        OrganizationId = organizationId;
        BranchId = branchId;
        ActorUserId = actorUserId;
        ActorEmployeeId = actorEmployeeId;
        ActorType = actorType;
        Action = action;
        EntitySchema = entitySchema;
        EntityName = entityName;
        EntityId = entityId;
        BeforeData = beforeData;
        AfterData = afterData;
        TraceId = traceId;
        SourcePromptId = sourcePromptId;
        CreatedAt = createdAt; // Injected from Service
    }
}