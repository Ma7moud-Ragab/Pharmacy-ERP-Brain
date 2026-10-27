using System;
using System.Collections.Generic;
using PharmacyERP.Domain.Enums;
using PharmacyERP.Domain.Exceptions;

namespace PharmacyERP.Domain.Entities.Inventory;

public class InventoryTxn
{
	public Guid InventoryTxnId { get; private set; }

	public Guid OrganizationId { get; private set; }

	public Guid BranchId { get; private set; }

	public string TransactionNo { get; private set; } = string.Empty;

	public InventoryTransactionType TransactionType { get; private set; }

	public InventoryTransactionStatus Status { get; private set; }

	public string? ReasonCode { get; private set; }

	public string? Note { get; private set; }

	public string IdempotencyKey { get; private set; } = string.Empty;

	public Guid CreatedByEmployeeId { get; private set; }

	public Guid? ReversesInventoryTxnId { get; private set; }

	// Optional cross-module FKs for future stages
	public Guid? SalesOrderId { get; private set; }

	public Guid? SalesReturnId { get; private set; }

	public Guid? PurchaseOrderId { get; private set; }

	public Guid? VendorReturnId { get; private set; }

	public DateTimeOffset CreatedAt { get; private set; }

	public DateTimeOffset? PostedAt { get; private set; }

	// Navigation Properties
	public virtual ICollection<InventoryTxnLine> Lines { get; private set; }
		= new List<InventoryTxnLine>();

	public virtual InventoryTxn? ReversesInventoryTxn { get; private set; }

	private InventoryTxn()
	{
	}

	public static InventoryTxn CreateDraft(
		Guid organizationId,
		Guid branchId,
		string transactionNo,
		InventoryTransactionType transactionType,
		string idempotencyKey,
		Guid createdByEmployeeId,
		DateTimeOffset now,
		string? reasonCode = null,
		string? note = null,
		Guid? reversesInventoryTxnId = null,
		Guid? salesOrderId = null,
		Guid? salesReturnId = null,
		Guid? purchaseOrderId = null,
		Guid? vendorReturnId = null)
	{
		ValidateCreationParameters(organizationId, branchId, transactionNo, idempotencyKey, createdByEmployeeId);

		return new InventoryTxn
		{
			InventoryTxnId = Guid.NewGuid(),
			OrganizationId = organizationId,
			BranchId = branchId,
			TransactionNo = transactionNo,
			TransactionType = transactionType,
			Status = InventoryTransactionStatus.DRAFT,
			ReasonCode = reasonCode,
			Note = note,
			IdempotencyKey = idempotencyKey,
			CreatedByEmployeeId = createdByEmployeeId,
			ReversesInventoryTxnId = reversesInventoryTxnId,
			SalesOrderId = salesOrderId,
			SalesReturnId = salesReturnId,
			PurchaseOrderId = purchaseOrderId,
			VendorReturnId = vendorReturnId,
			CreatedAt = now,
			PostedAt = null
		};
	}

	public static InventoryTxn CreatePosted(
		Guid organizationId,
		Guid branchId,
		string transactionNo,
		InventoryTransactionType transactionType,
		string idempotencyKey,
		Guid createdByEmployeeId,
		DateTimeOffset now,
		string? reasonCode = null,
		string? note = null,
		Guid? reversesInventoryTxnId = null,
		Guid? salesOrderId = null,
		Guid? salesReturnId = null,
		Guid? purchaseOrderId = null,
		Guid? vendorReturnId = null)
	{
		var txn = CreateDraft(
			organizationId,
			branchId,
			transactionNo,
			transactionType,
			idempotencyKey,
			createdByEmployeeId,
			now,
			reasonCode,
			note,
			reversesInventoryTxnId,
			salesOrderId,
			salesReturnId,
			purchaseOrderId,
			vendorReturnId);

		txn.Status = InventoryTransactionStatus.POSTED;
		txn.PostedAt = now;
		return txn;
	}

	public void AddLine(InventoryTxnLine line)
	{
		EnsureDraft();
		if (line == null) throw new ArgumentNullException(nameof(line));
		Lines.Add(line);
	}

	public void Post(DateTimeOffset postedAt)
	{
		EnsureDraft();
		Status = InventoryTransactionStatus.POSTED;
		PostedAt = postedAt;
	}

	public void Cancel()
	{
		EnsureDraft();
		Status = InventoryTransactionStatus.CANCELLED;
	}

	private void EnsureDraft()
	{
		if (Status == InventoryTransactionStatus.POSTED)
		{
			throw new ImmutablePostedTransactionException();
		}

		if (Status == InventoryTransactionStatus.CANCELLED)
		{
			throw new InvalidOperationException("Cannot mutate a cancelled transaction.");
		}
	}

	private static void ValidateCreationParameters(
		Guid organizationId,
		Guid branchId,
		string transactionNo,
		string idempotencyKey,
		Guid createdByEmployeeId)
	{
		if (organizationId == Guid.Empty)
			throw new ArgumentException("OrganizationId cannot be empty.", nameof(organizationId));

		if (branchId == Guid.Empty)
			throw new ArgumentException("BranchId cannot be empty.", nameof(branchId));

		if (string.IsNullOrWhiteSpace(transactionNo))
			throw new ArgumentException("TransactionNo is required.", nameof(transactionNo));

		if (transactionNo.Length > 40)
			throw new ArgumentException("TransactionNo cannot exceed 40 characters.", nameof(transactionNo));

		if (string.IsNullOrWhiteSpace(idempotencyKey))
			throw new ArgumentException("IdempotencyKey is required.", nameof(idempotencyKey));

		if (createdByEmployeeId == Guid.Empty)
			throw new ArgumentException("CreatedByEmployeeId cannot be empty.", nameof(createdByEmployeeId));
	}
}