using System.Linq;
using Microsoft.EntityFrameworkCore;
using PharmacyERP.Domain.Entities.Inventory;
using PharmacyERP.Infrastructure.Persistence.Configurations.Inventory;
using Xunit;

namespace PharmacyERP.UnitTests.Infrastructure;

public class InventoryModelConfigurationTests
{
    private readonly Microsoft.EntityFrameworkCore.Metadata.IModel _model;

    public InventoryModelConfigurationTests()
    {
        var modelBuilder = new ModelBuilder();

        modelBuilder.ApplyConfiguration(new InventoryLocationConfiguration());
        modelBuilder.ApplyConfiguration(new InventoryBatchConfiguration());
        modelBuilder.ApplyConfiguration(new StockBalanceConfiguration());
        modelBuilder.ApplyConfiguration(new InventoryTxnConfiguration());
        modelBuilder.ApplyConfiguration(new InventoryTxnLineConfiguration());

        _model = modelBuilder.FinalizeModel();
    }

    [Fact]
    public void Model_InventoryEntities_BelongToInventorySchema()
    {
        var entities = new[]
        {
            typeof(InventoryLocation),
            typeof(InventoryBatch),
            typeof(StockBalance),
            typeof(InventoryTxn),
            typeof(InventoryTxnLine)
        };

        foreach (var entityType in entities)
        {
            var entity = _model.FindEntityType(entityType);
            Assert.NotNull(entity);
            Assert.Equal("inventory", entity.GetSchema());
        }
    }

    [Fact]
    public void InventoryBatch_HasPartialUniqueIndexesAndFefoIndex()
    {
        var batchEntity = _model.FindEntityType(typeof(InventoryBatch));
        Assert.NotNull(batchEntity);

        var indexes = batchEntity.GetIndexes().ToList();

        // Check Partial Unique Index for non-null expires_on
        Assert.Contains(indexes, i => i.IsUnique && i.GetFilter() == "expires_on IS NOT NULL");

        // Check Partial Unique Index for null expires_on
        Assert.Contains(indexes, i => i.IsUnique && i.GetFilter() == "expires_on IS NULL");

        // Check FEFO Index
        Assert.Contains(indexes, i => i.Properties.Any(p => p.Name == "QualityStatus") &&
                                     i.Properties.Any(p => p.Name == "ExpiresOn"));
    }

    [Fact]
    public void StockBalance_HasCompositePrimaryKeyAndBatchReconciliationIndex()
    {
        var stockEntity = _model.FindEntityType(typeof(StockBalance));
        Assert.NotNull(stockEntity);

        // Composite PK check
        var primaryKey = stockEntity.FindPrimaryKey();
        Assert.NotNull(primaryKey);
        Assert.Equal(3, primaryKey.Properties.Count);

        // Batch Reconciliation Index check
        var indexes = stockEntity.GetIndexes();
        Assert.Contains(indexes, i => i.Properties.Select(p => p.Name).SequenceEqual(new[] { "OrganizationId", "BatchId", "LocationId" }));
    }

    [Fact]
    public void InventoryTxnLine_HasCheckConstraintsConfigured()
    {
        var lineEntity = _model.FindEntityType(typeof(InventoryTxnLine));
        Assert.NotNull(lineEntity);

        var constraints = lineEntity.GetCheckConstraints().ToList();
        Assert.Contains(constraints, c => c.Name == "CK_INVENTORY_TXN_LINE_positive_factors");
        Assert.Contains(constraints, c => c.Name == "CK_INVENTORY_TXN_LINE_delta_math");
    }
}