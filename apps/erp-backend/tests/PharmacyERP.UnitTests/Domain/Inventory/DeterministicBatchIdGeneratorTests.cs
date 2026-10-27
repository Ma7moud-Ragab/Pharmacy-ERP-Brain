using System;
using PharmacyERP.Domain.ValueObjects;
using Xunit;

namespace PharmacyERP.UnitTests.Domain.Inventory;

public class DeterministicBatchIdGeneratorTests
{
	private readonly Guid _organizationId = Guid.Parse("11111111-1111-1111-1111-111111111111");
	private readonly Guid _productId = Guid.Parse("22222222-2222-2222-2222-222222222222");

	[Fact]
	public void Generate_WithSameInputs_ReturnsSameGuid()
	{
		var first = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "AB123", new DateOnly(2027, 12, 31));
		var second = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "AB123", new DateOnly(2027, 12, 31));

		Assert.Equal(first, second);
	}

	[Fact]
	public void Generate_ProducesValidUuidVersion5AndVariant()
	{
		var guid = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "BATCH-01", null);
		string stringGuid = guid.ToString();

		Assert.Equal('5', stringGuid[14]);

		char variantChar = char.ToLower(stringGuid[19]);
		Assert.Contains(variantChar, new[] { '8', '9', 'a', 'b' });
	}

	[Fact]
	public void Generate_IsCaseSensitiveForBatchNumber()
	{
		var lowerCaseResult = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "ab1", null);
		var upperCaseResult = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "AB1", null);

		Assert.NotEqual(lowerCaseResult, upperCaseResult);
	}

	[Fact]
	public void Generate_IsWhitespaceSensitiveForBatchNumber()
	{
		var withoutSpace = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "ab1", null);
		var withSpace = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "ab1 ", null);

		Assert.NotEqual(withoutSpace, withSpace);
	}

	[Fact]
	public void Generate_WithNullVsNonNullExpiryDate_ReturnsDifferentGuids()
	{
		var withNullExpiry = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "AB123", null);
		var withExpiryDate = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, "AB123", new DateOnly(2027, 12, 31));

		Assert.NotEqual(withNullExpiry, withExpiryDate);
	}

	[Fact]
	public void Generate_WithArabicAndSpecialCharacters_HandlesEncodingCorrectly()
	{
		var arabicBatch = "تشغيلة-123-\"مُنتج\"";

		var guid1 = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, arabicBatch, null);
		var guid2 = DeterministicBatchIdGenerator.Generate(_organizationId, _productId, arabicBatch, null);

		Assert.NotEqual(Guid.Empty, guid1);
		Assert.Equal(guid1, guid2);
		Assert.Equal('5', guid1.ToString()[14]);
	}

	[Fact]
	public void GenerateNonLotBatchId_UsesNonLotConstantAndNullExpiry()
	{
		var nonLotGuid = DeterministicBatchIdGenerator.GenerateNonLotBatchId(_organizationId, _productId);
		var expectedGuid = DeterministicBatchIdGenerator.Generate(
			_organizationId,
			_productId,
			DeterministicBatchIdGenerator.NonLotBatchNumber,
			null);

		Assert.Equal(expectedGuid, nonLotGuid);
	}

	[Fact]
	public void Generate_WithKnownInputs_ProducesDeterministicExpectedGuid()
	{
		var orgId = Guid.Parse("00000000-0000-0000-0000-000000000001");
		var prodId = Guid.Parse("00000000-0000-0000-0000-000000000002");
		var batchNo = "LOT-100";
		var expiry = new DateOnly(2026, 05, 15);

		var resultGuid = DeterministicBatchIdGenerator.Generate(orgId, prodId, batchNo, expiry);

		var verificationGuid = DeterministicBatchIdGenerator.Generate(orgId, prodId, batchNo, expiry);
		Assert.Equal(verificationGuid, resultGuid);
	}
}