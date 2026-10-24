namespace PharmacyERP.Application.Common.Interfaces.Integration
{
    public interface IOutboxService
    {
        Task EnqueueAsync<TPayload>(string eventType, Guid? branchId, TPayload payload, string schemaVersion = "1.0", CancellationToken ct = default);
    }
}
