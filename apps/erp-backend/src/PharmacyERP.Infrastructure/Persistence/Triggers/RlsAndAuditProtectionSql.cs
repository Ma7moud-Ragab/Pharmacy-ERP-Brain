namespace PharmacyERP.Infrastructure.Persistence.Triggers;

public static class RlsAndAuditProtectionSql
{
    public static readonly IReadOnlyList<(string Schema, string Table)> TenantBoundTables = new List<(string, string)>
    {
        ("identity", "ORGANIZATION"),
        ("identity", "BRANCH"),
        ("identity", "EMPLOYEE"),
        ("identity", "USER_ACCOUNT"),
        ("identity", "USER_BRANCH_ACCESS"),
        ("identity", "USER_REFRESH_TOKEN"),
        ("identity", "BRANCH_ENROLLMENT"),
        ("catalog", "PRODUCT"),
        ("catalog", "PRODUCT_UOM"),
        ("catalog", "PRODUCT_REORDER_RULE"),
        ("inventory", "STORAGE_LOCATION"),
        ("inventory", "PRODUCT_BATCH"),
        ("inventory", "STOCK_BALANCE"),
        ("inventory", "INVENTORY_TXN"),
        ("inventory", "INVENTORY_TXN_LINE"),
        ("integration", "OUTBOX_EVENT_CURSOR"),
        ("integration", "OUTBOX_EVENT"),
        ("integration", "IDEMPOTENCY_RECORD"),
        ("integration", "AUDIT_LOG")
    };

    public static string GenerateEnableRlsSql(string schema, string tableName)
    {
        if (string.IsNullOrWhiteSpace(schema)) throw new ArgumentException("Schema is required.", nameof(schema));
        if (string.IsNullOrWhiteSpace(tableName)) throw new ArgumentException("Table name is required.", nameof(tableName));

        return $@"
ALTER TABLE {schema}.""{tableName}"" ENABLE ROW LEVEL SECURITY;
ALTER TABLE {schema}.""{tableName}"" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_policy ON {schema}.""{tableName}"";
CREATE POLICY tenant_isolation_policy ON {schema}.""{tableName}""
    USING (
        COALESCE(current_setting('app.system_bypass', true), 'false') = 'true'
        OR organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    )
    WITH CHECK (
        COALESCE(current_setting('app.system_bypass', true), 'false') = 'true'
        OR organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
    );";
    }

    public static string GenerateAuditLogImmutabilityTriggerSql()
    {
        return @"
CREATE OR REPLACE FUNCTION integration.prevent_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'integration.AUDIT_LOG is append-only. UPDATE and DELETE operations are strictly forbidden.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON integration.""AUDIT_LOG"";
CREATE TRIGGER trg_audit_log_immutable
BEFORE UPDATE OR DELETE ON integration.""AUDIT_LOG""
FOR EACH ROW EXECUTE FUNCTION integration.prevent_audit_log_mutation();";
    }

    public static string GenerateCompleteStage1SecuritySql()
    {
        var scripts = TenantBoundTables
            .Select(t => GenerateEnableRlsSql(t.Schema, t.Table))
            .ToList();

        scripts.Add(GenerateAuditLogImmutabilityTriggerSql());
        return string.Join(Environment.NewLine, scripts);
    }
}