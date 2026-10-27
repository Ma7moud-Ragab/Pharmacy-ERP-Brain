using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Integration;
using PharmacyERP.Application.Common.Utilities;
using PharmacyERP.Application.Features.Integration.Interfaces;
using PharmacyERP.Domain.Entities.Integration;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Application.Features.Integration.Services.Implementations;

public class IdempotencyService : IIdempotencyService
{
    private static readonly JsonSerializerOptions IdempotencyJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReferenceHandler = ReferenceHandler.IgnoreCycles,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Converters = { new JsonStringEnumConverter() }
    };

    private readonly IIdempotencyRepository _repository;
    private readonly ITenantContext _tenantContext;
    private readonly IDateTimeProvider _dateTimeProvider;

    public IdempotencyService(IIdempotencyRepository repository, ITenantContext tenantContext, IDateTimeProvider dateTimeProvider)
    {
        _repository = repository;
        _tenantContext = tenantContext;
        _dateTimeProvider = dateTimeProvider;
    }

    public async Task<IdempotencyCheckResult<TResponse>> CheckAsync<TRequest, TResponse>(
        string operationScope, string idempotencyKey, Guid? branchId, TRequest requestPayload, CancellationToken ct = default)
    {
        if (!_tenantContext.OrganizationId.HasValue)
        {
            throw new InvalidOperationException("OrganizationId is required to perform idempotency checks.");
        }

        if (string.IsNullOrWhiteSpace(operationScope))
        {
            throw new IntegrationDomainException("OperationScope is required.");
        }

        if (string.IsNullOrWhiteSpace(idempotencyKey))
        {
            throw new IntegrationDomainException("IdempotencyKey is required.");
        }

        var orgId = _tenantContext.OrganizationId.Value;
        var payloadHash = CanonicalJsonHasher.ComputeSha256Hex(requestPayload);
        var existingRecord = await _repository.GetAsync(orgId, branchId, operationScope, idempotencyKey, ct);

        if (existingRecord != null)
        {
            if (existingRecord.PayloadHash != payloadHash)
            {
                throw new IntegrationDomainException("IDEMPOTENCY_MISMATCH");
            }

            var response = JsonSerializer.Deserialize<TResponse>(existingRecord.ResponseBody, IdempotencyJsonOptions);

            return new IdempotencyCheckResult<TResponse> { IsReplay = true, ReplayedResponse = response };
        }

        return new IdempotencyCheckResult<TResponse> { IsReplay = false };
    }

    public async Task PersistResponseAsync<TRequest, TResponse>(
        string operationScope, string idempotencyKey, Guid? branchId, TRequest requestPayload, TResponse responseBody, CancellationToken ct = default)
    {
        if (!_tenantContext.OrganizationId.HasValue)
            throw new InvalidOperationException("OrganizationId is required to persist idempotency responses.");

        var orgId = _tenantContext.OrganizationId.Value;
        var payloadHash = CanonicalJsonHasher.ComputeSha256Hex(requestPayload);
        var responseJson = JsonSerializer.Serialize(responseBody, IdempotencyJsonOptions);

        var record = new IdempotencyRecord(orgId, branchId, operationScope, idempotencyKey, payloadHash, responseJson, _dateTimeProvider.UtcNow);
        await _repository.AddAsync(record, ct);
    }
}
