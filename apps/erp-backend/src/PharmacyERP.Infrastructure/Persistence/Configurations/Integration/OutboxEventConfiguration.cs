using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Integration;

public class OutboxEventConfiguration : IEntityTypeConfiguration<OutboxEvent>
{
    public void Configure(EntityTypeBuilder<OutboxEvent> builder)
    {
        builder.ToTable("OUTBOX_EVENT", "integration", t =>
        {
            t.HasCheckConstraint("CK_OUTBOX_EVENT_attempt_count", "attempt_count >= 0");
        });

        builder.HasKey(x => x.EventId);

        builder.HasIndex(x => new { x.OrganizationId, x.EventSequence }).IsUnique();
        builder.HasIndex(x => new { x.PublishedAt, x.OccurredAt }).HasFilter("published_at IS NULL");
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.EventSequence });

        builder.Property(x => x.EventId).HasColumnName("event_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id");
        builder.Property(x => x.EventSequence).HasColumnName("event_sequence").HasColumnType("bigint").IsRequired();
        builder.Property(x => x.EventType).HasColumnName("event_type").HasMaxLength(80).IsRequired();
        builder.Property(x => x.SchemaVersion).HasColumnName("schema_version").HasMaxLength(20).IsRequired();
        builder.Property(x => x.Payload).HasColumnName("payload").HasColumnType("jsonb").IsRequired();
        builder.Property(x => x.OccurredAt).HasColumnName("occurred_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.PublishedAt).HasColumnName("published_at").HasColumnType("timestamptz");
        builder.Property(x => x.AttemptCount).HasColumnName("attempt_count").HasDefaultValue(0).IsRequired();
        builder.Property(x => x.LastError).HasColumnName("last_error").HasMaxLength(500);
        builder.Property(x => x.TraceId).HasColumnName("trace_id").HasMaxLength(100).IsRequired();

        builder.HasOne<OutboxEventCursor>()
               .WithMany()
               .HasForeignKey(x => x.OrganizationId)
               .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.Branch)
               .WithMany()
               .HasForeignKey(x => new { x.OrganizationId, x.BranchId })
               .HasPrincipalKey(b => new { b.OrganizationId, b.BranchId })
               .IsRequired(false)
               .OnDelete(DeleteBehavior.Restrict);
    }
}