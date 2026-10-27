"""BB-24 group 4 (database half): canonical_cache is keyed by tenant. Hand-written.

The cache reader itself (BB-07, `brain/canonical`) does not exist yet; its half of group 4 is listed in README.md.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from brain.db.session import unit_of_work
from harness import A, B, H, P, ctx, snapshot

GET = text("SELECT tenant_id, payload->>'name' FROM ingest.canonical_cache WHERE entity_type = 'product' AND entity_id = :e")


def test_same_cache_key_returns_each_tenant_its_own_payload(world, engine_for):
    for t in (A, B):
        with unit_of_work(engine_for("brain_app"), ctx(t)) as s:
            assert s.execute(GET, {"e": str(P)}).all() == [(t, f"product of {t}")]


def test_cache_upsert_from_a_never_touches_b(world, engine_for):
    before = snapshot(B)
    with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
        s.execute(text("INSERT INTO ingest.canonical_cache (tenant_id, entity_type, entity_id, schema_name, schema_version, payload, "
                       "payload_sha256) VALUES (:t, 'product', :e, 'canonical.Product', '1.0', '{\"name\": \"renamed\"}', :h) "
                       "ON CONFLICT (tenant_id, entity_type, entity_id) DO UPDATE SET payload = EXCLUDED.payload"),
                  {"t": A, "e": str(P), "h": H})
    with unit_of_work(engine_for("brain_app"), ctx(B)) as s:
        assert s.execute(GET, {"e": str(P)}).all() == [(B, f"product of {B}")]
    assert snapshot(B) == before


def test_writing_b_cache_key_from_a_is_refused(world, engine_for):
    before = snapshot(B)
    with pytest.raises(ProgrammingError, match="row-level security"):
        with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
            s.execute(text("INSERT INTO ingest.canonical_cache (tenant_id, entity_type, entity_id, schema_name, schema_version, payload, "
                           "payload_sha256) VALUES (:t, 'product', 'x-1', 'canonical.Product', '1.0', '{}', :h)"), {"t": B, "h": H})
    assert snapshot(B) == before
