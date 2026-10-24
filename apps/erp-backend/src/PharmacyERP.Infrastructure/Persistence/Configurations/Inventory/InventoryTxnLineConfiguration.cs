using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Catalog;
using PharmacyERP.Domain.Entities.Inventory;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;

public class InventoryTxnLineConfiguration : IEntityTypeConfiguration<InventoryTxnLine>
{
    public void Configure(EntityTypeBuilder<InventoryTxnLine> builder)
    {
        builder.ToTable("INVENTORY_TXN_LINE", "inventory");

        builder.HasKey(x => x.InventoryTxnLineId);

        // Column Mappings
        builder.Property(x => x.InventoryTxnLineId).HasColumnName("inventory_txn_line_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.InventoryTxnId).HasColumnName("inventory_txn_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.Property(x => x.ProductId).HasColumnName("product_id").IsRequired();
        builder.Property(x => x.LocationId).HasColumnName("location_id").IsRequired();
        builder.Property(x => x.BatchId).HasColumnName("batch_id").IsRequired();
        builder.Property(x => x.ProductUomId).HasColumnName("product_uom_id").IsRequired();

        builder.Property(x => x.EnteredQty).HasColumnName("entered_qty").HasColumnType("numeric(18,4)").IsRequired();
        builder.Property(x => x.ConversionSnapshot).HasColumnName("conversion_snapshot").HasColumnType("numeric(18,6)").IsRequired();
        builder.Property(x => x.QuantityDeltaBase).HasColumnName("quantity_delta_base").HasColumnType("numeric(18,4)").IsRequired();
        builder.Property(x => x.UnitCostBase).HasColumnName("unit_cost_base").HasColumnType("numeric(18,4)").IsRequired();

        builder.Property(x => x.SalesOrderLineId).HasColumnName("sales_order_line_id");
        builder.Property(x => x.SalesReturnLineId).HasColumnName("sales_return_line_id");
        builder.Property(x => x.PurchaseOrderLineId).HasColumnName("purchase_order_line_id");
        builder.Property(x => x.VendorReturnLineId).HasColumnName("vendor_return_line_id");

        // Check Constraints
        builder.ToTable(t =>
        {
            t.HasCheckConstraint("CK_INVENTORY_TXN_LINE_positive_factors", "entered_qty > 0 AND conversion_snapshot > 0 AND quantity_delta_base <> 0 AND unit_cost_base >= 0");
            t.HasCheckConstraint("CK_INVENTORY_TXN_LINE_delta_math", "abs(quantity_delta_base) = round(entered_qty * conversion_snapshot, 4)");
        });

        // Composite Foreign Keys (Cross-Field Relational Integrity)
        builder.HasOne(x => x.InventoryTxn)
            .WithMany(x => x.Lines)
            .HasForeignKey(x => new { x.OrganizationId, x.InventoryTxnId, x.BranchId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.InventoryTxnId, x.BranchId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.Location)
            .WithMany(x => x.TxnLines)
            .HasForeignKey(x => new { x.OrganizationId, x.BranchId, x.LocationId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.BranchId, x.LocationId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.Batch)
            .WithMany(x => x.TxnLines)
            .HasForeignKey(x => new { x.OrganizationId, x.ProductId, x.BatchId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.ProductId, x.BatchId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne<ProductUom>()
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.ProductId, x.ProductUomId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.ProductId, x.ProductUomId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}