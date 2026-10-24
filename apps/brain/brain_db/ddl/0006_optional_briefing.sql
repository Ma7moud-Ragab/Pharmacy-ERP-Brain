-- 0006_optional_briefing: SHOULD-have table, safe to skip

-- ---- intel.briefing ----
CREATE TABLE intel.briefing (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    generated_by TEXT NOT NULL,
    llm_usage_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_briefing PRIMARY KEY (id),
    CONSTRAINT uq_briefing__tenant_date UNIQUE (tenant_id, briefing_date),
    CONSTRAINT ck_briefing__generated_by CHECK (generated_by IN ('template','llm')),
    CONSTRAINT ck_briefing__content_type CHECK (jsonb_typeof(content) = 'object')
);
COMMENT ON TABLE intel.briefing IS 'Cached daily morning briefing (`Explanation` subtype report) built from existing risks and pending proposals. SHOULD-have; the MVP does not depend on it.';
COMMENT ON COLUMN intel.briefing.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN intel.briefing.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN intel.briefing.briefing_date IS 'Business date the briefing is for.';
COMMENT ON COLUMN intel.briefing.content IS 'Structured briefing (top risks, pending approvals, summaries).';
COMMENT ON COLUMN intel.briefing.generated_by IS 'template | llm.';
COMMENT ON COLUMN intel.briefing.llm_usage_id IS 'audit.llm_usage row when an LLM polished the text (soft reference, no FK).';
COMMENT ON COLUMN intel.briefing.created_at IS 'Row creation time (UTC).';
COMMENT ON COLUMN intel.briefing.updated_at IS 'Last modification time (UTC); maintained by trigger.';
CREATE TRIGGER trg_briefing_set_updated_at BEFORE UPDATE ON intel.briefing FOR EACH ROW EXECUTE FUNCTION public.brain_set_updated_at();

GRANT SELECT, INSERT, UPDATE ON intel.briefing TO brain_app;
GRANT SELECT, INSERT, UPDATE ON intel.briefing TO brain_worker;
GRANT SELECT ON intel.briefing TO brain_readonly;
GRANT SELECT, DELETE ON intel.briefing TO brain_retention;
