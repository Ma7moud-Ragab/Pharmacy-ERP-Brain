using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace PharmacyERP.Application.Common.Utilities;

public static class CanonicalJsonHasher
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = false,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new CanonicalDecimalJsonConverter() }
    };

    public static string SerializeToCanonicalJson<T>(T payload)
    {
        if (payload is null) return "null";

        var jsonNode = JsonSerializer.SerializeToNode(payload, Options);
        var sortedNode = SortNode(jsonNode);

        return sortedNode?.ToJsonString(Options) ?? "null";
    }

    public static string ComputeSha256Hex<T>(T payload)
    {
        var canonicalJson = SerializeToCanonicalJson(payload);
        var utf8Bytes = Encoding.UTF8.GetBytes(canonicalJson);
        var hashBytes = SHA256.HashData(utf8Bytes);

        return Convert.ToHexString(hashBytes).ToLowerInvariant();
    }

    private static JsonNode? SortNode(JsonNode? node)
    {
        if (node is JsonObject jsonObj)
        {
            var sortedObj = new JsonObject();
            foreach (var kvp in jsonObj.OrderBy(p => p.Key, StringComparer.Ordinal))
            {
                sortedObj[kvp.Key] = SortNode(kvp.Value?.DeepClone());
            }
            return sortedObj;
        }

        if (node is JsonArray jsonArr)
        {
            var newArr = new JsonArray();
            foreach (var item in jsonArr)
            {
                newArr.Add(SortNode(item?.DeepClone()));
            }
            return newArr;
        }

        return node?.DeepClone();
    }

    private sealed class CanonicalDecimalJsonConverter : JsonConverter<decimal>
    {
        public override decimal Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
            => reader.GetDecimal();

        public override void Write(Utf8JsonWriter writer, decimal value, JsonSerializerOptions options)
        {
            decimal normalized = value / 1.000000000000000000000000000000000m;
            writer.WriteRawValue(normalized.ToString("G29", CultureInfo.InvariantCulture));
        }
    }
}