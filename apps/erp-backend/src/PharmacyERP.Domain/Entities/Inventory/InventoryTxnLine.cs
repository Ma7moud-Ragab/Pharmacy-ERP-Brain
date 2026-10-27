using System;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Inventory;

public class InventoryTxnLine
{
    public Guid InventoryTxnLineId { get; private set; }

    public Guid OrganizationId { get; private set; }

    public Guid InventoryTxnId { get; private set; }

    public Guid BranchId { get; private set; }

    public Guid ProductId { get; private set; }

    public Guid LocationId { get; private set; }

    public Guid BatchId { get; private set; }

    public Guid ProductUomId { get; private set; }

    public decimal EnteredQty { get; private set; }

    public decimal ConversionSnapshot { get; private set; }

    public decimal QuantityDeltaBase { get; private set; }

    public decimal UnitCostBase { get; private set; }

    // Optional cross-module FKs for future stages
    public Guid? SalesOrderLineId { get; private set; }

    public Guid? SalesReturnLineId { get; private set; }

    public Guid? PurchaseOrderLineId { get; private set; }

    public Guid? VendorReturnLineId { get; private set; }

    // Navigation Properties
    public virtual InventoryTxn InventoryTxn { get; private set; } = null!;

    public virtual InventoryLocation Location { get; private set; } = null!;

    public virtual InventoryBatch Batch { get; private set; } = null!;

    private InventoryTxnLine()
    {
    }

    public static InventoryTxnLine Create(
        Guid organizationId,
        Guid inventoryTxnId,
        Guid branchId,
        Guid productId,
        Guid locationId,
        Guid batchId,
        Guid productUomId,
        decimal enteredQty,
        decimal conversionSnapshot,
        decimal quantityDeltaBase,
        decimal unitCostBase,
        InventoryTransactionType transactionType,
        Guid? salesOrderLineId = null,
        Guid? salesReturnLineId = null,
        Guid? purchaseOrderLineId = null,
        Guid? vendorReturnLineId = null)
    {
        ValidateInputs(
            organizationId,
            inventoryTxnId,
            branchId,
            productId,
            locationId,
            batchId,
            productUomId,
            enteredQty,
            conversionSnapshot,
            quantityDeltaBase,
            unitCostBase,
            transactionType);

        return new InventoryTxnLine
        {
            InventoryTxnLineId = Guid.NewGuid(),
            OrganizationId = organizationId,
            InventoryTxnId = inventoryTxnId,
            BranchId = branchId,
            ProductId = productId,
            LocationId = locationId,
            BatchId = batchId,
            ProductUomId = productUomId,
            EnteredQty = enteredQty,
            ConversionSnapshot = conversionSnapshot,
            QuantityDeltaBase = quantityDeltaBase,
            UnitCostBase = unitCostBase,
            SalesOrderLineId = salesOrderLineId,
            SalesReturnLineId = salesReturnLineId,
            PurchaseOrderLineId = purchaseOrderLineId,
            VendorReturnLineId = vendorReturnLineId
        };
    }

    private static void ValidateInputs(
        Guid organizationId,
        Guid inventoryTxnId,
        Guid branchId,
        Guid productId,
        Guid locationId,
        Guid batchId,
        Guid productUomId,
        decimal enteredQty,
        decimal conversionSnapshot,
        decimal quantityDeltaBase,
        decimal unitCostBase,
        InventoryTransactionType transactionType)
    {
        if (organizationId == Guid.Empty) throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));
        if (inventoryTxnId == Guid.Empty) throw new ArgumentException("InventoryTxnId cannot be empty.", nameof(inventoryTxnId));
        if (branchId == Guid.Empty) throw new ArgumentException("BranchId cannot be empty.", nameof(branchId));
        if (productId == Guid.Empty) throw new ArgumentException("ProductId cannot be empty.", nameof(productId));
        if (locationId == Guid.Empty) throw new ArgumentException("LocationId cannot be empty.", nameof(locationId));
        if (batchId == Guid.Empty) throw new ArgumentException("BatchId cannot be empty.", nameof(batchId));
        if (productUomId == Guid.Empty) throw new ArgumentException("ProductUomId cannot be empty.", nameof(productUomId));

        if (enteredQty <= 0m || conversionSnapshot <= 0m || quantityDeltaBase == 0m || unitCostBase < 0m)
        {
            throw new InvalidTransactionSignOrLineMathException();
        }

        // Check math accuracy: abs(quantity_delta_base) = round(entered_qty * conversion_snapshot, 4)
        decimal expectedAbsDelta = Math.Round(enteredQty * conversionSnapshot, 4, MidpointRounding.AwayFromZero);
        if (Math.Abs(quantityDeltaBase) != expectedAbsDelta)
        {
            throw new InvalidTransactionSignOrLineMathException();
        }

        // Check delta sign based on transaction type
        switch (transactionType)
        {
            case InventoryTransactionType.OPENING_BALANCE:
            case InventoryTransactionType.ADJUSTMENT_IN:
            case InventoryTransactionType.SALES_RETURN_IN:
            case InventoryTransactionType.PURCHASE_RECEIPT:
                if (quantityDeltaBase <= 0m) throw new InvalidTransactionSignOrLineMathException();
                break;

            case InventoryTransactionType.ADJUSTMENT_OUT:
            case InventoryTransactionType.SALE_ISSUE:
            case InventoryTransactionType.VENDOR_RETURN_OUT:
            case InventoryTransactionType.SCRAP_OUT:
                if (quantityDeltaBase >= 0m) throw new InvalidTransactionSignOrLineMathException();
                break;

            case InventoryTransactionType.REVERSAL:
                // Reversal lines invert the original transaction's delta sign
                break;

            default:
                throw new ArgumentOutOfRangeException(nameof(transactionType), transactionType, "Unsupported transaction type.");
        }
    }
}