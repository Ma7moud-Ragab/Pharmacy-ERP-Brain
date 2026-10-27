namespace PharmacyERP.Application.Common.Interfaces.CrossModule;

public interface IProductInventoryUsageChecker
{
    Task<bool> HasAnyStockOrPostedHistoryForProductAsync(Guid organizationId, Guid productId, CancellationToken ct = default);
    Task<bool> HasAnyStockOrDocumentReferenceForUomAsync(Guid organizationId, Guid productId, Guid productUomId, CancellationToken ct = default);
}