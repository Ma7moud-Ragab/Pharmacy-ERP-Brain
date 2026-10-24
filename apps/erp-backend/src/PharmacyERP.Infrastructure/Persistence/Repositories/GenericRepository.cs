using Microsoft.EntityFrameworkCore;
using PharmacyERP.Application.Common.Interfaces.Persistence;
using PharmacyERP.Infrastructure.Persistence.Database;

namespace PharmacyERP.Infrastructure.Persistence.Repositories;

public class GenericRepository<T> : IGenericRepository<T> where T : class
{
    protected readonly PharmacyDbContext _dbContext;
    protected readonly DbSet<T> _dbSet;

    public GenericRepository(PharmacyDbContext dbContext)
    {
        _dbContext = dbContext;
        _dbSet = _dbContext.Set<T>();
    }

    public async Task<T?> GetByIdAsync(Guid id, CancellationToken ct = default)
    {
        return await _dbSet.FindAsync(new object[] { id }, ct);
    }

    public async Task AddAsync(T entity, CancellationToken ct = default)
    {
        await _dbSet.AddAsync(entity, ct);
    }

    public async Task AddRangeAsync(IEnumerable<T> entities, CancellationToken ct = default)
    {
        await _dbSet.AddRangeAsync(entities, ct);
    }

    public void Update(T entity)
    {
        _dbSet.Update(entity);
    }

    public IQueryable<T> AsQueryable()
    {
        return _dbSet.AsQueryable();
    }
}