namespace PharmacyERP.Domain.Exceptions;

public class IdentityDomainException : DomainException
{
    public IdentityDomainException(string message) : base(message) { }
}

public sealed class InvalidAddressException : IdentityDomainException
{
    public InvalidAddressException(string message = "The supplied address is invalid.") : base(message) { }
}

public sealed class InvalidTimeZoneException : IdentityDomainException
{
    public InvalidTimeZoneException(string message = "The supplied time zone is invalid.") : base(message) { }
}

public sealed class InvalidBranchScopeForRoleException : IdentityDomainException
{
    public InvalidBranchScopeForRoleException(string message = "Only an Admin may have ALL branch scope.") : base(message) { }
}

public sealed class RefreshTokenCompromisedException : IdentityDomainException
{
    public RefreshTokenCompromisedException(string message = "Refresh token reuse was detected.") : base(message) { }
}

public sealed class RefreshTokenExpiredOrRevokedException : IdentityDomainException
{
    public RefreshTokenExpiredOrRevokedException(string message = "The refresh token has expired or been revoked.") : base(message) { }
}

public sealed class EnrollmentTokenInvalidOrExpiredException : IdentityDomainException
{
    public EnrollmentTokenInvalidOrExpiredException(string message = "The enrollment token is invalid, expired, or already used.") : base(message) { }
}

public sealed class AccountLockedOutException : IdentityDomainException
{
    public AccountLockedOutException(string message = "The account is locked out.") : base(message) { }
}

public sealed class InactiveEntityException : IdentityDomainException
{
    public InactiveEntityException(string message = "The entity is inactive.") : base(message) { }
}
