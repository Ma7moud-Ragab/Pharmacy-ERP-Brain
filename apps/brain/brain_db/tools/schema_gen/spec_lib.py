"""Single source of truth for the brain_db schema. DDL, SQLModel, column tables and ERDs are generated from this."""
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"
SCHEMAS = ["ingest", "feat", "intel", "agent", "audit"]

@dataclass
class Col:
    name: str
    typ: str
    desc: str = ""
    null: bool = False
    default: Optional[str] = None      # SQL expression
    jsonb: Optional[str] = None        # 'object' | 'array' -> auto CHECK
    identity: bool = False

@dataclass
class FK:
    name: str
    cols: list
    ref: str            # 'schema.table'
    ref_cols: list
    on_delete: str = "RESTRICT"
    rel: Optional[str] = None     # child->parent relationship attr name
    back: Optional[str] = None    # parent->children collection attr name
    note: str = ""

@dataclass
class Idx:
    name: str
    cols: list
    unique: bool = False
    where: Optional[str] = None
    why: str = ""

@dataclass
class Table:
    schema: str
    name: str
    cls: str                       # python class name
    purpose: str
    tier: str                      # R rebuildable | O operational | H history-bearing derived | A audit-critical
    scope: str                     # MVP | SHOULD | FUTURE
    cols: list
    pk: list
    uniques: list = field(default_factory=list)    # (name, [cols])
    fks: list = field(default_factory=list)
    checks: list = field(default_factory=list)     # (name, expr)
    idxs: list = field(default_factory=list)
    fk_target: bool = False        # auto UNIQUE (tenant_id, id)
    updated_at_trigger: bool = False
    guard_mutable: Optional[list] = None           # columns allowed to change (generic guard trigger)
    append_only: Optional[str] = None              # 'update' | 'update_delete'
    custom_triggers: list = field(default_factory=list)  # raw SQL strings
    grants: str = "SIU"            # app privileges (brain_app, brain-api)
    worker_grants: str = ""        # brain_worker privileges (D-45); "" = none
    worker_update_cols: Optional[list] = None      # column-level UPDATE for brain_worker instead of table-level
    provisioner_grants: str = ""   # brain_provisioner privileges (N-01 provisioning CLI); "" = none
    rls: bool = True               # tenant_isolation RLS policy on tenant_id (N-02); every tenant table keeps True
    purge: bool = False            # retention role gets DELETE
    writer: str = ""
    readers: str = ""
    timestamps: str = ""
    jsonb_note: str = "No JSONB columns."
    access: str = ""
    mutability: str = ""
    retention: str = ""
    recovery: str = ""
    migration: str = ""
    tenancy: str = ""
    example: dict = field(default_factory=dict)

    @property
    def qname(self): return f"{self.schema}.{self.name}"

def col(name, typ, desc="", null=False, default=None, jsonb=None, identity=False):
    return Col(name, typ, desc, null, default, jsonb, identity)

TENANT = lambda: col("tenant_id", "UUID", "Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job's tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.")
ID = lambda: col("id", "UUID", "Internal Brain surrogate key.", default="gen_random_uuid()")
CREATED = lambda: col("created_at", "TIMESTAMPTZ", "Row creation time (UTC).", default="now()")
UPDATED = lambda: col("updated_at", "TIMESTAMPTZ", "Last modification time (UTC); maintained by trigger.", default="now()")
TRACE = lambda null=True: col("trace_id", "CHAR(32)", "W3C trace-id (32 lowercase hex) linking the work to the originating request/job.", null=null)
ROWV = lambda: col("row_version", "INTEGER", "Optimistic-concurrency counter; incremented on every UPDATE by the application.", default="1")

TENANCY_STD = "`tenant_id` NOT NULL with no default on every row; every query, update and delete is `WHERE tenant_id = :tenant_id` taken from the verified tenant context. Constraints and FKs include `tenant_id`. Multi-tenancy is a core requirement (D-34). Second wall (N-02, migration 0007): `FORCE ROW LEVEL SECURITY` with policy `pol_tenant_isolation` (`tenant_id = public.brain_current_tenant()`, the transaction-local `app.tenant_id`); without a tenant context the table reads as empty and rejects writes."
