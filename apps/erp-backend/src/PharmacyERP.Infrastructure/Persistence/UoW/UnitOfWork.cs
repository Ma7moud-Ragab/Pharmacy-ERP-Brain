using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using PharmacyERP.Application.Common.Interfaces.Context;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.UoW;

public class UnitOfWork : IUnitOfWork
{
    private readonly PharmacyDbContext _dbContext;
    private readonly ITenantContext _tenantContext;
    private IDbContextTransaction? _currentTransaction;

    public UnitOfWork(PharmacyDbContext dbContext, ITenantContext tenantContext)
    {
        _dbContext = dbContext;
        _tenantContext = tenantContext;
    }

    public bool HasActiveTransaction => _currentTransaction != null;

    public async Task BeginTransactionAsync(CancellationToken ct = default)
    {
        if (_currentTransaction != null)
        {
            throw new InvalidOperationException("A transaction is already active in this UnitOfWork.");
        }

        _currentTransaction = await _dbContext.Database.BeginTransactionAsync(ct);

        if (_dbContext.Database.IsRelational())
        {
            if (_tenantContext.IsTenantBound && _tenantContext.OrganizationId.HasValue)
            {
                var orgIdString = _tenantContext.OrganizationId.Value.ToString();
                await _dbContext.Database.ExecuteSqlInterpolatedAsync(
                    $"SELECT set_config('app.organization_id', {orgIdString}, true);", ct);
            }
            else if (_tenantContext.IsSystemBypassAllowed)
            {
                await _dbContext.Database.ExecuteSqlRawAsync(
                    "SELECT set_config('app.system_bypass', 'true', true);", ct);
            }
        }
    }

    public Task<int> SaveChangesAsync(CancellationToken ct = default)
    {
        return _dbContext.SaveChangesAsync(ct);
    }

    public async Task CommitTransactionAsync(CancellationToken ct = default)
    {
        if (_currentTransaction == null)
        {
            throw new InvalidOperationException("No active transaction to commit.");
        }

        try
        {
            await _dbContext.SaveChangesAsync(ct);
            await _currentTransaction.CommitAsync(ct);
        }
        catch
        {
            await RollbackTransactionAsync(ct);
            throw;
        }
        finally
        {
            await DisposeTransactionAsync();
        }
    }

    public async Task RollbackTransactionAsync(CancellationToken ct = default)
    {
        if (_currentTransaction == null)
        {
            return;
        }

        try
        {
            await _currentTransaction.RollbackAsync(ct);
        }
        finally
        {
            await DisposeTransactionAsync();
        }
    }

    private async Task DisposeTransactionAsync()
    {
        if (_currentTransaction != null)
        {
            await _currentTransaction.DisposeAsync();
            _currentTransaction = null;
        }
    }

    public void Dispose()
    {
        _currentTransaction?.Dispose();
        _currentTransaction = null;
    }

    public async ValueTask DisposeAsync()
    {
        await DisposeTransactionAsync();
    }
}