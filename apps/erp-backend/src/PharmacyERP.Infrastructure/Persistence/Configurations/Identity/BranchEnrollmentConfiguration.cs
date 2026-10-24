using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class BranchEnrollmentConfiguration : IEntityTypeConfiguration<BranchEnrollment>
{
    public void Configure(EntityTypeBuilder<BranchEnrollment> builder)
    {
        builder.ToTable("BRANCH_ENROLLMENT", "identity");
        builder.HasKey(x => x.EnrollmentId);
        builder.Property(x => x.EnrollmentId).HasColumnName("enrollment_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.Property(x => x.TokenHash).HasColumnName("token_hash").HasColumnType("bytea").IsRequired();
        builder.Property(x => x.ExpiresAt).HasColumnName("expires_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.UsedAt).HasColumnName("used_at").HasColumnType("timestamptz");
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => x.TokenHash).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.ExpiresAt });
        builder.HasOne(x => x.Branch).WithMany(x => x.Enrollments).HasForeignKey(x => new { x.OrganizationId, x.BranchId }).HasPrincipalKey(x => new { x.OrganizationId, x.BranchId }).OnDelete(DeleteBehavior.Restrict);
    }
}
