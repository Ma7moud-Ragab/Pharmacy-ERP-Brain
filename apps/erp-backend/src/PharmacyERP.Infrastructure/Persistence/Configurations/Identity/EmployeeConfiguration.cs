using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class EmployeeConfiguration : IEntityTypeConfiguration<Employee>
{
    public void Configure(EntityTypeBuilder<Employee> builder)
    {
        builder.ToTable("EMPLOYEE", "identity");
        builder.HasKey(x => x.EmployeeId);
        builder.HasAlternateKey(x => new { x.OrganizationId, x.BranchId, x.EmployeeId });
        builder.HasAlternateKey(x => new { x.OrganizationId, x.EmployeeId });
        builder.Property(x => x.EmployeeId).HasColumnName("employee_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.Property(x => x.EmployeeNo).HasColumnName("employee_no").HasColumnType("varchar(30)").HasMaxLength(30).IsRequired();
        builder.Property(x => x.FullName).HasColumnName("full_name").HasColumnType("varchar(150)").HasMaxLength(150).IsRequired();
        builder.Property(x => x.Email).HasColumnName("email").HasColumnType("varchar(254)").HasMaxLength(254);
        builder.Property(x => x.Phone).HasColumnName("phone").HasColumnType("varchar(30)").HasMaxLength(30);
        builder.Property(x => x.JobTitle).HasColumnName("job_title").HasColumnType("varchar(80)").HasMaxLength(80).IsRequired();
        builder.Property(x => x.HiredOn).HasColumnName("hired_on").HasColumnType("date").IsRequired();
        builder.Property(x => x.IsActive).HasColumnName("is_active").IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.EmployeeNo }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.FullName });
        builder.HasIndex(x => new { x.OrganizationId, x.Email });
        builder.HasIndex(x => new { x.OrganizationId, x.Phone });
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.IsActive });
        builder.HasOne(x => x.Branch).WithMany(x => x.Employees).HasForeignKey(x => new { x.OrganizationId, x.BranchId }).HasPrincipalKey(x => new { x.OrganizationId, x.BranchId }).OnDelete(DeleteBehavior.Restrict);
        builder.ComplexProperty(x => x.Address, a =>
        {
            a.Property(x => x.Line1).HasColumnName("address_line1").HasColumnType("varchar(200)").HasMaxLength(200).IsRequired();
            a.Property(x => x.Line2).HasColumnName("address_line2").HasColumnType("varchar(200)").HasMaxLength(200);
            a.Property(x => x.City).HasColumnName("address_city").HasColumnType("varchar(100)").HasMaxLength(100).IsRequired();
            a.Property(x => x.Region).HasColumnName("address_region").HasColumnType("varchar(100)").HasMaxLength(100);
            a.Property(x => x.PostalCode).HasColumnName("address_postal_code").HasColumnType("varchar(20)").HasMaxLength(20);
            a.Property(x => x.CountryCode).HasColumnName("address_country_code").HasColumnType("char(2)").HasMaxLength(2).IsRequired();
        });
    }
}
