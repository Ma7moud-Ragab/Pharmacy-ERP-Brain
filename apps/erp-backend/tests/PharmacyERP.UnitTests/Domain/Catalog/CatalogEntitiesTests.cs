using PharmacyERP.Domain.Entities.Catalog;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.UnitTests.Domain.Catalog;

public class CatalogEntitiesTests
{
    private static readonly Guid OrgId = Guid.NewGuid();
    private static readonly Guid CatId = Guid.NewGuid();
    private static readonly Guid BranchId = Guid.NewGuid();

    private static InitialUomDefinition CreateValidBaseUom(string code = "TAB", decimal price = 10m) =>
        new(code, "Tablet", 1m, price, IsBase: true, IsSellable: true, IsPurchasable: true);

    private static void WaitUntilClockAdvancesPast(DateTimeOffset timestamp)
    {
        var timeout = DateTimeOffset.UtcNow.AddSeconds(1);
        while (DateTimeOffset.UtcNow <= timestamp)
        {
            if (DateTimeOffset.UtcNow >= timeout)
                throw new TimeoutException("System clock did not advance within 1 second.");
            Thread.SpinWait(100);
        }
    }

    #region ProductCategory Tests & Boundaries

    [Fact]
    public void ProductCategory_Create_WithValidData_Succeeds()
    {
        var category = ProductCategory.Create(OrgId, "CAT01", "Analgesics", "Pain relief", null);

        Assert.NotEqual(Guid.Empty, category.CategoryId);
        Assert.Equal(OrgId, category.OrganizationId);
        Assert.Equal("CAT01", category.Code);
        Assert.Equal("Analgesics", category.Name);
        Assert.Equal("Pain relief", category.Description);
        Assert.Null(category.ParentCategoryId);
        Assert.True(category.IsActive);
        Assert.True(category.CreatedAt <= DateTimeOffset.UtcNow);
        Assert.Equal(category.CreatedAt, category.UpdatedAt);
    }

    [Fact]
    public void ProductCategory_Create_SelfParent_ThrowsCategorySelfParentException()
    {
        var categoryId = Guid.NewGuid();
        Assert.Throws<CategorySelfParentException>(() =>
            ProductCategory.Create(OrgId, "CAT01", "CatName", null, parentCategoryId: categoryId, categoryId: categoryId));
    }

    [Fact]
    public void ProductCategory_UpdateDetails_SelfParent_ThrowsCategorySelfParentException_AndLeavesStateUnchanged()
    {
        var category = ProductCategory.Create(OrgId, "CAT01", "CatName", "Initial Desc", null);
        var originalUpdatedAt = category.UpdatedAt;

        Assert.Throws<CategorySelfParentException>(() =>
            category.UpdateDetails("Updated Name", "Updated Desc", parentCategoryId: category.CategoryId));

        Assert.Equal(originalUpdatedAt, category.UpdatedAt);
        Assert.Equal("CatName", category.Name);
        Assert.Equal("Initial Desc", category.Description);
        Assert.Null(category.ParentCategoryId);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ProductCategory_Create_RequiredCode_Empty_ThrowsArgumentException(string? invalidCode)
    {
        Assert.Throws<ArgumentException>(() =>
            ProductCategory.Create(OrgId, invalidCode!, "Name", null, null));
    }

    [Fact]
    public void ProductCategory_CodeLengthBoundary_Enforced()
    {
        var validCode30 = new string('C', 30);
        var cat = ProductCategory.Create(OrgId, validCode30, "Name", null, null);
        Assert.Equal(validCode30, cat.Code);

        var invalidCode31 = new string('C', 31);
        Assert.Throws<ArgumentException>(() =>
            ProductCategory.Create(OrgId, invalidCode31, "Name", null, null));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ProductCategory_Create_RequiredName_Empty_ThrowsArgumentException(string? invalidName)
    {
        Assert.Throws<ArgumentException>(() =>
            ProductCategory.Create(OrgId, "CODE", invalidName!, null, null));
    }

    [Fact]
    public void ProductCategory_NameLengthBoundary_Enforced()
    {
        var validName100 = new string('N', 100);
        var cat = ProductCategory.Create(OrgId, "CODE", validName100, null, null);
        Assert.Equal(validName100, cat.Name);

        var invalidName101 = new string('N', 101);
        Assert.Throws<ArgumentException>(() =>
            ProductCategory.Create(OrgId, "CODE", invalidName101, null, null));
    }

    [Fact]
    public void ProductCategory_DescriptionLengthBoundary_Enforced()
    {
        var catNullDesc = ProductCategory.Create(OrgId, "CODE", "Name", null, null);
        Assert.Null(catNullDesc.Description);

        var validDesc250 = new string('D', 250);
        var cat = ProductCategory.Create(OrgId, "CODE2", "Name", validDesc250, null);
        Assert.Equal(validDesc250, cat.Description);

        var invalidDesc251 = new string('D', 251);
        Assert.Throws<ArgumentException>(() =>
            ProductCategory.Create(OrgId, "CODE3", "Name", invalidDesc251, null));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ProductCategory_UpdateDetails_InvalidName_ThrowsArgumentException_AndLeavesStateUnchanged(string? invalidName)
    {
        var category = ProductCategory.Create(OrgId, "CODE", "Original Name", "Original Desc", null);
        var originalUpdatedAt = category.UpdatedAt;

        Assert.Throws<ArgumentException>(() =>
            category.UpdateDetails(invalidName!, "New Desc", null));

        Assert.Equal("Original Name", category.Name);
        Assert.Equal("Original Desc", category.Description);
        Assert.Equal(originalUpdatedAt, category.UpdatedAt);
    }

    [Fact]
    public void ProductCategory_UpdateDetails_NameLengthBoundary_Enforced_AndLeavesStateUnchangedOnFailure()
    {
        var category = ProductCategory.Create(OrgId, "CODE", "Original Name", null, null);
        var validName100 = new string('N', 100);

        WaitUntilClockAdvancesPast(category.UpdatedAt);
        var beforeValidUpdate = category.UpdatedAt;
        category.UpdateDetails(validName100, null, null);
        Assert.Equal(validName100, category.Name);
        Assert.True(category.UpdatedAt > beforeValidUpdate);

        var originalUpdatedAt = category.UpdatedAt;
        var invalidName101 = new string('N', 101);
        Assert.Throws<ArgumentException>(() =>
            category.UpdateDetails(invalidName101, null, null));

        Assert.Equal(validName100, category.Name);
        Assert.Equal(originalUpdatedAt, category.UpdatedAt);
    }

    [Fact]
    public void ProductCategory_UpdateDetails_DescriptionLengthBoundary_Enforced_AndLeavesStateUnchangedOnFailure()
    {
        var category = ProductCategory.Create(OrgId, "CODE", "CatName", null, null);
        var validDesc250 = new string('D', 250);

        category.UpdateDetails("CatName", validDesc250, null);
        Assert.Equal(validDesc250, category.Description);

        var originalUpdatedAt = category.UpdatedAt;
        var invalidDesc251 = new string('D', 251);
        Assert.Throws<ArgumentException>(() =>
            category.UpdateDetails("CatName", invalidDesc251, null));

        Assert.Equal(validDesc250, category.Description);
        Assert.Equal(originalUpdatedAt, category.UpdatedAt);
    }

    [Fact]
    public void ProductCategory_SetActiveState_UpdatesStatusAndTimestamp()
    {
        var category = ProductCategory.Create(OrgId, "CAT01", "CatName", null, null);
        WaitUntilClockAdvancesPast(category.UpdatedAt);
        var initialUpdated = category.UpdatedAt;

        category.SetActiveState(false);

        Assert.False(category.IsActive);
        Assert.True(category.UpdatedAt > initialUpdated);
    }

    #endregion

    #region Product Creation & String Length Boundaries

    [Fact]
    public void Product_Create_WithValidData_Succeeds()
    {
        var uoms = new[] { CreateValidBaseUom("TAB", 2.5m) };
        var product = Product.Create(OrgId, CatId, "SKU-001", "1234567890", "Panadol Extra", "Paracetamol", "GSK", "TAB", 0.14m, null, true, 30, uoms);

        Assert.NotEqual(Guid.Empty, product.ProductId);
        Assert.Equal("SKU-001", product.Sku);
        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(0.14m, product.TaxRate);
        Assert.True(product.LotTrackingRequired);
        Assert.Equal(30, product.ExpiryAlertDays);
        Assert.Single(product.Uoms);
    }

    [Theory]
    [InlineData(0.0)]
    [InlineData(1.0)]
    [InlineData(0.14)]
    public void Product_TaxRate_ValidBoundaries_Accepted(decimal validTaxRate)
    {
        var uoms = new[] { CreateValidBaseUom() };
        var product = Product.Create(OrgId, CatId, "SKU-T", null, "Prod", null, null, "TAB", validTaxRate, null, false, 0, uoms);
        Assert.Equal(validTaxRate, product.TaxRate);
    }

    [Theory]
    [InlineData(-0.0001)]
    [InlineData(1.0001)]
    [InlineData(-1.0)]
    public void Product_TaxRate_InvalidBoundaries_ThrowsInvalidProductTaxRateException(decimal invalidTaxRate)
    {
        var uoms = new[] { CreateValidBaseUom() };
        Assert.Throws<InvalidProductTaxRateException>(() =>
            Product.Create(OrgId, CatId, "SKU-T", null, "Prod", null, null, "TAB", invalidTaxRate, null, false, 0, uoms));
    }

    [Fact]
    public void Product_ExpiryAlertDays_Boundaries_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var product = Product.Create(OrgId, CatId, "SKU-E", null, "Prod", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(0, product.ExpiryAlertDays);

        Assert.Throws<InvalidExpiryAlertDaysException>(() =>
            Product.Create(OrgId, CatId, "SKU-E", null, "Prod", null, null, "TAB", 0m, null, false, -1, uoms));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Product_Sku_Empty_ThrowsArgumentException(string? invalidSku)
    {
        var uoms = new[] { CreateValidBaseUom() };
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, invalidSku!, null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_SkuLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var validSku40 = new string('S', 40);
        var product = Product.Create(OrgId, CatId, validSku40, null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(validSku40, product.Sku);

        var invalidSku41 = new string('S', 41);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, invalidSku41, null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Barcode_OptionalAndLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var productNullBarcode = Product.Create(OrgId, CatId, "SKU", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Null(productNullBarcode.Barcode);

        var validBarcode80 = new string('B', 80);
        var product = Product.Create(OrgId, CatId, "SKU2", validBarcode80, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(validBarcode80, product.Barcode);

        var invalidBarcode81 = new string('B', 81);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU3", invalidBarcode81, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Product_Name_Empty_ThrowsArgumentException(string? invalidName)
    {
        var uoms = new[] { CreateValidBaseUom() };
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU", null, invalidName!, null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_NameLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var validName180 = new string('N', 180);
        var product = Product.Create(OrgId, CatId, "SKU", null, validName180, null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(validName180, product.Name);

        var invalidName181 = new string('N', 181);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU", null, invalidName181, null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_GenericName_OptionalAndLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var productNull = Product.Create(OrgId, CatId, "SKU1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Null(productNull.GenericName);

        var valid180 = new string('G', 180);
        var product = Product.Create(OrgId, CatId, "SKU2", null, "Name", valid180, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(valid180, product.GenericName);

        var invalid181 = new string('G', 181);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU3", null, "Name", invalid181, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_BrandName_OptionalAndLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var productNull = Product.Create(OrgId, CatId, "SKU1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Null(productNull.BrandName);

        var valid180 = new string('B', 180);
        var product = Product.Create(OrgId, CatId, "SKU2", null, "Name", null, valid180, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(valid180, product.BrandName);

        var invalid181 = new string('B', 181);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU3", null, "Name", null, invalid181, "TAB", 0m, null, false, 0, uoms));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Product_BaseUomCode_Empty_ThrowsArgumentException(string? invalidCode)
    {
        var uoms = new[] { CreateValidBaseUom() };
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU", null, "Name", null, null, invalidCode!, 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_BaseUomCodeLengthBoundary_Enforced()
    {
        var validCode20 = new string('U', 20);
        var uoms = new[] { CreateValidBaseUom(validCode20) };
        var product = Product.Create(OrgId, CatId, "SKU", null, "Name", null, null, validCode20, 0m, null, false, 0, uoms);
        Assert.Equal(validCode20, product.BaseUomCode);

        var invalidCode21 = new string('U', 21);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU", null, "Name", null, null, invalidCode21, 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_ImageUrl_OptionalAndLengthBoundary_Enforced()
    {
        var uoms = new[] { CreateValidBaseUom() };
        var productNull = Product.Create(OrgId, CatId, "SKU1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Null(productNull.ImageUrl);

        var validUrl300 = new string('x', 300);
        var product = Product.Create(OrgId, CatId, "SKU2", null, "Name", null, null, "TAB", 0m, validUrl300, false, 0, uoms);
        Assert.Equal(validUrl300, product.ImageUrl);

        var invalidUrl301 = new string('x', 301);
        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU3", null, "Name", null, null, "TAB", 0m, invalidUrl301, false, 0, uoms));
    }

    #endregion

    #region Base UOM Invariant & Case Sensitivity (Ordinal)

    [Fact]
    public void Product_CaseSensitiveUomCode_DifferentCase_IsTreatedAsDifferentUom()
    {
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("tab", "Lower case tab", 10m, 20m, IsBase: false, IsSellable: true, IsPurchasable: true)
        };

        var product = Product.Create(OrgId, CatId, "SKU-CASE", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(2, product.Uoms.Count);

        var lowerUom = product.Uoms.First(u => u.UomCode == "tab");
        var upperUom = product.Uoms.First(u => u.UomCode == "TAB");
        Assert.NotEqual(lowerUom.ProductUomId, upperUom.ProductUomId);
    }

    [Fact]
    public void Product_BaseUomCodeMismatch_DueToCaseDifference_ThrowsInvalidBaseUomInvariantException()
    {
        var uoms = new[] { CreateValidBaseUom("tab") };
        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Create_WithBaseUomCodeDifferingFromProductBaseUomCode_ThrowsInvalidBaseUomInvariantException()
    {
        var uoms = new[] { CreateValidBaseUom("TAB") };
        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "BOX", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Create_WithNoBaseUom_ThrowsInvalidBaseUomInvariantException()
    {
        var uoms = new[]
        {
            new InitialUomDefinition("BOX", "Box", 10m, 50m, IsBase: false, IsSellable: true, IsPurchasable: true)
        };
        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Create_WithTwoActiveBaseUoms_ThrowsInvalidBaseUomInvariantException()
    {
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("BOX", "Box", 1m, 50m, IsBase: true, IsSellable: true, IsPurchasable: true)
        };
        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Create_WithBaseUomConversionFactorNotOne_ThrowsInvalidUomConversionFactorException()
    {
        var uoms = new[]
        {
            new InitialUomDefinition("TAB", "Tab", 2m, 10m, IsBase: true, IsSellable: true, IsPurchasable: true)
        };
        Assert.Throws<InvalidUomConversionFactorException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_Create_InvalidUomCode_InInitialUoms_ThrowsArgumentException_BeforeDuplicateCheck()
    {
        var initialUoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("", "Display", 10m, 20m, IsBase: false, IsSellable: true, IsPurchasable: true)
        };

        Assert.Throws<ArgumentException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, initialUoms));
    }

    [Fact]
    public void Product_Create_WithExactDuplicateUomCode_ThrowsCatalogDomainException()
    {
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("TAB", "Tab Duplicate", 10m, 20m, IsBase: false, IsSellable: true, IsPurchasable: true)
        };

        Assert.Throws<CatalogDomainException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void Product_AddUom_ExactDuplicateCode_ThrowsCatalogDomainException_AndLeavesStateUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var originalCount = product.Uoms.Count;
        var originalUpdatedAt = product.UpdatedAt;

        Assert.Throws<CatalogDomainException>(() =>
            product.AddUom("TAB", "Duplicate", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true));

        Assert.Equal(originalCount, product.Uoms.Count);
        Assert.Equal(originalUpdatedAt, product.UpdatedAt);
    }

    [Fact]
    public void Product_AddUom_SecondActiveBase_ThrowsInvalidBaseUomInvariantException_AndLeavesStateUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var originalCount = product.Uoms.Count;
        var originalUpdatedAt = product.UpdatedAt;

        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            product.AddUom("BOX", "Box", 1m, 50m, isBase: true, isSellable: true, isPurchasable: true));

        Assert.Equal(originalCount, product.Uoms.Count);
        Assert.Equal(originalUpdatedAt, product.UpdatedAt);
    }

    [Fact]
    public void Product_AddUom_ValidNonBase_Succeeds_AndRefreshesTimestamp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        WaitUntilClockAdvancesPast(product.UpdatedAt);
        var initialUpdated = product.UpdatedAt;

        var stripUom = product.AddUom("STRIP", "Strip of 10", 10m, 25m, isBase: false, isSellable: true, isPurchasable: true);

        Assert.Equal(2, product.Uoms.Count);
        Assert.Equal("STRIP", stripUom.UomCode);
        Assert.True(product.UpdatedAt > initialUpdated);
    }

    #endregion

    #region ProductUom String Length Boundaries & Pricing Rules

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ProductUom_UomCode_Empty_ThrowsArgumentException(string? invalidCode)
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        Assert.Throws<ArgumentException>(() =>
            product.AddUom(invalidCode!, "Display", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true));
    }

    [Fact]
    public void ProductUom_UomCodeLengthBoundary_Enforced()
    {
        var validCode20 = new string('U', 20);
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var uom = product.AddUom(validCode20, "Display", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);
        Assert.Equal(validCode20, uom.UomCode);

        var invalidCode21 = new string('U', 21);
        Assert.Throws<ArgumentException>(() =>
            product.AddUom(invalidCode21, "Display", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ProductUom_DisplayName_Empty_ThrowsArgumentException(string? invalidDisplay)
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        Assert.Throws<ArgumentException>(() =>
            product.AddUom("CODE", invalidDisplay!, 10m, 20m, isBase: false, isSellable: true, isPurchasable: true));
    }

    [Fact]
    public void ProductUom_DisplayNameLengthBoundary_Enforced()
    {
        var validDisplay50 = new string('D', 50);
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var uom = product.AddUom("BOX", validDisplay50, 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);
        Assert.Equal(validDisplay50, uom.DisplayName);

        var invalidDisplay51 = new string('D', 51);
        Assert.Throws<ArgumentException>(() =>
            product.AddUom("BOX2", invalidDisplay51, 10m, 20m, isBase: false, isSellable: true, isPurchasable: true));
    }

    [Fact]
    public void ProductUom_UpdateNonHistoricalAttributes_DisplayNameBoundaries_Enforced_AndPreservesStateOnFailure()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB", 10m) });
        var uom = product.Uoms.First();
        var originalUpdated = uom.UpdatedAt;

        Assert.Throws<ArgumentException>(() =>
            uom.UpdateNonHistoricalAttributes("", 10m, isSellable: true, isPurchasable: true));

        var invalidDisplay51 = new string('D', 51);
        Assert.Throws<ArgumentException>(() =>
            uom.UpdateNonHistoricalAttributes(invalidDisplay51, 10m, isSellable: true, isPurchasable: true));

        Assert.Equal("Tablet", uom.DisplayName);
        Assert.Equal(10m, uom.SaleUnitPrice);
        Assert.Equal(originalUpdated, uom.UpdatedAt);
    }

    [Fact]
    public void ProductUom_UpdateNonHistoricalAttributes_AcceptsDisplayNameOfExactly50Characters()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB", 10m) });
        var uom = product.Uoms.First();
        var validDisplay50 = new string('D', 50);

        WaitUntilClockAdvancesPast(uom.UpdatedAt);
        var beforeUpdate = uom.UpdatedAt;
        uom.UpdateNonHistoricalAttributes(validDisplay50, 15m, isSellable: true, isPurchasable: true);

        Assert.Equal(validDisplay50, uom.DisplayName);
        Assert.True(uom.UpdatedAt > beforeUpdate);
    }

    [Fact]
    public void ProductUom_NonSellable_WithNonNullPrice_PreservesSuppliedPrice()
    {
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("RAW", "Raw Material", 1000m, 75.50m, IsBase: false, IsSellable: false, IsPurchasable: true)
        };
        var product = Product.Create(OrgId, CatId, "SKU-RAW", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        var rawUom = product.Uoms.First(u => u.UomCode == "RAW");

        Assert.False(rawUom.IsSellable);
        Assert.Equal(75.50m, rawUom.SaleUnitPrice);

        WaitUntilClockAdvancesPast(rawUom.UpdatedAt);
        var beforeUpdate = rawUom.UpdatedAt;
        rawUom.UpdateNonHistoricalAttributes("Raw Bulk", 80.00m, isSellable: false, isPurchasable: true);
        Assert.False(rawUom.IsSellable);
        Assert.Equal(80.00m, rawUom.SaleUnitPrice);
        Assert.True(rawUom.UpdatedAt > beforeUpdate);
    }

    [Fact]
    public void ProductUom_NonSellable_WithNullPrice_IsAccepted()
    {
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("RAW", "Raw Material", 1000m, null, IsBase: false, IsSellable: false, IsPurchasable: true)
        };
        var product = Product.Create(OrgId, CatId, "SKU-RAW-NULL", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        var rawUom = product.Uoms.First(u => u.UomCode == "RAW");
        Assert.False(rawUom.IsSellable);
        Assert.Null(rawUom.SaleUnitPrice);

        WaitUntilClockAdvancesPast(rawUom.UpdatedAt);
        var beforeUpdate = rawUom.UpdatedAt;
        rawUom.UpdateNonHistoricalAttributes("Raw Updated", null, isSellable: false, isPurchasable: true);
        Assert.Null(rawUom.SaleUnitPrice);
        Assert.True(rawUom.UpdatedAt > beforeUpdate);
    }

    [Theory]
    [InlineData(0.0)]
    [InlineData(25.50)]
    public void ProductUom_Sellable_WithNonNegativePrice_Succeeds(decimal validPrice)
    {
        var uoms = new[]
        {
            new InitialUomDefinition("TAB", "Tab", 1m, validPrice, IsBase: true, IsSellable: true, IsPurchasable: true)
        };
        var product = Product.Create(OrgId, CatId, "SKU-P", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms);
        Assert.Equal(validPrice, product.Uoms.First().SaleUnitPrice);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(-0.01)]
    [InlineData(-10.0)]
    public void ProductUom_Sellable_WithNullOrNegativePrice_ThrowsInvalidSellableUomPriceException(double? invalidPriceDouble)
    {
        decimal? invalidPrice = invalidPriceDouble.HasValue ? (decimal)invalidPriceDouble.Value : null;
        var uoms = new[]
        {
            new InitialUomDefinition("TAB", "Tab", 1m, invalidPrice, IsBase: true, IsSellable: true, IsPurchasable: true)
        };
        Assert.Throws<InvalidSellableUomPriceException>(() =>
            Product.Create(OrgId, CatId, "SKU-P", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));
    }

    [Fact]
    public void ProductUom_UpdateNonHistoricalAttributes_InvalidPrice_PreservesState()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB", 10m) });
        var uom = product.Uoms.First();
        var originalUpdated = uom.UpdatedAt;

        Assert.Throws<InvalidSellableUomPriceException>(() =>
            uom.UpdateNonHistoricalAttributes("New Name", -1m, isSellable: true, isPurchasable: true));

        Assert.Equal("Tablet", uom.DisplayName);
        Assert.Equal(10m, uom.SaleUnitPrice);
        Assert.Equal(originalUpdated, uom.UpdatedAt);
    }

    [Fact]
    public void ProductUom_Deactivate_BaseUom_ThrowsInvalidBaseUomInvariantException()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var baseUom = product.Uoms.First(u => u.IsBase);

        Assert.Throws<InvalidBaseUomInvariantException>(() => baseUom.Deactivate());
        Assert.True(baseUom.IsActive);
    }

    [Fact]
    public void ProductUom_Deactivate_NonBaseUom_Succeeds_AndRefreshesTimestamp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var stripUom = product.AddUom("STRIP", "Strip", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);

        WaitUntilClockAdvancesPast(stripUom.UpdatedAt);
        var initialUpdated = stripUom.UpdatedAt;
        stripUom.Deactivate();

        Assert.False(stripUom.IsActive);
        Assert.True(stripUom.UpdatedAt > initialUpdated);
    }

    #endregion

    #region Historical Modification Guarding & Conversion Factor

    [Fact]
    public void Product_ChangeLotTrackingPolicy_WithHistory_DifferentValue_ThrowsHistoricalUomModificationForbiddenException_AndPreservesState()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, lotTrackingRequired: true, 0, new[] { CreateValidBaseUom("TAB") });
        var originalUpdated = product.UpdatedAt;

        Assert.Throws<HistoricalUomModificationForbiddenException>(() =>
            product.ChangeLotTrackingPolicy(lotTrackingRequired: false, hasStockOrPostedHistory: true));

        Assert.True(product.LotTrackingRequired);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeLotTrackingPolicy_WithHistory_SameValue_IsNoOp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, lotTrackingRequired: true, 0, new[] { CreateValidBaseUom("TAB") });
        var originalUpdated = product.UpdatedAt;

        product.ChangeLotTrackingPolicy(lotTrackingRequired: true, hasStockOrPostedHistory: true);

        Assert.True(product.LotTrackingRequired);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeLotTrackingPolicy_WithoutHistory_Succeeds_AndRefreshesTimestamp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, lotTrackingRequired: true, 0, new[] { CreateValidBaseUom("TAB") });
        WaitUntilClockAdvancesPast(product.UpdatedAt);
        var originalUpdated = product.UpdatedAt;

        product.ChangeLotTrackingPolicy(lotTrackingRequired: false, hasStockOrPostedHistory: false);

        Assert.False(product.LotTrackingRequired);
        Assert.True(product.UpdatedAt > originalUpdated);
    }

    [Fact]
    public void Product_ChangeBaseUom_WithHistory_ThrowsHistoricalUomModificationForbiddenException_EvenIfSameCode()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var originalUpdated = product.UpdatedAt;

        Assert.Throws<HistoricalUomModificationForbiddenException>(() =>
            product.ChangeBaseUom("TAB", hasStockOrPostedHistory: true));

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeBaseUom_WithHistory_DifferentCode_ThrowsHistoricalUomModificationForbiddenException_AndPreservesState()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        product.AddUom("CAP", "Capsule", 1m, 10m, isBase: false, isSellable: true, isPurchasable: true);
        var originalUpdated = product.UpdatedAt;

        Assert.Throws<HistoricalUomModificationForbiddenException>(() =>
            product.ChangeBaseUom("CAP", hasStockOrPostedHistory: true));

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeBaseUom_TargetNotFound_ThrowsInvalidBaseUomInvariantException_AndLeavesStateUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var originalUpdated = product.UpdatedAt;

        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            product.ChangeBaseUom("NONEXISTENT", hasStockOrPostedHistory: false));

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeBaseUom_TargetInactive_ThrowsInvalidBaseUomInvariantException_AndLeavesStateUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var inactiveUom = product.AddUom("CAP", "Capsule", 1m, 10m, isBase: false, isSellable: true, isPurchasable: true);
        inactiveUom.Deactivate();

        var originalUpdated = product.UpdatedAt;

        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            product.ChangeBaseUom("CAP", hasStockOrPostedHistory: false));

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
        Assert.True(product.Uoms.First(u => u.UomCode == "TAB").IsBase);
        Assert.False(inactiveUom.IsBase);
    }

    [Fact]
    public void Product_ChangeBaseUom_TargetFactorNotOne_ThrowsInvalidBaseUomInvariantException_AndLeavesStateUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        product.AddUom("STRIP", "Strip", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);
        var originalUpdated = product.UpdatedAt;

        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            product.ChangeBaseUom("STRIP", hasStockOrPostedHistory: false));

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeBaseUom_CaseMismatch_DoesNotMatchDifferentCaseTarget()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        product.AddUom("CAP", "Capsule", 1m, 10m, isBase: false, isSellable: true, isPurchasable: true);

        Assert.Throws<InvalidBaseUomInvariantException>(() =>
            product.ChangeBaseUom("cap", hasStockOrPostedHistory: false));

        Assert.Equal("TAB", product.BaseUomCode);
    }

    [Fact]
    public void Product_ChangeBaseUom_TargetAlreadyBase_IsNoOp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var originalUpdated = product.UpdatedAt;

        product.ChangeBaseUom("TAB", hasStockOrPostedHistory: false);

        Assert.Equal("TAB", product.BaseUomCode);
        Assert.Equal(originalUpdated, product.UpdatedAt);
    }

    [Fact]
    public void Product_ChangeBaseUom_SuccessPath_AtomicallyFlipsBaseAndRefreshesTimestamps()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var newBaseUom = product.AddUom("CAP", "Capsule", 1m, 12m, isBase: false, isSellable: true, isPurchasable: true);
        var oldBaseUom = product.Uoms.First(u => u.UomCode == "TAB");

        WaitUntilClockAdvancesPast(product.UpdatedAt);
        var preChangeTime = product.UpdatedAt;

        product.ChangeBaseUom("CAP", hasStockOrPostedHistory: false);

        Assert.Equal("CAP", product.BaseUomCode);
        Assert.False(oldBaseUom.IsBase);
        Assert.True(newBaseUom.IsBase);
        Assert.True(product.UpdatedAt > preChangeTime);
        Assert.True(oldBaseUom.UpdatedAt > preChangeTime);
        Assert.True(newBaseUom.UpdatedAt > preChangeTime);
    }

    [Fact]
    public void ProductUom_UpdateConversionFactor_WithHistory_ThrowsHistoricalUomModificationForbiddenException_AndPreservesState()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var stripUom = product.AddUom("STRIP", "Strip", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);
        var originalUpdated = stripUom.UpdatedAt;

        Assert.Throws<HistoricalUomModificationForbiddenException>(() =>
            stripUom.UpdateConversionFactor(12m, isReferencedByStockOrDocuments: true));

        Assert.Equal(10m, stripUom.ConversionToBase);
        Assert.Equal(originalUpdated, stripUom.UpdatedAt);
    }

    [Fact]
    public void ProductUom_UpdateConversionFactor_OnBaseUom_ToNonOne_ThrowsInvalidUomConversionFactorException()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var baseUom = product.Uoms.First(u => u.IsBase);

        Assert.Throws<InvalidUomConversionFactorException>(() =>
            baseUom.UpdateConversionFactor(2m, isReferencedByStockOrDocuments: false));

        Assert.Equal(1m, baseUom.ConversionToBase);
    }

    [Fact]
    public void ProductUom_UpdateConversionFactor_WithoutHistory_UpdatesFactorAndRefreshesTimestamp()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var stripUom = product.AddUom("STRIP", "Strip", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);

        WaitUntilClockAdvancesPast(stripUom.UpdatedAt);
        var initialUpdated = stripUom.UpdatedAt;

        stripUom.UpdateConversionFactor(12m, isReferencedByStockOrDocuments: false);

        Assert.Equal(12m, stripUom.ConversionToBase);
        Assert.True(stripUom.UpdatedAt > initialUpdated);
    }

    [Fact]
    public void ProductUom_UpdateConversionFactor_WithSameValueAndHistory_DoesNotThrow_AndLeavesUpdatedAtUnchanged()
    {
        var product = Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        var stripUom = product.AddUom("STRIP", "Strip", 10m, 20m, isBase: false, isSellable: true, isPurchasable: true);
        var originalUpdated = stripUom.UpdatedAt;

        stripUom.UpdateConversionFactor(10m, isReferencedByStockOrDocuments: true);

        Assert.Equal(10m, stripUom.ConversionToBase);
        Assert.Equal(originalUpdated, stripUom.UpdatedAt);
    }

    [Theory]
    [InlineData(0.0)]
    [InlineData(-1.0)]
    public void ProductUom_NonBase_NonPositiveConversionFactor_ThrowsInvalidUomConversionFactorException(decimal invalidFactor)
    {
        // Via Product.Create
        var uoms = new[]
        {
            CreateValidBaseUom("TAB"),
            new InitialUomDefinition("STRIP", "Strip", invalidFactor, 20m, IsBase: false, IsSellable: true, IsPurchasable: true)
        };
        Assert.Throws<InvalidUomConversionFactorException>(() =>
            Product.Create(OrgId, CatId, "SKU-1", null, "Name", null, null, "TAB", 0m, null, false, 0, uoms));

        // Via AddUom
        var product = Product.Create(OrgId, CatId, "SKU-2", null, "Name", null, null, "TAB", 0m, null, false, 0, new[] { CreateValidBaseUom("TAB") });
        Assert.Throws<InvalidUomConversionFactorException>(() =>
            product.AddUom("STRIP", "Strip", invalidFactor, 20m, isBase: false, isSellable: true, isPurchasable: true));
    }

    #endregion

    #region ProductReorderRule Tests

    [Fact]
    public void ProductReorderRule_Create_WithValidData_Succeeds()
    {
        var rule = ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, reorderPointBase: 100m, reorderQuantityBase: 50m, maxQuantityBase: 200m);

        Assert.NotEqual(Guid.Empty, rule.ReorderRuleId);
        Assert.Equal(OrgId, rule.OrganizationId);
        Assert.Equal(BranchId, rule.BranchId);
        Assert.Equal(100m, rule.ReorderPointBase);
        Assert.Equal(50m, rule.ReorderQuantityBase);
        Assert.Equal(200m, rule.MaxQuantityBase);
        Assert.True(rule.IsActive);
    }

    [Fact]
    public void ProductReorderRule_Create_WithNullMaxQuantity_Succeeds()
    {
        var rule = ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, reorderPointBase: 50m, reorderQuantityBase: 20m, maxQuantityBase: null);

        Assert.Null(rule.MaxQuantityBase);
        Assert.Equal(50m, rule.ReorderPointBase);
        Assert.Equal(20m, rule.ReorderQuantityBase);
        Assert.True(rule.IsActive);
    }

    [Fact]
    public void ProductReorderRule_Create_MaxQuantityEqualsReorderPoint_Succeeds()
    {
        var rule = ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, reorderPointBase: 100m, reorderQuantityBase: 50m, maxQuantityBase: 100m);
        Assert.Equal(100m, rule.MaxQuantityBase);
    }

    [Fact]
    public void ProductReorderRule_Create_MaxQuantityLessThanReorderPoint_ThrowsInvalidReorderRuleQuantitiesException()
    {
        Assert.Throws<InvalidReorderRuleQuantitiesException>(() =>
            ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, reorderPointBase: 100m, reorderQuantityBase: 50m, maxQuantityBase: 99.99m));
    }

    [Theory]
    [InlineData(-1.0, 50.0)]
    [InlineData(100.0, -0.01)]
    public void ProductReorderRule_Create_NegativeQuantities_ThrowsInvalidReorderRuleQuantitiesException(decimal reorderPoint, decimal reorderQty)
    {
        Assert.Throws<InvalidReorderRuleQuantitiesException>(() =>
            ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, reorderPoint, reorderQty, null));
    }

    [Fact]
    public void ProductReorderRule_UpdateThresholds_ValidatesThresholds_AndRefreshesTimestamp()
    {
        var rule = ProductReorderRule.Create(OrgId, Guid.NewGuid(), BranchId, 50m, 20m, 100m);
        WaitUntilClockAdvancesPast(rule.UpdatedAt);
        var initialUpdated = rule.UpdatedAt;

        rule.UpdateThresholds(60m, 30m, 120m);

        Assert.Equal(60m, rule.ReorderPointBase);
        Assert.Equal(30m, rule.ReorderQuantityBase);
        Assert.Equal(120m, rule.MaxQuantityBase);
        Assert.True(rule.UpdatedAt > initialUpdated);

        var preFailureUpdated = rule.UpdatedAt;
        Assert.Throws<InvalidReorderRuleQuantitiesException>(() =>
            rule.UpdateThresholds(100m, 20m, 50m));

        Assert.Equal(60m, rule.ReorderPointBase);
        Assert.Equal(30m, rule.ReorderQuantityBase);
        Assert.Equal(120m, rule.MaxQuantityBase);
        Assert.Equal(preFailureUpdated, rule.UpdatedAt);
    }

    #endregion
}
