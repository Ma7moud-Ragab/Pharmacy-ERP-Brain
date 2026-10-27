namespace PharmacyERP.Domain.Exceptions;

public sealed class InvalidLocationSellableFlagException : DomainException
{
	public InvalidLocationSellableFlagException()
		: base("The location is not configured as sellable, but IsSellable flag was set to true.") { }

	public InvalidLocationSellableFlagException(string message)
		: base(message) { }
}

public sealed class InvalidBatchDatesException : DomainException
{
	public InvalidBatchDatesException()
		: base("Invalid batch dates: manufacturing date cannot be after expiry date, or required expiry date is missing.") { }

	public InvalidBatchDatesException(string message)
		: base(message) { }
}

public sealed class NonLotBatchMisuseException : DomainException
{
	public NonLotBatchMisuseException()
		: base("Cannot use NON-LOT batch identifier for a product that requires batch tracking.") { }

	public NonLotBatchMisuseException(string message)
		: base(message) { }
}

public sealed class InsufficientStockException : DomainException
{
	public InsufficientStockException()
		: base("Insufficient stock available to complete this operation.") { }

	public InsufficientStockException(string message)
		: base(message) { }
}

public sealed class NegativeCostOrQuantityException : DomainException
{
	public NegativeCostOrQuantityException()
		: base("Cost or quantity cannot be zero or negative for this operation.") { }

	public NegativeCostOrQuantityException(string message)
		: base(message) { }
}

public sealed class ImmutablePostedTransactionException : DomainException
{
	public ImmutablePostedTransactionException()
		: base("Cannot modify or cancel a transaction that has already been posted.") { }

	public ImmutablePostedTransactionException(string message)
		: base(message) { }
}

public sealed class InvalidTransactionSignOrLineMathException : DomainException
{
	public InvalidTransactionSignOrLineMathException()
		: base("Transaction quantity sign or unit conversion math is incorrect.") { }

	public InvalidTransactionSignOrLineMathException(string message)
		: base(message) { }
}

public sealed class CloudStockMutationForbiddenException : DomainException
{
	public CloudStockMutationForbiddenException()
		: base("Direct stock mutation for branch is forbidden in Cloud environment. Must be executed in BranchLocal.") { }

	public CloudStockMutationForbiddenException(string message)
		: base(message) { }
}