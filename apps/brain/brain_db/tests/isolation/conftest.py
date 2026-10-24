"""BB-24 isolation fixture: both tenants hold the SAME product, the SAME dates and the SAME model version, cache key and
recommendation type, so a query that forgets tenant_id finds a plausible wrong row instead of nothing. Hand-written.

Every row is written through brain/db/session.py by the login that owns that write in production (brain_worker for the
pipeline, brain_app for proposals); nothing is written by a superuser or bypasses RLS.
"""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from brain.db.session import unit_of_work
from harness import A, B, DAY, H, MODEL_VERSION, P, ctx


@pytest.fixture(scope="module")
def world(two_tenants, engine_for):
    worker, app = engine_for("brain_worker"), engine_for("brain_app")
    ids = {}
    for t in (A, B):
        i = {k: uuid4() for k in ("training_run", "model", "forecast", "risk", "recommendation", "proposal")}
        with unit_of_work(worker, ctx(t, actor="system:end_of_day")) as s:
            s.execute(text("INSERT INTO ingest.canonical_cache (tenant_id, entity_type, entity_id, schema_name, schema_version, payload, "
                           "payload_sha256) VALUES (:t, 'product', :e, 'canonical.Product', '1.0', CAST(:p AS jsonb), :h)"),
                      {"t": t, "e": str(P), "p": f'{{"name": "product of {t}"}}', "h": H})
            s.execute(text("INSERT INTO intel.training_run (id, tenant_id, trigger) VALUES (:id, :t, 'nightly')"),
                      {"id": i["training_run"], "t": t})
            s.execute(text("INSERT INTO intel.model_registry (id, tenant_id, scope, model_family, model_version, training_run_id, trained_at, "
                           "artifact_path, artifact_sha256, artifact_format) VALUES (:id, :t, 'shared', 'lightgbm', :v, :tr, now(), :path, :h, "
                           "'lightgbm_txt')"),
                      {"id": i["model"], "t": t, "v": MODEL_VERSION, "tr": i["training_run"], "path": f"models/{t}/{MODEL_VERSION}.txt", "h": H})
            s.execute(text("INSERT INTO intel.forecast (id, tenant_id, product_id, model_id, job_run_id, origin_date, horizon_days, trigger, "
                           "forecast_confidence, history_days) VALUES (:id, :t, :p, :m, :j, :d, 7, 'nightly', 'medium', 120)"),
                      {"id": i["forecast"], "t": t, "p": P, "m": i["model"], "j": uuid4(), "d": DAY})
            s.execute(text("INSERT INTO intel.forecast_point (forecast_id, tenant_id, target_date, predicted_demand) VALUES (:f, :t, :d, 5)"),
                      {"f": i["forecast"], "t": t, "d": date(2026, 10, 17)})
            s.execute(text("INSERT INTO intel.risk_assessment (id, tenant_id, product_id, risk_type, severity, days_of_cover, lead_time_days, "
                           "input_available_quantity, inventory_as_of, rule_version, rule_config_id) VALUES (:id, :t, :p, 'stockout_risk', "
                           "'high', 1.7, 5, 40, now(), 'risk-rules@1.0.0', "
                           "(SELECT id FROM intel.rule_config WHERE rule_set = 'risk' AND is_active))"),
                      {"id": i["risk"], "t": t, "p": P})
            s.execute(text("INSERT INTO intel.recommendation (id, tenant_id, product_id, risk_assessment_id, recommendation_type, payload, "
                           "expires_at, rule_version, rule_config_id) VALUES (:id, :t, :p, :r, 'create_purchase_order', '{}', "
                           "now() + interval '1 day', 'rec-rules-v1', (SELECT id FROM intel.rule_config WHERE rule_set = 'recommendation' AND is_active))"),
                      {"id": i["recommendation"], "t": t, "p": P, "r": i["risk"]})
        with unit_of_work(app, ctx(t, actor="u-1")) as s:
            s.execute(text("INSERT INTO agent.action_proposal (id, tenant_id, proposed_by, tool_name, tool_version, arguments, arguments_sha256, "
                           "policy_version, reason, recommendation_id, idempotency_key, expires_at, trace_id) VALUES (:id, :t, 'rules', "
                           "'create_purchase_order', '1.0', '{}', :h, 'static-policy@1', 'Stockout risk high', :rec, :id, "
                           "now() + interval '24 hours', :tr)"),
                      {"id": i["proposal"], "t": t, "h": H, "rec": i["recommendation"], "tr": "0" * 32})
        ids[t] = i
    return ids
