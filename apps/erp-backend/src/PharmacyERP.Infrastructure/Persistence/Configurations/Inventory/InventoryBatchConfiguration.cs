using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Catalog;
using PharmacyERP.Domain.Entities.Inventory;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;

public class InventoryBatchConfiguration : IEntityTypeConfiguration<InventoryBatch>
{
    public void Configure(EntityTypeBuilder<InventoryBatch> builder)
    {
        builder.ToTable("INVENTORY_BATCH", "inventory");

        builder.HasKey(x => x.BatchId);
        builder.Property(x => x.BatchId).HasColumnName("batch_id").ValueGeneratedNever();

        // Column Mappings
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.ProductId).HasColumnName("product_id").IsRequired();
        builder.Property(x => x.BatchNumber).HasColumnName("batch_number").HasMaxLength(80).IsRequired();
        builder.Property(x => x.ManufacturedOn).HasColumnName("manufactured_on").HasColumnType("date");
        builder.Property(x => x.ExpiresOn).HasColumnName("expires_on").HasColumnType("date");
        builder.Property(x => x.QualityStatus)
            .HasColumnName("quality_status")
            .HasConversion<string>()
            .HasMaxLength(25)
            .IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();

        // Alternate Keys
        builder.HasAlternateKey(x => new { x.OrganizationId, x.ProductId, x.BatchId });
        builder.HasAlternateKey(x => new { x.OrganizationId, x.BatchId });

        // Partial Unique Indexes for PostgreSQL (Handling NULL and NOT NULL expires_on)
        builder.HasIndex(x => new { x.OrganizationId, x.ProductId, x.BatchNumber, x.ExpiresOn })
            .IsUnique()
            .HasFilter("expires_on IS NOT NULL");

        builder.HasIndex(x => new { x.OrganizationId, x.ProductId, x.BatchNumber })
            .IsUnique()
            .HasFilter("expires_on IS NULL");

        // FEFO Index
        builder.HasIndex(x => new { x.OrganizationId, x.ProductId, x.QualityStatus, x.ExpiresOn, x.BatchId });

        // Check Constraints
        builder.ToTable(t =>
        {
            t.HasCheckConstraint("CK_INVENTORY_BATCH_quality_status", "quality_status IN ('AVAILABLE', 'QUARANTINED', 'EXPIRED', 'RECALLED')");
            t.HasCheckConstraint("CK_INVENTORY_BATCH_dates", "manufactured_on IS NULL OR expires_on IS NULL OR manufactured_on <= expires_on");
        });

        // Composite Foreign Key to Product
        builder.HasOne(x => x.Product)
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.ProductId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.ProductId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}