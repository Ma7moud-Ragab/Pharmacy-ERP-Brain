using System;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Inventory;

public class StockBalance
{
    public Guid OrganizationId { get; private set; }

    public Guid LocationId { get; private set; }

    public Guid BatchId { get; private set; }

    public decimal OnHandQtyBase { get; private set; }

    public decimal AverageUnitCost { get; private set; }

    public long RowVersion { get; private set; }

    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation Properties
    public virtual InventoryLocation Location { get; private set; } = null!;

    public virtual InventoryBatch Batch { get; private set; } = null!;

    private StockBalance()
    {
    }

    public static StockBalance Create(Guid organizationId, Guid locationId, Guid batchId, DateTimeOffset now)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (locationId == Guid.Empty)
            throw new ArgumentException("LocationId cannot be empty.", nameof(locationId));

        if (batchId == Guid.Empty)
            throw new ArgumentException("BatchId cannot be empty.", nameof(batchId));

        return new StockBalance
        {
            OrganizationId = organizationId,
            LocationId = locationId,
            BatchId = batchId,
            OnHandQtyBase = 0m,
            AverageUnitCost = 0m,
            RowVersion = 1,
            UpdatedAt = now
        };
    }

    public void ApplyIncomingStock(decimal acceptedQtyBase, decimal incomingUnitCostBase, DateTimeOffset now)
    {
        if (acceptedQtyBase <= 0m || incomingUnitCostBase < 0m)
            throw new NegativeCostOrQuantityException();

        decimal totalNewQty = OnHandQtyBase + acceptedQtyBase;
        decimal newTotalValue = (OnHandQtyBase * AverageUnitCost) + (acceptedQtyBase * incomingUnitCostBase);
        decimal newWeightedAverageCost = newTotalValue / totalNewQty;

        AverageUnitCost = Math.Round(newWeightedAverageCost, 4, MidpointRounding.AwayFromZero);
        OnHandQtyBase = Math.Round(totalNewQty, 4, MidpointRounding.AwayFromZero);
        RowVersion++;
        UpdatedAt = now;
    }

    public decimal ApplyOutgoingStock(decimal issueQtyBaseAbs, DateTimeOffset now)
    {
        if (issueQtyBaseAbs <= 0m)
            throw new NegativeCostOrQuantityException();

        if (OnHandQtyBase < issueQtyBaseAbs)
            throw new InsufficientStockException();

        OnHandQtyBase = Math.Round(OnHandQtyBase - issueQtyBaseAbs, 4, MidpointRounding.AwayFromZero);
        RowVersion++;
        UpdatedAt = now;

        return AverageUnitCost;
    }
}