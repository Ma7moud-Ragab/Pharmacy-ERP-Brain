-- 0004_audit_agent: audit + agent schemas

-- ---- audit.llm_usage ----
CREATE TABLE audit.llm_usage (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_route TEXT,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    tokens_cached_in INTEGER,
    estimated_cost_usd NUMERIC(12,6) NOT NULL,
    pricing_version TEXT,
    latency_ms INTEGER NOT NULL,
    cache_status TEXT NOT NULL DEFAULT 'miss',
    outcome TEXT NOT NULL,
    error_code TEXT,
    schema_valid BOOLEAN,
    prompt_sha256 CHAR(64),
    actor_id TEXT,
    session_id UUID,
    tool_step SMALLINT,
    trace_id CHAR(32) NOT NULL,
    span_id CHAR(16),
    CONSTRAINT pk_llm_usage PRIMARY KEY (id),
    CONSTRAINT uq_llm_usage__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_llm_usage__purpose CHECK (purpose IN ('explanation','assistant_chat','agent_reasoning','briefing','other')),
    CONSTRAINT ck_llm_usage__route CHECK (model_route IS NULL OR model_route IN ('template','small','large')),
    CONSTRAINT ck_llm_usage__tokens CHECK (tokens_in >= 0 AND tokens_out >= 0 AND (tokens_cached_in IS NULL OR (tokens_cached_in >= 0 AND tokens_cached_in <= tokens_in))),
    CONSTRAINT ck_llm_usage__cost CHECK (estimated_cost_usd >= 0),
    CONSTRAINT ck_llm_usage__latency CHECK (latency_ms >= 0),
    CONSTRAINT ck_llm_usage__cache_status CHECK (cache_status IN ('miss','hit','not_cacheable')),
    CONSTRAINT ck_llm_usage__outcome CHECK (outcome IN ('success','error','timeout','invalid_output','refused')),
    CONSTRAINT ck_llm_usage__span_format CHECK (span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'),
    CONSTRAINT ck_llm_usage__prompt_sha256_format CHECK (prompt_sha256 IS NULL OR prompt_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_llm_usage__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_llm_usage__tenant_occurred ON audit.llm_usage (tenant_id, occurred_at);
CREATE INDEX ix_llm_usage__tenant_purpose_occurred ON audit.llm_usage (tenant_id, purpose, occurred_at);
CREATE INDEX ix_llm_usage__trace ON audit.llm_usage (trace_id);
COMMENT ON TABLE audit.llm_usage IS 'One row per LLM layer call (and per cache hit that avoided a call): provider, model, prompt version, tokens, estimated cost, latency, outcome, trace. Feeds `/brain/admin/cost`. Stores NO prompt or completion text.';
COMMENT ON COLUMN audit.llm_usage.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN audit.llm_usage.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN audit.llm_usage.occurred_at IS 'Call time (UTC).';
COMMENT ON COLUMN audit.llm_usage.purpose IS 'explanation | assistant_chat | agent_reasoning | briefing | other.';
COMMENT ON COLUMN audit.llm_usage.provider IS 'LLM provider id (provider is an open decision, OD-18).';
COMMENT ON COLUMN audit.llm_usage.model IS 'Exact model identifier returned/used.';
COMMENT ON COLUMN audit.llm_usage.model_route IS 'template | small | large (model routing decision).';
COMMENT ON COLUMN audit.llm_usage.prompt_name IS 'Prompt file name from `llm/prompts/`.';
COMMENT ON COLUMN audit.llm_usage.prompt_version IS 'Prompt version (git-tracked).';
COMMENT ON COLUMN audit.llm_usage.tokens_in IS 'Input tokens.';
COMMENT ON COLUMN audit.llm_usage.tokens_out IS 'Output tokens.';
COMMENT ON COLUMN audit.llm_usage.tokens_cached_in IS 'Input tokens served from the provider''s prompt cache, if reported.';
COMMENT ON COLUMN audit.llm_usage.estimated_cost_usd IS 'Estimated cost in USD (micro-dollar precision).';
COMMENT ON COLUMN audit.llm_usage.pricing_version IS 'Price table used for the estimate.';
COMMENT ON COLUMN audit.llm_usage.latency_ms IS 'End-to-end latency.';
COMMENT ON COLUMN audit.llm_usage.cache_status IS 'miss | hit (response cache, zero tokens) | not_cacheable.';
COMMENT ON COLUMN audit.llm_usage.outcome IS 'success | error | timeout | invalid_output | refused.';
COMMENT ON COLUMN audit.llm_usage.error_code IS 'Short error code when outcome is not success.';
COMMENT ON COLUMN audit.llm_usage.schema_valid IS 'Whether the structured output validated against its JSON schema.';
COMMENT ON COLUMN audit.llm_usage.prompt_sha256 IS 'Hash of the rendered prompt (dedupe/cache analysis). The text itself is never stored.';
COMMENT ON COLUMN audit.llm_usage.actor_id IS 'JWT sub of the requesting user (pseudonymous), for per-user cost.';
COMMENT ON COLUMN audit.llm_usage.session_id IS 'agent_session id. SOFT reference (no FK): usage rows outlive sessions.';
COMMENT ON COLUMN audit.llm_usage.tool_step IS 'Step number inside an agent run.';
COMMENT ON COLUMN audit.llm_usage.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN audit.llm_usage.span_id IS 'W3C span-id.';
CREATE TRIGGER trg_llm_usage_forbid_update BEFORE UPDATE ON audit.llm_usage FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- audit.audit_log ----
CREATE TABLE audit.audit_log (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    seq BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    tenant_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    on_behalf_of_actor_id TEXT,
    approved_by_actor_id TEXT,
    tool_name TEXT,
    subject_type TEXT,
    subject_id UUID,
    arguments_sha256 CHAR(64),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    trace_id CHAR(32) NOT NULL,
    span_id CHAR(16),
    request_id TEXT,
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT uq_audit_log__seq UNIQUE (seq),
    CONSTRAINT ck_audit_log__event_type CHECK (event_type ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$'),
    CONSTRAINT ck_audit_log__outcome CHECK (outcome IN ('success','failure','denied','info')),
    CONSTRAINT ck_audit_log__actor_type CHECK (actor_type IN ('user','agent','system')),
    CONSTRAINT ck_audit_log__actor_required CHECK (actor_type = 'system' OR actor_id IS NOT NULL),
    CONSTRAINT ck_audit_log__subject_pair CHECK ((subject_type IS NULL) = (subject_id IS NULL)),
    CONSTRAINT ck_audit_log__details_size CHECK (octet_length(details::text) <= 8192),
    CONSTRAINT ck_audit_log__span_format CHECK (span_id IS NULL OR span_id ~ '^[0-9a-f]{16}$'),
    CONSTRAINT ck_audit_log__arguments_sha256_format CHECK (arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_audit_log__details_type CHECK (jsonb_typeof(details) = 'object'),
    CONSTRAINT ck_audit_log__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_audit_log__tenant_occurred ON audit.audit_log (tenant_id, occurred_at);
CREATE INDEX ix_audit_log__trace ON audit.audit_log (trace_id);
CREATE INDEX ix_audit_log__tenant_actor_occurred ON audit.audit_log (tenant_id, actor_id, occurred_at);
CREATE INDEX ix_audit_log__subject ON audit.audit_log (tenant_id, subject_type, subject_id, occurred_at);
COMMENT ON TABLE audit.audit_log IS 'Brain audit trail: who proposed, approved/rejected, executed, which tool, which payload fingerprint, outcome, trace. Distinct from `erp_db.AuditLog` (human changes in the ERP). Append-only.';
COMMENT ON COLUMN audit.audit_log.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN audit.audit_log.seq IS 'Monotonic ordering / keyset-pagination key.';
COMMENT ON COLUMN audit.audit_log.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN audit.audit_log.occurred_at IS 'Event time (UTC).';
COMMENT ON COLUMN audit.audit_log.event_type IS 'Dotted lowercase vocabulary, e.g. proposal.created, proposal.approved, proposal.rejected, execution.succeeded, tool.denied, model.status_changed.';
COMMENT ON COLUMN audit.audit_log.outcome IS 'success | failure | denied | info.';
COMMENT ON COLUMN audit.audit_log.actor_type IS 'user | agent | system.';
COMMENT ON COLUMN audit.audit_log.actor_id IS 'JWT sub for users; session id for agent; component name for system.';
COMMENT ON COLUMN audit.audit_log.on_behalf_of_actor_id IS 'User on whose behalf an agent acted.';
COMMENT ON COLUMN audit.audit_log.approved_by_actor_id IS 'Approver (JWT sub) when relevant.';
COMMENT ON COLUMN audit.audit_log.tool_name IS 'Registry tool name when relevant.';
COMMENT ON COLUMN audit.audit_log.subject_type IS 'Kind of Brain object the event concerns (action_proposal, model_registry, ...).';
COMMENT ON COLUMN audit.audit_log.subject_id IS 'Brain object id. SOFT reference (polymorphic, no FK): audit rows must outlive subjects.';
COMMENT ON COLUMN audit.audit_log.arguments_sha256 IS 'Fingerprint of the exact action payload involved.';
COMMENT ON COLUMN audit.audit_log.details IS 'Sanitised allow-listed context (status from/to, model_version, rule_version, result summary).';
COMMENT ON COLUMN audit.audit_log.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN audit.audit_log.span_id IS 'W3C span-id.';
COMMENT ON COLUMN audit.audit_log.request_id IS 'HTTP request id.';
CREATE TRIGGER trg_audit_log_forbid_update_delete BEFORE UPDATE OR DELETE ON audit.audit_log FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update_delete();
CREATE TRIGGER trg_audit_log_forbid_truncate BEFORE TRUNCATE ON audit.audit_log FOR EACH STATEMENT EXECUTE FUNCTION public.brain_forbid_truncate();

-- ---- agent.agent_session ----
CREATE TABLE agent.agent_session (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_actor_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    allowed_tools TEXT[] NOT NULL DEFAULT '{}'::text[],
    max_writes SMALLINT NOT NULL DEFAULT 3,
    write_proposals_count SMALLINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_agent_session PRIMARY KEY (id),
    CONSTRAINT uq_agent_session__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_agent_session__user CHECK (char_length(user_actor_id) BETWEEN 1 AND 128),
    CONSTRAINT ck_agent_session__status CHECK (status IN ('active','closed','expired')),
    CONSTRAINT ck_agent_session__state_size CHECK (octet_length(state::text) <= 16384),
    CONSTRAINT ck_agent_session__max_writes CHECK (max_writes BETWEEN 0 AND 20),
    CONSTRAINT ck_agent_session__write_cap CHECK (write_proposals_count >= 0 AND write_proposals_count <= max_writes),
    CONSTRAINT ck_agent_session__state_type CHECK (jsonb_typeof(state) = 'object'),
    CONSTRAINT ck_agent_session__trace_id_format CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ix_agent_session__user_activity ON agent.agent_session (tenant_id, user_actor_id, last_activity_at);
CREATE INDEX ix_agent_session__active_expiry ON agent.agent_session (tenant_id, expires_at) WHERE status = 'active';
COMMENT ON TABLE agent.agent_session IS 'Conversation/agent session: owner, small working context, tool allow-list, write cap, expiry. Survives a browser refresh. Session-scoped memory only (no cross-session memory in MVP).';
COMMENT ON COLUMN agent.agent_session.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_session.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_session.user_actor_id IS 'JWT `sub` of the user who owns the session.';
COMMENT ON COLUMN agent.agent_session.status IS 'active | closed | expired.';
COMMENT ON COLUMN agent.agent_session.state IS 'Compact working context (focused product ids, last intent). No PII, no raw ERP rows. <= 16 KB.';
COMMENT ON COLUMN agent.agent_session.allowed_tools IS 'Per-session tool allow-list (guardrail).';
COMMENT ON COLUMN agent.agent_session.max_writes IS 'Maximum write proposals per session (source example: 3).';
COMMENT ON COLUMN agent.agent_session.write_proposals_count IS 'Write proposals created so far; the CHECK against max_writes makes the cap a database guarantee.';
COMMENT ON COLUMN agent.agent_session.started_at IS 'Session start (UTC).';
COMMENT ON COLUMN agent.agent_session.last_activity_at IS 'Last turn (UTC).';
COMMENT ON COLUMN agent.agent_session.expires_at IS 'Inactivity expiry (UTC).';
COMMENT ON COLUMN agent.agent_session.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN agent.agent_session.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.agent_session.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN agent.agent_session.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_agent_session_set_updated_at BEFORE UPDATE ON agent.agent_session FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_agent_session_guard_update BEFORE UPDATE ON agent.agent_session FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'state', 'allowed_tools', 'max_writes', 'write_proposals_count', 'last_activity_at', 'expires_at', 'row_version', 'updated_at');

-- ---- agent.agent_message ----
CREATE TABLE agent.agent_message (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    pii_scrubbed BOOLEAN NOT NULL DEFAULT false,
    structured JSONB,
    llm_usage_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_agent_message PRIMARY KEY (id),
    CONSTRAINT uq_agent_message__session_turn UNIQUE (session_id, turn_index),
    CONSTRAINT ck_agent_message__turn CHECK (turn_index >= 0),
    CONSTRAINT ck_agent_message__role CHECK (role IN ('user','assistant','tool')),
    CONSTRAINT ck_agent_message__content_len CHECK (char_length(content) <= 4000),
    CONSTRAINT ck_agent_message__scrubbed CHECK (pii_scrubbed),
    CONSTRAINT ck_agent_message__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_agent_message__structured_type CHECK (structured IS NULL OR jsonb_typeof(structured) = 'object'),
    CONSTRAINT fk_agent_message__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_agent_message__tenant_expires ON agent.agent_message (tenant_id, expires_at);
CREATE INDEX ix_agent_message__tenant_session ON agent.agent_message (tenant_id, session_id);
COMMENT ON TABLE agent.agent_message IS 'Recent conversation turns (the ''last N messages'' memory). Content is PII-scrubbed and size-bounded; rows carry their own expiry and are hard-deleted on schedule.';
COMMENT ON COLUMN agent.agent_message.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_message.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_message.session_id IS 'Owning session.';
COMMENT ON COLUMN agent.agent_message.turn_index IS '0-based turn number within the session.';
COMMENT ON COLUMN agent.agent_message.role IS 'user | assistant | tool.';
COMMENT ON COLUMN agent.agent_message.content IS 'Scrubbed text (<= 4000 chars). Assistant turns hold the human-readable explanation.';
COMMENT ON COLUMN agent.agent_message.pii_scrubbed IS 'Writer''s attestation that the PII scrubber ran. CHECK forces TRUE.';
COMMENT ON COLUMN agent.agent_message.structured IS 'Typed Explanation JSON or compact tool-result summary (never raw ERP rows).';
COMMENT ON COLUMN agent.agent_message.llm_usage_id IS 'audit.llm_usage row for assistant turns (soft reference, no FK).';
COMMENT ON COLUMN agent.agent_message.created_at IS 'Turn time (UTC).';
COMMENT ON COLUMN agent.agent_message.expires_at IS 'Purge time for this turn (UTC).';
CREATE TRIGGER trg_agent_message_forbid_update BEFORE UPDATE ON agent.agent_message FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- agent.action_proposal ----
CREATE TABLE agent.action_proposal (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID,
    requested_by_actor_id TEXT,
    proposed_by TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    arguments JSONB NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT true,
    policy_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    recommendation_id UUID,
    risk_assessment_id UUID,
    llm_usage_id UUID,
    idempotency_key UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    trace_id CHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_action_proposal PRIMARY KEY (id),
    CONSTRAINT uq_action_proposal__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_action_proposal__tenant_idempotency UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT uq_action_proposal__id_hash UNIQUE (tenant_id, id, arguments_sha256),
    CONSTRAINT uq_action_proposal__id_idem UNIQUE (tenant_id, id, idempotency_key),
    CONSTRAINT ck_action_proposal__proposed_by CHECK (proposed_by IN ('rules','agent')),
    CONSTRAINT ck_action_proposal__agent_context CHECK (proposed_by <> 'agent' OR (session_id IS NOT NULL AND requested_by_actor_id IS NOT NULL)),
    CONSTRAINT ck_action_proposal__requires_approval CHECK (requires_approval),
    CONSTRAINT ck_action_proposal__status CHECK (status IN ('pending','approved','rejected','expired','cancelled','executing','succeeded','failed')),
    CONSTRAINT ck_action_proposal__tool_len CHECK (char_length(tool_name) BETWEEN 1 AND 100),
    CONSTRAINT ck_action_proposal__reason_len CHECK (char_length(reason) BETWEEN 1 AND 500),
    CONSTRAINT ck_action_proposal__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_action_proposal__args_size CHECK (octet_length(arguments::text) <= 32768),
    CONSTRAINT ck_action_proposal__arguments_type CHECK (jsonb_typeof(arguments) = 'object'),
    CONSTRAINT ck_action_proposal__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_proposal__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_proposal__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__recommendation FOREIGN KEY (tenant_id, recommendation_id) REFERENCES intel.recommendation (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__risk_assessment FOREIGN KEY (tenant_id, risk_assessment_id) REFERENCES intel.risk_assessment (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_proposal__llm_usage FOREIGN KEY (tenant_id, llm_usage_id) REFERENCES audit.llm_usage (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_action_proposal__pending ON agent.action_proposal (tenant_id, created_at) WHERE status = 'pending';
CREATE INDEX ix_action_proposal__tenant_session ON agent.action_proposal (tenant_id, session_id, created_at);
CREATE INDEX ix_action_proposal__tenant_requester ON agent.action_proposal (tenant_id, requested_by_actor_id, created_at);
CREATE INDEX ix_action_proposal__tenant_recommendation ON agent.action_proposal (tenant_id, recommendation_id);
CREATE UNIQUE INDEX uq_action_proposal__live_per_recommendation ON agent.action_proposal (tenant_id, recommendation_id) WHERE recommendation_id IS NOT NULL AND status IN ('pending','approved','executing');
COMMENT ON TABLE agent.action_proposal IS 'The immutable proposed write (tool + arguments) awaiting a human decision, plus its lifecycle status. Arguments and their SHA-256 can never change after insert; approvals and executions are cryptographically bound to that hash by composite FKs.';
COMMENT ON COLUMN agent.action_proposal.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_proposal.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_proposal.session_id IS 'Session that produced the proposal. Required when proposed_by = ''agent''; NULL allowed for deterministic rule proposals (D-29).';
COMMENT ON COLUMN agent.action_proposal.requested_by_actor_id IS 'JWT sub of the user who asked for the proposal. Required when proposed_by = ''agent''; NULL allowed for rule proposals created by the system (D-29).';
COMMENT ON COLUMN agent.action_proposal.proposed_by IS 'rules (deterministic, built from a recommendation without the LLM, D-18) | agent (conversational path). Set explicitly; no default (D-29).';
COMMENT ON COLUMN agent.action_proposal.tool_name IS 'Registry tool name (e.g. create_purchase_order).';
COMMENT ON COLUMN agent.action_proposal.tool_version IS 'Registry schema version of the tool, e.g. ''create_purchase_order@1''.';
COMMENT ON COLUMN agent.action_proposal.arguments IS 'Validated arguments exactly as they will be sent. Immutable.';
COMMENT ON COLUMN agent.action_proposal.arguments_sha256 IS 'SHA-256 (lowercase hex) of the RFC 8785 (JCS) canonical JSON of `arguments` (D-13; golden vectors in contracts/fixtures/hash). Approvals bind to it.';
COMMENT ON COLUMN agent.action_proposal.requires_approval IS 'Always TRUE in MVP (every write needs a human).';
COMMENT ON COLUMN agent.action_proposal.policy_version IS 'Static policy version that returned require-approval.';
COMMENT ON COLUMN agent.action_proposal.reason IS 'Templated human-readable reason (<= 500 chars), e.g. ''high stockout risk (cover 1.7d < lead time 5d)''. Generated by code, not by the LLM.';
COMMENT ON COLUMN agent.action_proposal.recommendation_id IS 'Recommendation the proposal was built from.';
COMMENT ON COLUMN agent.action_proposal.risk_assessment_id IS 'Risk assessment behind it. This is the API `insight_id` (OD-06).';
COMMENT ON COLUMN agent.action_proposal.llm_usage_id IS 'LLM call that proposed the tool call (which model proposed it).';
COMMENT ON COLUMN agent.action_proposal.idempotency_key IS 'Generated once at proposal creation; sent as `Idempotency-Key` on every execution attempt of this proposal.';
COMMENT ON COLUMN agent.action_proposal.status IS 'pending | approved | rejected | expired | cancelled | executing | succeeded | failed.';
COMMENT ON COLUMN agent.action_proposal.status_changed_at IS 'Last status change (set by trigger).';
COMMENT ON COLUMN agent.action_proposal.expires_at IS 'Approval deadline; after it a pending proposal cannot be approved.';
COMMENT ON COLUMN agent.action_proposal.row_version IS 'Optimistic-concurrency counter; incremented on every UPDATE by the application.';
COMMENT ON COLUMN agent.action_proposal.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.action_proposal.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN agent.action_proposal.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_action_proposal_set_updated_at BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();
CREATE TRIGGER trg_action_proposal_guard_update BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_guard_update('status', 'status_changed_at', 'row_version', 'updated_at');
CREATE TRIGGER trg_action_proposal_forbid_delete BEFORE DELETE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();

-- ---- agent.agent_action ----
CREATE TABLE agent.agent_action (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL,
    turn_index INTEGER,
    tool_name TEXT NOT NULL,
    tool_version TEXT,
    read_only BOOLEAN,
    requires_approval BOOLEAN,
    arguments JSONB,
    arguments_sha256 CHAR(64),
    outcome TEXT NOT NULL,
    proposal_id UUID,
    result_summary JSONB,
    error_code TEXT,
    duration_ms INTEGER,
    llm_usage_id UUID,
    trace_id CHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_agent_action PRIMARY KEY (id),
    CONSTRAINT ck_agent_action__outcome CHECK (outcome IN ('executed','pending_approval','denied_policy','rejected_unknown_tool','rejected_invalid_arguments','rejected_scope','error')),
    CONSTRAINT ck_agent_action__tool_len CHECK (char_length(tool_name) BETWEEN 1 AND 100),
    CONSTRAINT ck_agent_action__pending_has_proposal CHECK ((outcome = 'pending_approval') = (proposal_id IS NOT NULL)),
    CONSTRAINT ck_agent_action__write_args_on_proposal CHECK (proposal_id IS NULL OR arguments IS NULL),
    CONSTRAINT ck_agent_action__unknown_tool CHECK (outcome <> 'rejected_unknown_tool' OR read_only IS NULL),
    CONSTRAINT ck_agent_action__args_size CHECK (arguments IS NULL OR octet_length(arguments::text) <= 8192),
    CONSTRAINT ck_agent_action__duration CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ck_agent_action__arguments_type CHECK (arguments IS NULL OR jsonb_typeof(arguments) = 'object'),
    CONSTRAINT ck_agent_action__arguments_sha256_format CHECK (arguments_sha256 IS NULL OR arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_agent_action__result_summary_type CHECK (result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'),
    CONSTRAINT ck_agent_action__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_agent_action__agent_session FOREIGN KEY (tenant_id, session_id) REFERENCES agent.agent_session (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_action__action_proposal FOREIGN KEY (tenant_id, proposal_id) REFERENCES agent.action_proposal (tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_agent_action__tenant_session_created ON agent.agent_action (tenant_id, session_id, created_at);
CREATE INDEX ix_agent_action__tenant_tool_created ON agent.agent_action (tenant_id, tool_name, created_at);
CREATE INDEX ix_agent_action__trace ON agent.agent_action (trace_id);
CREATE INDEX ix_agent_action__tenant_proposal ON agent.agent_action (tenant_id, proposal_id) WHERE proposal_id IS NOT NULL;
COMMENT ON TABLE agent.agent_action IS 'Log of every tool call the agent attempted, including rejected ones (unknown tool, bad arguments, policy deny). For write tools it only points at the ActionProposal; the authorisation and execution detail live in the proposal/approval/execution tables.';
COMMENT ON COLUMN agent.agent_action.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.agent_action.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.agent_action.session_id IS 'Session.';
COMMENT ON COLUMN agent.agent_action.turn_index IS 'Turn that triggered the call (no FK; messages expire).';
COMMENT ON COLUMN agent.agent_action.tool_name IS 'Tool name as attempted (kept even when not in the registry).';
COMMENT ON COLUMN agent.agent_action.tool_version IS 'Registry version when known.';
COMMENT ON COLUMN agent.agent_action.read_only IS 'Registry flag; NULL for unknown tools.';
COMMENT ON COLUMN agent.agent_action.requires_approval IS 'Registry flag; NULL for unknown tools.';
COMMENT ON COLUMN agent.agent_action.arguments IS 'Arguments for read tools only (<= 8 KB). NULL for write intents - those live on the proposal.';
COMMENT ON COLUMN agent.agent_action.arguments_sha256 IS 'Fingerprint of the arguments.';
COMMENT ON COLUMN agent.agent_action.outcome IS 'executed | pending_approval | denied_policy | rejected_unknown_tool | rejected_invalid_arguments | rejected_scope | error.';
COMMENT ON COLUMN agent.agent_action.proposal_id IS 'Set when outcome is pending_approval.';
COMMENT ON COLUMN agent.agent_action.result_summary IS 'Compact result facts (counts, ids). Never raw rows.';
COMMENT ON COLUMN agent.agent_action.error_code IS 'Short error code.';
COMMENT ON COLUMN agent.agent_action.duration_ms IS 'Tool latency.';
COMMENT ON COLUMN agent.agent_action.llm_usage_id IS 'LLM call that proposed the tool call (soft reference).';
COMMENT ON COLUMN agent.agent_action.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
COMMENT ON COLUMN agent.agent_action.created_at IS 'Call time (UTC).';
CREATE TRIGGER trg_agent_action_forbid_update BEFORE UPDATE ON agent.agent_action FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update();

-- ---- agent.action_approval ----
CREATE TABLE agent.action_approval (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_round SMALLINT NOT NULL DEFAULT 1,
    decision TEXT NOT NULL,
    decided_by_actor_id TEXT NOT NULL,
    decider_scopes TEXT[] NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    reason_code TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id CHAR(32) NOT NULL,
    CONSTRAINT pk_action_approval PRIMARY KEY (id),
    CONSTRAINT uq_action_approval__proposal_round UNIQUE (tenant_id, proposal_id, approval_round),
    CONSTRAINT uq_action_approval__id_proposal_hash UNIQUE (tenant_id, id, proposal_id, arguments_sha256),
    CONSTRAINT ck_action_approval__round CHECK (approval_round >= 1),
    CONSTRAINT ck_action_approval__decision CHECK (decision IN ('approved','rejected')),
    CONSTRAINT ck_action_approval__scope CHECK ('agent:approve' = ANY(decider_scopes)),
    CONSTRAINT ck_action_approval__reason_code CHECK (reason_code IS NULL OR reason_code IN ('too_much','wrong_supplier','not_needed','stock_arriving','other')),
    CONSTRAINT ck_action_approval__actor CHECK (char_length(decided_by_actor_id) BETWEEN 1 AND 128),
    CONSTRAINT ck_action_approval__human_actor CHECK (left(decided_by_actor_id, 7) <> 'system:'),
    CONSTRAINT ck_action_approval__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_approval__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_approval__action_proposal FOREIGN KEY (tenant_id, proposal_id, arguments_sha256) REFERENCES agent.action_proposal (tenant_id, id, arguments_sha256) ON DELETE RESTRICT
);
CREATE INDEX ix_action_approval__tenant_actor_decided ON agent.action_approval (tenant_id, decided_by_actor_id, decided_at);
COMMENT ON TABLE agent.action_approval IS 'Immutable human decision (approve or reject) on a specific proposal payload. The composite FK to (proposal id, arguments_sha256) means an approval can only ever exist for the exact payload that was proposed.';
COMMENT ON COLUMN agent.action_approval.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_approval.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_approval.proposal_id IS 'Proposal decided.';
COMMENT ON COLUMN agent.action_approval.approval_round IS '1 for the first decision; 2+ only for a fresh human re-approval after the proposal failed with an unknown outcome (D-43). A round covers the worker''s same-key retries while the proposal is executing; once the proposal is failed, only a new round re-opens it.';
COMMENT ON COLUMN agent.action_approval.decision IS 'approved | rejected.';
COMMENT ON COLUMN agent.action_approval.decided_by_actor_id IS 'Authenticated approver (JWT sub). Never a job actor: CHECK rejects ''system:'' ids (D-45).';
COMMENT ON COLUMN agent.action_approval.decider_scopes IS 'Scopes in the approver''s JWT at decision time (must include agent:approve).';
COMMENT ON COLUMN agent.action_approval.arguments_sha256 IS 'Hash of the payload the approver saw; must equal the proposal''s (composite FK).';
COMMENT ON COLUMN agent.action_approval.reason_code IS 'Optional fixed code for a rejection (no free text, no PII).';
COMMENT ON COLUMN agent.action_approval.decided_at IS 'Decision time (UTC), always the server time of the insert (set by trigger). The approval is valid while now() <= decided_at + 24 h (D-44).';
COMMENT ON COLUMN agent.action_approval.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
CREATE TRIGGER trg_action_approval_forbid_update_delete BEFORE UPDATE OR DELETE ON agent.action_approval FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_update_delete();
CREATE TRIGGER trg_action_approval_forbid_truncate BEFORE TRUNCATE ON agent.action_approval FOR EACH STATEMENT EXECUTE FUNCTION public.brain_forbid_truncate();

-- ---- agent.action_execution ----
CREATE TABLE agent.action_execution (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_id UUID NOT NULL,
    attempt_no SMALLINT NOT NULL,
    arguments_sha256 CHAR(64) NOT NULL,
    idempotency_key UUID NOT NULL,
    on_behalf_of_actor_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    outcome_certainty TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    canonical_http_status SMALLINT,
    external_ref_type TEXT,
    external_ref_id TEXT,
    error_code TEXT,
    error_message TEXT,
    result JSONB,
    trace_id CHAR(32) NOT NULL,
    CONSTRAINT pk_action_execution PRIMARY KEY (id),
    CONSTRAINT uq_action_execution__tenant_id_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_action_execution__proposal_attempt UNIQUE (tenant_id, proposal_id, attempt_no),
    CONSTRAINT ck_action_execution__attempt CHECK (attempt_no >= 1),
    CONSTRAINT ck_action_execution__status CHECK (status IN ('started','succeeded','failed')),
    CONSTRAINT ck_action_execution__certainty CHECK (outcome_certainty IS NULL OR outcome_certainty IN ('definitive','unknown')),
    CONSTRAINT ck_action_execution__completion CHECK ((status = 'started') = (completed_at IS NULL)),
    CONSTRAINT ck_action_execution__failed_fields CHECK (status <> 'failed' OR (outcome_certainty IS NOT NULL AND error_code IS NOT NULL)),
    CONSTRAINT ck_action_execution__success_clean CHECK (status <> 'succeeded' OR error_code IS NULL),
    CONSTRAINT ck_action_execution__ref_type CHECK (external_ref_type IS NULL OR external_ref_type IN ('purchase_order')),
    CONSTRAINT ck_action_execution__message_len CHECK (error_message IS NULL OR char_length(error_message) <= 500),
    CONSTRAINT ck_action_execution__duration CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ck_action_execution__arguments_sha256_format CHECK (arguments_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_action_execution__result_type CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    CONSTRAINT ck_action_execution__trace_id_format CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT fk_action_execution__action_approval FOREIGN KEY (tenant_id, approval_id, proposal_id, arguments_sha256) REFERENCES agent.action_approval (tenant_id, id, proposal_id, arguments_sha256) ON DELETE RESTRICT,
    CONSTRAINT fk_action_execution__action_proposal FOREIGN KEY (tenant_id, proposal_id, idempotency_key) REFERENCES agent.action_proposal (tenant_id, id, idempotency_key) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX uq_action_execution__one_inflight ON agent.action_execution (tenant_id, proposal_id) WHERE status = 'started';
CREATE UNIQUE INDEX uq_action_execution__one_success ON agent.action_execution (tenant_id, proposal_id) WHERE status = 'succeeded';
CREATE INDEX ix_action_execution__tenant_started ON agent.action_execution (tenant_id, started_at);
CREATE INDEX ix_action_execution__trace ON agent.action_execution (trace_id);
COMMENT ON TABLE agent.action_execution IS 'One row per execution attempt of an approved proposal against the Canonical API. Records the ActionResult (success/failed, reason), outcome certainty and the ERP object created. Partial unique indexes make a second concurrent attempt or a second success impossible.';
COMMENT ON COLUMN agent.action_execution.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN agent.action_execution.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN agent.action_execution.proposal_id IS 'Proposal executed.';
COMMENT ON COLUMN agent.action_execution.approval_id IS 'Approval that authorised this attempt: always the latest decision round (D-43).';
COMMENT ON COLUMN agent.action_execution.attempt_no IS '1, 2, ... per proposal.';
COMMENT ON COLUMN agent.action_execution.arguments_sha256 IS 'Hash of the payload actually sent; must equal the approved hash (composite FK).';
COMMENT ON COLUMN agent.action_execution.idempotency_key IS 'Same key as the proposal; sent as Idempotency-Key (composite FK).';
COMMENT ON COLUMN agent.action_execution.on_behalf_of_actor_id IS 'User whose JWT scopes were used for the Canonical write.';
COMMENT ON COLUMN agent.action_execution.status IS 'started | succeeded | failed.';
COMMENT ON COLUMN agent.action_execution.outcome_certainty IS 'For failed: definitive (adapter rejected, no ERP write) | unknown (timeout/5xx; the write may have happened).';
COMMENT ON COLUMN agent.action_execution.started_at IS 'Attempt start (UTC).';
COMMENT ON COLUMN agent.action_execution.completed_at IS 'Attempt end (UTC).';
COMMENT ON COLUMN agent.action_execution.duration_ms IS 'Canonical call latency.';
COMMENT ON COLUMN agent.action_execution.canonical_http_status IS 'HTTP status from the Canonical API.';
COMMENT ON COLUMN agent.action_execution.external_ref_type IS 'Kind of ERP object created (purchase_order).';
COMMENT ON COLUMN agent.action_execution.external_ref_id IS 'ERP identifier/number of the created object (e.g. PO #1234).';
COMMENT ON COLUMN agent.action_execution.error_code IS 'Canonical error envelope code.';
COMMENT ON COLUMN agent.action_execution.error_message IS 'Sanitised message (<= 500 chars).';
COMMENT ON COLUMN agent.action_execution.result IS 'ActionResult JSON {status, reason, ...} validated against the ai-output schema.';
COMMENT ON COLUMN agent.action_execution.trace_id IS 'W3C trace-id (32 lowercase hex) linking the work to the originating request/job.';
CREATE TRIGGER trg_action_execution_forbid_delete BEFORE DELETE ON agent.action_execution FOR EACH ROW EXECUTE FUNCTION public.brain_forbid_delete();

-- ---- custom guard triggers (created after all agent tables exist) ----
CREATE OR REPLACE FUNCTION agent.guard_proposal_transition() RETURNS trigger LANGUAGE plpgsql AS $fn$
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
$fn$;
CREATE TRIGGER trg_action_proposal_transition BEFORE UPDATE ON agent.action_proposal FOR EACH ROW EXECUTE FUNCTION agent.guard_proposal_transition();
CREATE OR REPLACE FUNCTION agent.guard_approval_insert() RETURNS trigger LANGUAGE plpgsql AS $fn$
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
$fn$;
CREATE TRIGGER trg_action_approval_guard_insert BEFORE INSERT ON agent.action_approval FOR EACH ROW EXECUTE FUNCTION agent.guard_approval_insert();
CREATE OR REPLACE FUNCTION agent.guard_execution() RETURNS trigger LANGUAGE plpgsql AS $fn$
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
$fn$;
CREATE TRIGGER trg_action_execution_guard BEFORE INSERT OR UPDATE ON agent.action_execution FOR EACH ROW EXECUTE FUNCTION agent.guard_execution();

-- ---- projection: the source-shaped AgentAction (tool_name, arguments, status, requires_approval, approved_by, result) ----
CREATE VIEW agent.v_agent_action AS
SELECT p.tenant_id, p.id AS proposal_id, p.session_id, p.tool_name, p.arguments, p.requires_approval, p.status,
       a.decided_by_actor_id AS approved_by, a.decided_at AS approved_at,
       e.status AS execution_status, e.result, e.external_ref_type, e.external_ref_id, p.created_at, p.expires_at
  FROM agent.action_proposal p
  LEFT JOIN LATERAL (SELECT x.* FROM agent.action_approval x
                      WHERE x.tenant_id = p.tenant_id AND x.proposal_id = p.id AND x.decision = 'approved'
                      ORDER BY x.approval_round DESC LIMIT 1) a ON true
  LEFT JOIN LATERAL (SELECT y.* FROM agent.action_execution y
                      WHERE y.tenant_id = p.tenant_id AND y.proposal_id = p.id
                      ORDER BY y.attempt_no DESC LIMIT 1) e ON true;
COMMENT ON VIEW agent.v_agent_action IS 'Source-shaped AgentAction projection over proposal + latest approval + latest execution.';
