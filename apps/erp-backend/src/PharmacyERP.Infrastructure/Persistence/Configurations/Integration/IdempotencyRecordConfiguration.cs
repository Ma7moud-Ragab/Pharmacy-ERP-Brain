using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Integration;

public class IdempotencyRecordConfiguration : IEntityTypeConfiguration<IdempotencyRecord>
{
    public void Configure(EntityTypeBuilder<IdempotencyRecord> builder)
    {
        builder.ToTable("IDEMPOTENCY_RECORD", "integration");

        builder.HasKey(x => x.IdempotencyRecordId);

        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.OperationScope, x.IdempotencyKey })
               .IsUnique()
               .HasFilter("branch_id IS NOT NULL");

        builder.HasIndex(x => new { x.OrganizationId, x.OperationScope, x.IdempotencyKey })
               .IsUnique()
               .HasFilter("branch_id IS NULL");

        builder.Property(x => x.IdempotencyRecordId).HasColumnName("idempotency_record_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id");
        builder.Property(x => x.BranchId).HasColumnName("branch_id");
        builder.Property(x => x.OperationScope).HasColumnName("operation_scope").HasMaxLength(100).IsRequired();
        builder.Property(x => x.IdempotencyKey).HasColumnName("idempotency_key").HasMaxLength(100).IsRequired();
        builder.Property(x => x.PayloadHash).HasColumnName("payload_hash").HasColumnType("char(64)").HasMaxLength(64).IsFixedLength().IsRequired();
        builder.Property(x => x.ResponseBody).HasColumnName("response_body").HasColumnType("jsonb").IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();

        builder.HasOne(x => x.Branch)
               .WithMany()
               .HasForeignKey(x => new { x.OrganizationId, x.BranchId })
               .HasPrincipalKey(b => new { b.OrganizationId, b.BranchId })
               .IsRequired(false)
               .OnDelete(DeleteBehavior.Restrict);
    }
}