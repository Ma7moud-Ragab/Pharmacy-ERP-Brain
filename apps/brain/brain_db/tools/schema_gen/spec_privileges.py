"""Least-privilege role matrix after migration 0008 (B1, B7; D-51). Hand-maintained, reviewed with the decision log.

The `grants=` / `worker_grants=` / `provisioner_grants=` fields in spec_*.py describe what migrations 0005-0007 granted
and stay frozen, so those revisions are never rewritten. Migration 0008 is generated as the difference between them
and the target below. Source of the target: BRAIN_CONTRACTS.md section 3 (who writes what).
"""

# brain_app (brain-api) after 0008: the API writes proposals, decisions, executions, sessions, messages, agent_action,
# llm_usage and audit_log only. Every pipeline table is read-only for it.
APP_TARGET = {
    "ingest.sync_checkpoint": "S", "ingest.ingest_failure": "S", "ingest.canonical_cache": "S", "ingest.sales_fact": "S",
    "ingest.sales_day_coverage": "S", "feat.calendar_day": "S", "feat.feature_daily": "S", "intel.rule_config": "S",
    "intel.training_run": "S", "intel.model_registry": "S", "intel.model_evaluation": "S", "intel.forecast": "S",
    "intel.forecast_point": "S", "intel.anomaly_event": "S", "intel.risk_assessment": "S", "intel.recommendation": "S",
    "intel.briefing": "S",
    "agent.agent_session": "SIU", "agent.agent_message": "SI", "agent.action_proposal": "SI", "agent.agent_action": "SI",
    "agent.action_approval": "SI", "agent.action_execution": "SIU", "audit.llm_usage": "SI", "audit.audit_log": "SI",
    "ingest.tenant_registry": "S",
}
# Column-level UPDATE instead of table-level (same lifecycle columns as brain_worker; the guard trigger stays).
APP_UPDATE_COLS = {"agent.action_proposal": ["status", "status_changed_at", "row_version", "updated_at"]}

# brain_worker additions: the calendar seed and refresh (BB-09) is a per-tenant worker step.
WORKER_ADD = {"feat.calendar_day": "IU"}

# brain_provisioner additions: rule-set version changes go through `brain-provision` (BB-25), never the API.
# It may flip is_active only (the guard trigger already freezes every other column), and it writes the audit rows the
# provisioning commands owe (D-46) and the rule_config audit trigger inserts.
PROVISIONER_UPDATE_COLS = {"intel.rule_config": ["is_active"]}
PROVISIONER_ADD = {"audit.audit_log": "I"}
PROVISIONER_SCHEMAS = ["audit"]
