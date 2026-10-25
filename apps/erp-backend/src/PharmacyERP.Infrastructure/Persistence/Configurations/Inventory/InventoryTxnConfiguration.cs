using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Entities.Inventory;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;

public class InventoryTxnConfiguration : IEntityTypeConfiguration<InventoryTxn>
{
    public void Configure(EntityTypeBuilder<InventoryTxn> builder)
    {
        builder.ToTable("INVENTORY_TXN", "inventory");

        builder.HasKey(x => x.InventoryTxnId);

        // Column Mappings
        builder.Property(x => x.InventoryTxnId).HasColumnName("inventory_txn_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.Property(x => x.TransactionNo).HasColumnName("transaction_no").HasMaxLength(40).IsRequired();
        builder.Property(x => x.TransactionType)
            .HasColumnName("transaction_type")
            .HasConversion<string>()
            .HasMaxLength(30)
            .IsRequired();
        builder.Property(x => x.Status)
            .HasColumnName("status")
            .HasConversion<string>()
            .HasMaxLength(20)
            .IsRequired();
        builder.Property(x => x.ReasonCode).HasColumnName("reason_code").HasMaxLength(40);
        builder.Property(x => x.Note).HasColumnName("note").HasMaxLength(500);
        builder.Property(x => x.IdempotencyKey).HasColumnName("idempotency_key").HasMaxLength(100).IsRequired();
        builder.Property(x => x.CreatedByEmployeeId).HasColumnName("created_by_employee_id").IsRequired();
        builder.Property(x => x.ReversesInventoryTxnId).HasColumnName("reverses_inventory_txn_id");

        builder.Property(x => x.SalesOrderId).HasColumnName("sales_order_id");
        builder.Property(x => x.SalesReturnId).HasColumnName("sales_return_id");
        builder.Property(x => x.PurchaseOrderId).HasColumnName("purchase_order_id");
        builder.Property(x => x.VendorReturnId).HasColumnName("vendor_return_id");

        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.PostedAt).HasColumnName("posted_at").HasColumnType("timestamptz");

        // Alternate Keys
        builder.HasAlternateKey(x => new { x.OrganizationId, x.InventoryTxnId, x.BranchId });
        builder.HasAlternateKey(x => new { x.OrganizationId, x.InventoryTxnId });

        // Unique & Query Indexes
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.TransactionNo }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.TransactionType, x.IdempotencyKey }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.PostedAt, x.InventoryTxnId });

        // Check Constraints
        builder.ToTable(t =>
        {
            t.HasCheckConstraint("CK_INVENTORY_TXN_status", "status IN ('DRAFT', 'POSTED', 'CANCELLED')");
            t.HasCheckConstraint("CK_INVENTORY_TXN_type", "transaction_type IN ('OPENING_BALANCE', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT', 'SALE_ISSUE', 'SALES_RETURN_IN', 'PURCHASE_RECEIPT', 'VENDOR_RETURN_OUT', 'SCRAP_OUT', 'REVERSAL')");
        });

        // Composite Foreign Keys
        builder.HasOne<Branch>()
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.BranchId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.BranchId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne<Employee>()
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.CreatedByEmployeeId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.EmployeeId })
            .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.ReversesInventoryTxn)
            .WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.ReversesInventoryTxnId })
            .HasPrincipalKey(x => new { x.OrganizationId, x.InventoryTxnId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}