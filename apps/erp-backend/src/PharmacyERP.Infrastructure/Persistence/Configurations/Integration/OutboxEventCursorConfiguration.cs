using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Integration;

public class OutboxEventCursorConfiguration : IEntityTypeConfiguration<OutboxEventCursor>
{
    public void Configure(EntityTypeBuilder<OutboxEventCursor> builder)
    {
        builder.ToTable("OUTBOX_EVENT_CURSOR", "integration", t =>
        {
            t.HasCheckConstraint("CK_OUTBOX_EVENT_CURSOR_nonnegative", "last_event_sequence >= 0");
        });

        builder.HasKey(x => x.OrganizationId);

        builder.Property(x => x.OrganizationId).HasColumnName("organization_id");
        builder.Property(x => x.LastEventSequence).HasColumnName("last_event_sequence").HasColumnType("bigint").HasDefaultValue(0L).IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();

        builder.HasOne(x => x.Organization)
               .WithOne()
               .HasForeignKey<OutboxEventCursor>(x => x.OrganizationId)
               .OnDelete(DeleteBehavior.Restrict);
    }
}