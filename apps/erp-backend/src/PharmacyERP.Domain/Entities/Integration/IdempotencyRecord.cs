using PharmacyERP.Domain.Entities.Identity;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Integration;

public class IdempotencyRecord
{
    public Guid IdempotencyRecordId { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid? BranchId { get; private set; }
    public string OperationScope { get; private set; } = null!;
    public string IdempotencyKey { get; private set; } = null!;
    public string PayloadHash { get; private set; } = null!;
    public string ResponseBody { get; private set; } = null!;
    public DateTimeOffset CreatedAt { get; private set; }

    public Branch? Branch { get; private set; }

    private IdempotencyRecord() { }

    public IdempotencyRecord(Guid organizationId, Guid? branchId, string operationScope, string idempotencyKey, string payloadHash, string responseBody, DateTimeOffset createdAt)
    {
        if (string.IsNullOrWhiteSpace(payloadHash) || payloadHash.Length != 64)
            throw new InvalidIdempotencyHashException(payloadHash ?? "null");
        if (string.IsNullOrWhiteSpace(operationScope)) throw new IntegrationDomainException("OperationScope is required.");
        if (string.IsNullOrWhiteSpace(idempotencyKey)) throw new IntegrationDomainException("IdempotencyKey is required.");
        if (string.IsNullOrWhiteSpace(responseBody)) throw new IntegrationDomainException("ResponseBody is required.");

        IdempotencyRecordId = Guid.NewGuid();
        OrganizationId = organizationId;
        BranchId = branchId;
        OperationScope = operationScope;
        IdempotencyKey = idempotencyKey;
        PayloadHash = payloadHash;
        ResponseBody = responseBody;
        CreatedAt = createdAt; // Injected from Service
    }
}