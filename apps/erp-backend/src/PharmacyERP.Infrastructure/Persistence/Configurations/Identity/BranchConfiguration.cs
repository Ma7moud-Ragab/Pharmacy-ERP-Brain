using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class BranchConfiguration : IEntityTypeConfiguration<Branch>
{
    public void Configure(EntityTypeBuilder<Branch> builder)
    {
        builder.ToTable("BRANCH", "identity");
        builder.HasKey(x => x.BranchId);
        builder.HasAlternateKey(x => new { x.OrganizationId, x.BranchId });
        builder.Property(x => x.BranchId).HasColumnName("branch_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchCode).HasColumnName("branch_code").HasColumnType("varchar(30)").HasMaxLength(30).IsRequired();
        builder.Property(x => x.Name).HasColumnName("name").HasColumnType("varchar(150)").HasMaxLength(150).IsRequired();
        builder.Property(x => x.IsActive).HasColumnName("is_active").IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchCode }).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.IsActive, x.Name });
        builder.HasOne(x => x.Organization).WithMany(x => x.Branches).HasForeignKey(x => x.OrganizationId).OnDelete(DeleteBehavior.Restrict);
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
