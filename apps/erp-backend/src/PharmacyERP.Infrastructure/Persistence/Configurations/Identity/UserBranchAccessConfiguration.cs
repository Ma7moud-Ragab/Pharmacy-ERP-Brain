using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class UserBranchAccessConfiguration : IEntityTypeConfiguration<UserBranchAccess>
{
    public void Configure(EntityTypeBuilder<UserBranchAccess> builder)
    {
        builder.ToTable("USER_BRANCH_ACCESS", "identity");
        builder.HasKey(x => new { x.OrganizationId, x.UserId, x.BranchId });
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.UserId).HasColumnName("user_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id").IsRequired();
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.UserId });
        builder.HasOne(x => x.UserAccount).WithMany(x => x.BranchAccesses).HasForeignKey(x => new { x.OrganizationId, x.UserId }).HasPrincipalKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);
        builder.HasOne(x => x.Branch).WithMany(x => x.UserBranchAccesses).HasForeignKey(x => new { x.OrganizationId, x.BranchId }).HasPrincipalKey(x => new { x.OrganizationId, x.BranchId }).OnDelete(DeleteBehavior.Restrict);
    }
}
