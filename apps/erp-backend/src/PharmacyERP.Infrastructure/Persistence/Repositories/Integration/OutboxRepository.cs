using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories.Integration;

public class OutboxRepository : IOutboxRepository
{
    private readonly PharmacyDbContext _dbContext;

    public OutboxRepository(PharmacyDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<OutboxEventCursor?> LockAndGetCursorAsync(Guid organizationId, CancellationToken ct = default)
    {
        if (_dbContext.Database.IsRelational())
        {
            await _dbContext.Database.ExecuteSqlInterpolatedAsync(
                $@"INSERT INTO integration.""OUTBOX_EVENT_CURSOR"" (organization_id, last_event_sequence, updated_at)
                   VALUES ({organizationId}, 0, NOW())
                   ON CONFLICT (organization_id) DO NOTHING;", ct);

            var cursors = await _dbContext.OutboxEventCursors
                .FromSqlInterpolated($"SELECT * FROM integration.\"OUTBOX_EVENT_CURSOR\" WHERE organization_id = {organizationId} FOR UPDATE")
                .ToListAsync(ct);

            return cursors.FirstOrDefault();
        }

        var localCursor = await _dbContext.OutboxEventCursors
            .FirstOrDefaultAsync(x => x.OrganizationId == organizationId, ct);

        if (localCursor == null)
        {
            localCursor = new OutboxEventCursor(organizationId);
            await _dbContext.OutboxEventCursors.AddAsync(localCursor, ct);
        }

        return localCursor;
    }

    public async Task AddEventAsync(OutboxEvent outboxEvent, CancellationToken ct = default)
    {
        await _dbContext.OutboxEvents.AddAsync(outboxEvent, ct);
    }
}