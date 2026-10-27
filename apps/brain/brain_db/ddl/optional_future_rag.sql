-- OPTIONAL / FUTURE ONLY: RAG. Not part of the MVP. Requires the pgvector extension.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE TABLE rag.embedding (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_uri TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_embedding PRIMARY KEY (id),
    CONSTRAINT uq_embedding__source_chunk UNIQUE (tenant_id, source_uri, source_sha256, chunk_index),
    CONSTRAINT ck_embedding__chunk CHECK (chunk_index >= 0),
    CONSTRAINT ck_embedding__source_sha256_format CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_embedding__metadata_type CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE INDEX ix_embedding__tenant_source ON rag.embedding (tenant_id, source_uri);
COMMENT ON TABLE rag.embedding IS 'FUTURE ONLY. Document chunks and embeddings (pgvector) for unstructured text such as policies or drug leaflets. Never holds sales or inventory data. Not created by MVP migrations.';
COMMENT ON COLUMN rag.embedding.id IS 'Internal Brain surrogate key.';
COMMENT ON COLUMN rag.embedding.tenant_id IS 'Tenant UUID = ERP organization id (external reference owned by ERP Identity; not a FK). Always set explicitly from the verified tenant context (JWT for API calls, the job''s tenant for worker runs). No column default (decision D-34): a missing tenant fails the insert instead of landing in a default tenant.';
COMMENT ON COLUMN rag.embedding.source_uri IS 'Document identifier (file/URL) in the knowledge base.';
COMMENT ON COLUMN rag.embedding.source_sha256 IS 'Hash of the source document version.';
COMMENT ON COLUMN rag.embedding.chunk_index IS 'Chunk order within the document.';
COMMENT ON COLUMN rag.embedding.content IS 'Chunk text.';
COMMENT ON COLUMN rag.embedding.embedding IS 'Embedding vector. Dimension depends on the embedding model (OD-18).';
COMMENT ON COLUMN rag.embedding.metadata IS 'Title, page, language.';
COMMENT ON COLUMN rag.embedding.created_at IS 'Row creation time (UTC).';
CREATE INDEX ix_embedding__hnsw_cosine ON rag.embedding USING hnsw (embedding vector_cosine_ops);
GRANT SELECT, INSERT, UPDATE, DELETE ON rag.embedding TO brain_app;
GRANT USAGE ON SCHEMA rag TO brain_app, brain_readonly;
