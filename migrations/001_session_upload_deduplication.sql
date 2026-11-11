-- Index for restricting Streamlit uploads to the current session.
-- Google Drive documents are excluded because drive_file_id is not NULL.
CREATE INDEX IF NOT EXISTS idx_documents_streamlit_session
ON public.documents (
    (metadata->>'upload_session_id')
)
WHERE drive_file_id IS NULL
  AND metadata->>'source_type' = 'streamlit_upload'
  AND metadata->>'upload_session_id' IS NOT NULL;


-- Optional integrity index: prevent the same PDF content
-- from being uploaded more than once within the same Streamlit session.
-- Google Drive documents are excluded because drive_file_id is not NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_streamlit_session_content_hash
ON public.documents (
    (metadata->>'upload_session_id'),
    content_hash
)
WHERE drive_file_id IS NULL
  AND metadata->>'source_type' = 'streamlit_upload'
  AND metadata->>'upload_session_id' IS NOT NULL
  AND content_hash IS NOT NULL;