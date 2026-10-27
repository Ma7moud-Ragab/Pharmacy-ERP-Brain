"""BB-24 group 5 (database half): forecasts and models never cross tenants. Hand-written.

Not covered here (needs code that does not exist yet): the artifact store refusing a path outside models/{tenant_id}/
(BB-12, `brain/forecasting/artifacts.py`). The database only refuses absolute and `..` paths, tested below.
"""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from brain.db.session import unit_of_work
from harness import A, B, DAY, H, MODEL_VERSION, P, ctx, snapshot


def test_each_tenants_forecasts_reference_only_its_own_models(world, engine_for):
    for t in (A, B):
        with unit_of_work(engine_for("brain_app"), ctx(t)) as s:
            rows = s.execute(text("SELECT f.tenant_id, m.tenant_id, m.id FROM intel.forecast f "
                                  "JOIN intel.model_registry m ON m.id = f.model_id")).all()
            assert rows == [(t, t, world[t]["model"])]
            assert s.execute(text("SELECT model_version FROM intel.model_registry")).scalars().all() == [MODEL_VERSION]


@pytest.mark.parametrize("what, sql, constraint", [
    ("forecast of A on B's model", "INSERT INTO intel.forecast (tenant_id, product_id, model_id, job_run_id, origin_date, horizon_days, "
     "trigger, forecast_confidence, history_days) VALUES (:a, :p, :b_model, :j, :d, 7, 'nightly', 'low', 1)", "fk_forecast__model_registry"),
    ("A's product model on B's shared artifact", "INSERT INTO intel.model_registry (tenant_id, product_id, scope, shared_model_id, "
     "model_family, model_version, training_run_id, trained_at) VALUES (:a, :p, 'product', :b_model, 'lightgbm', 'x-cross', :a_run, now())",
     "fk_model_registry__shared_model"),
    ("A's forecast point on B's forecast", "INSERT INTO intel.forecast_point (forecast_id, tenant_id, target_date, predicted_demand) "
     "VALUES (:b_forecast, :a, '2026-10-18', 1)", "fk_forecast_point__forecast"),
    ("A's model trained by B's training run", "INSERT INTO intel.model_registry (tenant_id, scope, model_family, model_version, "
     "training_run_id, trained_at) VALUES (:a, 'shared', 'seasonal_naive', 'x-run', :b_run, now())", "fk_model_registry__training_run"),
])
def test_cross_tenant_references_are_refused_by_composite_keys(world, engine_for, what, sql, constraint):
    before = snapshot(B)
    params = {"a": A, "p": P, "d": DAY, "j": uuid4(), "b_model": world[B]["model"], "b_forecast": world[B]["forecast"],
              "b_run": world[B]["training_run"], "a_run": world[A]["training_run"]}
    with pytest.raises(IntegrityError, match=constraint):
        with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
            s.execute(text(sql), params)
    assert snapshot(B) == before


@pytest.mark.parametrize("path", ["/var/lib/brain/models/x.txt", "C:/models/x.txt", f"models/{A}/../{B}/x.txt"])
def test_absolute_or_parent_artifact_paths_are_refused(world, engine_for, path):
    before = snapshot(B)
    with pytest.raises(IntegrityError, match="ck_model_registry__artifact_path_relative"):
        with unit_of_work(engine_for("brain_worker"), ctx(A)) as s:
            s.execute(text("INSERT INTO intel.model_registry (tenant_id, scope, model_family, model_version, training_run_id, trained_at, "
                           "artifact_path, artifact_sha256, artifact_format) VALUES (:a, 'shared', 'lightgbm', :v, :run, now(), :path, :h, "
                           "'lightgbm_txt')"), {"a": A, "v": f"x-{uuid4()}", "run": world[A]["training_run"], "path": path, "h": H})
    assert snapshot(B) == before
