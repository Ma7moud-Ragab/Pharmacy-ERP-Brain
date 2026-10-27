using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Inventory;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;

public class StockBalanceConfiguration : IEntityTypeConfiguration<StockBalance>
{
    public void Configure(EntityTypeBuilder<StockBalance> builder)
    {
        builder.ToTable("STOCK_BALANCE", "inventory");

        // Composite PK
        builder.HasKey(x => new { x.OrganizationId, x.LocationId, x.BatchId });

        // Column Mappings
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id");
        builder.Property(x => x.LocationId).HasColumnName("location_id");
        builder.Property(x => x.BatchId).HasColumnName("batch_id");

        builder.Property(x => x.OnHandQtyBase).HasColumnName("on_hand_qty_base").HasColumnType("numeric(18,4)").IsRequired();
        builder.Property(x => x.AverageUnitCost).HasColumnName("average_unit_cost").HasColumnType("numeric(18,4)").IsRequired();
        builder.Property(x => x.RowVersion).HasColumnName("row_version").IsConcurrencyToken().IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();

        // Batch Reconciliation Index
        builder.HasIndex(x => new { x.OrganizationId, x.BatchId, x.LocationId });

        // Check Constraints
        builder.ToTable(t =>
        {
            t.HasCheckConstraint("CK_STOCK_BALANCE_nonnegative_qty", "on_hand_qty_base >= 0");
            t.HasCheckConstraint("CK_STOCK_BALANCE_nonnegative_cost", "average_unit_cost >= 0");
        });

        // Composite Foreign Keys
        builder.HasOne(x => x.Location)
            .WithMany(x => x.StockBalances)
            .HasForeignKey(x => new { x.OrganizationId, x.LocationId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.LocationId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.Batch)
            .WithMany(x => x.StockBalances)
            .HasForeignKey(x => new { x.OrganizationId, x.BatchId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.BatchId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}