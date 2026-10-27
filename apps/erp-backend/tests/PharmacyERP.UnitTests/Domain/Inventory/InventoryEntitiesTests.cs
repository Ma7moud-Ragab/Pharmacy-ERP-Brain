using System;
using Xunit;
using PharmacyERP.Domain.Entities.Inventory;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.UnitTests.Domain.Inventory;

public class InventoryEntitiesTests
{
    private readonly Guid _orgId = Guid.NewGuid();
    private readonly Guid _branchId = Guid.NewGuid();
    private readonly Guid _productId = Guid.NewGuid();
    private readonly Guid _locationId = Guid.NewGuid();
    private readonly Guid _batchId = Guid.NewGuid();
    private readonly Guid _uomId = Guid.NewGuid();
    private readonly Guid _employeeId = Guid.NewGuid();
    private readonly DateTimeOffset _now = DateTimeOffset.UtcNow;

    #region InventoryLocation Tests

    [Theory]
    [InlineData(LocationType.QUARANTINE)]
    [InlineData(LocationType.DAMAGED)]
    [InlineData(LocationType.SCRAP)]
    public void InventoryLocation_Create_NonSellableTypeWithIsSellableTrue_ThrowsException(LocationType type)
    {
        Assert.Throws<InvalidLocationSellableFlagException>(() =>
            InventoryLocation.Create(_orgId, _branchId, "LOC-01", "Test Location", type, isSellable: true, _now));
    }

    [Fact]
    public void InventoryLocation_CreateDefaultSellable_SetsCorrectProperties()
    {
        var loc = InventoryLocation.CreateDefaultSellable(_orgId, _branchId, _now);

        Assert.Equal("MAIN-SELLABLE", loc.LocationCode);
        Assert.Equal(LocationType.SELLABLE, loc.LocationType);
        Assert.True(loc.IsSellable);
        Assert.True(loc.IsActive);
    }

    #endregion

    #region StockBalance & Weighted Average Cost Tests

    [Fact]
    public void StockBalance_ApplyIncomingStock_CalculatesWeightedAverageCostCorrectly()
    {
        var balance = StockBalance.Create(_orgId, _locationId, _batchId, _now);

        // Batch 1: Add 10 units @ $10.00 each -> Total = $100.00
        balance.ApplyIncomingStock(acceptedQtyBase: 10m, incomingUnitCostBase: 10m, _now);
        Assert.Equal(10m, balance.OnHandQtyBase);
        Assert.Equal(10m, balance.AverageUnitCost);

        // Batch 2: Add 20 units @ $25.00 each -> Total = $500.00
        // New Total Qty = 30, New Total Cost = $600.00 -> New Avg = $20.00
        balance.ApplyIncomingStock(acceptedQtyBase: 20m, incomingUnitCostBase: 25m, _now);
        Assert.Equal(30m, balance.OnHandQtyBase);
        Assert.Equal(20m, balance.AverageUnitCost);

        // Batch 3: Add 5 units @ $12.3333 each
        // New Total Qty = 35, New Total Cost = $600 + $61.6665 = $661.6665 -> Avg = 18.9048
        balance.ApplyIncomingStock(acceptedQtyBase: 5m, incomingUnitCostBase: 12.3333m, _now);
        Assert.Equal(35m, balance.OnHandQtyBase);
        Assert.Equal(18.9048m, balance.AverageUnitCost);
    }

    [Fact]
    public void StockBalance_ApplyOutgoingStock_PreservesCostAndDecreasesQty()
    {
        var balance = StockBalance.Create(_orgId, _locationId, _batchId, _now);
        balance.ApplyIncomingStock(acceptedQtyBase: 10m, incomingUnitCostBase: 20m, _now);

        decimal costSnapshot = balance.ApplyOutgoingStock(issueQtyBaseAbs: 4m, _now);

        Assert.Equal(6m, balance.OnHandQtyBase);
        Assert.Equal(20m, balance.AverageUnitCost);
        Assert.Equal(20m, costSnapshot);
    }

    [Fact]
    public void StockBalance_ApplyOutgoingStock_InsufficientStock_ThrowsException()
    {
        var balance = StockBalance.Create(_orgId, _locationId, _batchId, _now);
        balance.ApplyIncomingStock(acceptedQtyBase: 5m, incomingUnitCostBase: 10m, _now);

        Assert.Throws<InsufficientStockException>(() =>
            balance.ApplyOutgoingStock(issueQtyBaseAbs: 6m, _now));
    }

    #endregion

    #region InventoryTxn Immutability Tests

    [Fact]
    public void InventoryTxn_Post_LocksTransactionFromMutations()
    {
        var txn = InventoryTxn.CreateDraft(_orgId, _branchId, "TXN-001", InventoryTransactionType.ADJUSTMENT_IN, "KEY-1", _employeeId, _now);
        var line = InventoryTxnLine.Create(_orgId, txn.InventoryTxnId, _branchId, _productId, _locationId, _batchId, _uomId, 5m, 1m, 5m, 10m, InventoryTransactionType.ADJUSTMENT_IN);
        txn.AddLine(line);

        txn.Post(_now);

        Assert.Equal(InventoryTransactionStatus.POSTED, txn.Status);
        Assert.Throws<ImmutablePostedTransactionException>(() => txn.AddLine(line));
        Assert.Throws<ImmutablePostedTransactionException>(() => txn.Post(_now));
        Assert.Throws<ImmutablePostedTransactionException>(() => txn.Cancel());
    }

    #endregion

    #region InventoryTxnLine Math & Sign Verification Tests

    [Fact]
    public void InventoryTxnLine_Create_InconsistentDeltaMath_ThrowsException()
    {
        // 5 * 1 = 5, but delta passed is 10
        Assert.Throws<InvalidTransactionSignOrLineMathException>(() =>
            InventoryTxnLine.Create(_orgId, Guid.NewGuid(), _branchId, _productId, _locationId, _batchId, _uomId,
                enteredQty: 5m, conversionSnapshot: 1m, quantityDeltaBase: 10m, unitCostBase: 10m, InventoryTransactionType.ADJUSTMENT_IN));
    }

    [Fact]
    public void InventoryTxnLine_Create_WrongSignForType_ThrowsException()
    {
        // ADJUSTMENT_IN must have positive delta
        Assert.Throws<InvalidTransactionSignOrLineMathException>(() =>
            InventoryTxnLine.Create(_orgId, Guid.NewGuid(), _branchId, _productId, _locationId, _batchId, _uomId,
                enteredQty: 5m, conversionSnapshot: 1m, quantityDeltaBase: -5m, unitCostBase: 10m, InventoryTransactionType.ADJUSTMENT_IN));

        // ADJUSTMENT_OUT must have negative delta
        Assert.Throws<InvalidTransactionSignOrLineMathException>(() =>
            InventoryTxnLine.Create(_orgId, Guid.NewGuid(), _branchId, _productId, _locationId, _batchId, _uomId,
                enteredQty: 5m, conversionSnapshot: 1m, quantityDeltaBase: 5m, unitCostBase: 10m, InventoryTransactionType.ADJUSTMENT_OUT));
    }

    #endregion
}