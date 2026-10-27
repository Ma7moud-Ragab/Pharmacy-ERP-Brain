using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Catalog;

/// <summary>
/// Represents a unit of measure for a product with its conversion factor and pricing (catalog.PRODUCT_UOM).
/// </summary>
public class ProductUom
{
    public Guid ProductUomId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid ProductId { get; private set; }
    public string UomCode { get; private set; } = string.Empty;
    public string DisplayName { get; private set; } = string.Empty;
    public decimal ConversionToBase { get; private set; }
    public decimal? SaleUnitPrice { get; private set; }
    public bool IsBase { get; private set; }
    public bool IsSellable { get; private set; }
    public bool IsPurchasable { get; private set; }
    public bool IsActive { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation property
    public Product Product { get; private set; } = null!;

    private ProductUom()
    {
    }

    internal static ProductUom Create(
        Guid organizationId,
        Guid productId,
        string uomCode,
        string displayName,
        decimal conversionToBase,
        decimal? saleUnitPrice,
        bool isBase,
        bool isSellable,
        bool isPurchasable,
        Guid? productUomId = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (productId == Guid.Empty)
            throw new ArgumentException("ProductId cannot be empty.", nameof(productId));

        if (string.IsNullOrWhiteSpace(uomCode))
            throw new ArgumentException("UomCode is required.", nameof(uomCode));

        if (uomCode.Length > 20)
            throw new ArgumentException("UomCode cannot exceed 20 characters.", nameof(uomCode));

        if (string.IsNullOrWhiteSpace(displayName))
            throw new ArgumentException("DisplayName is required.", nameof(displayName));

        if (displayName.Length > 50)
            throw new ArgumentException("DisplayName cannot exceed 50 characters.", nameof(displayName));

        if (conversionToBase <= 0m || (isBase && conversionToBase != 1m))
            throw new InvalidUomConversionFactorException();

        if (isSellable && (!saleUnitPrice.HasValue || saleUnitPrice.Value < 0m))
            throw new InvalidSellableUomPriceException();

        var now = DateTimeOffset.UtcNow;

        return new ProductUom
        {
            ProductUomId = productUomId ?? Guid.NewGuid(),
            OrganizationId = organizationId,
            ProductId = productId,
            UomCode = uomCode,
            DisplayName = displayName,
            ConversionToBase = conversionToBase,
            SaleUnitPrice = saleUnitPrice,
            IsBase = isBase,
            IsSellable = isSellable,
            IsPurchasable = isPurchasable,
            IsActive = true,
            CreatedAt = now,
            UpdatedAt = now
        };
    }

    public void UpdateNonHistoricalAttributes(string displayName, decimal? saleUnitPrice, bool isSellable, bool isPurchasable)
    {
        if (string.IsNullOrWhiteSpace(displayName))
            throw new ArgumentException("DisplayName is required.", nameof(displayName));

        if (displayName.Length > 50)
            throw new ArgumentException("DisplayName cannot exceed 50 characters.", nameof(displayName));

        if (isSellable && (!saleUnitPrice.HasValue || saleUnitPrice.Value < 0m))
            throw new InvalidSellableUomPriceException();

        DisplayName = displayName;
        SaleUnitPrice = saleUnitPrice;
        IsSellable = isSellable;
        IsPurchasable = isPurchasable;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void UpdateConversionFactor(decimal newConversionToBase, bool isReferencedByStockOrDocuments)
    {
        if (isReferencedByStockOrDocuments && newConversionToBase != ConversionToBase)
            throw new HistoricalUomModificationForbiddenException("Cannot modify conversion factor for a UOM that has existing stock or document references.");

        if (newConversionToBase <= 0m || (IsBase && newConversionToBase != 1m))
            throw new InvalidUomConversionFactorException();

        if (newConversionToBase == ConversionToBase)
            return;

        ConversionToBase = newConversionToBase;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void Deactivate()
    {
        if (IsBase)
            throw new InvalidBaseUomInvariantException("Cannot deactivate the base UOM of a product without assigning an active replacement.");

        if (!IsActive)
            return;

        IsActive = false;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    internal void SetAsBase()
    {
        if (!IsActive)
            throw new InvalidBaseUomInvariantException("Cannot set an inactive UOM as base UOM.");

        if (ConversionToBase != 1m)
            throw new InvalidBaseUomInvariantException("Target base UOM must have a conversion factor of exactly 1.");

        IsBase = true;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    internal void UnsetBase()
    {
        IsBase = false;
        UpdatedAt = DateTimeOffset.UtcNow;
    }
}