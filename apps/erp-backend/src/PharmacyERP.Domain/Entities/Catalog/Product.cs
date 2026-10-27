using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Catalog;

/// <summary>
/// Definition record for initial units of measure passed during product creation.
/// </summary>
public sealed record InitialUomDefinition(
    string UomCode,
    string DisplayName,
    decimal ConversionToBase,
    decimal? SaleUnitPrice,
    bool IsBase,
    bool IsSellable,
    bool IsPurchasable);

/// <summary>
/// Represents a catalog product or medication (catalog.PRODUCT).
/// </summary>
public class Product
{
    public Guid ProductId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid CategoryId { get; private set; }
    public string Sku { get; private set; } = string.Empty;
    public string? Barcode { get; private set; }
    public string Name { get; private set; } = string.Empty;
    public string? GenericName { get; private set; }
    public string? BrandName { get; private set; }
    public string BaseUomCode { get; private set; } = string.Empty;
    public decimal TaxRate { get; private set; }
    public string? ImageUrl { get; private set; }
    public bool LotTrackingRequired { get; private set; }
    public int ExpiryAlertDays { get; private set; }
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation properties
    public ProductCategory Category { get; private set; } = null!;

    /// <summary>
    /// Collection of attached UOM conversions for this product.
    /// NOTE ON MUTABILITY LIMITATION: Per the project specification requiring public ICollection&lt;ProductUom&gt;,
    /// external callers with access to this reference can technically mutate the collection directly without calling
    /// AddUom. Aggregate invariants are strictly validated by Product factory and domain methods, but arbitrary external
    /// collection mutation cannot be prevented at the compile-time type level under this specification signature.
    /// </summary>
    public ICollection<ProductUom> Uoms { get; private set; } = new List<ProductUom>();

    public ICollection<ProductReorderRule> ReorderRules { get; private set; } = new List<ProductReorderRule>();

    private Product()
    {
    }

    public static Product Create(
        Guid organizationId,
        Guid categoryId,
        string sku,
        string? barcode,
        string name,
        string? genericName,
        string? brandName,
        string baseUomCode,
        decimal taxRate,
        string? imageUrl,
        bool lotTrackingRequired,
        int expiryAlertDays,
        IEnumerable<InitialUomDefinition> initialUoms,
        Guid? productId = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (categoryId == Guid.Empty)
            throw new ArgumentException("CategoryId cannot be empty.", nameof(categoryId));

        if (string.IsNullOrWhiteSpace(sku))
            throw new ArgumentException("Sku is required.", nameof(sku));

        if (sku.Length > 40)
            throw new ArgumentException("Sku cannot exceed 40 characters.", nameof(sku));

        if (barcode != null && barcode.Length > 80)
            throw new ArgumentException("Barcode cannot exceed 80 characters.", nameof(barcode));

        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Name is required.", nameof(name));

        if (name.Length > 180)
            throw new ArgumentException("Name cannot exceed 180 characters.", nameof(name));

        if (genericName != null && genericName.Length > 180)
            throw new ArgumentException("GenericName cannot exceed 180 characters.", nameof(genericName));

        if (brandName != null && brandName.Length > 180)
            throw new ArgumentException("BrandName cannot exceed 180 characters.", nameof(brandName));

        if (string.IsNullOrWhiteSpace(baseUomCode))
            throw new ArgumentException("BaseUomCode is required.", nameof(baseUomCode));

        if (baseUomCode.Length > 20)
            throw new ArgumentException("BaseUomCode cannot exceed 20 characters.", nameof(baseUomCode));

        if (imageUrl != null && imageUrl.Length > 300)
            throw new ArgumentException("ImageUrl cannot exceed 300 characters.", nameof(imageUrl));

        if (taxRate < 0m || taxRate > 1m)
            throw new InvalidProductTaxRateException();

        if (expiryAlertDays < 0)
            throw new InvalidExpiryAlertDaysException();

        ArgumentNullException.ThrowIfNull(initialUoms);

        var resolvedProductId = productId ?? Guid.NewGuid();
        var now = DateTimeOffset.UtcNow;

        var product = new Product
        {
            ProductId = resolvedProductId,
            OrganizationId = organizationId,
            CategoryId = categoryId,
            Sku = sku,
            Barcode = barcode,
            Name = name,
            GenericName = genericName,
            BrandName = brandName,
            BaseUomCode = baseUomCode,
            TaxRate = taxRate,
            ImageUrl = imageUrl,
            LotTrackingRequired = lotTrackingRequired,
            ExpiryAlertDays = expiryAlertDays,
            IsActive = true,
            CreatedAt = now,
            UpdatedAt = now
        };

        foreach (var uomDef in initialUoms)
        {
            var uom = ProductUom.Create(
                organizationId,
                resolvedProductId,
                uomDef.UomCode,
                uomDef.DisplayName,
                uomDef.ConversionToBase,
                uomDef.SaleUnitPrice,
                uomDef.IsBase,
                uomDef.IsSellable,
                uomDef.IsPurchasable);

            if (product.Uoms.Any(existing => string.Equals(existing.UomCode, uom.UomCode, StringComparison.Ordinal)))
                throw new CatalogDomainException($"Duplicate UOM code '{uom.UomCode}' found in product creation payload.");

            product.Uoms.Add(uom);
        }

        product.EnsureSingleActiveBaseUomInvariant();

        return product;
    }

    public ProductUom AddUom(
        string uomCode,
        string displayName,
        decimal conversionToBase,
        decimal? saleUnitPrice,
        bool isBase,
        bool isSellable,
        bool isPurchasable)
    {
        if (Uoms.Any(u => string.Equals(u.UomCode, uomCode, StringComparison.Ordinal)))
            throw new CatalogDomainException($"A UOM with code '{uomCode}' already exists for product '{ProductId}'.");

        if (isBase && Uoms.Any(u => u.IsBase && u.IsActive))
            throw new InvalidBaseUomInvariantException("Cannot add a second active base UOM to the product.");

        var uom = ProductUom.Create(
            OrganizationId,
            ProductId,
            uomCode,
            displayName,
            conversionToBase,
            saleUnitPrice,
            isBase,
            isSellable,
            isPurchasable);

        Uoms.Add(uom);
        UpdatedAt = DateTimeOffset.UtcNow;

        return uom;
    }

    public void EnsureSingleActiveBaseUomInvariant()
    {
        var activeBaseUoms = Uoms.Where(u => u.IsBase && u.IsActive).ToList();

        if (activeBaseUoms.Count != 1)
            throw new InvalidBaseUomInvariantException($"The product must have exactly one active base UOM, found {activeBaseUoms.Count}.");

        var baseUom = activeBaseUoms[0];

        if (!string.Equals(baseUom.UomCode, BaseUomCode, StringComparison.Ordinal))
            throw new InvalidBaseUomInvariantException($"Base UOM code '{baseUom.UomCode}' does not match Product.BaseUomCode '{BaseUomCode}'.");

        if (baseUom.ConversionToBase != 1m)
            throw new InvalidBaseUomInvariantException($"Base UOM '{baseUom.UomCode}' must have a conversion factor of exactly 1.");
    }

    public void ChangeLotTrackingPolicy(bool lotTrackingRequired, bool hasStockOrPostedHistory)
    {
        if (lotTrackingRequired == LotTrackingRequired)
            return;

        if (hasStockOrPostedHistory)
            throw new HistoricalUomModificationForbiddenException("Cannot change lot tracking policy for a product that has existing stock balances or posted transaction history.");

        LotTrackingRequired = lotTrackingRequired;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    /// <summary>
    /// Changes the base UOM to an existing active UOM of this product that has a conversion factor of 1.
    /// CONSERVATIVE SPEC IMPLEMENTATION NOTE:
    /// The requirement that the target UOM must already possess ConversionToBase == 1m (with no automatic
    /// factor rescaling across other UOMs) is a conservative implementation strictly adhering to the current spec.
    /// Any changes to conversion factor rescaling semantics will require a separate team architectural decision.
    /// </summary>
    public void ChangeBaseUom(string newBaseUomCode, bool hasStockOrPostedHistory)
    {
        if (hasStockOrPostedHistory)
            throw new HistoricalUomModificationForbiddenException("Cannot modify base UOM for a product that has existing stock balances or posted transaction history.");

        if (string.Equals(BaseUomCode, newBaseUomCode, StringComparison.Ordinal))
            return;

        var targetUom = Uoms.FirstOrDefault(u => string.Equals(u.UomCode, newBaseUomCode, StringComparison.Ordinal));

        if (targetUom == null || !targetUom.IsActive)
            throw new InvalidBaseUomInvariantException($"Target UOM '{newBaseUomCode}' must be an existing active UOM of this product.");

        if (targetUom.ConversionToBase != 1m)
            throw new InvalidBaseUomInvariantException($"Target base UOM '{newBaseUomCode}' must have ConversionToBase equal to 1.");

        var currentBase = Uoms.FirstOrDefault(u => u.IsBase && u.IsActive);

        // Validation passed; apply changes atomically
        currentBase?.UnsetBase();
        targetUom.SetAsBase();

        BaseUomCode = targetUom.UomCode;
        UpdatedAt = DateTimeOffset.UtcNow;

        EnsureSingleActiveBaseUomInvariant();
    }
}
