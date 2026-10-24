using Microsoft.EntityFrameworkCore;
using Moq;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Features.Integration.Services.Implementations;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Infrastructure.Persistence.Database;
using PharmacyERP.Infrastructure.Persistence.Repositories.Integration;
using PharmacyERP.Infrastructure.Services.Context;
using Xunit;

namespace PharmacyERP.IntegrationTests.Persistence;

public class IdempotencyAndOutboxAtomicityTests
{
    [Fact]
    public async Task OutboxAndIdempotency_WhenChangeTrackerClearedBeforeSave_LeavesNoGapInSequenceAndAllowsRetry()
    {
        var dbName = Guid.NewGuid().ToString();
        var orgId = Guid.NewGuid();

        var tenantContext = new TenantContext();
        tenantContext.SetTenant(orgId);

        var options = new DbContextOptionsBuilder<PharmacyDbContext>()
            .UseInMemoryDatabase(dbName)
            .Options;

        var currentUserMock = new Mock<ICurrentUser>();
        currentUserMock.SetupGet(x => x.IsAuthenticated).Returns(true);
        currentUserMock.SetupGet(x => x.TraceId).Returns("trace-atomicity-1");

        var dateTimeProvider = new DateTimeProvider();

        await using (var seedContext = new PharmacyDbContext(options, tenantContext))
        {
            seedContext.OutboxEventCursors.Add(new OutboxEventCursor(orgId));
            await seedContext.SaveChangesAsync();
        }

        // Simulate failed unit of work before SaveChanges / Rollback
        await using (var failedContext = new PharmacyDbContext(options, tenantContext))
        {
            var outboxRepo = new OutboxRepository(failedContext);
            var idempotencyRepo = new IdempotencyRepository(failedContext);

            var outboxService = new OutboxService(outboxRepo, tenantContext, dateTimeProvider, currentUserMock.Object);
            var idempotencyService = new IdempotencyService(idempotencyRepo, tenantContext, dateTimeProvider);

            await outboxService.EnqueueAsync("catalog.product.created", null, new { Name = "Panadol" });
            await idempotencyService.PersistResponseAsync("catalog.product.create", "idem-key-1", null, new { Name = "Panadol" }, new { Status = "OK" });

            // Simulate transaction rollback by discarding uncommitted changes
            failedContext.ChangeTracker.Clear();
        }

        // Verify database state was not mutated and retry gets sequence #1
        await using (var retryContext = new PharmacyDbContext(options, tenantContext))
        {
            var outboxRepo = new OutboxRepository(retryContext);
            var idempotencyRepo = new IdempotencyRepository(retryContext);

            var outboxService = new OutboxService(outboxRepo, tenantContext, dateTimeProvider, currentUserMock.Object);
            var idempotencyService = new IdempotencyService(idempotencyRepo, tenantContext, dateTimeProvider);

            var check = await idempotencyService.CheckAsync<object, object>("catalog.product.create", "idem-key-1", null, new { Name = "Panadol" });
            Assert.False(check.IsReplay);

            await outboxService.EnqueueAsync("catalog.product.created", null, new { Name = "Panadol" });
            await idempotencyService.PersistResponseAsync("catalog.product.create", "idem-key-1", null, new { Name = "Panadol" }, new { Status = "OK" });

            await retryContext.SaveChangesAsync();

            var savedEvents = await retryContext.OutboxEvents.ToListAsync();
            Assert.Single(savedEvents);
            Assert.Equal(1L, savedEvents[0].EventSequence);

            var replayCheck = await idempotencyService.CheckAsync<object, object>("catalog.product.create", "idem-key-1", null, new { Name = "Panadol" });
            Assert.True(replayCheck.IsReplay);
        }
    }
}