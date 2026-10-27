using System;
using System.Collections.Generic;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Domain.Entities.Inventory;

public class InventoryLocation
{
	public Guid LocationId { get; private set; }

	public Guid OrganizationId { get; private set; }

	public Guid BranchId { get; private set; }

	public string LocationCode { get; private set; } = string.Empty;

	public string Name { get; private set; } = string.Empty;

	public LocationType LocationType { get; private set; }

	public bool IsSellable { get; private set; }

	public bool IsActive { get; private set; } = true;

	public DateTimeOffset CreatedAt { get; private set; }

	public DateTimeOffset UpdatedAt { get; private set; }

	// Navigation Properties
	public virtual Branch Branch { get; private set; } = null!;

	public virtual ICollection<StockBalance> StockBalances { get; private set; }
		= new List<StockBalance>();

	public virtual ICollection<InventoryTxnLine> TxnLines { get; private set; }
		= new List<InventoryTxnLine>();

	// Private constructor required for ORM / Object Mapping
	private InventoryLocation()
	{
	}

	public static InventoryLocation Create(
		Guid organizationId,
		Guid branchId,
		string locationCode,
		string name,
		LocationType locationType,
		bool isSellable,
		DateTimeOffset now)
	{
		ValidateSellableFlag(locationType, isSellable);
		ValidateInput(organizationId, branchId, locationCode, name);

		return new InventoryLocation
		{
			LocationId = Guid.NewGuid(),
			OrganizationId = organizationId,
			BranchId = branchId,
			LocationCode = locationCode,
			Name = name,
			LocationType = locationType,
			IsSellable = isSellable,
			IsActive = true,
			CreatedAt = now,
			UpdatedAt = now
		};
	}

	public void Update(
		string locationCode,
		string name,
		LocationType locationType,
		bool isSellable,
		bool isActive,
		DateTimeOffset now)
	{
		ValidateSellableFlag(locationType, isSellable);
		ValidateInput(OrganizationId, BranchId, locationCode, name);

		LocationCode = locationCode;
		Name = name;
		LocationType = locationType;
		IsSellable = isSellable;
		IsActive = isActive;
		UpdatedAt = now;
	}

	public static InventoryLocation CreateDefaultSellable(
		Guid organizationId,
		Guid branchId,
		DateTimeOffset now)
	{
		return Create(
			organizationId,
			branchId,
			"MAIN-SELLABLE",
			"Main Sellable Stock",
			LocationType.SELLABLE,
			true,
			now);
	}

	public static InventoryLocation CreateDefaultQuarantine(
		Guid organizationId,
		Guid branchId,
		DateTimeOffset now)
	{
		return Create(
			organizationId,
			branchId,
			"MAIN-QUARANTINE",
			"Quarantine Area",
			LocationType.QUARANTINE,
			false,
			now);
	}

	public static InventoryLocation CreateDefaultScrap(
		Guid organizationId,
		Guid branchId,
		DateTimeOffset now)
	{
		return Create(
			organizationId,
			branchId,
			"MAIN-SCRAP",
			"Scrap & Disposal",
			LocationType.SCRAP,
			false,
			now);
	}

	private static void ValidateSellableFlag(
		LocationType locationType,
		bool isSellable)
	{
		if (locationType != LocationType.SELLABLE && isSellable)
		{
			throw new InvalidLocationSellableFlagException();
		}
	}

	private static void ValidateInput(
		Guid organizationId,
		Guid branchId,
		string locationCode,
		string name)
	{
		if (organizationId == Guid.Empty)
		{
			throw new ArgumentException(
				"OrganizationId cannot be empty.",
				nameof(organizationId));
		}

		if (branchId == Guid.Empty)
		{
			throw new ArgumentException(
				"BranchId cannot be empty.",
				nameof(branchId));
		}

		if (string.IsNullOrWhiteSpace(locationCode))
		{
			throw new ArgumentException(
				"LocationCode is required.",
				nameof(locationCode));
		}

		if (locationCode.Length > 30)
		{
			throw new ArgumentException(
				"LocationCode cannot exceed 30 characters.",
				nameof(locationCode));
		}

		if (string.IsNullOrWhiteSpace(name))
		{
			throw new ArgumentException(
				"Name is required.",
				nameof(name));
		}

		if (name.Length > 100)
		{
			throw new ArgumentException(
				"Name cannot exceed 100 characters.",
				nameof(name));
		}
	}
}