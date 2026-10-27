using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Enums;

namespace PharmacyERP.Application.Features.Integration.Services.Implementations;

public class AuditLogger : IAuditLogger
{
    private static readonly JsonSerializerOptions AuditJsonOptions = new()
    {
        WriteIndented = false,
        ReferenceHandler = ReferenceHandler.IgnoreCycles,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new JsonStringEnumConverter() }
    };

    private readonly IAuditLogRepository _repository;
    private readonly ITenantContext _tenantContext;
    private readonly ICurrentUser _currentUser;
    private readonly IDateTimeProvider _dateTimeProvider;

    public AuditLogger(IAuditLogRepository repository, ITenantContext tenantContext, ICurrentUser currentUser, IDateTimeProvider dateTimeProvider)
    {
        _repository = repository;
        _tenantContext = tenantContext;
        _currentUser = currentUser;
        _dateTimeProvider = dateTimeProvider;
    }

    public async Task LogAsync(
         string action, string entitySchema, string entityName, Guid entityId,
         object? beforeData, object? afterData, Guid? branchId = null,
         AuditActorType? actorTypeOverride = null, string? sourcePromptId = null, CancellationToken ct = default)
    {
        if (!_tenantContext.OrganizationId.HasValue)
            throw new InvalidOperationException("OrganizationId is required for audit logs.");

        var orgId = _tenantContext.OrganizationId.Value;
        var actorType = actorTypeOverride ?? (_currentUser.IsAuthenticated ? AuditActorType.USER : AuditActorType.SYSTEM);
        var beforeJson = beforeData != null ? JsonSerializer.Serialize(beforeData, AuditJsonOptions) : null;
        var afterJson = afterData != null ? JsonSerializer.Serialize(afterData, AuditJsonOptions) : null;

        var logEntry = new AuditLog(orgId, branchId, _currentUser.UserId, _currentUser.EmployeeId, actorType, action,
            entitySchema, entityName, entityId, beforeJson, afterJson, _currentUser.TraceId, _dateTimeProvider.UtcNow, sourcePromptId);

        await _repository.AddAsync(logEntry, ct);
    }
}