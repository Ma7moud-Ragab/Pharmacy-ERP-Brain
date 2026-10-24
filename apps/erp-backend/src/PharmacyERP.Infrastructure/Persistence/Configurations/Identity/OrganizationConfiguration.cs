using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class OrganizationConfiguration : IEntityTypeConfiguration<Organization>
{
    public void Configure(EntityTypeBuilder<Organization> builder)
    {
        builder.ToTable("ORGANIZATION", "identity");
        builder.HasKey(x => x.OrganizationId);
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationCode).HasColumnName("organization_code").HasColumnType("varchar(30)").HasMaxLength(30).IsRequired();
        builder.Property(x => x.Name).HasColumnName("name").HasColumnType("varchar(150)").HasMaxLength(150).IsRequired();
        builder.Property(x => x.BaseCurrency).HasColumnName("base_currency").HasColumnType("char(3)").HasMaxLength(3).HasDefaultValue("EGP").IsRequired();
        builder.Property(x => x.TimeZoneId).HasColumnName("time_zone_id").HasColumnType("varchar(64)").HasMaxLength(64).IsRequired();
        builder.Property(x => x.IsActive).HasColumnName("is_active").HasDefaultValue(true).IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => x.OrganizationCode).IsUnique();
        builder.HasIndex(x => x.Name);
        builder.HasIndex(x => x.IsActive);
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
