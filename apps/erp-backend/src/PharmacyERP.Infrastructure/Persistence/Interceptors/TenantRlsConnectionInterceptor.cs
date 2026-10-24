using System.Data.Common;
using Microsoft.EntityFrameworkCore.Diagnostics;
using PharmacyERP.Application.Common.Interfaces.Context;

namespace PharmacyERP.Infrastructure.Persistence.Interceptors;

public class TenantRlsConnectionInterceptor : DbCommandInterceptor
{
    private readonly ITenantContext _tenantContext;

    public TenantRlsConnectionInterceptor(ITenantContext tenantContext)
    {
        _tenantContext = tenantContext;
    }

    public override InterceptionResult<DbDataReader> ReaderExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.ReaderExecuting(command, eventData, result);
    }

    public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.ReaderExecutingAsync(command, eventData, result, cancellationToken);
    }

    public override InterceptionResult<int> NonQueryExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<int> result)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.NonQueryExecuting(command, eventData, result);
    }

    public override ValueTask<InterceptionResult<int>> NonQueryExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<int> result, CancellationToken cancellationToken = default)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.NonQueryExecutingAsync(command, eventData, result, cancellationToken);
    }

    public override InterceptionResult<object> ScalarExecuting(
        DbCommand command, CommandEventData eventData, InterceptionResult<object> result)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.ScalarExecuting(command, eventData, result);
    }

    public override ValueTask<InterceptionResult<object>> ScalarExecutingAsync(
        DbCommand command, CommandEventData eventData, InterceptionResult<object> result, CancellationToken cancellationToken = default)
    {
        ValidateRlsAndTransactionGuard(command);
        return base.ScalarExecutingAsync(command, eventData, result, cancellationToken);
    }

    private void ValidateRlsAndTransactionGuard(DbCommand command)
    {
        if (string.IsNullOrWhiteSpace(command.CommandText) ||
            command.CommandText.Contains("set_config('app.", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (_tenantContext.IsSystemBypassEnabled)
        {
            return;
        }

        if (command.Transaction == null)
        {
            throw new InvalidOperationException("Database commands on tenant-scoped tables must be executed within an active transaction.");
        }

        if (!_tenantContext.IsTenantBound || !_tenantContext.OrganizationId.HasValue)
        {
            throw new UnauthorizedAccessException("Tenant context is not bound to a valid OrganizationId.");
        }
    }
}