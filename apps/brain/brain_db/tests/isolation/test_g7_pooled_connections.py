"""BB-24 group 7: pooled connections, through the real brain/db/session.py (D-47). Hand-written.

Two tenants alternating on one pool leave no tenant state behind, a connection without app.tenant_id sees zero rows and
writes nothing, and a connection left with a tenant (the forbidden session-level pattern) is discarded at checkout.
"""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from brain.db.session import unit_of_work
from harness import A, B, P, ctx

SALES = text("SELECT tenant_id FROM ingest.sales_fact")
PROBE = text("SELECT pg_backend_pid(), nullif(current_setting('app.tenant_id', true), ''), (SELECT count(*) FROM ingest.sales_fact)")


def test_without_a_tenant_context_nothing_is_read_or_written(two_tenants, engine_for):
    app, worker = engine_for("brain_app"), engine_for("brain_worker")
    with app.connect() as c:          # bypassing unit_of_work: no app.tenant_id at all
        assert c.execute(text("SELECT count(*) FROM ingest.sales_fact")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM agent.action_proposal")).scalar() == 0
        c.rollback()
    with worker.connect() as c:
        with pytest.raises(ProgrammingError, match="row-level security"):
            c.execute(text("INSERT INTO ingest.sales_fact (tenant_id, product_id, sales_date, units_sold, units_returned, net_units, "
                           "day_status, source_updated_at) VALUES (:t, :p, '2026-10-01', 1, 0, 1, 'closed', now())"), {"t": A, "p": P})
        c.rollback()


def test_context_ends_with_commit_and_rollback_on_the_same_pooled_connection(two_tenants, engine_for):
    eng = engine_for("brain_app", pool_size=1, max_overflow=0)
    with unit_of_work(eng, ctx(A)) as s:
        pid, tenant, n = s.execute(PROBE).one()
    assert tenant == str(A) and n == 1
    with eng.connect() as c:
        assert c.execute(PROBE).one() == (pid, None, 0)
        c.rollback()
    with pytest.raises(RuntimeError):
        with unit_of_work(eng, ctx(B)) as s:
            s.execute(PROBE)
            raise RuntimeError("simulated failure inside the unit of work")
    with eng.connect() as c:
        assert c.execute(PROBE).one() == (pid, None, 0)
        c.rollback()


def test_checkout_hook_discards_a_connection_left_with_a_tenant(two_tenants, engine_for):
    eng = engine_for("brain_app", pool_size=1, max_overflow=0)
    with eng.connect() as c:   # the forbidden anti-pattern, done on purpose: a session-level value survives commit
        c.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(B)})
        c.commit()
        poisoned = c.execute(text("SELECT pg_backend_pid()")).scalar()
        c.rollback()
    with unit_of_work(eng, ctx(A)) as s:
        pid, tenant, n = s.execute(PROBE).one()
    assert pid != poisoned and tenant == str(A) and n == 1
    with eng.connect() as c:
        assert c.execute(PROBE).one()[1:] == (None, 0)
        c.rollback()


def test_alternating_tenants_on_one_pooled_connection(two_tenants, engine_for):
    eng = engine_for("brain_app", pool_size=1, max_overflow=0)
    pids = set()
    for i in range(40):
        t = A if i % 2 == 0 else B
        with unit_of_work(eng, ctx(t)) as s:
            pid, tenant, _ = s.execute(PROBE).one()
            assert tenant == str(t) and {r[0] for r in s.execute(SALES)} == {t}
            pids.add(pid)
    assert len(pids) == 1


def test_threads_interleaving_tenants_on_a_shared_pool(two_tenants, engine_for):
    eng = engine_for("brain_worker", pool_size=4, max_overflow=0)
    errors = []

    def work(t):
        for _ in range(25):
            with unit_of_work(eng, ctx(t)) as s:
                seen = {r[0] for r in s.execute(SALES)}
            if seen != {t}:
                errors.append((t, seen))
    threads = [threading.Thread(target=work, args=(A if i % 2 == 0 else B,)) for i in range(8)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert not errors
