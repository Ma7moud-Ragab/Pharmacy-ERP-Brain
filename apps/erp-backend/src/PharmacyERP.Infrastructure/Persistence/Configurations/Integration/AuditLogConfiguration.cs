using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PharmacyERP.Domain.Entities.Integration;

namespace PharmacyERP.Infrastructure.Persistence.Configurations.Integration;

public class AuditLogConfiguration : IEntityTypeConfiguration<AuditLog>
{
    public void Configure(EntityTypeBuilder<AuditLog> builder)
    {
        builder.ToTable("AUDIT_LOG", "integration", t =>
        {
            t.HasCheckConstraint("CK_AUDIT_LOG_actor_type", "actor_type IN ('USER', 'SYSTEM', 'AI_ASSISTED')");
        });

        builder.HasKey(x => x.AuditLogId);

        builder.HasIndex(x => new { x.OrganizationId, x.CreatedAt });
        builder.HasIndex(x => new { x.OrganizationId, x.BranchId, x.CreatedAt });
        builder.HasIndex(x => new { x.OrganizationId, x.EntitySchema, x.EntityName, x.EntityId });
        builder.HasIndex(x => new { x.OrganizationId, x.ActorUserId, x.CreatedAt });

        builder.Property(x => x.AuditLogId).HasColumnName("audit_log_id");
        builder.Property(x => x.OrganizationId).HasColumnName("organization_id").IsRequired();
        builder.Property(x => x.BranchId).HasColumnName("branch_id");
        builder.Property(x => x.ActorUserId).HasColumnName("actor_user_id");
        builder.Property(x => x.ActorEmployeeId).HasColumnName("actor_employee_id");
        builder.Property(x => x.ActorType).HasColumnName("actor_type").HasConversion<string>().HasMaxLength(20).IsRequired();
        builder.Property(x => x.Action).HasColumnName("action").HasMaxLength(80).IsRequired();
        builder.Property(x => x.EntitySchema).HasColumnName("entity_schema").HasMaxLength(63).IsRequired();
        builder.Property(x => x.EntityName).HasColumnName("entity_name").HasMaxLength(100).IsRequired();
        builder.Property(x => x.EntityId).HasColumnName("entity_id").IsRequired();
        builder.Property(x => x.SourcePromptId).HasColumnName("source_prompt_id").HasMaxLength(100);
        builder.Property(x => x.BeforeData).HasColumnName("before_data").HasColumnType("jsonb");
        builder.Property(x => x.AfterData).HasColumnName("after_data").HasColumnType("jsonb");
        builder.Property(x => x.TraceId).HasColumnName("trace_id").HasMaxLength(100).IsRequired();
        builder.Property(x => x.CreatedAt).HasColumnName("created_at").HasColumnType("timestamptz").IsRequired();

        builder.HasOne(x => x.Branch)
               .WithMany()
               .HasForeignKey(x => new { x.OrganizationId, x.BranchId })
               .HasPrincipalKey(b => new { b.OrganizationId, b.BranchId })
               .IsRequired(false)
               .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.ActorUser)
               .WithMany()
               .HasForeignKey(x => new { x.OrganizationId, x.ActorUserId })
               .HasPrincipalKey(u => new { u.OrganizationId, u.UserId })
               .IsRequired(false)
               .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(x => x.ActorEmployee)
               .WithMany()
               .HasForeignKey(x => new { x.OrganizationId, x.ActorEmployeeId })
               .HasPrincipalKey(e => new { e.OrganizationId, e.EmployeeId })
               .IsRequired(false)
               .OnDelete(DeleteBehavior.Restrict);
    }
}