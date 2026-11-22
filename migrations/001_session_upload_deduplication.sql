-- 1. فهرس موحد وسريع لجلب ملفات الجلسة (سواء من FastAPI أو Streamlit)
DROP INDEX IF EXISTS idx_documents_streamlit_session;
DROP INDEX IF EXISTS idx_documents_session_uploads;

CREATE INDEX IF NOT EXISTS idx_documents_session_uploads
ON public.documents (
    (metadata->>'upload_session_id')
)
WHERE drive_file_id IS NULL
  AND status = 'processed'
  AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
  AND metadata->>'upload_session_id' IS NOT NULL;


-- 2. فهرس فريد موحد لمنع تكرار رفع نفس الملف في نفس الجلسة
DROP INDEX IF EXISTS idx_documents_streamlit_session_content_hash;

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_session_content_hash
ON public.documents (
    (metadata->>'upload_session_id'),
    content_hash
)
WHERE drive_file_id IS NULL
  AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
  AND metadata->>'upload_session_id' IS NOT NULL
  AND content_hash IS NOT NULL;
