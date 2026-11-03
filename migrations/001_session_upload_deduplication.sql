-- Optional integrity index: one identical PDF content hash per Streamlit session.
-- Google Drive documents are excluded because drive_file_id is not NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_streamlit_session_content_hash
ON public.documents (
    (metadata->>'upload_session_id'),
    content_hash
)
WHERE drive_file_id IS NULL
  AND metadata->>'source_type' = 'streamlit_upload'
  AND content_hash IS NOT NULL;
