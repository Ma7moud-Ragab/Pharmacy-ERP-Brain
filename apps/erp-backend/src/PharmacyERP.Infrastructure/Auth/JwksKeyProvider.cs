using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace PharmacyERP.Infrastructure.Auth;

/// <summary>Process-scoped RSA signing key. Private key parameters are never exported.</summary>
public sealed class JwksKeyProvider : IDisposable
{
    private readonly RSA _rsa;
    public string KeyId { get; } = Guid.NewGuid().ToString("N");

    public JwksKeyProvider() => _rsa = RSA.Create(3072);

    public SigningCredentials CreateSigningCredentials()
        => new(new RsaSecurityKey(_rsa) { KeyId = KeyId }, SecurityAlgorithms.RsaSha256);

    public RSAParameters GetPublicKeyParameters() => _rsa.ExportParameters(false);

    public string GetPublicJwksJson()
    {
        var parameters = _rsa.ExportParameters(false);
        return JsonSerializer.Serialize(new
        {
            keys = new[]
            {
                new
                {
                    kty = "RSA", use = "sig", alg = "RS256", kid = KeyId,
                    n = Base64UrlEncode(parameters.Modulus!), e = Base64UrlEncode(parameters.Exponent!)
                }
            }
        });
    }

    public static string Base64UrlEncode(byte[] value)
        => Convert.ToBase64String(value).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public static byte[] Base64UrlDecode(string value)
    {
        var normalized = value.Replace('-', '+').Replace('_', '/');
        normalized = normalized.PadRight(normalized.Length + ((4 - normalized.Length % 4) % 4), '=');
        return Convert.FromBase64String(normalized);
    }

    public void Dispose() => _rsa.Dispose();
}
