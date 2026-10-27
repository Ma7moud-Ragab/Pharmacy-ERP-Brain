namespace PharmacyERP.Domain.Exceptions;

public class CatalogDomainException : DomainException
{
    public CatalogDomainException(string message) : base(message) { }
    public CatalogDomainException(string message, Exception innerException) : base(message, innerException) { }
}

public sealed class CategorySelfParentException : CatalogDomainException
{
    public CategorySelfParentException(string message = "A product category cannot be set as its own parent.")
        : base(message) { }
}

public sealed class InvalidProductTaxRateException : CatalogDomainException
{
    public InvalidProductTaxRateException(string message = "Product tax rate must be between 0 and 1 (inclusive).")
        : base(message) { }
}

public sealed class InvalidExpiryAlertDaysException : CatalogDomainException
{
    public InvalidExpiryAlertDaysException(string message = "Expiry alert days must be zero or a positive integer.")
        : base(message) { }
}

public sealed class InvalidBaseUomInvariantException : CatalogDomainException
{
    public InvalidBaseUomInvariantException(string message = "The product must have exactly one active base UOM with a conversion factor of 1 matching its base UOM code.")
        : base(message) { }
}

public sealed class InvalidUomConversionFactorException : CatalogDomainException
{
    public InvalidUomConversionFactorException(string message = "UOM conversion factor must be greater than zero, and base UOM conversion factor must equal 1.")
        : base(message) { }
}

public sealed class InvalidSellableUomPriceException : CatalogDomainException
{
    public InvalidSellableUomPriceException(string message = "A sellable UOM must have a sale unit price provided and must not be negative.")
        : base(message) { }
}

public sealed class HistoricalUomModificationForbiddenException : CatalogDomainException
{
    public HistoricalUomModificationForbiddenException(string message = "Cannot modify base UOM, conversion factor, or lot tracking policy for a product with existing stock or posted history.")
        : base(message) { }
}

public sealed class InvalidReorderRuleQuantitiesException : CatalogDomainException
{
    public InvalidReorderRuleQuantitiesException(string message = "Reorder quantities must be non-negative, and maximum quantity if specified must be greater than or equal to reorder point.")
        : base(message) { }
}
