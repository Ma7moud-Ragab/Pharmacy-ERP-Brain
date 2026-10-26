using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Catalog;

/// <summary>
/// Represents a hierarchical product category (catalog.PRODUCT_CATEGORY).
/// </summary>
public class ProductCategory
{
    public Guid CategoryId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid? ParentCategoryId { get; private set; }
    public string Code { get; private set; } = string.Empty;
    public string Name { get; private set; } = string.Empty;
    public string? Description { get; private set; }
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation properties
    public ProductCategory? Parent { get; private set; }
    public ICollection<ProductCategory> Children { get; private set; } = new List<ProductCategory>();
    public ICollection<Product> Products { get; private set; } = new List<Product>();

    private ProductCategory()
    {
    }

    public static ProductCategory Create(
        Guid organizationId,
        string code,
        string name,
        string? description,
        Guid? parentCategoryId,
        Guid? categoryId = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (string.IsNullOrWhiteSpace(code))
            throw new ArgumentException("Code is required.", nameof(code));

        if (code.Length > 30)
            throw new ArgumentException("Code cannot exceed 30 characters.", nameof(code));

        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Name is required.", nameof(name));

        if (name.Length > 100)
            throw new ArgumentException("Name cannot exceed 100 characters.", nameof(name));

        if (description != null && description.Length > 250)
            throw new ArgumentException("Description cannot exceed 250 characters.", nameof(description));

        var resolvedCategoryId = categoryId ?? Guid.NewGuid();

        if (parentCategoryId.HasValue && parentCategoryId.Value == resolvedCategoryId)
            throw new CategorySelfParentException();

        var now = DateTimeOffset.UtcNow;

        return new ProductCategory
        {
            CategoryId = resolvedCategoryId,
            OrganizationId = organizationId,
            ParentCategoryId = parentCategoryId,
            Code = code,
            Name = name,
            Description = description,
            IsActive = true,
            CreatedAt = now,
            UpdatedAt = now
        };
    }

    public void UpdateDetails(string name, string? description, Guid? parentCategoryId)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Name is required.", nameof(name));

        if (name.Length > 100)
            throw new ArgumentException("Name cannot exceed 100 characters.", nameof(name));

        if (description != null && description.Length > 250)
            throw new ArgumentException("Description cannot exceed 250 characters.", nameof(description));

        if (parentCategoryId.HasValue && parentCategoryId.Value == CategoryId)
            throw new CategorySelfParentException();

        Name = name;
        Description = description;
        ParentCategoryId = parentCategoryId;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void SetActiveState(bool isActive)
    {
        IsActive = isActive;
        UpdatedAt = DateTimeOffset.UtcNow;
    }
}
