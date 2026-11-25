const TOKEN_KEY = 'rag_auth_token';
const SESSION_KEY = 'rag_guest_session_id';

export function getAuthToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null): void {
  if (token) {
    sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function rotateGuestSessionId(): string {
  const sid = `guest_${crypto.randomUUID().replace(/-/g, '')}`;
  localStorage.setItem(SESSION_KEY, sid);
  return sid;
}

export function getGuestSessionId(): string {
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid || sid.length < 16) {
    sid = rotateGuestSessionId();
  }
  return sid;
}

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;

  constructor(status: number, message: string, code = 'API_ERROR', requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function buildHeaders(extra?: Record<string, string>, isFormData = false): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Session-ID': getGuestSessionId(),
    ...extra,
  };
  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function apiRequest<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    isFormData?: boolean;
  } = {}
): Promise<T> {
  const { method = 'GET', body, isFormData = false } = options;
  const response = await fetch(path, {
    method,
    headers: buildHeaders(undefined, isFormData),
    body: body ? (isFormData ? (body as FormData) : JSON.stringify(body)) : undefined,
  });

  const requestId = response.headers.get('x-request-id') || undefined;

  if (!response.ok) {
    let errMsg = `Request failed (${response.status})`;
    let errCode = 'HTTP_ERROR';
    try {
      const errData = await response.json();
      errMsg = errData.detail || errData.message || errMsg;
      errCode = errData.error_code || errCode;
    } catch {
      // ignore non-json error body
    }
    throw new ApiError(response.status, errMsg, errCode, requestId);
  }

  return (await response.json()) as T;
}

export interface StreamCallbacks {
  onStatus?: (stage: string, message: string) => void;
  onChunk?: (text: string) => void;
  onMetadata?: (meta: {
    sources: unknown[];
    citations: unknown[];
    retrieval_mode: string;
    documents_searched: number;
    prompt_access_level: string;
  }) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export async function streamChatRequest(
  payload: {
    question: string;
    retrieval_mode: 'hybrid' | 'semantic' | 'keyword';
    top_k: number;
    include_session_uploads: boolean;
  },
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch('/api/v1/chat/ask/stream', {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    let msg = `Stream failed (${response.status})`;
    try {
      const err = await response.json();
      msg = err.detail || err.message || msg;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, msg);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const rawEvent of events) {
      let eventType = 'message';
      let dataLine = '';
      for (const line of rawEvent.split('\n')) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        if (line.startsWith('data:')) dataLine += line.slice(5).trim();
      }
      if (!dataLine) continue;
      const parsed = JSON.parse(dataLine);

      if (eventType === 'status') callbacks.onStatus?.(parsed.step || parsed.stage, parsed.message);
      else if (eventType === 'chunk') callbacks.onChunk?.(parsed.text);
      else if (eventType === 'metadata') callbacks.onMetadata?.(parsed);
      else if (eventType === 'error') callbacks.onError?.(parsed.message);
      else if (eventType === 'done') callbacks.onDone?.();
    }
  }
}
