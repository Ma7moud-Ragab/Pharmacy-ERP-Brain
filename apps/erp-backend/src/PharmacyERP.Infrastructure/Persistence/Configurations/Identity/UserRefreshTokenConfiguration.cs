using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Identity;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Identity;

public sealed class UserRefreshTokenConfiguration : IEntityTypeConfiguration<UserRefreshToken>
{
    public void Configure(EntityTypeBuilder<UserRefreshToken> builder)
    {
        builder.ToTable("USER_REFRESH_TOKEN", "identity", t =>
            t.HasCheckConstraint("CK_USER_REFRESH_TOKEN_expiry", "expires_at > issued_at"));
        builder.HasKey(x => x.RefreshTokenId);
        builder.Property(x => x.RefreshTokenId).HasColumnName("refresh_token_id").ValueGeneratedNever();
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.UserId).HasColumnName("user_id").IsRequired();
        builder.Property(x => x.TokenHash).HasColumnName("token_hash").HasColumnType("bytea").IsRequired();
        builder.Property(x => x.TokenFamilyId).HasColumnName("token_family_id").IsRequired();
        builder.Property(x => x.IssuedAt).HasColumnName("issued_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.ExpiresAt).HasColumnName("expires_at").HasColumnType("timestamptz").IsRequired();
        builder.Property(x => x.ConsumedAt).HasColumnName("consumed_at").HasColumnType("timestamptz");
        builder.Property(x => x.RevokedAt).HasColumnName("revoked_at").HasColumnType("timestamptz");
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();
        builder.HasIndex(x => x.TokenHash).IsUnique();
        builder.HasIndex(x => new { x.OrganizationId, x.UserId, x.RevokedAt });
        builder.HasIndex(x => new { x.OrganizationId, x.TokenFamilyId });
        builder.HasOne(x => x.UserAccount).WithMany(x => x.RefreshTokens).HasForeignKey(x => new { x.OrganizationId, x.UserId }).HasPrincipalKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);
    }
}
