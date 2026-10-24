using Microsoft.EntityFrameworkCore;
using PharmacyERP.Domain.Entities.Identity;


namespace PharmacyERP.Infrastructure.Persistence.Database
{
    public partial class PharmacyDbContext
    {
        public DbSet<Organization> Organizations => Set<Organization>();
        public DbSet<Branch> Branches => Set<Branch>();
        public DbSet<Employee> Employees => Set<Employee>();
        public DbSet<UserAccount> UserAccounts => Set<UserAccount>();
        public DbSet<UserBranchAccess> UserBranchAccesses => Set<UserBranchAccess>();
        public DbSet<BranchEnrollment> BranchEnrollments => Set<BranchEnrollment>();
        public DbSet<UserRefreshToken> UserRefreshTokens => Set<UserRefreshToken>();
    }
}
