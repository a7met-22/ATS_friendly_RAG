import React, { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import { apiRequest } from '../../api/client';

interface SyncState {
  status: string;
  triggered_by?: string;
  started_at?: string;
  finished_at?: string;
  summary?: Record<string, number>;
  error?: string;
}

export const DriveSyncCard: React.FC = () => {
  const [state, setState] = useState<SyncState>({ status: 'idle' });
  const [loading, setLoading] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await apiRequest<SyncState>('/api/v1/admin/sync-status');
      setState(res);
    } catch {
      // ignore initial status fetch errors
    }
  };

  useEffect(() => {
    void fetchStatus();
  }, []);

  useEffect(() => {
    if (state.status !== 'running') return;
    const interval = setInterval(() => void fetchStatus(), 2000);
    return () => clearInterval(interval);
  }, [state.status]);

  const triggerSync = async () => {
    setLoading(true);
    try {
      await apiRequest('/api/v1/admin/sync-drive', { method: 'POST' });
      await fetchStatus();
    } catch (err) {
      setState({
        status: 'failed',
        error: err instanceof Error ? err.message : 'Sync trigger failed',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Google Drive Repository Sync</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Synchronize PDF resumes from company Google Drive into pgvector embeddings.
          </p>
        </div>
        <button
          onClick={triggerSync}
          disabled={loading || state.status === 'running'}
          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-2 transition"
        >
          <RefreshCw className={`w-4 h-4 ${state.status === 'running' ? 'animate-spin' : ''}`} />
          {state.status === 'running' ? 'Syncing...' : 'Start Sync Now'}
        </button>
      </div>

      <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">Current Status:</span>
          <span className="font-semibold uppercase text-indigo-400">{state.status}</span>
        </div>
        {state.triggered_by && (
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Triggered By:</span>
            <span className="text-slate-200">{state.triggered_by}</span>
          </div>
        )}
        {state.summary && (
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 pt-2 border-t border-slate-800 text-center">
            {Object.entries(state.summary).map(([k, v]) => (
              <div key={k} className="p-2 rounded bg-slate-900">
                <div className="text-sm font-bold text-slate-100">{v}</div>
                <div className="text-[10px] text-slate-400 capitalize">{k}</div>
              </div>
            ))}
          </div>
        )}
        {state.status === 'completed' && (
          <div className="flex items-center gap-1.5 text-emerald-400 pt-1">
            <CheckCircle2 className="w-4 h-4" />
            <span>Synchronization completed cleanly.</span>
          </div>
        )}
        {state.error && (
          <div className="flex items-center gap-1.5 text-rose-400 pt-1">
            <AlertTriangle className="w-4 h-4" />
            <span>{state.error}</span>
          </div>
        )}
      </div>
    </div>
  );
};
