using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.BackgroundServices;

public class OutboxPublisherWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<OutboxPublisherWorker> _logger;
    private readonly TimeSpan _pollingInterval;

    public OutboxPublisherWorker(
        IServiceScopeFactory scopeFactory,
        ILogger<OutboxPublisherWorker> logger,
        TimeSpan? pollingInterval = null)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _pollingInterval = pollingInterval ?? TimeSpan.FromSeconds(5);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ProcessPendingOutboxBatchAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error occurred while processing pending outbox events.");
            }

            await Task.Delay(_pollingInterval, stoppingToken);
        }
    }

    public async Task<int> ProcessPendingOutboxBatchAsync(CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var tenantContext = scope.ServiceProvider.GetRequiredService<ITenantContext>();
        var dbContext = scope.ServiceProvider.GetRequiredService<PharmacyDbContext>();
        var unitOfWork = scope.ServiceProvider.GetRequiredService<IUnitOfWork>();
        var dateTimeProvider = scope.ServiceProvider.GetRequiredService<IDateTimeProvider>();

        tenantContext.AllowSystemBypass();

        await unitOfWork.BeginTransactionAsync(ct);
        try
        {
            var pendingEvents = await dbContext.OutboxEvents
                .IgnoreQueryFilters()
                .Where(e => e.PublishedAt == null)
                .OrderBy(e => e.OrganizationId)
                .ThenBy(e => e.EventSequence)
                .Take(50)
                .ToListAsync(ct);

            foreach (var outboxEvent in pendingEvents)
            {
                try
                {
                    outboxEvent.MarkPublished(dateTimeProvider.UtcNow);
                }
                catch (Exception ex)
                {
                    outboxEvent.RecordPublishFailure(ex.Message, dateTimeProvider.UtcNow);
                }
            }

            await unitOfWork.CommitTransactionAsync(ct);
            return pendingEvents.Count;
        }
        catch
        {
            await unitOfWork.RollbackTransactionAsync(ct);
            throw;
        }
    }
}