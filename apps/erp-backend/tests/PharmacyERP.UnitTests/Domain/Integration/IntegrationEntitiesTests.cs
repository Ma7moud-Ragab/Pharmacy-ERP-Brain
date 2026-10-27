using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using Xunit;

namespace PharmacyERP.UnitTests.Domain.Integration;

public class IntegrationEntitiesTests
{
    [Fact]
    public void OutboxEventCursor_AllocateNextSequence_IncrementsMonotonically()
    {
        var orgId = Guid.NewGuid();
        var cursor = new OutboxEventCursor(orgId);
        var now = DateTimeOffset.UtcNow;

        Assert.Equal(0, cursor.LastEventSequence);

        var seq1 = cursor.AllocateNextSequence(now);
        var seq2 = cursor.AllocateNextSequence(now.AddSeconds(1));

        Assert.Equal(1, seq1);
        Assert.Equal(2, seq2);
        Assert.Equal(2, cursor.LastEventSequence);
    }

    [Fact]
    public void OutboxEvent_Lifecycle_RecordsFailureAndMarksPublished()
    {
        var evt = new OutboxEvent(
            Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(),
            1, "inventory.stock.adjusted", "{\"qty\":5}", "trace-123");

        var longError = new string('E', 600);
        evt.RecordPublishFailure(longError, DateTimeOffset.UtcNow);

        Assert.Equal(1, evt.AttemptCount);
        Assert.Equal(500, evt.LastError!.Length);
        Assert.Null(evt.PublishedAt);

        var publishedTime = DateTimeOffset.UtcNow;
        evt.MarkPublished(publishedTime);

        Assert.Equal(publishedTime, evt.PublishedAt);
        Assert.Null(evt.LastError);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-5)]
    public void OutboxEvent_InvalidSequence_ThrowsIntegrationDomainException(long invalidSequence)
    {
        Assert.Throws<IntegrationDomainException>(() =>
            new OutboxEvent(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), invalidSequence, "type", "{}", "trace"));
    }

    [Fact]
    public void OutboxEvent_EmptyRequiredFields_ThrowsIntegrationDomainException()
    {
        Assert.Throws<IntegrationDomainException>(() =>
            new OutboxEvent(Guid.NewGuid(), Guid.NewGuid(), null, 1, "", "{}", "trace"));

        Assert.Throws<IntegrationDomainException>(() =>
            new OutboxEvent(Guid.NewGuid(), Guid.NewGuid(), null, 1, "type", "", "trace"));
    }

    [Fact]
    public void IdempotencyRecord_InvalidHashLength_ThrowsInvalidIdempotencyHashException()
    {
        Assert.Throws<InvalidIdempotencyHashException>(() =>
            new IdempotencyRecord(Guid.NewGuid(), null, "catalog.product.create", "key-1", "short-hash", "{}", DateTimeOffset.UtcNow));
    }

    [Fact]
    public void IdempotencyRecord_EmptyRequiredFields_ThrowsIntegrationDomainException()
    {
        var validHash = new string('a', 64);

        Assert.Throws<IntegrationDomainException>(() =>
            new IdempotencyRecord(Guid.NewGuid(), null, "", "key", validHash, "{}", DateTimeOffset.UtcNow));

        Assert.Throws<IntegrationDomainException>(() =>
            new IdempotencyRecord(Guid.NewGuid(), null, "scope", "", validHash, "{}", DateTimeOffset.UtcNow));
    }

    [Fact]
    public void AuditLog_AiAssistedWithoutPromptIdOrUserId_ThrowsMissingSourcePromptIdException()
    {
        Assert.Throws<MissingSourcePromptIdException>(() =>
            new AuditLog(Guid.NewGuid(), null, Guid.NewGuid(), null, AuditActorType.AI_ASSISTED,
                "CREATE", "catalog", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-1", DateTimeOffset.UtcNow, sourcePromptId: null));

        Assert.Throws<MissingSourcePromptIdException>(() =>
            new AuditLog(Guid.NewGuid(), null, actorUserId: null, null, AuditActorType.AI_ASSISTED,
                "CREATE", "catalog", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-1", DateTimeOffset.UtcNow, sourcePromptId: "prompt-99"));
    }

    [Fact]
    public void AuditLog_EmptyRequiredFields_ThrowsIntegrationDomainException()
    {
        Assert.Throws<IntegrationDomainException>(() =>
            new AuditLog(Guid.NewGuid(), null, Guid.NewGuid(), null, AuditActorType.USER,
                "", "catalog", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-1", DateTimeOffset.UtcNow));

        Assert.Throws<IntegrationDomainException>(() =>
            new AuditLog(Guid.NewGuid(), null, Guid.NewGuid(), null, AuditActorType.USER,
                "CREATE", "", "PRODUCT", Guid.NewGuid(), null, "{}", "trace-1", DateTimeOffset.UtcNow));
    }
}