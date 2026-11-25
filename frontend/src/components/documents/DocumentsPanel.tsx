import React, { useCallback, useEffect, useState } from 'react';
import { FileText, Upload, Trash2, Loader2, FolderLock } from 'lucide-react';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { SessionDocument } from '../../types/api';

export const DocumentsPanel: React.FC = () => {
  const { can, sessionId } = useAuth();
  const [docs, setDocs] = useState<SessionDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const loadSessionDocs = useCallback(async () => {
    try {
      const res = await apiRequest<{ documents: SessionDocument[] }>('/api/v1/documents/session');
      setDocs(res.documents || []);
    } catch {
      setDocs([]);
    }
  }, [sessionId]);

  useEffect(() => {
    setDocs([]);
    void loadSessionDocs();
  }, [loadSessionDocs, sessionId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.item(0);
    if (!file) return;
    setError('');
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await apiRequest('/api/v1/documents/upload', {
        method: 'POST',
        body: formData,
        isFormData: true,
      });
      await loadSessionDocs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (docId: number) => {
    try {
      await apiRequest(`/api/v1/documents/session/${docId}`, { method: 'DELETE' });
      setDocs((prev) => prev.filter((d) => d.document_id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  return (
    <aside className="w-80 border-r border-slate-800 bg-slate-900/50 p-4 flex flex-col gap-4 overflow-y-auto">
      {can('search_system_documents') && (
        <div className="p-3 rounded-xl bg-indigo-950/40 border border-indigo-800/50 flex items-start gap-2.5">
          <FolderLock className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-medium text-indigo-200">Company Drive Scope Active</div>
            <p className="text-[11px] text-indigo-300/80 mt-0.5">
              Your queries search synced company resumes. Use the toggle in chat to include session PDFs.
            </p>
          </div>
        </div>
      )}

      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Session Resumes (PDF)
        </h2>
        <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-xl cursor-pointer bg-slate-900/70 transition">
          {uploading ? (
            <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
          ) : (
            <Upload className="w-6 h-6 text-slate-400" />
          )}
          <span className="text-xs text-slate-300 mt-2 font-medium">
            {uploading ? 'Parsing & Indexing...' : 'Upload PDF Resume'}
          </span>
          <span className="text-[11px] text-slate-500 mt-0.5">Max 20MB • Isolated to current session</span>
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {error && (
        <p className="text-xs text-rose-400 bg-rose-950/50 p-2 rounded-lg border border-rose-800">{error}</p>
      )}

      <div className="flex-1 space-y-2">
        {docs.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-6">No session PDFs uploaded yet.</p>
        ) : (
          docs.map((doc) => (
            <div
              key={doc.document_id}
              className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="w-4 h-4 text-indigo-400 shrink-0" />
                <div className="truncate">
                  <div className="text-xs font-medium text-slate-200 truncate">{doc.filename}</div>
                  <div className="text-[10px] text-slate-500">{doc.chunks_created} chunks</div>
                </div>
              </div>
              <button
                onClick={() => void handleDelete(doc.document_id)}
                className="p-1.5 text-slate-400 hover:text-rose-400 rounded-md hover:bg-slate-800"
                title="Remove document"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  );
};
