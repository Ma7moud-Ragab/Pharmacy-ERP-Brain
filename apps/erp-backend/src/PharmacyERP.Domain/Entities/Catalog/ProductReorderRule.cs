using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Catalog;

/// <summary>
/// Represents branch-level reorder point and threshold configuration for a product (catalog.PRODUCT_REORDER_RULE).
/// </summary>
public class ProductReorderRule
{
    public Guid ReorderRuleId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid ProductId { get; private set; }
    public Guid BranchId { get; private set; }
    public decimal ReorderPointBase { get; private set; }
    public decimal ReorderQuantityBase { get; private set; }
    public decimal? MaxQuantityBase { get; private set; }
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation properties
    public Product Product { get; private set; } = null!;
    public Branch Branch { get; private set; } = null!;

    private ProductReorderRule()
    {
    }

    public static ProductReorderRule Create(
        Guid organizationId,
        Guid productId,
        Guid branchId,
        decimal reorderPointBase,
        decimal reorderQuantityBase,
        decimal? maxQuantityBase,
        Guid? reorderRuleId = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (productId == Guid.Empty)
            throw new ArgumentException("ProductId cannot be empty.", nameof(productId));

        if (branchId == Guid.Empty)
            throw new ArgumentException("BranchId cannot be empty.", nameof(branchId));

        ValidateThresholds(reorderPointBase, reorderQuantityBase, maxQuantityBase);

        var now = DateTimeOffset.UtcNow;

        return new ProductReorderRule
        {
            ReorderRuleId = reorderRuleId ?? Guid.NewGuid(),
            OrganizationId = organizationId,
            ProductId = productId,
            BranchId = branchId,
            ReorderPointBase = reorderPointBase,
            ReorderQuantityBase = reorderQuantityBase,
            MaxQuantityBase = maxQuantityBase,
            IsActive = true,
            CreatedAt = now,
            UpdatedAt = now
        };
    }

    public void UpdateThresholds(decimal reorderPointBase, decimal reorderQuantityBase, decimal? maxQuantityBase)
    {
        ValidateThresholds(reorderPointBase, reorderQuantityBase, maxQuantityBase);

        ReorderPointBase = reorderPointBase;
        ReorderQuantityBase = reorderQuantityBase;
        MaxQuantityBase = maxQuantityBase;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    private static void ValidateThresholds(decimal reorderPointBase, decimal reorderQuantityBase, decimal? maxQuantityBase)
    {
        if (reorderPointBase < 0m || reorderQuantityBase < 0m)
            throw new InvalidReorderRuleQuantitiesException("Reorder point and reorder quantity must be non-negative.");

        if (maxQuantityBase.HasValue && maxQuantityBase.Value < reorderPointBase)
            throw new InvalidReorderRuleQuantitiesException("Maximum quantity cannot be less than reorder point.");
    }
}
