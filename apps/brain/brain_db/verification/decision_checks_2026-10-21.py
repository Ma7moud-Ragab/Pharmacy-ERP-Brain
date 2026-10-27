"""Decision checks for D-28..D-34 (21 Oct 2026). Hand-written, not generated.

Usage: build an EMPTY scratch database as the migration owner (`alembic upgrade head` or brain_db_mvp.sql; D-50), then
    python decision_checks_2026-10-21.py <dbname>
Connection: BB_OWNER_DSN (the migration owner, never a superuser; see bbsetup.py). Every statement runs as the owner
inside the transaction-local context of the tenant it writes (FORCE RLS binds the owner too). Exits non-zero if any check fails.
Note: until task BB-05G fixes guard_proposal_transition, the DDL only loads with that fix applied.
"""
import json, sys
import psycopg
import bbsetup
DB = sys.argv[1]
T="00000000-0000-0000-0000-000000000001"; T2="00000000-0000-0000-0000-000000000002"
P="b3f1c2a0-4e51-4a2e-9d3e-000000000001"; RC="a880747f-63cc-4fd7-97d2-4eb20ad9181f"; RK="d637e434-59a3-4671-8608-3afb031f3b59"
OWN = bbsetup.owner(DB)
def fmt(v):  # print values the way psql -tA did (jsonb as JSON text)
    return "" if v is None else json.dumps(v) if isinstance(v, (list, dict)) else str(v)
def run(sql, tenant=T):
    """One transaction in `tenant`'s context. Returns (succeeded, output) like the earlier psql version."""
    try:
        with bbsetup.tenant(OWN, tenant):
            cur = OWN.execute(sql)
            rows = cur.fetchall() if cur.description else []
        return True, "\n".join("|".join(fmt(v) for v in r) for r in rows)
    except psycopg.Error as e:
        return False, str(e).strip()
res=[]
def expect(name, sql, ok, tenant=T):
    good, out = run(sql, tenant); passed = (good==ok)
    res.append(passed); print(("PASS" if passed else "FAIL"), name, "" if passed else out[:300])
rc = lambda: f"(SELECT id FROM intel.rule_config WHERE tenant_id='{T}' AND rule_set='recommendation')"
ok0,o0=run(f"INSERT INTO intel.risk_assessment(id,tenant_id,product_id,risk_type,severity,days_of_cover,lead_time_days,input_available_quantity,inventory_as_of,rule_version,rule_config_id) VALUES ('f0000000-0000-4000-8000-000000000001','{T}','{P}','stockout_risk','high',1.7,5,40,now(),'risk-rules@1.0.0',(SELECT id FROM intel.rule_config WHERE tenant_id='{T}' AND rule_set='risk'))")
print("setup risk",ok0,o0[:300]); ok,o=run(f"INSERT INTO intel.recommendation(id,tenant_id,product_id,risk_assessment_id,recommendation_type,payload,expires_at,rule_version,rule_config_id) VALUES ('e0000000-0000-4000-8000-000000000001','{T}','{P}','f0000000-0000-4000-8000-000000000001','create_purchase_order','{{}}',now()+interval '1 day','rec-rules-v1',(SELECT id FROM intel.rule_config WHERE tenant_id='{T}' AND rule_set='recommendation'))"); print("setup recommendation", ok, o[:200])
H="d67ad9758d7806f685b4294e16a538f84157456e2de40b23aa5ca9c6993b57ce"
def prop(pid, by, rec=True, session="NULL", actor="NULL", tenant=T):
    r = "'e0000000-0000-4000-8000-000000000001'" if rec else "NULL"
    return (f"INSERT INTO agent.action_proposal(id,tenant_id,proposed_by,session_id,requested_by_actor_id,tool_name,tool_version,arguments,arguments_sha256,policy_version,reason,recommendation_id,idempotency_key,expires_at,trace_id) "
            f"VALUES ('{pid}','{tenant}','{by}',{session},{actor},'create_purchase_order','1.0','{{\"supplier_id\":\"c0ffee00-0000-4000-8000-000000000001\",\"lines\":[{{\"product_id\":\"{P}\",\"quantity\":110}}]}}','{H}','static-policy@1','Stockout risk high',{r},'{pid}',now()+interval '24 hours','{'0'*32}')")
expect("Q-01 rules proposal without session/requester inserts", prop("a9000000-0000-4000-8000-000000000001","rules"), True)
expect("Q-01 agent proposal without session is rejected", prop("a9000000-0000-4000-8000-000000000002","agent",rec=False), False)
expect("Q-01 unknown proposed_by rejected", prop("a9000000-0000-4000-8000-000000000003","llm",rec=False), False)
expect("Q-02 second live proposal for the same recommendation rejected", prop("a9000000-0000-4000-8000-000000000004","rules"), False)
expect("Q-02 setup: first proposal -> rejected (decision row + status)",
  f"INSERT INTO agent.action_approval(tenant_id,proposal_id,approval_round,decision,decided_by_actor_id,decider_scopes,arguments_sha256,decided_at,trace_id) VALUES ('{T}','a9000000-0000-4000-8000-000000000001',1,'rejected','u-1',ARRAY['agent:approve'],'{H}',now(),'{'0'*32}'); UPDATE agent.action_proposal SET status='rejected' WHERE id='a9000000-0000-4000-8000-000000000001'", True)
expect("Q-02 new proposal allowed once the old one is no longer live", prop("a9000000-0000-4000-8000-000000000005","rules"), True)
expect("Trigger: pending -> succeeded is illegal", "UPDATE agent.action_proposal SET status='succeeded' WHERE id='a9000000-0000-4000-8000-000000000005'", False)
expect("Q-11 insert without tenant_id fails (no default)", f"INSERT INTO ingest.sales_fact(product_id,sales_date,day_status,source_updated_at) VALUES ('{P}','2026-10-20','closed',now())", False)
run(f"INSERT INTO intel.training_run(id,tenant_id,trigger) VALUES ('7d3e0c10-6b1a-4f6e-8c20-000000000001','{T}','nightly')")
expect("D-28 training_run trigger weekly_full rejected", f"INSERT INTO intel.training_run(tenant_id,trigger) VALUES ('{T}','weekly_full')", False)
SH="9b1e0000-0000-4000-8000-0000000000aa"
expect("Q-03 shared LightGBM row (product_id NULL, own artifact)", f"INSERT INTO intel.model_registry(id,tenant_id,scope,model_family,model_version,training_run_id,trained_at,artifact_path,artifact_sha256,artifact_format) VALUES ('{SH}','{T}','shared','lightgbm','lgbm-global-1','7d3e0c10-6b1a-4f6e-8c20-000000000001',now(),'{T}/models/lgbm-global-1.txt','{H}','lightgbm_txt')", True)
expect("Q-03 product row pointing at the shared artifact", f"INSERT INTO intel.model_registry(tenant_id,product_id,scope,shared_model_id,model_family,model_version,training_run_id,trained_at,status,validated_at) VALUES ('{T}','{P}','product','{SH}','lightgbm','lgbm-global-1/amox','7d3e0c10-6b1a-4f6e-8c20-000000000001',now(),'validated',now())", True)
expect("Q-03 product row cannot both reference shared AND carry its own artifact", f"INSERT INTO intel.model_registry(tenant_id,product_id,scope,shared_model_id,model_family,model_version,training_run_id,trained_at,artifact_path,artifact_sha256,artifact_format) VALUES ('{T}','{P}','product','{SH}','lightgbm','x2','7d3e0c10-6b1a-4f6e-8c20-000000000001',now(),'a.txt','{H}','lightgbm_txt')", False)
expect("Q-03 shared row with a product_id rejected", f"INSERT INTO intel.model_registry(tenant_id,product_id,scope,model_family,model_version,training_run_id,trained_at) VALUES ('{T}','{P}','shared','seasonal_naive','x3','7d3e0c10-6b1a-4f6e-8c20-000000000001',now())", False)
run(f"INSERT INTO intel.training_run(id,tenant_id,trigger) VALUES ('7d3e0c10-6b1a-4f6e-8c20-000000000002','{T2}','nightly')", T2)
expect("Q-11 product row of tenant 2 cannot reference tenant 1's shared artifact (composite FK)", f"INSERT INTO intel.model_registry(tenant_id,product_id,scope,shared_model_id,model_family,model_version,training_run_id,trained_at) VALUES ('{T2}','{P}','product','{SH}','lightgbm','t2-x','7d3e0c10-6b1a-4f6e-8c20-000000000002',now())", False, T2)
expect("Q-05 pickle artifact rejected", f"INSERT INTO intel.model_registry(tenant_id,scope,model_family,model_version,training_run_id,trained_at,artifact_path,artifact_sha256,artifact_format) VALUES ('{T}','shared','lightgbm','x4','7d3e0c10-6b1a-4f6e-8c20-000000000001',now(),'b.pkl','{H}','pickle')", False)
expect("Q-05 joblib artifact rejected", f"INSERT INTO intel.model_registry(tenant_id,scope,model_family,model_version,training_run_id,trained_at,artifact_path,artifact_sha256,artifact_format) VALUES ('{T}','shared','lightgbm','x5','7d3e0c10-6b1a-4f6e-8c20-000000000001',now(),'b.joblib','{H}','joblib')", False)
expect("Q-04 holt_winters family rejected", f"INSERT INTO intel.model_registry(tenant_id,scope,model_family,model_version,training_run_id,trained_at) VALUES ('{T}','shared','holt_winters','x6','7d3e0c10-6b1a-4f6e-8c20-000000000001',now())", False)
ok,o=run("SELECT params->'candidates' FROM intel.rule_config WHERE rule_set='forecast'"); res.append(o=='["seasonal_naive", "lightgbm"]'); print("PASS" if res[-1] else "FAIL","Q-04 seed candidates =",o)
expect("Q-06 sales_fact keeps negative net_units (raw values preserved)", f"INSERT INTO ingest.sales_fact(tenant_id,product_id,sales_date,units_sold,units_returned,net_units,day_status,is_complete,source_updated_at,source_mode) VALUES ('{T}','{P}','2026-10-19',2,5,-3,'closed',true,now(),'poll')", True)
ok,o=run("SELECT net_units FROM ingest.sales_fact WHERE sales_date='2026-10-19'"); res.append(o.startswith('-3')); print("PASS" if res[-1] else "FAIL","Q-06 stored net_units =",o)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
