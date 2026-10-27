using System.Text.Json;
using Moq;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Utilities;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Application.Features.Integration.Services.Implementations;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using Xunit;

namespace PharmacyERP.UnitTests.Application.Integration;

public class IntegrationServicesTests
{
    private readonly Mock<ITenantContext> _tenantContextMock;
    private readonly Mock<ICurrentUser> _currentUserMock;
    private readonly Mock<IDateTimeProvider> _dateTimeProviderMock;
    private readonly Guid _organizationId;

    public IntegrationServicesTests()
    {
        _organizationId = Guid.NewGuid();

        _tenantContextMock = new Mock<ITenantContext>();
        _tenantContextMock.Setup(x => x.OrganizationId).Returns(_organizationId);
        _tenantContextMock.Setup(x => x.IsTenantBound).Returns(true);

        _currentUserMock = new Mock<ICurrentUser>();
        _currentUserMock.Setup(x => x.UserId).Returns(Guid.NewGuid());
        _currentUserMock.Setup(x => x.TraceId).Returns("test-trace-id");
        _currentUserMock.Setup(x => x.IsAuthenticated).Returns(true);

        _dateTimeProviderMock = new Mock<IDateTimeProvider>();
        _dateTimeProviderMock.Setup(x => x.UtcNow).Returns(DateTimeOffset.UtcNow);
    }

    [Fact]
    public async Task IdempotencyService_CheckAsync_ReturnsIsReplayTrue_WhenHashMatches()
    {
        var repositoryMock = new Mock<IIdempotencyRepository>();
        var idempotencyKey = "test-key-123";
        var operationScope = "test.scope";
        var requestPayload = new { Amount = 100 };
        var payloadHash = CanonicalJsonHasher.ComputeSha256Hex(requestPayload);

        var existingRecord = new IdempotencyRecord(_organizationId, null, operationScope, idempotencyKey, payloadHash, "{\"status\":\"success\"}", _dateTimeProviderMock.Object.UtcNow);

        repositoryMock.Setup(x => x.GetAsync(_organizationId, null, operationScope, idempotencyKey, It.IsAny<CancellationToken>())).ReturnsAsync(existingRecord);

        var service = new IdempotencyService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object);
        var result = await service.CheckAsync<object, object>(operationScope, idempotencyKey, null, requestPayload);

        Assert.True(result.IsReplay);
        Assert.NotNull(result.ReplayedResponse);
    }

    [Fact]
    public async Task IdempotencyService_CheckAsync_ThrowsException_WhenHashMismatches()
    {
        var repositoryMock = new Mock<IIdempotencyRepository>();
        var idempotencyKey = "test-key-123";
        var operationScope = "test.scope";

        var originalPayload = new { Amount = 100 };
        var tamperedPayload = new { Amount = 500 };
        var originalHash = CanonicalJsonHasher.ComputeSha256Hex(originalPayload);

        var existingRecord = new IdempotencyRecord(_organizationId, null, operationScope, idempotencyKey, originalHash, "{}", _dateTimeProviderMock.Object.UtcNow);

        repositoryMock.Setup(x => x.GetAsync(_organizationId, null, operationScope, idempotencyKey, It.IsAny<CancellationToken>())).ReturnsAsync(existingRecord);

        var service = new IdempotencyService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object);

        await Assert.ThrowsAsync<IntegrationDomainException>(() => service.CheckAsync<object, object>(operationScope, idempotencyKey, null, tamperedPayload));
    }

    [Fact]
    public async Task IdempotencyService_CheckAsync_ReturnsIsReplayFalse_WhenRecordDoesNotExist()
    {
        var repositoryMock = new Mock<IIdempotencyRepository>();
        var idempotencyKey = "new-key-456";
        var operationScope = "test.scope";

        repositoryMock.Setup(x => x.GetAsync(_organizationId, null, operationScope, idempotencyKey, It.IsAny<CancellationToken>())).ReturnsAsync((IdempotencyRecord?)null);

        var service = new IdempotencyService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object);
        var result = await service.CheckAsync<object, object>(operationScope, idempotencyKey, null, new { Amount = 200 });

        Assert.False(result.IsReplay);
        Assert.Null(result.ReplayedResponse);
    }

    [Fact]
    public async Task IdempotencyService_PersistResponseAsync_SavesRecordWithCorrectHashAndSerializedResponse()
    {
        var repositoryMock = new Mock<IIdempotencyRepository>();
        var idempotencyKey = "test-key-789";
        var operationScope = "test.scope";
        var requestPayload = new { Command = "Create" };
        var responsePayload = new { ResultId = 123, Status = "Created" };

        IdempotencyRecord? savedRecord = null;
        repositoryMock.Setup(x => x.AddAsync(It.IsAny<IdempotencyRecord>(), It.IsAny<CancellationToken>()))
            .Callback<IdempotencyRecord, CancellationToken>((rec, _) => savedRecord = rec)
            .Returns(Task.CompletedTask);

        var service = new IdempotencyService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object);
        await service.PersistResponseAsync(operationScope, idempotencyKey, null, requestPayload, responsePayload);

        Assert.NotNull(savedRecord);
        Assert.Equal(idempotencyKey, savedRecord.IdempotencyKey);
        Assert.Equal(operationScope, savedRecord.OperationScope);
        Assert.Contains("123", savedRecord.ResponseBody);
        Assert.Contains("Created", savedRecord.ResponseBody);
        Assert.Equal(64, savedRecord.PayloadHash.Length);
    }

    [Fact]
    public async Task OutboxService_EnqueueAsync_AllocatesSequenceAndSavesEvent()
    {
        var repositoryMock = new Mock<IOutboxRepository>();
        var cursor = new OutboxEventCursor(_organizationId);

        repositoryMock.Setup(x => x.LockAndGetCursorAsync(_organizationId, It.IsAny<CancellationToken>())).ReturnsAsync(cursor);

        OutboxEvent? savedEvent = null;
        repositoryMock.Setup(x => x.AddEventAsync(It.IsAny<OutboxEvent>(), It.IsAny<CancellationToken>()))
            .Callback<OutboxEvent, CancellationToken>((evt, _) => savedEvent = evt)
            .Returns(Task.CompletedTask);

        var service = new OutboxService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object, _currentUserMock.Object);
        await service.EnqueueAsync("inventory.stock.adjusted", null, new { ProductId = Guid.NewGuid(), Qty = 5 });

        Assert.NotNull(savedEvent);
        Assert.Equal(1, savedEvent.EventSequence);
        Assert.Equal("inventory.stock.adjusted", savedEvent.EventType);
        Assert.Equal(1, cursor.LastEventSequence);
    }

    [Fact]
    public async Task OutboxService_EnqueueAsync_ThrowsInvalidOperationException_WhenCursorIsMissing()
    {
        var repositoryMock = new Mock<IOutboxRepository>();
        repositoryMock.Setup(x => x.LockAndGetCursorAsync(_organizationId, It.IsAny<CancellationToken>())).ReturnsAsync((OutboxEventCursor?)null);

        var service = new OutboxService(repositoryMock.Object, _tenantContextMock.Object, _dateTimeProviderMock.Object, _currentUserMock.Object);
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => service.EnqueueAsync("test.event", null, new { Data = "Test" }));

        Assert.Contains("OutboxEventCursor missing", exception.Message);
    }

    [Fact]
    public async Task AuditLogger_LogAsync_CreatesValidAuditEntry()
    {
        var repositoryMock = new Mock<IAuditLogRepository>();

        AuditLog? savedLog = null;
        repositoryMock.Setup(x => x.AddAsync(It.IsAny<AuditLog>(), It.IsAny<CancellationToken>()))
            .Callback<AuditLog, CancellationToken>((log, _) => savedLog = log)
            .Returns(Task.CompletedTask);

        var service = new AuditLogger(repositoryMock.Object, _tenantContextMock.Object, _currentUserMock.Object, _dateTimeProviderMock.Object);
        await service.LogAsync("UPDATE", "catalog", "PRODUCT", Guid.NewGuid(), new { Price = 10 }, new { Price = 20 });

        Assert.NotNull(savedLog);
        Assert.Equal("UPDATE", savedLog.Action);
        Assert.Equal("catalog", savedLog.EntitySchema);
        Assert.Equal(AuditActorType.USER, savedLog.ActorType);
        Assert.Equal("test-trace-id", savedLog.TraceId);
        Assert.Contains("10", savedLog.BeforeData);
        Assert.Contains("20", savedLog.AfterData);
    }

    [Fact]
    public async Task AuditLogger_LogAsync_UsesSystemActor_WhenUserIsNotAuthenticatedAndNoOverrideProvided()
    {
        var repositoryMock = new Mock<IAuditLogRepository>();
        var unauthenticatedUserMock = new Mock<ICurrentUser>();
        unauthenticatedUserMock.Setup(x => x.IsAuthenticated).Returns(false);
        unauthenticatedUserMock.Setup(x => x.TraceId).Returns("system-trace-id");

        AuditLog? savedLog = null;
        repositoryMock.Setup(x => x.AddAsync(It.IsAny<AuditLog>(), It.IsAny<CancellationToken>()))
            .Callback<AuditLog, CancellationToken>((log, _) => savedLog = log)
            .Returns(Task.CompletedTask);

        var service = new AuditLogger(repositoryMock.Object, _tenantContextMock.Object, unauthenticatedUserMock.Object, _dateTimeProviderMock.Object);
        await service.LogAsync("BACKGROUND_SYNC", "integration", "SYSTEM", Guid.NewGuid(), null, null);

        Assert.NotNull(savedLog);
        Assert.Equal(AuditActorType.SYSTEM, savedLog.ActorType);
        Assert.Null(savedLog.ActorUserId);
    }

    [Fact]
    public async Task Services_ThrowInvalidOperationException_WhenOrganizationIdIsMissing()
    {
        var noTenantMock = new Mock<ITenantContext>();
        noTenantMock.Setup(x => x.OrganizationId).Returns((Guid?)null);

        var idempotencyService = new IdempotencyService(new Mock<IIdempotencyRepository>().Object, noTenantMock.Object, _dateTimeProviderMock.Object);
        var outboxService = new OutboxService(new Mock<IOutboxRepository>().Object, noTenantMock.Object, _dateTimeProviderMock.Object, _currentUserMock.Object);
        var auditLogger = new AuditLogger(new Mock<IAuditLogRepository>().Object, noTenantMock.Object, _currentUserMock.Object, _dateTimeProviderMock.Object);

        await Assert.ThrowsAsync<InvalidOperationException>(() => idempotencyService.CheckAsync<object, object>("scope", "key", null, new { }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => outboxService.EnqueueAsync("event", null, new { }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => auditLogger.LogAsync("ACTION", "schema", "entity", Guid.NewGuid(), null, null));
    }
}