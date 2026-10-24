using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class UserAccountConfiguration : IEntityTypeConfiguration<UserAccount>
{
    public void Configure(EntityTypeBuilder<UserAccount> builder)
    {
        builder.ToTable("USER_ACCOUNT", "identity", t =>
        {
            t.HasCheckConstraint("CK_USER_ACCOUNT_role", "role IN ('Admin', 'Pharmacist', 'Cashier')");
            t.HasCheckConstraint("CK_USER_ACCOUNT_branch_scope", "branch_scope IN ('ALL', 'ASSIGNED')");
            t.HasCheckConstraint("CK_USER_ACCOUNT_scope_admin_only", "branch_scope <> 'ALL' OR role = 'Admin'");
        });
        builder.HasKey(x => x.UserId);
        builder.HasAlternateKey(x => new { x.OrganizationId, x.UserId });
        builder.Property(x => x.UserId).HasColumnName("user_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.EmployeeId).HasColumnName("employee_id").IsRequired();
        builder.Property(x => x.Username).HasColumnName("username").HasColumnType("varchar(80)").HasMaxLength(80).IsRequired();
        builder.Property(x => x.NormalizedUsername).HasColumnName("normalized_username").HasColumnType("varchar(80)").HasMaxLength(80).IsRequired();
        builder.Property(x => x.PasswordHash).HasColumnName("password_hash").HasColumnType("varchar(500)").HasMaxLength(500).IsRequired();
        builder.Property(x => x.Role).HasColumnName("role").HasConversion<string>().HasColumnType("varchar(30)").HasMaxLength(30).IsRequired();
        builder.Property(x => x.BranchScope).HasColumnName("branch_scope").HasConversion<string>().HasColumnType("varchar(10)").HasMaxLength(10).IsRequired();
        builder.Property(x => x.IsActive).HasColumnName("is_active").IsRequired();
        builder.Property(x => x.AccessFailedCount).HasColumnName("access_failed_count").HasDefaultValue(0).IsRequired();
        builder.Property(x => x.LockoutEnd).HasColumnName("lockout_end").HasColumnType("timestamptz");
        builder.Property(x => x.LastLoginAt).HasColumnName("last_login_at").HasColumnType("timestamptz");
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => new { x.OrganizationId, x.NormalizedUsername }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.EmployeeId }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.Role, x.IsActive });
        builder.HasOne(x => x.Employee).WithOne(x => x.UserAccount).HasForeignKey<UserAccount>(x => new { x.OrganizationId, x.EmployeeId }).HasPrincipalKey<Employee>(x => new { x.OrganizationId, x.EmployeeId }).OnDelete(DeleteBehavior.Restrict);
    }
}
