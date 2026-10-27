"""Regenerates ddl/, models.py, erd/ and docs/ from the schema definition (spec_*.py) and the doc templates (tpl/).
Reference tooling (see OD-24). Not executed against a database."""
import re
import ast, os, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("BRAIN_ROOT", HERE.parents[1] if HERE.name == "schema_gen" else "/mnt/user-data/outputs/brain_db_handoff"))
from gen_core import *
from gen_models import build_models
import gen_docs as gd

def main():
    errs = validate()
    assert not errs, errs
    for d in ["ddl", "python/brain/db", "erd", "docs"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    sql = build_sql()
    for k, v in sql.items():
        (ROOT / "ddl" / k).write_text(v)
    src = build_models(); ast.parse(src)
    (ROOT / "python/brain/db/models.py").write_text(src)
    erds = gd.build_erds()
    for k, v in erds.items():
        (ROOT / "erd" / k).write_text(v + "\n")

    n_trg = len(re.findall(r"CREATE (?:CONSTRAINT )?TRIGGER", sql["brain_db_mvp.sql"]))
    tabs = ALL
    stats = (f"{sum(1 for t in tabs if t.scope=='MVP')} mandatory tables, {sum(1 for t in tabs if t.scope=='SHOULD')} optional (SHOULD) table and "
             f"{len(TABLES_FUTURE)} future-only table, with {sum(len(t.cols) for t in tabs)} columns, {sum(len(t.fks) for t in tabs)} foreign keys, "
             f"{sum(len(auto_checks(t)) for t in tabs)} CHECK constraints, {sum(len(auto_uniques(t)) + sum(1 for i in t.idxs if i.unique) for t in tabs)} unique constraints/indexes, "
             f"{sum(1 for t in tabs for i in t.idxs if not i.unique)} secondary indexes, {n_trg} triggers and 3 projection views.")
    fd = next(t for t in tabs if t.name == "feature_daily")
    def block(tables): return "\n".join(gd.table_md(t) for t in tables)
    by = {t.name: t for t in tabs + TABLES_FUTURE}
    frags = {
        "STATS_SENTENCE": stats,
        "FEATURE_COLS": str(len(fd.cols)),
        "INVENTORY": gd.inventory_md(),
        "FKS": gd.fk_md(), "SOFT": gd.soft_md(),
        "TABLES_INGEST": block(TABLES_INGEST),
        "TABLES_INTEL": block(TABLES_INTEL),
        "TABLES_AGENT": block([by[n] for n in ["agent_session","agent_message","action_proposal","agent_action","action_approval","action_execution","llm_usage","audit_log"]]),
        "TABLES_FUTURE": block(TABLES_FUTURE),
        "TABLES_TENANCY": block(TABLES_TENANCY),
    }
    names = {"01": "01_architecture_traceability_conventions", "02": "02_table_specifications",
             "03": "03_lifecycle_security_performance_testing", "04": "04_migration_backlog_decisions_handoff"}
    for k, name in names.items():
        t = (HERE / "tpl" / f"{k}.md").read_text()
        def repl(m):
            key = m.group(1)
            if key.startswith("ERD:"):
                return (HERE.parent / "erd" / (key[4:] + ".mmd")).read_text().strip() if False else erds[key[4:] + ".mmd"].strip()
            return frags[key]
        out = re.sub(r"@@([A-Za-z_:]+)@@", repl, t)
        assert "@@" not in out, f"unresolved placeholder in {k}"
        (ROOT / "docs" / f"{name}.md").write_text(out)
    print("built into", ROOT)
    print(stats)

if __name__ == "__main__":
    main()
