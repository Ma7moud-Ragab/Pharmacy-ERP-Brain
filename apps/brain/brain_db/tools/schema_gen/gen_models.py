import re
from gen_core import *

def sa_type(typ):
    if typ == "UUID": return "PG_UUID(as_uuid=True)"
    if typ == "TEXT": return "Text"
    m = re.fullmatch(r"CHAR\((\d+)\)", typ)
    if m: return f"CHAR({m.group(1)})"
    if typ == "TIMESTAMPTZ": return "DateTime(timezone=True)"
    if typ == "DATE": return "Date"
    m = re.fullmatch(r"NUMERIC\((\d+),(\d+)\)", typ)
    if m: return f"Numeric({m.group(1)}, {m.group(2)})"
    if typ == "INTEGER": return "Integer"
    if typ == "SMALLINT": return "SmallInteger"
    if typ == "BIGINT": return "BigInteger"
    if typ == "BOOLEAN": return "Boolean"
    if typ == "JSONB": return "JSONB"
    if typ == "TEXT[]": return "ARRAY(Text)"
    raise ValueError(typ)

def py_type(c):
    typ = c.typ
    if typ == "UUID": return "uuid.UUID"
    if typ in ("TEXT",) or typ.startswith("CHAR"): return "str"
    if typ == "TIMESTAMPTZ": return "datetime"
    if typ == "DATE": return "date"
    if typ.startswith("NUMERIC"): return "Decimal"
    if typ in ("INTEGER", "SMALLINT", "BIGINT"): return "int"
    if typ == "BOOLEAN": return "bool"
    if typ == "JSONB": return "List[Any]" if c.jsonb == "array" else ("Dict[str, Any]" if c.jsonb == "object" else "Any")
    if typ == "TEXT[]": return "List[str]"
    raise ValueError(typ)

def q(s): return json.dumps(s)  # double-quoted python string literal

def model_class(t):
    pk = set(t.pk)
    args = []
    args.append(f"        PrimaryKeyConstraint({', '.join(q(c) for c in t.pk)}, name={q('pk_' + t.name)}),")
    for n, cols in auto_uniques(t):
        args.append(f"        UniqueConstraint({', '.join(q(c) for c in cols)}, name={q(n)}),")
    for n, e in auto_checks(t):
        args.append(f"        CheckConstraint({q(e)}, name={q(n)}),")
    for fk in t.fks:
        refs = [f"{fk.ref}.{c}" for c in fk.ref_cols]
        args.append(f"        ForeignKeyConstraint([{', '.join(q(c) for c in fk.cols)}], [{', '.join(q(r) for r in refs)}], name={q(fk.name)}, ondelete={q(fk.on_delete)}),")
    for i in t.idxs:
        w = f", postgresql_where=text({q(i.where)})" if i.where else ""
        u = ", unique=True" if i.unique else ""
        args.append(f"        Index({q(i.name)}, {', '.join(q(c) for c in i.cols)}{u}{w}),")
    args.append(f"        {{\"schema\": {q(t.schema)}, \"comment\": {q(comment_text(t.purpose))}}},")
    L = [f"class {t.cls}(BrainBase, table=True):", f'    """{t.qname}: {t.purpose.split(". ")[0].rstrip(".")}."""', "",
         f"    __tablename__ = {q(t.name)}", "    __table_args__ = (", *args, "    )", ""]
    for c in t.cols:
        optional = c.null or c.default is not None or c.identity
        base = py_type(c)
        ann = f"Optional[{base}]" if optional else base
        colargs = [q(c.name), sa_type(c.typ)]
        if c.identity: colargs.append("Identity(always=True)")
        if c.name in pk: colargs.append("primary_key=True")
        colargs.append(f"nullable={'True' if c.null else 'False'}" if c.name not in pk else "nullable=False")
        if c.default is not None: colargs.append(f"server_default=text({q(c.default)})")
        if c.desc: colargs.append(f"comment={q(comment_text(c.desc))}")
        dflt = "default=None, " if optional else ""
        L.append(f"    {c.name}: {ann} = Field({dflt}sa_column=Column({', '.join(colargs)}))")
    rels = []
    for fk in t.fks:
        if fk.rel and fk.ref != t.qname:
            parent = BY_Q[fk.ref]
            rels.append(f'    {fk.rel}: Optional["{parent.cls}"] = Relationship(sa_relationship_kwargs=RO)')
    for other in ALL:
        if other.scope == "FUTURE": continue
        for fk in other.fks:
            if fk.back and fk.ref == t.qname and fk.ref != other.qname:
                rels.append(f'    {fk.back}: List["{other.cls}"] = Relationship(sa_relationship_kwargs=RO)')
    if rels:
        L.append(""); L.append("    # read-only convenience relationships (writes go through repositories)")
        L.extend(rels)
    return "\n".join(L)

HEADER = '''"""brain_db SQLModel models (generated from the same schema definition as the DDL).

* One metadata, five PostgreSQL schemas: ingest, feat, intel, agent, audit.
* Constraint/index names match ddl/*.sql exactly so `alembic check` can detect drift.
* Relationships are viewonly + lazy="raise": always load explicitly (selectinload) and write via repositories.
* Business logic does NOT live here. JSONB payload shapes live in contracts_jsonb.py (Pydantic).
* The DDL files are the authoritative migration source; triggers, grants and roles exist only there. Table and column
  comments are repeated here from the same definition so `alembic check` compares them (B6).

Not executed by the author - run `alembic upgrade head` + `alembic check` in a scratch database first.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKeyConstraint,
    Identity, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, UUID as PG_UUID
from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel

# keyword arguments shared by all relationships
RO = {"viewonly": True, "lazy": "raise"}


class BrainBase(SQLModel):
    """Shared base. Pydantic v2 reserves the `model_` prefix; columns such as model_id / model_version / model_family
    are deliberate (the source says `model_version`), so the protected-namespace check is disabled."""

    model_config = ConfigDict(protected_namespaces=())

DEFAULT_TENANT_ID = uuid.UUID("%s")  # MVP single seeded tenant (OD-23)

''' % DEFAULT_TENANT

def build_models():
    parts = [HEADER]
    for t in ALL:
        parts.append("\n\n" + model_class(t))
    allnames = ", ".join(q(t.cls) for t in ALL)
    parts.append(f"\n\n__all__ = [{allnames}, \"DEFAULT_TENANT_ID\"]\n")
    return "".join(parts)

if __name__ == "__main__":
    import ast
    src = build_models()
    ast.parse(src)
    print("models parse OK,", len(src.splitlines()), "lines")
