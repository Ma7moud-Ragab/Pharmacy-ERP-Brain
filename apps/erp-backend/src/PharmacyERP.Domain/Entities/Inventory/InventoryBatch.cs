using System;
using System.Collections.Generic;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using PharmacyERP.Domain.ValueObjects;
using PharmacyERP.Domain.Entities.Catalog;

namespace PharmacyERP.Domain.Entities.Inventory;

public class InventoryBatch
{
    public Guid BatchId { get; private set; }

    public Guid OrganizationId { get; private set; }

    public Guid ProductId { get; private set; }

    public string BatchNumber { get; private set; } = string.Empty;

    public DateOnly? ManufacturedOn { get; private set; }

    public DateOnly? ExpiresOn { get; private set; }

    public BatchQualityStatus QualityStatus { get; private set; }

    public DateTimeOffset CreatedAt { get; private set; }

    public DateTimeOffset UpdatedAt { get; private set; }

    // Navigation Properties
    public virtual Product Product { get; private set; } = null!;

    public virtual ICollection<StockBalance> StockBalances { get; private set; }
        = new List<StockBalance>();

    public virtual ICollection<InventoryTxnLine> TxnLines { get; private set; }
        = new List<InventoryTxnLine>();

    private InventoryBatch()
    {
    }

    public static InventoryBatch CreateDatedBatch(
        Guid organizationId,
        Guid productId,
        string batchNumber,
        DateOnly expiresOn,
        DateOnly? manufacturedOn = null,
        BatchQualityStatus qualityStatus = BatchQualityStatus.AVAILABLE,
        DateTimeOffset? now = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (productId == Guid.Empty)
            throw new ArgumentException("ProductId cannot be empty.", nameof(productId));

        if (string.IsNullOrWhiteSpace(batchNumber))
            throw new ArgumentException("BatchNumber is required.", nameof(batchNumber));

        if (string.Equals(batchNumber, DeterministicBatchIdGenerator.NonLotBatchNumber, StringComparison.OrdinalIgnoreCase))
            throw new NonLotBatchMisuseException();

        if (manufacturedOn.HasValue && manufacturedOn.Value > expiresOn)
            throw new InvalidBatchDatesException();

        var timestamp = now ?? DateTimeOffset.UtcNow;
        var batchId = DeterministicBatchIdGenerator.Generate(organizationId, productId, batchNumber, expiresOn);

        return new InventoryBatch
        {
            BatchId = batchId,
            OrganizationId = organizationId,
            ProductId = productId,
            BatchNumber = batchNumber,
            ManufacturedOn = manufacturedOn,
            ExpiresOn = expiresOn,
            QualityStatus = qualityStatus,
            CreatedAt = timestamp,
            UpdatedAt = timestamp
        };
    }

    public static InventoryBatch CreateNonLotSystemBatch(
        Guid organizationId,
        Guid productId,
        DateTimeOffset? now = null)
    {
        if (organizationId == Guid.Empty)
            throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

        if (productId == Guid.Empty)
            throw new ArgumentException("ProductId cannot be empty.", nameof(productId));

        var timestamp = now ?? DateTimeOffset.UtcNow;
        var batchId = DeterministicBatchIdGenerator.GenerateNonLotBatchId(organizationId, productId);

        return new InventoryBatch
        {
            BatchId = batchId,
            OrganizationId = organizationId,
            ProductId = productId,
            BatchNumber = DeterministicBatchIdGenerator.NonLotBatchNumber,
            ManufacturedOn = null,
            ExpiresOn = null,
            QualityStatus = BatchQualityStatus.AVAILABLE,
            CreatedAt = timestamp,
            UpdatedAt = timestamp
        };
    }

    public bool IsEligibleForSale(DateOnly organizationBusinessDate)
    {
        if (QualityStatus != BatchQualityStatus.AVAILABLE)
            return false;

        if (ExpiresOn.HasValue && ExpiresOn.Value <= organizationBusinessDate)
            return false;

        return true;
    }

    public void UpdateQualityStatus(BatchQualityStatus newStatus, DateTimeOffset now)
    {
        QualityStatus = newStatus;
        UpdatedAt = now;
    }
}