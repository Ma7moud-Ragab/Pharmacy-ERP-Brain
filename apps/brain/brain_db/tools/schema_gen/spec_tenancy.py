from spec_lib import *

T = DEFAULT_TENANT
REQUIRED_RULE_SETS = ["platform", "anomaly", "risk", "recommendation", "forecast"]

GUARD_TENANT_REGISTRY = """CREATE OR REPLACE FUNCTION ingest.guard_tenant_registry() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  missing text;
BEGIN
  -- N-01: a tenant is never activated silently. It is created as 'provisioning' and becomes 'active' only through an
  -- explicit UPDATE that passes the checks below. All times are database server time (client values are ignored).
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'provisioning' THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: a tenant must be created in status provisioning (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.created_at := now(); NEW.updated_at := now();
    NEW.activated_at := NULL; NEW.suspended_at := NULL;
    IF NEW.credential_validated_at IS NOT NULL THEN NEW.credential_validated_at := now(); END IF;
    RETURN NEW;
  END IF;

  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION USING MESSAGE = 'tenant_registry: tenant_id is immutable', ERRCODE = 'check_violation';
  END IF;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := now();

  -- A new or rotated credential counts as validated only when the same UPDATE records a validation.
  IF (NEW.credential_ref IS DISTINCT FROM OLD.credential_ref OR NEW.credential_sha256 IS DISTINCT FROM OLD.credential_sha256)
     AND NEW.credential_validated_at IS NOT DISTINCT FROM OLD.credential_validated_at THEN
    IF NEW.status = 'active' THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: credential of an active tenant changed without a new validation (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.credential_validated_at := NULL;
  ELSIF NEW.credential_validated_at IS DISTINCT FROM OLD.credential_validated_at AND NEW.credential_validated_at IS NOT NULL THEN
    NEW.credential_validated_at := now();
  END IF;
  IF NEW.credential_ref IS DISTINCT FROM OLD.credential_ref OR NEW.credential_sha256 IS DISTINCT FROM OLD.credential_sha256 THEN
    NEW.credential_version := OLD.credential_version + 1;
  ELSE
    NEW.credential_version := OLD.credential_version;
  END IF;

  IF NEW.status = 'active' AND OLD.status <> 'active' THEN
    IF NEW.credential_validated_at IS NULL THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: cannot activate tenant ' || NEW.tenant_id || ': its Canonical credential is not validated (N-01)', ERRCODE = 'check_violation';
    END IF;
    SELECT string_agg(s, ', ' ORDER BY s) INTO missing
      FROM unnest(ARRAY[@@RULE_SETS@@]) AS s
     WHERE NOT EXISTS (SELECT 1 FROM intel.rule_config r
                        WHERE r.tenant_id = NEW.tenant_id AND r.rule_set = s AND r.is_active);
    IF missing IS NOT NULL THEN
      RAISE EXCEPTION USING MESSAGE = 'tenant_registry: cannot activate tenant ' || NEW.tenant_id || ': no active rule_config for ' || missing || ' (N-01)', ERRCODE = 'check_violation';
    END IF;
    NEW.activated_at := now();
    NEW.suspended_at := NULL;
  ELSIF NEW.status = 'suspended' AND OLD.status <> 'suspended' THEN
    NEW.suspended_at := now();
    NEW.activated_at := OLD.activated_at;
  ELSE
    NEW.activated_at := OLD.activated_at;
    NEW.suspended_at := OLD.suspended_at;
  END IF;
  RETURN NEW;
END
$fn$;
CREATE TRIGGER trg_tenant_registry_guard BEFORE INSERT OR UPDATE ON ingest.tenant_registry FOR EACH ROW EXECUTE FUNCTION ingest.guard_tenant_registry();""".replace(
    "@@RULE_SETS@@", ",".join(f"'{s}'" for s in REQUIRED_RULE_SETS))

tenant_registry = Table(
    schema="ingest", name="tenant_registry", cls="TenantRegistry", tier="O", scope="MVP",
    purpose="Stable registry of the tenants (ERP organizations) this Brain serves, with a REFERENCE to each tenant's Canonical API credential (never the secret). brain-worker runs jobs only for `active` tenants; brain-api refuses tokens of tenants that are not `active` (N-01). A tenant is created as `provisioning` and becomes `active` only when its credential was validated and its rule sets exist.",
    cols=[col("tenant_id", "UUID", "Tenant UUID = ERP organization id (external reference owned by ERP Identity). Primary key: one row per tenant, never reused or renamed."),
          col("display_label", "TEXT", "Short non-sensitive label for operators (e.g. 'Demo pharmacy A'). Never used for authorization.", null=True),
          col("status", "TEXT", "provisioning (created, not yet usable) | active (jobs run, API serves) | suspended (jobs skipped, API refuses; data kept).", default="'provisioning'"),
          col("status_reason", "TEXT", "Why the tenant is suspended (operator text, <= 200 chars, no secrets).", null=True),
          col("credential_ref", "TEXT", "Name of this tenant's Canonical API credential in the secret store, e.g. 'canonical/<tenant_id>' (a file under CANONICAL_CREDENTIALS_DIR). A reference only: the secret itself never enters the database, source control or logs.", null=True),
          col("credential_sha256", "CHAR(64)", "SHA-256 of the credential value that was validated. brain-worker refuses to call Canonical when the loaded secret does not match it (stale or swapped secret). Not reversible to the secret.", null=True),
          col("credential_version", "INTEGER", "Incremented by trigger on every credential change (rotation counter).", default="0"),
          col("credential_validated_at", "TIMESTAMPTZ", "Server time of the last successful validation: a Canonical read made with this credential returned this tenant_id. Cleared by trigger when the credential changes without a new validation.", null=True),
          col("activated_at", "TIMESTAMPTZ", "Server time of the last move to active (set by trigger).", null=True),
          col("suspended_at", "TIMESTAMPTZ", "Server time of the last move to suspended (set by trigger).", null=True),
          col("provisioned_by", "TEXT", "Operator id that ran the provisioning command (audit; no secrets)."),
          CREATED(), UPDATED()],
    pk=["tenant_id"],
    checks=[("ck_tenant_registry__status", "status IN ('provisioning','active','suspended')"),
            ("ck_tenant_registry__label_len", "display_label IS NULL OR char_length(display_label) BETWEEN 1 AND 100"),
            ("ck_tenant_registry__reason_len", "status_reason IS NULL OR char_length(status_reason) <= 200"),
            ("ck_tenant_registry__credential_ref_format", "credential_ref IS NULL OR credential_ref ~ '^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_.-]*){0,4}$' AND char_length(credential_ref) <= 200"),
            ("ck_tenant_registry__credential_version", "credential_version >= 0"),
            ("ck_tenant_registry__validated_needs_credential", "credential_validated_at IS NULL OR (credential_ref IS NOT NULL AND credential_sha256 IS NOT NULL)"),
            ("ck_tenant_registry__active_requirements", "status <> 'active' OR (credential_validated_at IS NOT NULL AND activated_at IS NOT NULL)"),
            ("ck_tenant_registry__suspended_requirements", "status <> 'suspended' OR (suspended_at IS NOT NULL AND status_reason IS NOT NULL)")],
    idxs=[Idx("ix_tenant_registry__status", ["status"], why="brain-worker lists active tenants at every scheduler tick.")],
    append_only="delete",
    custom_triggers=[GUARD_TENANT_REGISTRY],
    grants="S", worker_grants="S", provisioner_grants="SIU",
    writer="Provisioning command only (`brain-provision` login granted brain_provisioner, N-01): create, validate credential, activate, rotate, suspend. No runtime role can write it; nobody can delete a row.",
    readers="brain-worker (list active tenants, credential reference); brain-api (is the token's tenant active); ops.",
    tenancy="Keyed by `tenant_id`. RLS (N-02): `pol_tenant_isolation` limits brain-api, brain_provisioner, retention and read-only roles to the current tenant's row; `pol_worker_list_tenants` lets brain_worker read every row (it has to discover the tenants before it has a tenant context). The worker reads ids, status and credential references, never tenant business data.",
    timestamps="UTC TIMESTAMPTZ, all set by trigger from the database server clock.",
    access="Worker: `SELECT ... WHERE status = 'active'` once per scheduler tick. API: point read by the token's tenant (cacheable for a short time).",
    mutability="Mutable only through the provisioning command. Status moves: provisioning -> active, active <-> suspended, provisioning -> suspended. Insert as anything but provisioning is refused; activation needs a validated credential and an active rule_config row for each of: " + ", ".join(REQUIRED_RULE_SETS) + ". A credential change on an active tenant must carry a new validation in the same UPDATE.",
    retention="Permanent. Rows are never deleted (`trg_tenant_registry_forbid_delete`); a tenant that leaves is suspended.",
    recovery="Re-run the provisioning command for the tenant; it is idempotent.",
    migration="Added in migration 0007 (N-01) with the RLS policies (N-02). No migration inserts tenants: dev and test tenants come from the dev seed or the provisioning command.",
    example={"tenant_id": T, "display_label": "Demo pharmacy A", "status": "active", "credential_ref": "canonical/" + T, "credential_version": 1, "credential_validated_at": "2026-10-21T18:00:00Z", "activated_at": "2026-10-21T18:00:01Z", "provisioned_by": "ops:ibrahim"})

TABLES_TENANCY = [tenant_registry]
