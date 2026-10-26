using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.UnitTests.Domain.Catalog;

public class CatalogExceptionsTests
{
    [Fact]
    public void CatalogDomainException_InheritsFromDomainException()
    {
        var ex = new CatalogDomainException("test");
        Assert.IsAssignableFrom<DomainException>(ex);
    }

    [Theory]
    [MemberData(nameof(AllCatalogExceptions))]
    public void Exception_CanBeInstantiated_AndInheritsFromCatalogDomainException(CatalogDomainException exception)
    {
        Assert.IsAssignableFrom<CatalogDomainException>(exception);
        Assert.IsAssignableFrom<DomainException>(exception);
        Assert.False(string.IsNullOrWhiteSpace(exception.Message));
    }

    public static TheoryData<CatalogDomainException> AllCatalogExceptions => new()
    {
        new CategorySelfParentException(),
        new InvalidProductTaxRateException(),
        new InvalidExpiryAlertDaysException(),
        new InvalidBaseUomInvariantException(),
        new InvalidUomConversionFactorException(),
        new InvalidSellableUomPriceException(),
        new HistoricalUomModificationForbiddenException(),
        new InvalidReorderRuleQuantitiesException()
    };

    [Fact]
    public void CategorySelfParentException_HasMeaningfulMessage()
    {
        var ex = new CategorySelfParentException();
        Assert.Contains("parent", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InvalidProductTaxRateException_HasMeaningfulMessage()
    {
        var ex = new InvalidProductTaxRateException();
        Assert.Contains("0", ex.Message);
        Assert.Contains("1", ex.Message);
    }

    [Fact]
    public void InvalidExpiryAlertDaysException_HasMeaningfulMessage()
    {
        var ex = new InvalidExpiryAlertDaysException();
        Assert.Contains("expiry", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InvalidBaseUomInvariantException_HasMeaningfulMessage()
    {
        var ex = new InvalidBaseUomInvariantException();
        Assert.Contains("base UOM", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InvalidUomConversionFactorException_HasMeaningfulMessage()
    {
        var ex = new InvalidUomConversionFactorException();
        Assert.Contains("conversion", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("1", ex.Message);
    }

    [Fact]
    public void InvalidSellableUomPriceException_HasMeaningfulMessage()
    {
        var ex = new InvalidSellableUomPriceException();
        Assert.Contains("sellable", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("must not be negative", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void HistoricalUomModificationForbiddenException_HasMeaningfulMessage()
    {
        var ex = new HistoricalUomModificationForbiddenException();
        Assert.Contains("stock", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InvalidReorderRuleQuantitiesException_HasMeaningfulMessage()
    {
        var ex = new InvalidReorderRuleQuantitiesException();
        Assert.Contains("reorder", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CustomMessage_OverridesDefault()
    {
        const string custom = "Custom error message";
        var ex = new CategorySelfParentException(custom);
        Assert.Equal(custom, ex.Message);
    }

    [Fact]
    public void CatalogConfigurationAction_HasExpectedEnumValues()
    {
        Assert.Equal(1, (int)CatalogConfigurationAction.CreateProduct);
        Assert.Equal(2, (int)CatalogConfigurationAction.UpdateProduct);
        Assert.Equal(3, (int)CatalogConfigurationAction.AddUom);
        Assert.Equal(4, (int)CatalogConfigurationAction.UpdateUom);
        Assert.Equal(5, (int)CatalogConfigurationAction.DeactivateUom);
    }
}
