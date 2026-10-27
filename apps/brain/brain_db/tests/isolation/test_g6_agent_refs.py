"""BB-24 group 6 (database half): A's proposals, decisions and executions cannot touch B's rows. Hand-written.

Not covered here (needs code that does not exist yet): that the ERP write uses tenant A's credential (BB-17/BB-18,
`brain/agent/execution.py` with the per-tenant CredentialProvider of BB-25).
"""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.db.session import unit_of_work
from harness import A, B, H, ctx, snapshot

TR = "0" * 32


@pytest.mark.parametrize("what, sql, expect", [
    ("proposal of A for B's recommendation",
     "INSERT INTO agent.action_proposal (tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, policy_version, "
     "reason, recommendation_id, idempotency_key, expires_at, trace_id) VALUES (:a, 'rules', 'create_purchase_order', '1.0', '{}', :h, "
     "'p', 'r', :b_rec, :k, now() + interval '1 hour', :tr)", "fk_action_proposal__recommendation"),
    ("decision of A on B's proposal",
     "INSERT INTO agent.action_approval (tenant_id, proposal_id, approval_round, decision, decided_by_actor_id, decider_scopes, "
     "arguments_sha256, trace_id) VALUES (:a, :b_prop, 1, 'approved', 'u-1', ARRAY['agent:approve'], :h, :tr)", "unknown proposal"),
    ("decision recorded in B's name from A's context",
     "INSERT INTO agent.action_approval (tenant_id, proposal_id, approval_round, decision, decided_by_actor_id, decider_scopes, "
     "arguments_sha256, trace_id) VALUES (:b, :b_prop, 1, 'approved', 'u-1', ARRAY['agent:approve'], :h, :tr)", ("unknown proposal", "row-level security")),
])
def test_agent_writes_of_a_cannot_reach_b(world, engine_for, what, sql, expect):
    before = snapshot(B)
    params = {"a": A, "b": B, "h": H, "tr": TR, "k": str(uuid4()), "b_rec": world[B]["recommendation"], "b_prop": world[B]["proposal"]}
    with pytest.raises(DBAPIError) as e:
        with unit_of_work(engine_for("brain_app"), ctx(A, actor="u-1")) as s:
            s.execute(text(sql), params)
    msgs = expect if isinstance(expect, tuple) else (expect,)
    assert any(m in str(e.value) for m in msgs), str(e.value)
    assert snapshot(B) == before


EXEC = text("INSERT INTO agent.action_execution (tenant_id, proposal_id, approval_id, attempt_no, arguments_sha256, idempotency_key, "
            "on_behalf_of_actor_id, trace_id) VALUES (:t, :p, :ap, 1, :h, :p, 'u-1', :tr)")


class Rollback(Exception):
    """Raised inside a unit of work to undo a row that was only written to prove it is accepted."""


@pytest.fixture(scope="module")
def executing(world, engine_for):
    """One proposal per tenant, approved by a human and moved to executing through the real path, so an execution row
    for it is valid in its own tenant. tenant -> {"p": proposal id, "ap": approval id}."""
    app, out = engine_for("brain_app"), {}
    for t in (A, B):
        p, ap = uuid4(), uuid4()
        with unit_of_work(app, ctx(t, actor="u-1")) as s:
            s.execute(text("INSERT INTO agent.action_proposal (id, tenant_id, proposed_by, tool_name, tool_version, arguments, "
                           "arguments_sha256, policy_version, reason, idempotency_key, expires_at, trace_id) VALUES (:p, :t, 'rules', "
                           "'create_purchase_order', '1.0', '{}', :h, 'static-policy@1', 'Stockout risk high', :p, "
                           "now() + interval '24 hours', :tr)"), {"p": p, "t": t, "h": H, "tr": TR})
            s.execute(text("INSERT INTO agent.action_approval (id, tenant_id, proposal_id, approval_round, decision, decided_by_actor_id, "
                           "decider_scopes, arguments_sha256, trace_id) VALUES (:ap, :t, :p, 1, 'approved', 'u-1', ARRAY['agent:approve'], "
                           ":h, :tr)"), {"ap": ap, "t": t, "p": p, "h": H, "tr": TR})
            s.execute(text("UPDATE agent.action_proposal SET status = 'approved' WHERE id = :p"), {"p": p})
            s.execute(text("UPDATE agent.action_proposal SET status = 'executing' WHERE id = :p"), {"p": p})
        out[t] = {"p": p, "ap": ap}
    return out


@pytest.mark.parametrize("claimed, approval_of, expect", [
    ("A", "B", "execution requires an approved decision"),      # B's proposal and B's valid approval, filed under tenant A
    ("A", "A", "execution requires the proposal to be executing"),  # A's valid approval pointed at B's executing proposal
    ("B", "B", "execution requires an approved decision"),      # B's own row, written from A's context
], ids=["a_tenant_with_bs_approval", "a_approval_on_bs_proposal", "b_tenant_from_a_context"])
def test_execution_of_a_cannot_hang_on_bs_proposal(executing, engine_for, claimed, approval_of, expect):
    """Differential test: the control proves the very same execution row is ACCEPTED for B in B's own context (and for A's
    own proposal in A's context), so the refusal from A's context can only come from the tenant boundary."""
    app, tenant = engine_for("brain_app"), {"A": A, "B": B}
    row = {"p": executing[B]["p"], "ap": executing[tenant[approval_of]]["ap"], "h": H, "tr": TR}
    own = {"t": tenant[approval_of], "p": executing[tenant[approval_of]]["p"], "ap": row["ap"], "h": H, "tr": TR}
    with pytest.raises(Rollback):   # control: that approval executes its own tenant's proposal
        with unit_of_work(app, ctx(tenant[approval_of], actor="u-1")) as s:
            assert s.execute(EXEC, own).rowcount == 1
            raise Rollback
    before = snapshot(B)
    with pytest.raises(DBAPIError) as e:
        with unit_of_work(app, ctx(A, actor="u-1")) as s:
            s.execute(EXEC, {**row, "t": tenant[claimed]})
    assert expect in str(e.value), str(e.value)
    assert snapshot(B) == before


def test_bs_proposal_is_invisible_and_unchangeable_from_a(world, engine_for):
    before = snapshot(B)
    with unit_of_work(engine_for("brain_app"), ctx(A, actor="u-1")) as s:
        assert s.execute(text("SELECT count(*) FROM agent.action_proposal WHERE id = :p"), {"p": world[B]["proposal"]}).scalar() == 0
        assert s.execute(text("UPDATE agent.action_proposal SET status = 'cancelled' WHERE id = :p"), {"p": world[B]["proposal"]}).rowcount == 0
    with unit_of_work(engine_for("brain_app"), ctx(B, actor="u-1")) as s:
        assert s.execute(text("SELECT status FROM agent.action_proposal WHERE id = :p"), {"p": world[B]["proposal"]}).scalar() == "pending"
    assert snapshot(B) == before
