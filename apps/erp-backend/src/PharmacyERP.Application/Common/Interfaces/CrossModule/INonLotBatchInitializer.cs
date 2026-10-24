namespace PharmacyERP.Application.Common.Interfaces.CrossModule;

public interface INonLotBatchInitializer
{
    Task EnsureNonLotBatchExistsAsync(Guid organizationId, Guid productId, CancellationToken ct = default);
}