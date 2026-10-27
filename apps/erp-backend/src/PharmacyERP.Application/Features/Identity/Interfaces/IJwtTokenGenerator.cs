using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Application.Features.Identity.Interfaces;

public sealed record GeneratedAccessToken(string Token, DateTimeOffset ExpiresAt);

public interface IJwtTokenGenerator
{
    GeneratedAccessToken GenerateAccessToken(UserAccount user, IReadOnlyCollection<Guid> branchIds);
}
