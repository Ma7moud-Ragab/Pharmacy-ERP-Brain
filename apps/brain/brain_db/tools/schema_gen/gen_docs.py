import json, re
from gen_core import *

TIER = {"R": "R - rebuildable", "O": "O - operational state", "H": "H - history-bearing derived", "A": "A - audit-critical"}

def esc_md(s): return s.replace("|", "\\|")

def key_tags(t, c):
    tags = []
    if c.name in t.pk: tags.append("PK")
    for fk in t.fks:
        if c.name in fk.cols and c.name != "tenant_id":
            tags.append(f"FK&rarr;{fk.ref.split('.')[1]}")
    for n, cols in auto_uniques(t):
        if cols == [c.name]: tags.append("UQ")
    return ", ".join(dict.fromkeys(tags))

def table_md(t):
    L = [f"#### `{t.qname}` - {t.cls}", ""]
    L.append(f"**Scope:** {t.scope} &nbsp;|&nbsp; **Durability tier:** {TIER[t.tier]} &nbsp;|&nbsp; **Class:** `{t.cls}`")
    L.append("")
    L.append("| # | Item | Specification |"); L.append("|---|---|---|")
    L.append(f"| 1 | Table / schema | `{t.name}` in schema `{t.schema}` |")
    L.append(f"| 2 | Purpose & ownership | {esc_md(t.purpose)} |")
    L.append(f"| 3 | Writers / readers | **Writes:** {esc_md(t.writer)} **Reads:** {esc_md(t.readers)} |")
    L.append(f"| 4 | Primary key | `pk_{t.name}` ({', '.join(t.pk)}) |")
    fks = "<br>".join(f"`{f.name}`: ({', '.join(f.cols)}) &rarr; `{f.ref}` ({', '.join(f.ref_cols)}) ON DELETE {f.on_delete}" + (f" - {esc_md(f.note)}" if f.note else "") for f in t.fks) or "None (external references only)"
    L.append(f"| 5 | Foreign keys | {fks} |")
    uq = "<br>".join(f"`{n}` ({', '.join(c)})" for n, c in auto_uniques(t)) + "".join(f"<br>`{i.name}` ({', '.join(i.cols)}) WHERE {esc_md(i.where) if i.where else 'true'}" for i in t.idxs if i.unique)
    L.append(f"| 6 | Unique constraints | {uq or 'None beyond the PK'} |")
    L.append(f"| 7 | Check constraints | {len(auto_checks(t))} (listed below) |")
    ix = "<br>".join(f"`{i.name}` ({', '.join(i.cols)}){' WHERE ' + esc_md(i.where) if i.where else ''}{' [unique]' if i.unique else ''}" for i in t.idxs if not i.unique) or "None beyond PK/unique constraints"
    L.append(f"| 8 | Indexes | {ix} |")
    L.append(f"| 9 | Tenant isolation | {esc_md(t.tenancy)} |")
    L.append(f"| 10 | Timestamp semantics | {esc_md(t.timestamps)} |")
    L.append(f"| 11 | JSONB usage | {esc_md(t.jsonb_note)} |")
    L.append(f"| 12 | Access patterns | {esc_md(t.access)} |")
    L.append(f"| 13 | Mutability | {esc_md(t.mutability)} |")
    L.append(f"| 14 | Retention / deletion | {esc_md(t.retention)} |")
    L.append(f"| 15 | Recovery / backfill | {esc_md(t.recovery)} |")
    L.append(f"| 16 | Migration notes | {esc_md(t.migration)} |")
    trg = [x.split()[2] for x in std_triggers(t)]
    L.append(f"| - | Triggers | {', '.join('`'+x+'`' for x in trg) or 'none'}{' + custom guard function' if t.custom_triggers else ''} |")
    wk = (t.worker_grants.replace("U", "") + f" + UPDATE({', '.join(t.worker_update_cols)})") if t.worker_update_cols else (t.worker_grants or "none")
    L.append(f"| - | App privileges | brain_app: {t.grants}; brain_worker: {wk}; retention role DELETE: {'yes' if t.purge else 'no'} |")
    L.append("")
    L.append("**Columns**"); L.append("")
    L.append("| Column | PostgreSQL type | Nullable | Default | PK/FK/Unique | Description |"); L.append("|---|---|---|---|---|---|")
    for c in t.cols:
        typ = c.typ + (" (identity)" if c.identity else "")
        dflt = f"`{esc_md(c.default)}`" if c.default is not None else ""
        L.append(f"| `{c.name}` | `{typ}` | {'yes' if c.null else 'no'} | {dflt} | {key_tags(t, c)} | {esc_md(c.desc)} |")
    L.append("")
    L.append("**Check constraints**"); L.append("")
    for n, e in auto_checks(t):
        L.append(f"- `{n}`: `{e}`")
    L.append("")
    L.append("**Indexes - rationale**"); L.append("")
    for i in t.idxs:
        L.append(f"- `{i.name}` - {i.why}")
    if not t.idxs: L.append("- (only the PK / unique-constraint indexes)")
    L.append("")
    L.append("**Example record** (illustrative values only)"); L.append("")
    L.append("```json"); L.append(json.dumps(t.example, indent=2, default=str)); L.append("```"); L.append("")
    return "\n".join(L)

def inventory_md():
    L = ["| Schema.table | Scope | Tier | Purpose | Written by |", "|---|---|---|---|---|"]
    for t in ALL + TABLES_FUTURE:
        first = t.purpose.split(". ")[0].rstrip(".") + "."
        w = t.writer.split(" - ")[0].split(". ")[0].rstrip(".")
        L.append(f"| `{t.qname}` | {t.scope} | {t.tier} | {esc_md(first)} | {esc_md(w)} |")
    return "\n".join(L)

def fk_md():
    L = ["| Child | FK constraint | Child columns | Parent | Parent columns | Cardinality | ON DELETE | Note |", "|---|---|---|---|---|---|---|---|"]
    for t in ALL:
        for f in t.fks:
            nullable = all(next(c for c in t.cols if c.name == x).null for x in f.cols if x != "tenant_id")
            card = "parent 0..1 : child 0..n" if nullable else "parent 1 : child 0..n"
            L.append(f"| `{t.qname}` | `{f.name}` | {', '.join(f.cols)} | `{f.ref}` | {', '.join(f.ref_cols)} | {card} | {f.on_delete} | {esc_md(f.note)} |")
    return "\n".join(L)

SOFT = [
 ("every table", "tenant_id", "ERP Identity (external)", "JWT claim / event envelope; allow-list in MVP", "no FK - contract + app-level validation"),
 ("sales_fact, feature_daily, forecast, model_registry, anomaly_event, risk_assessment, recommendation", "product_id", "Canonical Product (ERP)", "Canonical contract; existence checked lazily via canonical_cache", "no FK - external identifier (OD-02)"),
 ("risk_assessment, recommendation", "supplier_id", "Canonical Supplier (ERP)", "canonical_cache(entity_type='supplier')", "no FK - external identifier (OD-04)"),
 ("canonical_cache", "entity_id", "Canonical entity id", "Canonical API", "no FK - cache key"),
 ("feature_daily", "(tenant, product, feature_date)", "sales_fact (tenant, product, sales_date)", "Feature pipeline; tests T-FEAT-01, T-FEAT-02", "logical only - feature rows exist for zero/missing/future days with no sales_fact row"),
 ("feature_daily", "feature_date", "calendar_day.calendar_date", "Feature pipeline", "logical (copied attributes)"),
 ("feature_daily", "y_status", "sales_day_coverage.status", "Feature pipeline", "logical (zero vs missing rule)"),
 ("agent_message, agent_action, briefing", "llm_usage_id", "audit.llm_usage.id", "Application", "soft reference: usage rows outlive messages; no FK"),
 ("llm_usage", "session_id", "agent.agent_session.id", "Application", "soft reference: audit rows outlive sessions; no FK"),
 ("audit_log", "subject_type + subject_id", "any Brain object", "Audit writer vocabulary", "soft polymorphic reference; audit must outlive subjects"),
 ("agent_action", "turn_index", "agent_message.turn_index", "Application", "soft reference: messages expire"),
]
def soft_md():
    L = ["| Table(s) | Column | Refers to | Validated by | Integrity |", "|---|---|---|---|---|"]
    for r in SOFT: L.append("| " + " | ".join(esc_md(x) for x in r) + " |")
    return "\n".join(L)

# ---------- Mermaid -----------------------------------------------------------------
MT = {"UUID": "uuid", "TEXT": "text", "TIMESTAMPTZ": "timestamptz", "DATE": "date", "INTEGER": "int", "SMALLINT": "smallint", "BIGINT": "bigint", "BOOLEAN": "bool", "JSONB": "jsonb", "TEXT[]": "text_array"}
def mtype(typ):
    if typ in MT: return MT[typ]
    if typ.startswith("CHAR"): return "char"
    if typ.startswith("NUMERIC"): return "numeric"
    if typ.startswith("VECTOR"): return "vector"
    raise ValueError(typ)

def entity(t, full=True):
    fkcols = {c for f in t.fks for c in f.cols if c != "tenant_id"}
    L = [f"    {t.name} {{"]
    for c in t.cols:
        if not full and c.name not in t.pk and c.name not in fkcols: continue
        if not full and c.name == "tenant_id" and c.name not in t.pk: continue
        keys = []
        if c.name in t.pk: keys.append("PK")
        if c.name in fkcols: keys.append("FK")
        if not keys and any(cols == [c.name] for _, cols in auto_uniques(t)): keys.append("UK")
        L.append(f"        {mtype(c.typ)} {c.name}" + (f" {', '.join(keys)}" if keys else ""))
    L.append("    }")
    return "\n".join(L)

def rel_lines(names):
    L = []
    for t in ALL:
        if t.name not in names: continue
        for f in t.fks:
            p = BY_Q[f.ref]
            if p.name not in names: continue
            nullable = all(next(c for c in t.cols if c.name == x).null for x in f.cols if x != "tenant_id")
            left = "|o" if nullable else "||"
            label = (f.rel or f.name.replace(f"fk_{t.name}__", ""))
            L.append(f'    {p.name} {left}--o{{ {t.name} : "{label}"')
    return L

def erd(title_names, full_names, extra_logical=(), keys_only=()):
    names = set(full_names) | set(keys_only)
    L = ["erDiagram"]
    for t in ALL:
        if t.name in full_names: L.append(entity(t, True))
    for t in ALL:
        if t.name in keys_only: L.append(entity(t, False))
    L.extend(rel_lines(names))
    for a, b, lab in extra_logical:
        L.append(f'    {a} ||..o{{ {b} : "{lab}"')
    return "\n".join(L)

N = lambda lst: [t.name for t in lst]
G1 = ["sync_checkpoint","ingest_failure","canonical_cache","sales_fact","sales_day_coverage","calendar_day","feature_daily"]
G2 = ["rule_config","training_run","model_registry","model_evaluation","forecast","forecast_point","anomaly_event","risk_assessment","recommendation"]
G3 = ["agent_session","agent_message","agent_action","action_proposal","action_approval","action_execution","llm_usage","audit_log"]

CONCEPTUAL = '''erDiagram
    ERP_CANONICAL_API ||--o{ INGESTION_STATE : "polled daily totals (watermark)"
    ERP_CANONICAL_API ||--o{ CANONICAL_CACHE : "validated payloads"
    INGESTION_STATE ||--o{ SALES_FACT : "absolute upsert by product+date"
    SALES_FACT ||--o{ FEATURE_ROW : "feeds"
    CALENDAR ||--o{ FEATURE_ROW : "calendar features"
    TRAINING_RUN ||--o{ MODEL : "produces"
    MODEL ||--o{ FORECAST : "generates"
    FEATURE_ROW ||--o{ FORECAST : "inputs"
    FORECAST ||--o{ ANOMALY_EVENT : "expected value"
    FORECAST ||--o{ RISK_ASSESSMENT : "demand over lead time"
    CANONICAL_CACHE ||--o{ RISK_ASSESSMENT : "inventory and lead time inputs"
    ANOMALY_EVENT |o--o{ RISK_ASSESSMENT : "may escalate"
    RULE_CONFIG ||--o{ RISK_ASSESSMENT : "parameters used"
    RISK_ASSESSMENT ||--o{ RECOMMENDATION : "answered by"
    AGENT_SESSION ||--o{ AGENT_MESSAGE : "turns"
    AGENT_SESSION ||--o{ TOOL_CALL : "tool calls"
    AGENT_SESSION ||--o{ ACTION_PROPOSAL : "write proposals"
    RECOMMENDATION |o--o{ ACTION_PROPOSAL : "source of"
    ACTION_PROPOSAL ||--o{ APPROVAL : "human decision"
    APPROVAL ||--o{ EXECUTION : "authorises"
    ACTION_PROPOSAL ||--o{ EXECUTION : "attempts"
    ACTION_PROPOSAL ||..o{ AUDIT_LOG : "audited"
    LLM_USAGE ||..o{ AUDIT_LOG : "same trace"'''

def build_erds():
    mvp = [t.name for t in ALL]
    master_logical = [("sales_fact", "feature_daily", "logical product+date"), ("calendar_day", "feature_daily", "logical date"),
                      ("sales_day_coverage", "feature_daily", "logical zero vs missing"), ("llm_usage", "agent_action", "soft ref"),
                      ("llm_usage", "agent_message", "soft ref"), ("agent_session", "llm_usage", "soft ref")]
    out = {}
    out["erd_conceptual.mmd"] = CONCEPTUAL
    out["erd_logical_master.mmd"] = erd(None, mvp, master_logical)
    out["erd_ingestion_features.mmd"] = erd(None, G1, [("sales_fact", "feature_daily", "logical product+date"), ("calendar_day", "feature_daily", "logical date"), ("sales_day_coverage", "feature_daily", "logical zero vs missing")])
    out["erd_forecast_risk.mmd"] = erd(None, G2, [("feature_daily", "forecast", "logical inputs"), ("canonical_cache", "risk_assessment", "logical inputs")], keys_only=["feature_daily", "canonical_cache"])
    out["erd_agent_audit.mmd"] = erd(None, G3, [("llm_usage", "agent_action", "soft ref"), ("llm_usage", "agent_message", "soft ref"), ("agent_session", "llm_usage", "soft ref"), ("action_proposal", "audit_log", "soft ref subject")], keys_only=["recommendation", "risk_assessment"])
    return out

def stats():
    cols = sum(len(t.cols) for t in ALL if t.scope == "MVP")
    return dict(mvp=sum(1 for t in ALL if t.scope=="MVP"), should=sum(1 for t in ALL if t.scope=="SHOULD"), future=len(TABLES_FUTURE),
        cols=cols, fks=sum(len(t.fks) for t in ALL), checks=sum(len(auto_checks(t)) for t in ALL),
        idx=sum(len(t.idxs) for t in ALL), uq=sum(len(auto_uniques(t)) for t in ALL))

if __name__ == "__main__":
    import os
    os.makedirs("out", exist_ok=True)
    for k, v in build_erds().items(): open(f"out/{k}", "w").write(v + "\n")
    print(stats())
