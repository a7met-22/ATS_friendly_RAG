



-- =====================================================
-- RAG Resume Database Schema and Migration
-- Target schema: public
-- =====================================================


-- 1. Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;


-- 2. Create base documents table if it does not exist
CREATE TABLE IF NOT EXISTS public.documents (

    id BIGSERIAL PRIMARY KEY,

    filename TEXT NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 3. Create base document_chunks table if it does not exist
CREATE TABLE IF NOT EXISTS public.document_chunks (

    id BIGSERIAL PRIMARY KEY,

    document_id BIGINT NOT NULL
        REFERENCES public.documents(id) ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    embedding VECTOR(768),

    UNIQUE (document_id, chunk_index)
);


-- 4. Add Drive synchronization columns
ALTER TABLE public.documents

    ADD COLUMN IF NOT EXISTS drive_folder_id TEXT,

    ADD COLUMN IF NOT EXISTS drive_file_id TEXT,

    ADD COLUMN IF NOT EXISTS content_hash CHAR(64),

    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,

    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;


-- 5. Remove old unique constraint on filename
ALTER TABLE public.documents

    DROP CONSTRAINT IF EXISTS documents_filename_key;


-- 6. Ensure each Drive file is registered only once
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_drive_file_id

    ON public.documents (drive_file_id)

    WHERE drive_file_id IS NOT NULL;


-- 7. Create document version history
CREATE TABLE IF NOT EXISTS public.document_versions (

    id BIGSERIAL PRIMARY KEY,

    document_id BIGINT NOT NULL
        REFERENCES public.documents(id) ON DELETE CASCADE,

    version INTEGER NOT NULL,

    filename TEXT NOT NULL,

    content_hash CHAR(64) NOT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, version)
);


-- 8. Set embedding dimensions to 768
-- Run only after confirming that existing vectors
-- do not contain data that needs to be preserved.

ALTER TABLE public.document_chunks

    ALTER COLUMN embedding TYPE VECTOR(768)

    USING embedding::VECTOR(768);


-- 9. Add generated full-text search column
ALTER TABLE public.document_chunks

    ADD COLUMN IF NOT EXISTS search_vector TSVECTOR

    GENERATED ALWAYS AS (
        to_tsvector('simple'::regconfig, content)
    ) STORED;


-- 10. Full-text search index
CREATE INDEX IF NOT EXISTS idx_document_chunks_search_vector

    ON public.document_chunks

    USING GIN (search_vector);


-- 11. Document lookup index
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id

    ON public.document_chunks (document_id);


-- 12. Vector similarity index
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw

    ON public.document_chunks

    USING hnsw (embedding vector_cosine_ops)

    WHERE embedding IS NOT NULL;


-- =====================================================
-- Verification queries
-- =====================================================

-- Check pgvector extension
-- SELECT extname, extversion
-- FROM pg_extension
-- WHERE extname = 'vector';


-- Check embedding dimensions and search column
-- SELECT column_name, data_type, udt_name
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name = 'document_chunks';


-- Check chunk and embedding counts
-- SELECT
--     COUNT(*) AS total_chunks,
--     COUNT(embedding) AS chunks_with_embeddings
-- FROM public.document_chunks;







--
--                    ┌─────────────────────┐
--                    │     documents       │
--                    │─────────────────────│
--                    │ id                  │
--                    │ filename            │
--                    │ status              │
--                    │ drive_file_id       │
--                    │ content_hash        │
--                    │ version             │
--                    │ metadata            │
--                    └──────────┬──────────┘
--                               │
--                               │ document_id
--                               │
--                               ▼
--                    ┌─────────────────────┐
--                    │  document_chunks     │
--                    │─────────────────────│
--                    │ id                  │
--                    │ document_id         │
--                    │ chunk_index         │
--                    │ content             │
--                    │ metadata            │
--                    │ embedding VECTOR768  │
--                    │ search_vector       │
--                    └──────────┬──────────┘
--                               │
--                    ┌──────────┴──────────┐
--                    │                     │
--                    ▼                     ▼
--                 GIN Index             HNSW Index
--              Full-text search       Vector search
--
--
--                    documents
--                       │
--                       │ document_id
--                       ▼
--             ┌─────────────────────┐
--             │ document_versions   │
--             │─────────────────────│
--             │ version             │
--             │ filename            │
--             │ content_hash        │
--             │ metadata            │
--             │ created_at          │
--             └─────────────────────┘