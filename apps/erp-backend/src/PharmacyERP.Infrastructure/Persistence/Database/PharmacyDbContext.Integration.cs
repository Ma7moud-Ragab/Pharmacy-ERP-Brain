using Microsoft.EntityFrameworkCore;
using PharmacyERP.Domain.Entities.Integration;


namespace PharmacyERP.Infrastructure.Persistence.Database
{
    public partial class PharmacyDbContext
    {
        public DbSet<OutboxEventCursor> OutboxEventCursors => Set<OutboxEventCursor>();
        public DbSet<OutboxEvent> OutboxEvents => Set<OutboxEvent>();
        public DbSet<IdempotencyRecord> IdempotencyRecords => Set<IdempotencyRecord>();
        public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    }
}
