using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Entities.Inventory;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;

public class InventoryLocationConfiguration : IEntityTypeConfiguration<InventoryLocation>
{
    public void Configure(EntityTypeBuilder<InventoryLocation> builder)
    {
        builder.ToTable("INVENTORY_LOCATION", "inventory");

        builder.HasKey(x => x.LocationId);

        // Column Mappings
        builder.Property(x => x.LocationId).HasColumnName("location_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.Property(x => x.LocationCode).HasColumnName("location_code").HasMaxLength(30).IsRequired();
        builder.Property(x => x.Name).HasColumnName("name").HasMaxLength(100).IsRequired();
        builder.Property(x => x.LocationType)
            .HasColumnName("location_type")
            .HasConversion<string>()
            .HasMaxLength(25)
            .IsRequired();
        builder.Property(x => x.IsSellable).HasColumnName("is_sellable").IsRequired();
        builder.Property(x => x.IsActive).HasColumnName("is_active").IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();

        // Alternate Keys (used for cross-field relational integrity)
        builder.HasAlternateKey(x => new { x.OrganizationId, x.BranchId, x.LocationId });
        builder.HasAlternateKey(x => new { x.OrganizationId, x.LocationId });

        // Unique & FEFO Indexes
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.LocationCode }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.IsSellable, x.LocationId });

        // Check Constraints
        builder.ToTable(t =>
        {
            t.HasCheckConstraint("CK_INVENTORY_LOCATION_type", "location_type IN ('SELLABLE', 'QUARANTINE', 'DAMAGED', 'SCRAP')");
            t.HasCheckConstraint("CK_INVENTORY_LOCATION_sellable_rule", "NOT is_sellable OR location_type = 'SELLABLE'");
        });

        // Composite Foreign Key to Branch
        builder.HasOne(x => x.Branch)
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.BranchId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.BranchId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}