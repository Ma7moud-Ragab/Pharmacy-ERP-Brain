"""Lifecycle checks for agent.action_proposal (BB-05G, guard_proposal_transition). Hand-written, not generated.

Usage: build an EMPTY scratch database as the migration owner (`alembic upgrade head` or brain_db_mvp.sql; D-50), then
    python proposal_transition_checks.py <dbname>
Connection: BB_OWNER_DSN, the migration owner (never a superuser; see bbsetup.py). Needs psycopg 3. Exits non-zero if any
check fails. FORCE RLS binds the owner, so every transaction runs in the context of the tenant it writes: tenant 2 for
statements that name tenant 2, tenant 1 otherwise (TenantDB below).
Each case uses its own proposal, so the cases do not depend on each other. Refusals are matched on the error text,
so a case only passes when the expected guard fired (not just any error).
"""
import os, sys, threading, time, uuid
from contextlib import contextmanager
import psycopg
import bbsetup

DB = sys.argv[1]
T = "00000000-0000-0000-0000-000000000001"; T2 = "00000000-0000-0000-0000-000000000002"
P = "b3f1c2a0-4e51-4a2e-9d3e-000000000001"
H = "d67ad9758d7806f685b4294e16a538f84157456e2de40b23aa5ca9c6993b57ce"
TRACE = "0" * 32
ARGS = '{"supplier_id":"c0ffee00-0000-4000-8000-000000000001","lines":[{"product_id":"%s","quantity":110}]}' % P


def connect():
    return bbsetup.owner(DB)


def tenant_of(*stmts):
    return T2 if any(T2 in s for s in stmts) else T


class TenantDB:
    """The owner connection; every statement outside an explicit transaction gets its own one-statement transaction,
    and every transaction starts with the transaction-local tenant context (D-47)."""

    def __init__(self, conn):
        self.c, self.depth = conn, 0

    @contextmanager
    def transaction(self, tenant=T):
        with self.c.transaction():
            if self.depth == 0:
                bbsetup.set_tenant(self.c, tenant)
            self.depth += 1
            try:
                yield self
            finally:
                self.depth -= 1

    def execute(self, sql):
        if self.depth:
            return self.c.execute(sql)
        with self.transaction(tenant_of(sql)):
            return self.c.execute(sql)


db = TenantDB(connect())
res = []


def report(name, passed, detail=""):
    res.append(passed)
    print(("PASS" if passed else "FAIL"), name, "" if passed else detail[:300])


def ok(name, *stmts):
    """All statements run in one transaction and must succeed."""
    try:
        with db.transaction(tenant_of(*stmts)):
            for s in stmts:
                db.execute(s)
        report(name, True)
    except psycopg.Error as e:
        report(name, False, str(e))


def refused(name, expect_msg, *stmts):
    """The transaction must fail, and the error must contain expect_msg (proves which guard fired)."""
    try:
        with db.transaction(tenant_of(*stmts)):
            for s in stmts:
                db.execute(s)
        report(name, False, "statement was accepted")
    except psycopg.Error as e:
        report(name, expect_msg in str(e), f"wrong error: {e}")


def proposal(expires="now() + interval '24 hours'", created="now()", rec="NULL", tenant=T):
    pid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO agent.action_proposal(id,tenant_id,proposed_by,tool_name,tool_version,arguments,arguments_sha256,"
        "policy_version,reason,recommendation_id,idempotency_key,created_at,expires_at,trace_id) "
        f"VALUES ('{pid}','{tenant}','rules','create_purchase_order','1.0','{ARGS}','{H}','static-policy@1','Stockout risk high',"
        f"{rec},'{pid}',{created},{expires},'{TRACE}')")
    return pid


def approval(pid, decision, rnd=1, tenant=T, scopes="ARRAY['agent:approve']", sha=H):
    aid = str(uuid.uuid4())
    return aid, (f"INSERT INTO agent.action_approval(id,tenant_id,proposal_id,approval_round,decision,decided_by_actor_id,decider_scopes,"
                 f"arguments_sha256,trace_id) VALUES ('{aid}','{tenant}','{pid}',{rnd},'{decision}','u-1',{scopes},'{sha}','{TRACE}')")


def status(pid, s):
    return f"UPDATE agent.action_proposal SET status='{s}' WHERE id='{pid}'"


def execution(pid, aid, attempt):
    eid = str(uuid.uuid4())
    return eid, (f"INSERT INTO agent.action_execution(id,tenant_id,proposal_id,approval_id,attempt_no,arguments_sha256,idempotency_key,"
                 f"on_behalf_of_actor_id,trace_id) VALUES ('{eid}','{T}','{pid}','{aid}',{attempt},'{H}','{pid}','u-1','{TRACE}')")


def fail_exec(eid, certainty):
    return (f"UPDATE agent.action_execution SET status='failed', outcome_certainty='{certainty}', error_code='timeout', "
            f"completed_at=now() WHERE id='{eid}'")


def to_executing(pid):
    """pending -> approved -> executing with one approved round-1 decision. Returns the approval id."""
    aid, a = approval(pid, "approved")
    with db.transaction():
        db.execute(a); db.execute(status(pid, "approved"))
    db.execute(status(pid, "executing"))
    return aid


def current(pid):
    return db.execute(f"SELECT status FROM agent.action_proposal WHERE id='{pid}'").fetchone()[0]


# ---------- 1. Transition table (Answers/02 section 7) ----------
p1 = proposal(); _, a1 = approval(p1, "approved")
ok("#1 pending -> approved with an 'approved' decision", a1, status(p1, "approved"))
ok("#2 approved -> executing (latest decision 'approved')", status(p1, "executing"))
ok("#3 executing -> succeeded", status(p1, "succeeded"))

p4 = proposal(); _, a4 = approval(p4, "rejected")
ok("#4 pending -> rejected with a 'rejected' decision", a4, status(p4, "rejected"))

p5 = proposal()
refused("#5 pending -> approved without a decision record", "requires a decision record", status(p5, "approved"))

p6 = proposal(); _, a6 = approval(p6, "rejected")
refused("#6 pending -> approved with a 'rejected' decision (the line that did not compile)",
        "requires a matching decision record", a6, status(p6, "approved"))
p6b = proposal(); _, a6b = approval(p6b, "approved")
refused("#6b pending -> rejected with an 'approved' decision", "requires a matching decision record", a6b, status(p6b, "rejected"))

p7 = proposal()
refused("#7 pending -> succeeded is illegal", "illegal action_proposal transition pending -> succeeded", status(p7, "succeeded"))
refused("#8 succeeded -> pending is illegal (final state)", "illegal action_proposal transition succeeded -> pending", status(p1, "pending"))
refused("#8b rejected -> approved is illegal (final state)", "illegal action_proposal transition rejected -> approved", status(p4, "approved"))

p9 = proposal(created="now() - interval '2 days'", expires="now() - interval '1 day'"); _, a9 = approval(p9, "approved")
refused("#9 expired proposal: approval insert refused by guard_approval_insert", "proposal expired at", a9)
refused("#9 expired proposal: status update without decision refused", "requires a decision record", status(p9, "approved"))

# 9c reaches the expiry branch of guard_proposal_transition itself: the decision is recorded before the deadline,
# the status change is attempted after it.
p9c = proposal(expires="clock_timestamp() + interval '2 seconds'"); _, a9c = approval(p9c, "approved")
db.execute(a9c); time.sleep(2.5)
refused("#9c approved decision recorded in time, status change after expires_at", "proposal expired at", status(p9c, "approved"))

p10 = proposal(); a10 = to_executing(p10); e10, x10 = execution(p10, a10, 1)
ok("#10 attempt 1 fails with unknown outcome; proposal executing -> failed", x10, fail_exec(e10, "unknown"), status(p10, "failed"))
_, r10 = approval(p10, "approved", rnd=2)
ok("#10 failed -> approved after an unknown outcome (round-2 decision)", r10, status(p10, "approved"))

p11 = proposal(); a11 = to_executing(p11); e11, x11 = execution(p11, a11, 1)
ok("#11 attempt fails definitively; executing -> failed", x11, fail_exec(e11, "definitive"), status(p11, "failed"))
_, r11 = approval(p11, "approved", rnd=2)
refused("#11 failed -> approved after a definitive failure", "re-approval is only allowed after an attempt with unknown outcome",
        r11, status(p11, "approved"))

# 11b: only the LATEST attempt counts. Attempt 1 unknown, attempt 2 definitive -> no further re-approval.
p11b = proposal(); a11b = to_executing(p11b); e1, x1 = execution(p11b, a11b, 1)
with db.transaction():
    db.execute(x1); db.execute(fail_exec(e1, "unknown")); db.execute(status(p11b, "failed"))
r2id, r2 = approval(p11b, "approved", rnd=2)
with db.transaction():
    db.execute(r2); db.execute(status(p11b, "approved"))
db.execute(status(p11b, "executing")); e2, x2 = execution(p11b, r2id, 2)
with db.transaction():
    db.execute(x2); db.execute(fail_exec(e2, "definitive")); db.execute(status(p11b, "failed"))
refused("#11b failed -> approved when an earlier attempt was unknown but the latest was definitive",
        "re-approval is only allowed after an attempt with unknown outcome", status(p11b, "approved"))

p12 = proposal()
ok("#12 pending -> expired needs no decision record", status(p12, "expired"))

# ---------- 2. Other lifecycle rules ----------
p13 = proposal()
ok("same-status update is a no-op and allowed", status(p13, "pending"))
ok("pending -> cancelled needs no decision record", status(p13, "cancelled"))
p14 = proposal(); to_executing(p14)
refused("executing -> approved is illegal", "illegal action_proposal transition executing -> approved", status(p14, "approved"))
p15 = proposal()
before = db.execute(f"SELECT status_changed_at FROM agent.action_proposal WHERE id='{p15}'").fetchone()[0]
db.execute(status(p15, "expired"))
after = db.execute(f"SELECT status_changed_at FROM agent.action_proposal WHERE id='{p15}'").fetchone()[0]
report("status_changed_at is set by the trigger on a real transition", after > before, f"{before} -> {after}")
refused("arguments are immutable", "immutable column changed on agent.action_proposal", f"UPDATE agent.action_proposal SET arguments='{{}}' WHERE id='{p15}'")
refused("DELETE of a proposal is forbidden", "DELETE on agent.action_proposal is not allowed", f"DELETE FROM agent.action_proposal WHERE id='{p15}'")

# ---------- 3. Approval and execution safeguards ----------
p16 = proposal()
refused("approval without scope agent:approve", "ck_action_approval__scope", approval(p16, "approved", scopes="ARRAY['inventory:read']")[1])
refused("approval bound to a different payload hash", "fk_action_approval__action_proposal", approval(p16, "approved", sha="f" * 64)[1])
refused("tenant 2 cannot record a decision on tenant 1's proposal", "unknown proposal", approval(p16, "approved", tenant=T2)[1])
refused("round-2 decision while not failed", "re-approval requires status failed", approval(p16, "approved", rnd=2)[1])
a16id, a16 = approval(p16, "approved"); db.execute(a16)
refused("decision rows are immutable (UPDATE)", "UPDATE on agent.action_approval is not allowed", f"UPDATE agent.action_approval SET decision='rejected' WHERE id='{a16id}'")
refused("decision rows are immutable (DELETE)", "DELETE on agent.action_approval is not allowed", f"DELETE FROM agent.action_approval WHERE id='{a16id}'")

p17 = proposal(); a17id, a17 = approval(p17, "rejected")
with db.transaction():
    db.execute(a17); db.execute(status(p17, "rejected"))
refused("execution under a 'rejected' decision", "execution requires an approved decision", execution(p17, a17id, 1)[1])
p18 = proposal(); a18 = to_executing(p18); e18, x18 = execution(p18, a18, 1)
refused("execution inserted as succeeded", "execution must be inserted as started", x18.replace("trace_id) VALUES", "status,completed_at,trace_id) VALUES").replace(f"'u-1','{TRACE}')", f"'u-1','succeeded',now(),'{TRACE}')"))
db.execute(x18); db.execute(f"UPDATE agent.action_execution SET status='succeeded', completed_at=now() WHERE id='{e18}'")
refused("a completed execution row is final", "execution row is final", fail_exec(e18, "unknown"))
refused("second success for one proposal (T-AGT-09)", "uq_action_execution__one_success", execution(p18, a18, 2)[1],
        f"UPDATE agent.action_execution SET status='succeeded', completed_at=now() WHERE tenant_id='{T}' AND proposal_id='{p18}' AND attempt_no=2")

# ---------- 3b. Fresh human approval for every retry (D-43) ----------
def unknown_failure(pid, aid, attempt):
    """Attempt `attempt` under approval `aid` fails with unknown outcome; proposal executing -> failed."""
    eid, x = execution(pid, aid, attempt)
    with db.transaction():
        db.execute(x); db.execute(fail_exec(eid, "unknown")); db.execute(status(pid, "failed"))

p30 = proposal(); a30 = to_executing(p30); unknown_failure(p30, a30, 1)
refused("D-43 failed -> approved reusing the round-1 approval (no new round)", "re-approval requires a new decision round",
        status(p30, "approved"))
_, rej30 = approval(p30, "rejected", rnd=2)
refused("D-43 failed -> approved when the new round is a rejection", "requires a matching decision record", rej30, status(p30, "approved"))
refused("D-43 round-2 decision without agent:approve", "ck_action_approval__scope",
        approval(p30, "approved", rnd=2, scopes="ARRAY['inventory:read']")[1])
refused("D-43 round-2 decision bound to a different payload hash", "fk_action_approval__action_proposal",
        approval(p30, "approved", rnd=2, sha="f" * 64)[1])
refused("D-43 tenant 2 cannot re-approve tenant 1's proposal", "unknown proposal", approval(p30, "approved", rnd=2, tenant=T2)[1])
r30id, r30 = approval(p30, "approved", rnd=2)
db.execute(r30)
refused("D-43 no attempt while the proposal is still failed (even with the new round)", "execution requires the proposal to be executing",
        execution(p30, r30id, 2)[1])
ok("D-43 failed -> approved with the new round-2 decision", status(p30, "approved"))
refused("D-43 no attempt while approved but not yet executing", "execution requires the proposal to be executing", execution(p30, r30id, 2)[1])
db.execute(status(p30, "executing"))
refused("D-43 new attempt under the old round-1 approval", "execution must use the latest decision round", execution(p30, a30, 2)[1])
refused("D-43 new attempt with a different idempotency key", "fk_action_execution__action_proposal",
        execution(p30, r30id, 2)[1].replace(f"'{H}','{p30}','u-1'", f"'{H}','{uuid.uuid4()}','u-1'"))
e30, x30 = execution(p30, r30id, 2)
ok("D-43 attempt 2 under round 2, same idempotency key, succeeds", x30,
   f"UPDATE agent.action_execution SET status='succeeded', completed_at=now(), external_ref_type='purchase_order', external_ref_id='PO-1' WHERE id='{e30}'",
   status(p30, "succeeded"))
keys = db.execute(f"SELECT count(DISTINCT idempotency_key), count(*) FROM agent.action_execution WHERE proposal_id='{p30}'").fetchone()
report("D-43 every attempt of the proposal carried the same idempotency key", keys == (1, 2), str(keys))

p31 = proposal(); a31 = to_executing(p31); e31, x31 = execution(p31, a31, 1)
db.execute(x31); db.execute(fail_exec(e31, "unknown"))
e31b, x31b = execution(p31, a31, 2)
ok("D-43 worker same-key retry under the same approval while still executing (allowed)", x31b, fail_exec(e31b, "unknown"),
   status(p31, "failed"))
refused("D-43 after the worker's retries the proposal is failed: old approval cannot re-open it", "re-approval requires a new decision round",
        status(p31, "approved"))
refused("D-43 worker cannot add an attempt to the failed proposal under the old approval", "execution requires the proposal to be executing",
        execution(p31, a31, 3)[1])

p32 = proposal(); a32 = to_executing(p32); unknown_failure(p32, a32, 1)
r32a, x = approval(p32, "approved", rnd=2)
with db.transaction():
    db.execute(x); db.execute(status(p32, "approved"))
db.execute(status(p32, "executing")); unknown_failure(p32, r32a, 2)
refused("D-43 after attempt 2 fails, round 2 cannot authorise round 3's attempt", "re-approval requires a new decision round",
        status(p32, "approved"))
_, r32b = approval(p32, "approved", rnd=3)
ok("D-43 a third human round re-opens the proposal", r32b, status(p32, "approved"))

# ---------- 3c. Approval validity: 24 h from the server time of each human decision (D-44) ----------
# Time is simulated by back-dating decided_at inside the test transaction: the owner (no superuser) switches the table's
# user triggers off for that one UPDATE only and back on before anything else runs; the DDL is transactional.
# now() is fixed per transaction, so "exactly 24 h" is an exact boundary.
def aged(aid, age):
    return ["ALTER TABLE agent.action_approval DISABLE TRIGGER USER",
            f"UPDATE agent.action_approval SET decided_at = now() - interval '{age}' WHERE id = '{aid}'",
            "ALTER TABLE agent.action_approval ENABLE TRIGGER USER"]

p40 = proposal(); a40, x40 = approval(p40, "approved")
ok("D-44 a client-supplied decided_at is ignored (server time is used)",
   x40.replace("trace_id) VALUES", "decided_at,trace_id) VALUES").replace(f"'{H}','{TRACE}')", f"'{H}','2000-01-01T00:00:00Z','{TRACE}')"),
   status(p40, "approved"))
d40 = db.execute(f"SELECT now() - decided_at < interval '1 minute' FROM agent.action_approval WHERE id = '{a40}'").fetchone()[0]
report("D-44 stored decided_at is the insert time", d40 is True, str(d40))

p41 = proposal(); a41 = to_executing(p41)  # leaves the proposal executing; use fresh ones for approved -> executing
p42 = proposal(); a42, x = approval(p42, "approved")
with db.transaction():
    db.execute(x); db.execute(status(p42, "approved"))
ok("D-44 approved -> executing exactly 24 h after the approval (boundary, still valid)", *aged(a42, "24 hours"), status(p42, "executing"))
p43 = proposal(); a43, x = approval(p43, "approved")
with db.transaction():
    db.execute(x); db.execute(status(p43, "approved"))
refused("D-44 approved -> executing 24 h + 1 microsecond after the approval", "approval round 1 expired at",
        *aged(a43, "24 hours 1 microsecond"), status(p43, "executing"))

ok("D-44 first attempt exactly 24 h after the approval (boundary)", *aged(a41, "24 hours"), execution(p41, a41, 1)[1])
p44 = proposal(); a44 = to_executing(p44)
refused("D-44 first attempt 24 h + 1 microsecond after the approval", "approval expired at",
        *aged(a44, "24 hours 1 microsecond"), execution(p44, a44, 1)[1])

# Worker retry under an expired approval is refused; a fresh human round gives a fresh 24 h window.
p45 = proposal(); a45 = to_executing(p45); e45, x45 = execution(p45, a45, 1)
db.execute(x45); db.execute(fail_exec(e45, "unknown"))
refused("D-44 worker same-key retry after the approval expired", "approval expired at", *aged(a45, "25 hours"), execution(p45, a45, 2)[1])
ok("D-44 the worker then gives up: executing -> failed", *aged(a45, "25 hours"), status(p45, "failed"))
r45, x = approval(p45, "approved", rnd=2)
ok("D-44 fresh round 2 re-opens it with a new window", x, status(p45, "approved"), status(p45, "executing"), execution(p45, r45, 2)[1])

p46 = proposal(); a46 = to_executing(p46); unknown_failure(p46, a46, 1)
r46, x46 = approval(p46, "approved", rnd=2); db.execute(x46)
refused("D-44 failed -> approved with a round-2 decision older than 24 h", "approval round 2 expired at",
        *aged(r46, "24 hours 1 microsecond"), status(p46, "approved"))
ok("D-44 failed -> approved with a round-2 decision exactly 24 h old (boundary)", *aged(r46, "24 hours"), status(p46, "approved"))

# The re-approval window starts at the new decision, not at the proposal's original 24 h deadline.
p47 = proposal(); a47 = to_executing(p47); unknown_failure(p47, a47, 1)
with db.transaction():
    for q in ["ALTER TABLE agent.action_proposal DISABLE TRIGGER USER", "ALTER TABLE agent.action_approval DISABLE TRIGGER USER",
              f"UPDATE agent.action_proposal SET created_at = now() - interval '3 days', expires_at = now() - interval '2 days' WHERE id = '{p47}'",
              f"UPDATE agent.action_approval SET decided_at = now() - interval '3 days' WHERE id = '{a47}'",
              "ALTER TABLE agent.action_proposal ENABLE TRIGGER USER", "ALTER TABLE agent.action_approval ENABLE TRIGGER USER"]:
        db.execute(q)
r47, x47 = approval(p47, "approved", rnd=2)
ok("D-44 re-approval after the proposal's original expires_at (window starts at the new approval)", x47, status(p47, "approved"))

# ---------- 4. Concurrency (two connections) ----------
def race(stmt_a, stmt_b, hold=0.5):
    """A runs stmt_a in an open transaction; B starts stmt_b (it may block on A's locks); A commits; B finishes.
    Returns (a_error, b_error)."""
    ca, cb = connect(), connect()
    out = {}
    ca.execute("BEGIN"); bbsetup.set_tenant(ca, T)
    try:
        for s in stmt_a: ca.execute(s)
        out["a"] = None
    except psycopg.Error as e:
        out["a"] = e
    def b():
        try:
            with bbsetup.tenant(cb, T):
                for s in stmt_b: cb.execute(s)
            out["b"] = None
        except psycopg.Error as e:
            out["b"] = e
    t = threading.Thread(target=b); t.start(); time.sleep(hold)
    ca.execute("COMMIT" if out["a"] is None else "ROLLBACK"); t.join(10)
    ca.close(); cb.close()
    return out["a"], out.get("b", "B did not finish")


def one_winner(name, errs, expect_msg):
    a, b = errs
    passed = a is None and b is not None and expect_msg in str(b)
    report(name, passed, f"A={a!r} B={b!r}")


# T-AGT-05: two concurrent first-round decisions on one proposal.
p19 = proposal()
_, d1 = approval(p19, "approved"); _, d2 = approval(p19, "approved")
one_winner("T-AGT-05 two concurrent approvals of one proposal -> one wins", race([d1, status(p19, "approved")], [d2, status(p19, "approved")]),
           "first decision requires status pending")

# Status compare-and-set: two workers move the same proposal approved -> executing.
p20 = proposal(); aid, a = approval(p20, "approved")
with db.transaction():
    db.execute(a); db.execute(status(p20, "approved"))
ca, cb = connect(), connect(); ca.execute("BEGIN"); bbsetup.set_tenant(ca, T)


def cas_b():
    with bbsetup.tenant(cb, T):
        nb["n"] = cb.execute(f"UPDATE agent.action_proposal SET status='executing' WHERE id='{p20}' AND status='approved'").rowcount


na = ca.execute(f"UPDATE agent.action_proposal SET status='executing' WHERE id='{p20}' AND status='approved'").rowcount
nb = {}
tb = threading.Thread(target=cas_b)
tb.start(); time.sleep(0.5); ca.execute("COMMIT"); tb.join(10); ca.close(); cb.close()
report("status CAS approved -> executing from two workers -> exactly one row updated", (na, nb.get("n")) == (1, 0), f"A={na} B={nb}")

# D-43: two concurrent re-approvals of one failed proposal.
p33 = proposal(); a33 = to_executing(p33); unknown_failure(p33, a33, 1)
_, q1 = approval(p33, "approved", rnd=2); _, q2 = approval(p33, "approved", rnd=2)
one_winner("D-43 two concurrent re-approvals of one failed proposal -> one wins", race([q1, status(p33, "approved")], [q2, status(p33, "approved")]),
           "re-approval requires status failed")

# T-AGT-08: two concurrent execution attempts of one proposal.
_, ex1 = execution(p20, aid, 1); _, ex2 = execution(p20, aid, 2)
one_winner("T-AGT-08 two concurrent executions of one proposal -> second fails (one_inflight)", race([ex1], [ex2]), "uq_action_execution__one_inflight")

# D-30: two concurrent creates of a live proposal for one recommendation.
db.execute(f"INSERT INTO intel.risk_assessment(id,tenant_id,product_id,risk_type,severity,days_of_cover,lead_time_days,input_available_quantity,inventory_as_of,rule_version,rule_config_id) "
           f"VALUES ('f0000000-0000-4000-8000-0000000000b1','{T}','{P}','stockout_risk','high',1.7,5,40,now(),'risk-rules@1.0.0',(SELECT id FROM intel.rule_config WHERE tenant_id='{T}' AND rule_set='risk'))")
db.execute(f"INSERT INTO intel.recommendation(id,tenant_id,product_id,risk_assessment_id,recommendation_type,payload,expires_at,rule_version,rule_config_id) "
           f"VALUES ('e0000000-0000-4000-8000-0000000000b1','{T}','{P}','f0000000-0000-4000-8000-0000000000b1','create_purchase_order','{{}}',now()+interval '1 day','rec-rules-v1',(SELECT id FROM intel.rule_config WHERE tenant_id='{T}' AND rule_set='recommendation'))")
REC = "'e0000000-0000-4000-8000-0000000000b1'"
def prop_sql():
    pid = str(uuid.uuid4())
    return (f"INSERT INTO agent.action_proposal(id,tenant_id,proposed_by,tool_name,tool_version,arguments,arguments_sha256,policy_version,reason,"
            f"recommendation_id,idempotency_key,expires_at,trace_id) VALUES ('{pid}','{T}','rules','create_purchase_order','1.0','{ARGS}','{H}',"
            f"'static-policy@1','Stockout risk high',{REC},'{pid}',now()+interval '24 hours','{TRACE}')")
one_winner("D-30 two concurrent live proposals for one recommendation -> one unique violation", race([prop_sql()], [prop_sql()]),
           "uq_action_proposal__live_per_recommendation")

print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
