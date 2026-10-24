namespace PharmacyERP.Application.Common.Interfaces.CrossModule;

public interface IBranchDefaultLocationSeeder
{
    Task SeedDefaultLocationsAsync(Guid organizationId, Guid branchId, CancellationToken ct = default);
}