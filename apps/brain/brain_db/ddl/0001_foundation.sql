-- 0001_foundation: schemas and shared trigger functions (no tables)
-- Requires PostgreSQL >= 13 (gen_random_uuid() is built in; no extension needed for the MVP).
CREATE SCHEMA IF NOT EXISTS ingest;   -- event-processing state, canonical cache, sales_fact          (rebuildable / operational)
CREATE SCHEMA IF NOT EXISTS feat;     -- calendar + feature tables                                       (rebuildable)
CREATE SCHEMA IF NOT EXISTS intel;    -- models, forecasts, anomalies, risk, recommendations, rule config (history-bearing derived)
CREATE SCHEMA IF NOT EXISTS agent;    -- sessions, messages, tool calls, proposals, approvals, executions (audit-critical)
CREATE SCHEMA IF NOT EXISTS audit;    -- audit_log, llm_usage                                            (audit-critical)

CREATE OR REPLACE FUNCTION public.brain_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_update() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'UPDATE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (append-only)', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'DELETE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_update_delete() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = TG_OP || ' on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (immutable)', ERRCODE = 'insufficient_privilege';
END
$fn$;

CREATE OR REPLACE FUNCTION public.brain_forbid_truncate() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  RAISE EXCEPTION USING MESSAGE = 'TRUNCATE on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' is not allowed (immutable)', ERRCODE = 'insufficient_privilege';
END
$fn$;

-- Generic guard: only the columns listed in the trigger arguments may change on UPDATE.
CREATE OR REPLACE FUNCTION public.brain_guard_update() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF (to_jsonb(NEW) - TG_ARGV) IS DISTINCT FROM (to_jsonb(OLD) - TG_ARGV) THEN
    RAISE EXCEPTION USING MESSAGE = 'immutable column changed on ' || TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || ' (mutable: ' || array_to_string(TG_ARGV, ',') || ')', ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$fn$;
