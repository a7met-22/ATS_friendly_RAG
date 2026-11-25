import React, { useEffect, useState } from 'react';
import { Send, Sparkles, BookOpen, Loader2 } from 'lucide-react';
import { streamChatRequest } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { Citation } from '../../types/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  meta?: string;
}

export const ChatWorkspace: React.FC = () => {
  const { isAuthenticated, sessionId } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'hybrid' | 'semantic' | 'keyword'>('hybrid');
  const [includeSessionUploads, setIncludeSessionUploads] = useState<boolean>(false);
  const [statusText, setStatusText] = useState('');
  const [streaming, setStreaming] = useState(false);

  // مسح سجل المحادثة تلقائياً عند تسجيل الدخول أو الخروج لضمان الخصوصية الكاملة
  useEffect(() => {
    setMessages([]);
    setIncludeSessionUploads(false);
  }, [sessionId, isAuthenticated]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || streaming) return;

    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: question };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [...prev, userMsg, { id: assistantId, role: 'assistant', content: '' }]);
    setInput('');
    setStreaming(true);
    setStatusText('Initializing...');

    try {
      await streamChatRequest(
        {
          question,
          retrieval_mode: mode,
          top_k: 6,
          include_session_uploads: isAuthenticated ? includeSessionUploads : true,
        },
        {
          onStatus: (_stage, msg) => setStatusText(msg),
          onChunk: (text) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + text } : m))
            );
          },
          onMetadata: (meta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      citations: (meta.citations as Citation[]) || [],
                      meta: `${meta.retrieval_mode.toUpperCase()} • ${meta.documents_searched} docs • ${meta.prompt_access_level}`,
                    }
                  : m
              )
            );
          },
          onError: (errMsg) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: `Error: ${errMsg}` } : m))
            );
          },
          onDone: () => setStatusText(''),
        }
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to generate answer';
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: `Error: ${msg}` } : m))
      );
    } finally {
      setStreaming(false);
      setStatusText('');
    }
  };

  return (
    <main className="flex-1 flex flex-col bg-slate-950 min-w-0">
      <div className="border-b border-slate-800/80 px-6 py-2.5 flex flex-wrap items-center justify-between gap-3 bg-slate-900/30">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span>Grounded Resume Analysis with Citation Verification</span>
        </div>

        <div className="flex items-center gap-4">
          {isAuthenticated && (
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none bg-slate-900 border border-slate-700 px-2.5 py-1 rounded-md">
              <input
                type="checkbox"
                checked={includeSessionUploads}
                onChange={(e) => setIncludeSessionUploads(e.target.checked)}
                className="accent-indigo-600 rounded cursor-pointer"
              />
              <span>Include Session Uploads</span>
            </label>
          )}

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Search Mode:</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as 'hybrid' | 'semantic' | 'keyword')}
              className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-md px-2.5 py-1 focus:outline-none"
            >
              <option value="hybrid">Hybrid (Semantic + Keyword)</option>
              <option value="semantic">Semantic Vector</option>
              <option value="keyword">Exact Keyword</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
            <Sparkles className="w-10 h-10 text-indigo-500/60 mb-3" />
            <h3 className="text-base font-medium text-slate-200">Ask about candidates, skills, or experience</h3>
            <p className="text-xs text-slate-400 mt-1">
              Upload PDF resumes on the left or sign in to query your synchronized Google Drive talent pool.
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-3xl rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-900 border border-slate-800 text-slate-100'
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content || (streaming ? '...' : '')}</div>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-slate-800 flex flex-wrap gap-1.5">
                    {m.citations.map((c, idx) => (
                      <span
                        key={`${c.chunk_id}-${idx}`}
                        className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700"
                      >
                        <BookOpen className="w-3 h-3" />
                        {c.document_title} (#{c.chunk_id})
                      </span>
                    ))}
                  </div>
                )}
                {m.meta && <div className="mt-2 text-[10px] text-slate-500">{m.meta}</div>}
              </div>
            </div>
          ))
        )}
      </div>

      {statusText && (
        <div className="px-6 py-1.5 text-xs text-indigo-400 flex items-center gap-2 bg-indigo-950/20 border-t border-indigo-900/40">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>{statusText}</span>
        </div>
      )}

      <form onSubmit={handleAsk} className="p-4 border-t border-slate-800 bg-slate-900/50">
        <div className="max-w-4xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Compare candidates, extract tech stacks, or check years of experience..."
            className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium flex items-center gap-2 transition"
          >
            <Send className="w-4 h-4" />
            Ask
          </button>
        </div>
      </form>
    </main>
  );
};
