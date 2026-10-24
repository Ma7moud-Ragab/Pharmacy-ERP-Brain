from spec_lib import *

T = DEFAULT_TENANT
AMOX = "b3f1c2a0-5d1e-4c7a-9a10-000000000001"
SUP = "8a1e5b3c-7d2f-4e1a-b6c4-000000000001"
EJ = "'{}'::jsonb"
def tfk(name, col_, ref, on_delete="RESTRICT", rel=None, back=None, note=""):
    return FK(name, ["tenant_id", col_], ref, ["tenant_id", "id"], on_delete, rel, back, note)

llm_usage = Table(
    schema="audit", name="llm_usage", cls="LlmUsage", tier="A", scope="MVP",
    purpose="One row per LLM layer call (and per cache hit that avoided a call): provider, model, prompt version, tokens, estimated cost, latency, outcome, trace. Feeds `/brain/admin/cost`. Stores NO prompt or completion text.",
    cols=[ID(), TENANT(),
          col("occurred_at", "TIMESTAMPTZ", "Call time (UTC).", default="now()"),
          col("purpose", "TEXT", "explanation | assistant_chat | agent_reasoning | briefing | other."),
          col("provider", "TEXT", "LLM provider id (provider is an open decision, OD-18)."),
          col("model", "TEXT", "Exact model identifier returned/used."),
          col("model_route", "TEXT", "template | small | large (model routing decision).", null=True),
          col("prompt_name", "TEXT", "Prompt file name from `llm/prompts/`."),
          col("prompt_version", "TEXT", "Prompt version (git-tracked)."),
          col("tokens_in", "INTEGER", "Input tokens."),
          col("tokens_out", "INTEGER", "Output tokens."),
          col("tokens_cached_in", "INTEGER", "Input tokens served from the provider's prompt cache, if reported.", null=True),
          col("estimated_cost_usd", "NUMERIC(12,6)", "Estimated cost in USD (micro-dollar precision)."),
          col("pricing_version", "TEXT", "Price table used for the estimate.", null=True),
          col("latency_ms", "INTEGER", "End-to-end latency."),
          col("cache_status", "TEXT", "miss | hit (response cache, zero tokens) | not_cacheable.", default="'miss'"),
          col("outcome", "TEXT", "success | error | timeout | invalid_output | refused."),
          col("error_code", "TEXT", "Short error code when outcome is not success.", null=True),
          col("schema_valid", "BOOLEAN", "Whether the structured output validated against its JSON schema.", null=True),
          col("prompt_sha256", "CHAR(64)", "Hash of the rendered prompt (dedupe/cache analysis). The text itself is never stored.", null=True),
          col("actor_id", "TEXT", "JWT sub of the requesting user (pseudonymous), for per-user cost.", null=True),
          col("session_id", "UUID", "agent_session id. SOFT reference (no FK): usage rows outlive sessions.", null=True),
          col("tool_step", "SMALLINT", "Step number inside an agent run.", null=True),
          TRACE(null=False),
          col("span_id", "CHAR(16)", "W3C span-id.", null=True)],
    pk=["id"], fk_target=True,
    checks=[("ck_llm_usage__purpose", "purpose IN ('explanation','assistant_chat','agent_reasoning','briefing','other')"),
            ("ck_llm_usage__route", "model_route IS NULL OR model_route IN ('template','small','large')"),
            ("ck_llm_usage__tokens", "tokens_in >= 0 AND tokens_out >= 0 AND (tokens_cached_in IS NULL OR (tokens_cached_in >= 0 AND tokens_cached_in <= tokens_in))"),
            ("ck_llm_usage__cost", "estimated_cost_usd >= 0"),
            ("ck_llm_usage__latency", "latency_ms >= 0"),
            ("ck_llm_usage__cache_status", "cache_status IN ('miss','hit','not_cacheable')"),
            ("ck_llm_usage__outcome", "outcome IN ('success','error','timeout','invalid_output','refused')"),
            ("ck_llm_usage__span_format", "span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'")],
    idxs=[Idx("ix_llm_usage__tenant_occurred", ["tenant_id", "occurred_at"], why="Cost per day/week dashboards."),
          Idx("ix_llm_usage__tenant_purpose_occurred", ["tenant_id", "purpose", "occurred_at"], why="Cost by purpose."),
          Idx("ix_llm_usage__trace", ["trace_id"], why="Join with audit_log and logs by trace.")],
    append_only="update", grants="SI", purge=True,
    writer="LLM layer `llm/client.py` (Ibrahim).",
    readers="Cost view, Ibrahim/Ali dashboards, action_proposal provenance.",
    tenancy=TENANCY_STD,
    timestamps="`occurred_at` UTC.",
    access="Insert-only; aggregate by day/purpose/model; lookup by trace.",
    mutability="Append-only; UPDATE forbidden; DELETE only by the retention role.",
    retention="13 months raw (aggregates may be kept longer); rows referenced by an action_proposal are kept (FK RESTRICT).",
    recovery="Not rebuildable: backed up with the audit tier.",
    migration="Created before agent tables (proposal references it).",
    example={"tenant_id": T, "purpose": "explanation", "provider": "<provider>", "model": "<model-id>", "model_route": "small", "prompt_name": "explain_stockout_risk", "prompt_version": "1.2.0", "tokens_in": 412, "tokens_out": 96, "estimated_cost_usd": 0.000731, "latency_ms": 1180, "cache_status": "miss", "outcome": "success", "schema_valid": True, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"})

audit_log = Table(
    schema="audit", name="audit_log", cls="AuditLog", tier="A", scope="MVP",
    purpose="Brain audit trail: who proposed, approved/rejected, executed, which tool, which payload fingerprint, outcome, trace. Distinct from `erp_db.AuditLog` (human changes in the ERP). Append-only.",
    cols=[ID(),
          col("seq", "BIGINT", "Monotonic ordering / keyset-pagination key.", identity=True),
          TENANT(),
          col("occurred_at", "TIMESTAMPTZ", "Event time (UTC).", default="now()"),
          col("event_type", "TEXT", "Dotted lowercase vocabulary, e.g. proposal.created, proposal.approved, proposal.rejected, execution.succeeded, tool.denied, model.status_changed."),
          col("outcome", "TEXT", "success | failure | denied | info."),
          col("actor_type", "TEXT", "user | agent | system."),
          col("actor_id", "TEXT", "JWT sub for users; session id for agent; component name for system.", null=True),
          col("on_behalf_of_actor_id", "TEXT", "User on whose behalf an agent acted.", null=True),
          col("approved_by_actor_id", "TEXT", "Approver (JWT sub) when relevant.", null=True),
          col("tool_name", "TEXT", "Registry tool name when relevant.", null=True),
          col("subject_type", "TEXT", "Kind of Brain object the event concerns (action_proposal, model_registry, ...).", null=True),
          col("subject_id", "UUID", "Brain object id. SOFT reference (polymorphic, no FK): audit rows must outlive subjects.", null=True),
          col("arguments_sha256", "CHAR(64)", "Fingerprint of the exact action payload involved.", null=True),
          col("details", "JSONB", "Sanitised allow-listed context (status from/to, model_version, rule_version, result summary).", default=EJ, jsonb="object"),
          TRACE(null=False),
          col("span_id", "CHAR(16)", "W3C span-id.", null=True),
          col("request_id", "TEXT", "HTTP request id.", null=True)],
    pk=["id"],
    uniques=[("uq_audit_log__seq", ["seq"])],
    checks=[("ck_audit_log__event_type", "event_type ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$'"),
            ("ck_audit_log__outcome", "outcome IN ('success','failure','denied','info')"),
            ("ck_audit_log__actor_type", "actor_type IN ('user','agent','system')"),
            ("ck_audit_log__actor_required", "actor_type = 'system' OR actor_id IS NOT NULL"),
            ("ck_audit_log__subject_pair", "(subject_type IS NULL) = (subject_id IS NULL)"),
            ("ck_audit_log__details_size", "octet_length(details::text) <= 8192"),
            ("ck_audit_log__span_format", "span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'")],
    idxs=[Idx("ix_audit_log__tenant_occurred", ["tenant_id", "occurred_at"], why="Time-ordered review."),
          Idx("ix_audit_log__trace", ["trace_id"], why="'Which trace links the events together?'"),
          Idx("ix_audit_log__tenant_actor_occurred", ["tenant_id", "actor_id", "occurred_at"], why="Audit by actor."),
          Idx("ix_audit_log__subject", ["tenant_id", "subject_type", "subject_id", "occurred_at"], why="Full history of one proposal/model.")],
    append_only="update_delete", grants="SI", worker_grants="I",
    writer="Audit writer `observability/audit.py` (Ibrahim) called by Approval Engine, Orchestrator, Registry.",
    readers="Reviewers, debugging, compliance export.",
    tenancy=TENANCY_STD,
    timestamps="`occurred_at` UTC.",
    jsonb_note="`details`: allow-listed keys per event_type, <= 8 KB (CHECK), validated by Pydantic `AuditDetails`; never raw ERP rows, prompts, tokens or customer data.",
    access="Insert-only; read by trace, actor, subject, time. Keyset pagination on `seq`.",
    mutability="Immutable: UPDATE/DELETE/TRUNCATE rejected by trigger; brain_app has no UPDATE/DELETE privilege.",
    retention="No deletion in MVP (OD-12). Revisit with monthly partitioning (DROP PARTITION is the only purge path) when volume or policy requires.",
    recovery="Not rebuildable. Daily dump of the `audit` and `agent` schemas with the longest retention tier; consider WAL archiving (Ali).",
    migration="Created before `agent` schema (no dependency). Hash-chaining for tamper evidence is a future upgrade.",
    example={"tenant_id": T, "seq": 1042, "event_type": "proposal.approved", "outcome": "success", "actor_type": "user", "actor_id": "u-3f2a...(JWT sub)", "approved_by_actor_id": "u-3f2a...", "tool_name": "create_purchase_order", "subject_type": "action_proposal", "subject_id": "d4c1...-uuid", "arguments_sha256": "5e88...(64 hex)", "details": {"status_from": "pending", "status_to": "approved"}, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"})

agent_session = Table(
    schema="agent", name="agent_session", cls="AgentSession", tier="A", scope="MVP",
    purpose="Conversation/agent session: owner, small working context, tool allow-list, write cap, expiry. Survives a browser refresh. Session-scoped memory only (no cross-session memory in MVP).",
    cols=[ID(), TENANT(),
          col("user_actor_id", "TEXT", "JWT `sub` of the user who owns the session."),
          col("status", "TEXT", "active | closed | expired.", default="'active'"),
          col("state", "JSONB", "Compact working context (focused product ids, last intent). No PII, no raw ERP rows. <= 16 KB.", default=EJ, jsonb="object"),
          col("allowed_tools", "TEXT[]", "Per-session tool allow-list (guardrail).", default="'{}'::text[]"),
          col("max_writes", "SMALLINT", "Maximum write proposals per session (source example: 3).", default="3"),
          col("write_proposals_count", "SMALLINT", "Write proposals created so far; the CHECK against max_writes makes the cap a database guarantee.", default="0"),
          col("started_at", "TIMESTAMPTZ", "Session start (UTC).", default="now()"),
          col("last_activity_at", "TIMESTAMPTZ", "Last turn (UTC).", default="now()"),
          col("expires_at", "TIMESTAMPTZ", "Inactivity expiry (UTC)."),
          ROWV(), TRACE(), CREATED(), UPDATED()],
    pk=["id"], fk_target=True,
    checks=[("ck_agent_session__user", "char_length(user_actor_id) BETWEEN 1 AND 128"),
            ("ck_agent_session__status", "status IN ('active','closed','expired')"),
            ("ck_agent_session__state_size", "octet_length(state::text) <= 16384"),
            ("ck_agent_session__max_writes", "max_writes BETWEEN 0 AND 20"),
            ("ck_agent_session__write_cap", "write_proposals_count >= 0 AND write_proposals_count <= max_writes")],
    idxs=[Idx("ix_agent_session__user_activity", ["tenant_id", "user_actor_id", "last_activity_at"], why="Resume the user's latest session."),
          Idx("ix_agent_session__active_expiry", ["tenant_id", "expires_at"], where="status = 'active'", why="Expiry sweeper.")],
    updated_at_trigger=True,
    guard_mutable=["status", "state", "allowed_tools", "max_writes", "write_proposals_count", "last_activity_at", "expires_at", "row_version", "updated_at"],
    grants="SIU", purge=True,
    writer="Orchestrator (Ibrahim).", readers="Orchestrator, Brain API, ApprovalModal flow.",
    tenancy=TENANCY_STD + " Session access also requires `user_actor_id` = JWT sub (or an admin scope).",
    timestamps="UTC.",
    jsonb_note="`state`: object `SessionState`, size-capped by CHECK; Pydantic `SessionState`.",
    access="Point by id; latest for user; expiry sweep.",
    mutability="Mutable with optimistic concurrency (`row_version`); identity fields immutable.",
    retention="Sessions without proposals: 30 days after expiry. Sessions referenced by proposals are kept (FK RESTRICT) but their messages are purged on schedule.",
    recovery="Not rebuildable (conversation context); loss only costs context.",
    migration="First table of the `agent` schema.",
    example={"tenant_id": T, "user_actor_id": "u-3f2a...", "status": "active", "state": {"focus_product_id": AMOX}, "allowed_tools": ["get_inventory", "get_forecast", "get_supplier", "get_insight", "create_purchase_order"], "max_writes": 3, "write_proposals_count": 1, "expires_at": "2026-09-24T14:16:00Z"})

agent_message = Table(
    schema="agent", name="agent_message", cls="AgentMessage", tier="A", scope="MVP",
    purpose="Recent conversation turns (the 'last N messages' memory). Content is PII-scrubbed and size-bounded; rows carry their own expiry and are hard-deleted on schedule.",
    cols=[ID(), TENANT(),
          col("session_id", "UUID", "Owning session."),
          col("turn_index", "INTEGER", "0-based turn number within the session."),
          col("role", "TEXT", "user | assistant | tool."),
          col("content", "TEXT", "Scrubbed text (<= 4000 chars). Assistant turns hold the human-readable explanation."),
          col("pii_scrubbed", "BOOLEAN", "Writer's attestation that the PII scrubber ran. CHECK forces TRUE.", default="false"),
          col("structured", "JSONB", "Typed Explanation JSON or compact tool-result summary (never raw ERP rows).", null=True, jsonb="object"),
          col("llm_usage_id", "UUID", "audit.llm_usage row for assistant turns (soft reference, no FK).", null=True),
          col("created_at", "TIMESTAMPTZ", "Turn time (UTC).", default="now()"),
          col("expires_at", "TIMESTAMPTZ", "Purge time for this turn (UTC).")],
    pk=["id"],
    uniques=[("uq_agent_message__session_turn", ["session_id", "turn_index"])],
    fks=[tfk("fk_agent_message__agent_session", "session_id", "agent.agent_session", on_delete="CASCADE", rel="session", back="messages")],
    checks=[("ck_agent_message__turn", "turn_index >= 0"),
            ("ck_agent_message__role", "role IN ('user','assistant','tool')"),
            ("ck_agent_message__content_len", "char_length(content) <= 4000"),
            ("ck_agent_message__scrubbed", "pii_scrubbed"),
            ("ck_agent_message__expiry", "expires_at > created_at")],
    idxs=[Idx("ix_agent_message__tenant_expires", ["tenant_id", "expires_at"], why="Purge job."),
          Idx("ix_agent_message__tenant_session", ["tenant_id", "session_id"], why="FK support; last-N read uses the unique (session_id, turn_index) index.")],
    append_only="update", grants="SI", purge=True,
    writer="Orchestrator.", readers="Orchestrator (last N), Brain API.",
    tenancy=TENANCY_STD,
    timestamps="UTC.",
    jsonb_note="`structured`: object `Explanation` or `ToolResultSummary` (Pydantic). Never raw ERP rows.",
    access="Insert per turn; read last N by (session_id, turn_index DESC).",
    mutability="Append-only; deleted by retention job when expired.",
    retention="30 days (configurable via expires_at).",
    recovery="Not rebuildable; non-critical.",
    migration="Depends on agent_session (CASCADE).",
    example={"tenant_id": T, "session_id": "5a1f...-uuid", "turn_index": 2, "role": "assistant", "content": "Amoxicillin covers about 1.7 days of demand; the supplier needs 5.", "pii_scrubbed": True, "structured": {"type": "explanation", "insight_id": "r-9f2a..."}})

action_proposal = Table(
    schema="agent", name="action_proposal", cls="ActionProposal", tier="A", scope="MVP",
    purpose="The immutable proposed write (tool + arguments) awaiting a human decision, plus its lifecycle status. Arguments and their SHA-256 can never change after insert; approvals and executions are cryptographically bound to that hash by composite FKs.",
    cols=[ID(), TENANT(),
          col("session_id", "UUID", "Session that produced the proposal. Required when proposed_by = 'agent'; NULL allowed for deterministic rule proposals (D-29).", null=True),
          col("requested_by_actor_id", "TEXT", "JWT sub of the user who asked for the proposal. Required when proposed_by = 'agent'; NULL allowed for rule proposals created by the system (D-29).", null=True),
          col("proposed_by", "TEXT", "rules (deterministic, built from a recommendation without the LLM, D-18) | agent (conversational path). Set explicitly; no default (D-29)."),
          col("tool_name", "TEXT", "Registry tool name (e.g. create_purchase_order)."),
          col("tool_version", "TEXT", "Registry schema version of the tool, e.g. 'create_purchase_order@1'."),
          col("arguments", "JSONB", "Validated arguments exactly as they will be sent. Immutable.", jsonb="object"),
          col("arguments_sha256", "CHAR(64)", "SHA-256 (lowercase hex) of the RFC 8785 (JCS) canonical JSON of `arguments` (D-13; golden vectors in contracts/fixtures/hash). Approvals bind to it."),
          col("requires_approval", "BOOLEAN", "Always TRUE in MVP (every write needs a human).", default="true"),
          col("policy_version", "TEXT", "Static policy version that returned require-approval."),
          col("reason", "TEXT", "Templated human-readable reason (<= 500 chars), e.g. 'high stockout risk (cover 1.7d < lead time 5d)'. Generated by code, not by the LLM."),
          col("recommendation_id", "UUID", "Recommendation the proposal was built from.", null=True),
          col("risk_assessment_id", "UUID", "Risk assessment behind it. This is the API `insight_id` (OD-06).", null=True),
          col("llm_usage_id", "UUID", "LLM call that proposed the tool call (which model proposed it).", null=True),
          col("idempotency_key", "UUID", "Generated once at proposal creation; sent as `Idempotency-Key` on every execution attempt of this proposal."),
          col("status", "TEXT", "pending | approved | rejected | expired | cancelled | executing | succeeded | failed.", default="'pending'"),
          col("status_changed_at", "TIMESTAMPTZ", "Last status change (set by trigger).", default="now()"),
          col("expires_at", "TIMESTAMPTZ", "Approval deadline; after it a pending proposal cannot be approved."),
          ROWV(), TRACE(null=False), CREATED(), UPDATED()],
    pk=["id"], fk_target=True,
    uniques=[("uq_action_proposal__tenant_idempotency", ["tenant_id", "idempotency_key"]),
             ("uq_action_proposal__id_hash", ["tenant_id", "id", "arguments_sha256"]),
             ("uq_action_proposal__id_idem", ["tenant_id", "id", "idempotency_key"])],
    fks=[tfk("fk_action_proposal__agent_session", "session_id", "agent.agent_session", rel="session", back="proposals"),
         tfk("fk_action_proposal__recommendation", "recommendation_id", "intel.recommendation", rel="recommendation"),
         tfk("fk_action_proposal__risk_assessment", "risk_assessment_id", "intel.risk_assessment", rel="risk_assessment"),
         tfk("fk_action_proposal__llm_usage", "llm_usage_id", "audit.llm_usage", rel="llm_usage")],
    checks=[("ck_action_proposal__proposed_by", "proposed_by IN ('rules','agent')"),
            ("ck_action_proposal__agent_context", "proposed_by <> 'agent' OR (session_id IS NOT NULL AND requested_by_actor_id IS NOT NULL)"),
            ("ck_action_proposal__requires_approval", "requires_approval"),
            ("ck_action_proposal__status", "status IN ('pending','approved','rejected','expired','cancelled','executing','succeeded','failed')"),
            ("ck_action_proposal__tool_len", "char_length(tool_name) BETWEEN 1 AND 100"),
            ("ck_action_proposal__reason_len", "char_length(reason) BETWEEN 1 AND 500"),
            ("ck_action_proposal__expiry", "expires_at > created_at"),
            ("ck_action_proposal__args_size", "octet_length(arguments::text) <= 32768")],
    idxs=[Idx("ix_action_proposal__pending", ["tenant_id", "created_at"], where="status = 'pending'", why="ApprovalModal / pending approvals list."),
          Idx("ix_action_proposal__tenant_session", ["tenant_id", "session_id", "created_at"], why="Proposals of a session; FK support."),
          Idx("ix_action_proposal__tenant_requester", ["tenant_id", "requested_by_actor_id", "created_at"], why="Audit by requester."),
          Idx("ix_action_proposal__tenant_recommendation", ["tenant_id", "recommendation_id"], why="'Was this recommendation actioned?' (derived status); FK support."),
          Idx("uq_action_proposal__live_per_recommendation", ["tenant_id", "recommendation_id"], unique=True, where="recommendation_id IS NOT NULL AND status IN ('pending','approved','executing')", why="At most one live proposal per recommendation (D-30). Concurrent creates: the loser gets a unique violation and returns the existing proposal. Complements, does not replace, the ERP Idempotency-Key (D-09).")],
    updated_at_trigger=True, guard_mutable=["status", "status_changed_at", "row_version", "updated_at"], append_only="delete", grants="SIU", worker_grants="SU", worker_update_cols=['status', 'status_changed_at', 'row_version', 'updated_at'],
    custom_triggers=["""CREATE OR REPLACE FUNCTION agent.guard_proposal_transition() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_latest RECORD;
  v_last RECORD;
  v_ok boolean;
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  -- D-45: a session acting as brain_worker (not superuser) may only expire, or complete an execution.
  IF to_regrole('brain_worker') IS NOT NULL AND pg_has_role(current_user, 'brain_worker', 'MEMBER')
     AND NOT (SELECT r.rolsuper FROM pg_roles r WHERE r.rolname = current_user)
     AND NOT ((OLD.status = 'pending' AND NEW.status = 'expired')
           OR (OLD.status = 'executing' AND NEW.status IN ('succeeded','failed'))) THEN
    RAISE EXCEPTION USING MESSAGE = 'brain_worker may not move action_proposal ' || OLD.status || ' -> ' || NEW.status, ERRCODE = 'insufficient_privilege';
  END IF;
  v_ok := CASE OLD.status
    WHEN 'pending'   THEN NEW.status IN ('approved','rejected','expired','cancelled')
    WHEN 'approved'  THEN NEW.status IN ('executing','cancelled')
    WHEN 'executing' THEN NEW.status IN ('succeeded','failed')
    WHEN 'failed'    THEN NEW.status = 'approved'
    ELSE false END;
  IF NOT v_ok THEN
    RAISE EXCEPTION USING MESSAGE = 'illegal action_proposal transition ' || OLD.status || ' -> ' || NEW.status, ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IN ('approved','rejected') OR (OLD.status = 'approved' AND NEW.status = 'executing') THEN
    SELECT * INTO v_latest FROM agent.action_approval
     WHERE tenant_id = OLD.tenant_id AND proposal_id = OLD.id
     ORDER BY approval_round DESC LIMIT 1;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'status ' || NEW.status || ' requires a decision record', ERRCODE = 'check_violation';
    END IF;
    IF v_latest.decision <> (CASE WHEN NEW.status = 'rejected' THEN 'rejected' ELSE 'approved' END) THEN
      RAISE EXCEPTION USING MESSAGE = 'status ' || NEW.status || ' requires a matching decision record', ERRCODE = 'check_violation';
    END IF;
    -- D-44: an approval is valid while now() <= decided_at + 24 h (decided_at is the server time of that human decision).
    IF NEW.status <> 'rejected' AND now() > v_latest.decided_at + interval '24 hours' THEN
      RAISE EXCEPTION USING MESSAGE = 'approval round ' || v_latest.approval_round || ' expired at ' || (v_latest.decided_at + interval '24 hours')::text, ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF OLD.status = 'pending' AND NEW.status = 'approved' AND now() > OLD.expires_at THEN
    RAISE EXCEPTION USING MESSAGE = 'proposal expired at ' || OLD.expires_at::text, ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'failed' AND NEW.status = 'approved' THEN
    -- Latest attempt and the decision round that authorised it.
    SELECT e.status, e.outcome_certainty, a.approval_round INTO v_last
      FROM agent.action_execution e
      JOIN agent.action_approval a ON a.tenant_id = e.tenant_id AND a.id = e.approval_id
     WHERE e.tenant_id = OLD.tenant_id AND e.proposal_id = OLD.id
     ORDER BY e.attempt_no DESC LIMIT 1;
    IF NOT FOUND OR v_last.status <> 'failed' OR v_last.outcome_certainty IS DISTINCT FROM 'unknown' THEN
      RAISE EXCEPTION 're-approval is only allowed after an attempt with unknown outcome' USING ERRCODE = 'check_violation';
    END IF;
    -- A failed proposal never reuses the approval its last attempt ran under: a new human decision round is required (D-43).
    IF v_latest.approval_round <= v_last.approval_round THEN
      RAISE EXCEPTION USING MESSAGE = 're-approval requires a new decision round after attempt round ' || v_last.approval_round, ERRCODE = 'check_violation';
    END IF;
  END IF;
  NEW.status_changed_at := now();
  RETURN NEW;
END
$fn$;""",
        "CREATE TRIGGER trg_action_proposal_transition BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION agent.guard_proposal_transition();"],
    writer="Proposal service (rules) or assistant (agent) creates with status pending; approval and execution services transition it - Ahmed Emad (logic), schema by Ibrahim (D-02).",
    readers="ApprovalModal API, audit, Approval Engine, execution worker.",
    tenancy=TENANCY_STD + " Approval additionally requires scope `agent:approve` and the tenant in the JWT to match the row.",
    timestamps="UTC. `status_changed_at` set by trigger.",
    jsonb_note="`arguments`: validated with the tool's `input_schema` (jsonschema/Pydantic) before insert; <= 32 KB (CHECK); immutable (guard trigger) and fingerprinted by `arguments_sha256`.",
    access="Insert by orchestrator; list pending by tenant; point by id with `SELECT ... FOR UPDATE` in the approval transaction.",
    mutability="Only status, status_changed_at, row_version, updated_at change. Transition legality enforced by trigger: pending->approved|rejected|expired|cancelled; approved->executing|cancelled; executing->succeeded|failed; failed->approved only after an 'unknown'-outcome attempt and with a new human decision round (D-43). DELETE forbidden.",
    retention="Kept with the audit tier (no purge in MVP).",
    recovery="Not rebuildable. Backed up with the `agent`/`audit` tier.",
    migration="Depends on agent_session, recommendation, risk_assessment, llm_usage. Trigger function is created after all agent tables exist (end of migration 0004).",
    example={"tenant_id": T, "session_id": "5a1f...-uuid", "requested_by_actor_id": "u-3f2a...", "tool_name": "create_purchase_order", "tool_version": "create_purchase_order@1", "arguments": {"supplier_id": SUP, "lines": [{"product_id": AMOX, "quantity": 100}]}, "arguments_sha256": "5e88...(64 hex)", "requires_approval": True, "policy_version": "static-policy@1", "reason": "high stockout risk (cover 1.7d < lead time 5d)", "idempotency_key": "e7f0c9c4-2a1b-4d3e-9f55-000000000001", "status": "pending", "expires_at": "2026-09-25T10:17:00Z"})

agent_action = Table(
    schema="agent", name="agent_action", cls="AgentAction", tier="A", scope="MVP",
    purpose="Log of every tool call the agent attempted, including rejected ones (unknown tool, bad arguments, policy deny). For write tools it only points at the ActionProposal; the authorisation and execution detail live in the proposal/approval/execution tables.",
    cols=[ID(), TENANT(),
          col("session_id", "UUID", "Session."),
          col("turn_index", "INTEGER", "Turn that triggered the call (no FK; messages expire).", null=True),
          col("tool_name", "TEXT", "Tool name as attempted (kept even when not in the registry)."),
          col("tool_version", "TEXT", "Registry version when known.", null=True),
          col("read_only", "BOOLEAN", "Registry flag; NULL for unknown tools.", null=True),
          col("requires_approval", "BOOLEAN", "Registry flag; NULL for unknown tools.", null=True),
          col("arguments", "JSONB", "Arguments for read tools only (<= 8 KB). NULL for write intents - those live on the proposal.", null=True, jsonb="object"),
          col("arguments_sha256", "CHAR(64)", "Fingerprint of the arguments.", null=True),
          col("outcome", "TEXT", "executed | pending_approval | denied_policy | rejected_unknown_tool | rejected_invalid_arguments | rejected_scope | error."),
          col("proposal_id", "UUID", "Set when outcome is pending_approval.", null=True),
          col("result_summary", "JSONB", "Compact result facts (counts, ids). Never raw rows.", null=True, jsonb="object"),
          col("error_code", "TEXT", "Short error code.", null=True),
          col("duration_ms", "INTEGER", "Tool latency.", null=True),
          col("llm_usage_id", "UUID", "LLM call that proposed the tool call (soft reference).", null=True),
          TRACE(null=False),
          col("created_at", "TIMESTAMPTZ", "Call time (UTC).", default="now()")],
    pk=["id"],
    fks=[tfk("fk_agent_action__agent_session", "session_id", "agent.agent_session", on_delete="CASCADE", rel="session", back="actions"),
         tfk("fk_agent_action__action_proposal", "proposal_id", "agent.action_proposal", rel="proposal")],
    checks=[("ck_agent_action__outcome", "outcome IN ('executed','pending_approval','denied_policy','rejected_unknown_tool','rejected_invalid_arguments','rejected_scope','error')"),
            ("ck_agent_action__tool_len", "char_length(tool_name) BETWEEN 1 AND 100"),
            ("ck_agent_action__pending_has_proposal", "(outcome = 'pending_approval') = (proposal_id IS NOT NULL)"),
            ("ck_agent_action__write_args_on_proposal", "proposal_id IS NULL OR arguments IS NULL"),
            ("ck_agent_action__unknown_tool", "outcome <> 'rejected_unknown_tool' OR read_only IS NULL"),
            ("ck_agent_action__args_size", "arguments IS NULL OR octet_length(arguments::text) <= 8192"),
            ("ck_agent_action__duration", "duration_ms IS NULL OR duration_ms >= 0")],
    idxs=[Idx("ix_agent_action__tenant_session_created", ["tenant_id", "session_id", "created_at"], why="Replay a session; FK support."),
          Idx("ix_agent_action__tenant_tool_created", ["tenant_id", "tool_name", "created_at"], why="Tool-call accuracy evaluation and dashboards."),
          Idx("ix_agent_action__trace", ["trace_id"], why="Join by trace."),
          Idx("ix_agent_action__tenant_proposal", ["tenant_id", "proposal_id"], where="proposal_id IS NOT NULL", why="FK support.")],
    append_only="update", grants="SI", purge=True,
    writer="Tool Registry / Orchestrator (Ibrahim).", readers="Evaluation (tool-call accuracy), debugging, UI action history.",
    tenancy=TENANCY_STD,
    timestamps="UTC.",
    jsonb_note="`arguments`, `result_summary`: objects; Pydantic `ToolResultSummary`. Read-tool arguments are small (<= 8 KB CHECK).",
    access="Insert per tool call; read by session, by tool, by trace.",
    mutability="Append-only; UPDATE forbidden.",
    retention="180 days (the audit trail for writes is audit_log + proposal/approval/execution).",
    recovery="Not rebuildable; debugging value only.",
    migration="Depends on agent_session and action_proposal.",
    example={"tenant_id": T, "session_id": "5a1f...-uuid", "turn_index": 2, "tool_name": "get_forecast", "tool_version": "get_forecast@1", "read_only": True, "requires_approval": False, "arguments": {"product_id": AMOX}, "outcome": "executed", "result_summary": {"forecast_id": "c0a8...", "horizon_days": 14}, "duration_ms": 18, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"})

action_approval = Table(
    schema="agent", name="action_approval", cls="ActionApproval", tier="A", scope="MVP",
    purpose="Immutable human decision (approve or reject) on a specific proposal payload. The composite FK to (proposal id, arguments_sha256) means an approval can only ever exist for the exact payload that was proposed.",
    cols=[ID(), TENANT(),
          col("proposal_id", "UUID", "Proposal decided."),
          col("approval_round", "SMALLINT", "1 for the first decision; 2+ only for a fresh human re-approval after the proposal failed with an unknown outcome (D-43). A round covers the worker's same-key retries while the proposal is executing; once the proposal is failed, only a new round re-opens it.", default="1"),
          col("decision", "TEXT", "approved | rejected."),
          col("decided_by_actor_id", "TEXT", "Authenticated approver (JWT sub). Never a job actor: CHECK rejects 'system:' ids (D-45)."),
          col("decider_scopes", "TEXT[]", "Scopes in the approver's JWT at decision time (must include agent:approve)."),
          col("arguments_sha256", "CHAR(64)", "Hash of the payload the approver saw; must equal the proposal's (composite FK)."),
          col("reason_code", "TEXT", "Optional fixed code for a rejection (no free text, no PII).", null=True),
          col("decided_at", "TIMESTAMPTZ", "Decision time (UTC), always the server time of the insert (set by trigger). The approval is valid while now() <= decided_at + 24 h (D-44).", default="now()"),
          TRACE(null=False)],
    pk=["id"],
    uniques=[("uq_action_approval__proposal_round", ["tenant_id", "proposal_id", "approval_round"]),
             ("uq_action_approval__id_proposal_hash", ["tenant_id", "id", "proposal_id", "arguments_sha256"])],
    fks=[FK("fk_action_approval__action_proposal", ["tenant_id", "proposal_id", "arguments_sha256"], "agent.action_proposal", ["tenant_id", "id", "arguments_sha256"], "RESTRICT", rel="proposal", back="approvals", note="binds the decision to the exact payload hash")],
    checks=[("ck_action_approval__round", "approval_round >= 1"),
            ("ck_action_approval__decision", "decision IN ('approved','rejected')"),
            ("ck_action_approval__scope", "'agent:approve' = ANY(decider_scopes)"),
            ("ck_action_approval__reason_code", "reason_code IS NULL OR reason_code IN ('too_much','wrong_supplier','not_needed','stock_arriving','other')"),
            ("ck_action_approval__actor", "char_length(decided_by_actor_id) BETWEEN 1 AND 128"),
            ("ck_action_approval__human_actor", "left(decided_by_actor_id, 7) <> 'system:'")],
    idxs=[Idx("ix_action_approval__tenant_actor_decided", ["tenant_id", "decided_by_actor_id", "decided_at"], why="Audit by approver.")],
    append_only="update_delete", grants="SI", worker_grants="S",
    custom_triggers=["""CREATE OR REPLACE FUNCTION agent.guard_approval_insert() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_status text;
  v_expires timestamptz;
BEGIN
  SELECT status, expires_at INTO v_status, v_expires FROM agent.action_proposal
   WHERE tenant_id = NEW.tenant_id AND id = NEW.proposal_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'unknown proposal'; END IF;
  IF NEW.approval_round = 1 AND v_status <> 'pending' THEN
    RAISE EXCEPTION USING MESSAGE = 'first decision requires status pending (is ' || v_status || ')', ERRCODE = 'check_violation';
  END IF;
  IF NEW.approval_round > 1 AND v_status <> 'failed' THEN
    RAISE EXCEPTION USING MESSAGE = 're-approval requires status failed (is ' || v_status || ')', ERRCODE = 'check_violation';
  END IF;
  IF NEW.approval_round = 1 AND NEW.decision = 'approved' AND now() > v_expires THEN
    RAISE EXCEPTION USING MESSAGE = 'proposal expired at ' || v_expires::text, ERRCODE = 'check_violation';
  END IF;
  -- D-44: the 24 h validity window starts at the server time of this decision; a client-supplied value is ignored.
  NEW.decided_at := now();
  RETURN NEW;
END
$fn$;""",
        "CREATE TRIGGER trg_action_approval_guard_insert BEFORE INSERT ON agent.action_approval FOR EACH ROW EXECUTE FUNCTION agent.guard_approval_insert();"],
    writer="Approval Engine (Ibrahim) via `POST /agent/proposals/{id}/approve|reject`, scope `agent:approve`.",
    readers="Audit, ApprovalModal history, execution (FK).",
    tenancy=TENANCY_STD,
    timestamps="`decided_at` UTC.",
    access="Insert once per decision; read by proposal or approver.",
    mutability="Immutable: UPDATE/DELETE rejected.",
    retention="Audit tier (no purge in MVP).",
    recovery="Not rebuildable; audit-critical backup tier.",
    migration="Depends on action_proposal (unique on (tenant_id, id, arguments_sha256)).",
    example={"tenant_id": T, "proposal_id": "d4c1...-uuid", "approval_round": 1, "decision": "approved", "decided_by_actor_id": "u-3f2a...", "decider_scopes": ["agent:approve", "inventory:read"], "arguments_sha256": "5e88...(64 hex)", "decided_at": "2026-09-24T10:18:10Z"})

action_execution = Table(
    schema="agent", name="action_execution", cls="ActionExecution", tier="A", scope="MVP",
    purpose="One row per execution attempt of an approved proposal against the Canonical API. Records the ActionResult (success/failed, reason), outcome certainty and the ERP object created. Partial unique indexes make a second concurrent attempt or a second success impossible.",
    cols=[ID(), TENANT(),
          col("proposal_id", "UUID", "Proposal executed."),
          col("approval_id", "UUID", "Approval that authorised this attempt: always the latest decision round (D-43)."),
          col("attempt_no", "SMALLINT", "1, 2, ... per proposal."),
          col("arguments_sha256", "CHAR(64)", "Hash of the payload actually sent; must equal the approved hash (composite FK)."),
          col("idempotency_key", "UUID", "Same key as the proposal; sent as Idempotency-Key (composite FK)."),
          col("on_behalf_of_actor_id", "TEXT", "User whose JWT scopes were used for the Canonical write."),
          col("status", "TEXT", "started | succeeded | failed.", default="'started'"),
          col("outcome_certainty", "TEXT", "For failed: definitive (adapter rejected, no ERP write) | unknown (timeout/5xx; the write may have happened).", null=True),
          col("started_at", "TIMESTAMPTZ", "Attempt start (UTC).", default="now()"),
          col("completed_at", "TIMESTAMPTZ", "Attempt end (UTC).", null=True),
          col("duration_ms", "INTEGER", "Canonical call latency.", null=True),
          col("canonical_http_status", "SMALLINT", "HTTP status from the Canonical API.", null=True),
          col("external_ref_type", "TEXT", "Kind of ERP object created (purchase_order).", null=True),
          col("external_ref_id", "TEXT", "ERP identifier/number of the created object (e.g. PO #1234).", null=True),
          col("error_code", "TEXT", "Canonical error envelope code.", null=True),
          col("error_message", "TEXT", "Sanitised message (<= 500 chars).", null=True),
          col("result", "JSONB", "ActionResult JSON {status, reason, ...} validated against the ai-output schema.", null=True, jsonb="object"),
          TRACE(null=False)],
    pk=["id"], fk_target=True,
    uniques=[("uq_action_execution__proposal_attempt", ["tenant_id", "proposal_id", "attempt_no"])],
    fks=[FK("fk_action_execution__action_approval", ["tenant_id", "approval_id", "proposal_id", "arguments_sha256"], "agent.action_approval", ["tenant_id", "id", "proposal_id", "arguments_sha256"], "RESTRICT", rel="approval", back="executions", note="executed payload hash must equal the approved hash"),
         FK("fk_action_execution__action_proposal", ["tenant_id", "proposal_id", "idempotency_key"], "agent.action_proposal", ["tenant_id", "id", "idempotency_key"], "RESTRICT", rel="proposal", back="executions", note="same idempotency key on every attempt")],
    checks=[("ck_action_execution__attempt", "attempt_no >= 1"),
            ("ck_action_execution__status", "status IN ('started','succeeded','failed')"),
            ("ck_action_execution__certainty", "outcome_certainty IS NULL OR outcome_certainty IN ('definitive','unknown')"),
            ("ck_action_execution__completion", "(status = 'started') = (completed_at IS NULL)"),
            ("ck_action_execution__failed_fields", "status <> 'failed' OR (outcome_certainty IS NOT NULL AND error_code IS NOT NULL)"),
            ("ck_action_execution__success_clean", "status <> 'succeeded' OR error_code IS NULL"),
            ("ck_action_execution__ref_type", "external_ref_type IS NULL OR external_ref_type IN ('purchase_order')"),
            ("ck_action_execution__message_len", "error_message IS NULL OR char_length(error_message) <= 500"),
            ("ck_action_execution__duration", "duration_ms IS NULL OR duration_ms >= 0")],
    idxs=[Idx("uq_action_execution__one_inflight", ["tenant_id", "proposal_id"], unique=True, where="status = 'started'", why="Never two concurrent attempts for one proposal."),
          Idx("uq_action_execution__one_success", ["tenant_id", "proposal_id"], unique=True, where="status = 'succeeded'", why="A proposal can succeed at most once: database-level duplicate-write guard."),
          Idx("ix_action_execution__tenant_started", ["tenant_id", "started_at"], why="Recent executions."),
          Idx("ix_action_execution__trace", ["trace_id"], why="Join by trace.")],
    append_only="delete", grants="SIU", worker_grants="SIU",
    custom_triggers=["""CREATE OR REPLACE FUNCTION agent.guard_execution() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  v_mutable text[] := ARRAY['status','outcome_certainty','completed_at','duration_ms','canonical_http_status','external_ref_type','external_ref_id','error_code','error_message','result'];
  v_decided timestamptz;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'started' THEN
      RAISE EXCEPTION 'execution must be inserted as started' USING ERRCODE = 'check_violation';
    END IF;
    SELECT a.decided_at INTO v_decided FROM agent.action_approval a
     WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.approval_id AND a.decision = 'approved';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'execution requires an approved decision' USING ERRCODE = 'check_violation';
    END IF;
    -- D-44: every attempt (first send or worker retry) starts only while its approval is valid.
    IF now() > v_decided + interval '24 hours' THEN
      RAISE EXCEPTION USING MESSAGE = 'approval expired at ' || (v_decided + interval '24 hours')::text, ERRCODE = 'check_violation';
    END IF;
    -- FOR SHARE serialises with guard_approval_insert (FOR UPDATE), so no new round can appear mid-check.
    PERFORM 1 FROM agent.action_proposal p
      WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.proposal_id AND p.status = 'executing' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'execution requires the proposal to be executing' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM agent.action_approval a
                WHERE a.tenant_id = NEW.tenant_id AND a.proposal_id = NEW.proposal_id
                  AND a.approval_round > (SELECT b.approval_round FROM agent.action_approval b
                                           WHERE b.tenant_id = NEW.tenant_id AND b.id = NEW.approval_id)) THEN
      RAISE EXCEPTION 'execution must use the latest decision round' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'started' THEN
    RAISE EXCEPTION 'execution row is final' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status NOT IN ('succeeded','failed') THEN
    RAISE EXCEPTION 'execution may only complete as succeeded or failed' USING ERRCODE = 'check_violation';
  END IF;
  IF (to_jsonb(NEW) - v_mutable) IS DISTINCT FROM (to_jsonb(OLD) - v_mutable) THEN
    RAISE EXCEPTION 'only completion fields of an execution may change' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$fn$;""",
        "CREATE TRIGGER trg_action_execution_guard BEFORE INSERT OR UPDATE ON agent.action_execution FOR EACH ROW EXECUTE FUNCTION agent.guard_execution();"],
    writer="Approval Engine / execution step after approval (Ibrahim; write path contract with Yassin).",
    readers="UI (ActionResult), audit, evaluation.",
    tenancy=TENANCY_STD,
    timestamps="UTC.",
    jsonb_note="`result`: Pydantic `ActionResult {status, reason, external_ref?}`; error text sanitised; no raw ERP payloads.",
    access="Insert 'started' then complete once; read by proposal.",
    mutability="Inserted as started (proposal executing, latest approved decision round, D-43); completion fields may be set once; row is then final. DELETE forbidden.",
    retention="Audit tier (no purge in MVP).",
    recovery="Not rebuildable; audit-critical backup tier.",
    migration="Depends on action_approval and action_proposal. The failed-with-unknown-outcome retry path needs a new approval round (D-43) and must reuse the proposal's idempotency key (enforced by FK).",
    example={"tenant_id": T, "proposal_id": "d4c1...-uuid", "approval_id": "b9e2...-uuid", "attempt_no": 1, "arguments_sha256": "5e88...(64 hex)", "idempotency_key": "e7f0c9c4-2a1b-4d3e-9f55-000000000001", "on_behalf_of_actor_id": "u-3f2a...", "status": "succeeded", "completed_at": "2026-09-24T10:18:11Z", "duration_ms": 412, "canonical_http_status": 201, "external_ref_type": "purchase_order", "external_ref_id": "PO-1234", "result": {"status": "success", "po_status": "draft"}})

embedding = Table(
    schema="rag", name="embedding", cls="Embedding", tier="R", scope="FUTURE",
    purpose="FUTURE ONLY. Document chunks and embeddings (pgvector) for unstructured text such as policies or drug leaflets. Never holds sales or inventory data. Not created by MVP migrations.",
    cols=[ID(), TENANT(),
          col("source_uri", "TEXT", "Document identifier (file/URL) in the knowledge base."),
          col("source_sha256", "CHAR(64)", "Hash of the source document version."),
          col("chunk_index", "INTEGER", "Chunk order within the document."),
          col("content", "TEXT", "Chunk text."),
          col("embedding", "VECTOR(1536)", "Embedding vector. Dimension depends on the embedding model (OD-18)."),
          col("metadata", "JSONB", "Title, page, language.", default=EJ, jsonb="object"),
          CREATED()],
    pk=["id"],
    uniques=[("uq_embedding__source_chunk", ["tenant_id", "source_uri", "source_sha256", "chunk_index"])],
    checks=[("ck_embedding__chunk", "chunk_index >= 0")],
    idxs=[Idx("ix_embedding__tenant_source", ["tenant_id", "source_uri"], why="Delete/refresh a document.")],
    custom_triggers=["CREATE INDEX ix_embedding__hnsw_cosine ON rag.embedding USING hnsw (embedding vector_cosine_ops);"],
    grants="SIUD",
    writer="RAG ingestion job (future).", readers="LLM layer retrieval (future).",
    tenancy=TENANCY_STD + " Retrieval must filter by tenant_id before similarity ranking.",
    timestamps="UTC.", jsonb_note="`metadata`: object, free-form but size-bounded by the writer.",
    access="Top-k cosine search filtered by tenant.", mutability="Re-ingest replaces chunks of a document version.",
    retention="Until the source document is removed.", recovery="Rebuildable by re-embedding sources.",
    migration="Separate optional file; requires `CREATE EXTENSION vector` (not installed in MVP).",
    example={"tenant_id": T, "source_uri": "kb/returns-policy.pdf", "chunk_index": 0, "content": "Returns are accepted within 14 days ..."})

TABLES_AGENT = [llm_usage, audit_log, agent_session, agent_message, action_proposal, agent_action, action_approval, action_execution]
TABLES_FUTURE = [embedding]
