namespace PharmacyERP.Domain.Exceptions;



public class IntegrationDomainException : DomainException
{
    public IntegrationDomainException(string message) : base(message) { }
}

public class InvalidIdempotencyHashException : IntegrationDomainException
{
    public InvalidIdempotencyHashException(string hash)
        : base($"Invalid payload hash '{hash}'. Must be exactly 64 hex characters.") { }
}

public class MissingSourcePromptIdException : IntegrationDomainException
{
    public MissingSourcePromptIdException()
        : base("Both ActorUserId and SourcePromptId are strictly required when ActorType is AI_ASSISTED.") { }
}