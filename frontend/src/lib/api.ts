export class ApiError extends Error {
  constructor(
    public message: string,
    public status: number,
    public requestId?: string,
    public detail?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Live production backend URL on Render
const LIVE_BACKEND_URL = 'https://documind-backend-j6el.onrender.com';

// Wakeup: ping /health until backend responds (handles Render free-tier cold starts ~30s)
async function wakeupBackend(baseUrl: string): Promise<void> {
  const maxAttempts = 14;
  const delayMs = 2500;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const r = await fetch(`${baseUrl}/health`, { method: 'GET', signal: AbortSignal.timeout(4000) });
      if (r.ok) return;
    } catch {
      // still sleeping, wait and retry
    }
    await new Promise((res) => setTimeout(res, delayMs));
  }
}

function resolveBaseUrl(): string {
  let rawBaseUrl =
    (import.meta as any).env.VITE_API_BASE_URL ||
    (import.meta as any).env.VITE_API_URL ||
    (import.meta as any).env.NEXT_PUBLIC_API_URL;

  const isProd =
    (import.meta as any).env.PROD ||
    (typeof window !== 'undefined' && window.location.protocol === 'https:');

  if (!rawBaseUrl || isProd) {
    if (
      !rawBaseUrl ||
      rawBaseUrl.includes('localhost') ||
      rawBaseUrl.includes('127.0.0.1') ||
      (rawBaseUrl.includes('documind-backend') && !rawBaseUrl.includes('documind-backend-j6el'))
    ) {
      rawBaseUrl = LIVE_BACKEND_URL;
    }
  }

  // Ensure proper http/https protocol
  if (rawBaseUrl && !rawBaseUrl.startsWith('http://') && !rawBaseUrl.startsWith('https://')) {
    rawBaseUrl = `https://${rawBaseUrl}`;
  }

  // Upgrade http:// to https:// on HTTPS pages for non-localhost hosts to prevent mixed content blocks
  if (
    typeof window !== 'undefined' &&
    window.location.protocol === 'https:' &&
    rawBaseUrl.startsWith('http://') &&
    !rawBaseUrl.includes('localhost') &&
    !rawBaseUrl.includes('127.0.0.1')
  ) {
    rawBaseUrl = rawBaseUrl.replace(/^http:\/\//, 'https://');
  }

  // Strip trailing slashes and normalize /api/v1 prefix
  rawBaseUrl = rawBaseUrl.replace(/\/+$/, '');
  if (rawBaseUrl.endsWith('/api/v1')) {
    rawBaseUrl = rawBaseUrl.slice(0, -7);
  } else if (rawBaseUrl.endsWith('/api')) {
    rawBaseUrl = rawBaseUrl.slice(0, -4);
  }

  return rawBaseUrl;
}

const BASE_URL = resolveBaseUrl();

export async function apiRequest(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  const headers = new Headers(options.headers || {});

  const fullUrl = `${BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(fullUrl, {
      ...options,
      headers,
    });
  } catch {
    // First fetch failed — backend may be cold-starting on Render free tier (~30s wake time)
    // Wait for it to become healthy before retrying the real request
    try {
      await wakeupBackend(BASE_URL);
      response = await fetch(fullUrl, {
        ...options,
        headers,
      });
    } catch (retryErr: any) {
      const isLocal = BASE_URL.includes('localhost') || BASE_URL.includes('127.0.0.1');
      const userMessage = isLocal
        ? `Unable to connect to local backend at ${BASE_URL}. Please ensure your FastAPI server is running.`
        : `Unable to reach the backend server. It may still be waking up — please wait a moment and try again.`;

      throw new ApiError(userMessage, 0, undefined, { originalError: retryErr?.message, url: fullUrl });
    }
  }

  const requestId = response.headers.get('x-request-id') || undefined;

  let data: any = null;
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      // Ignored
    }
  } else {
    try {
      data = { detail: await response.text() };
    } catch {
      // Ignored
    }
  }

  if (!response.ok) {
    const status = response.status;
    let message = 'An unexpected error occurred. Please try again.';

    if (data && typeof data.detail === 'string') {
      message = data.detail;
    } else if (data && typeof data.detail === 'object' && data.detail !== null) {
      if (Array.isArray(data.detail)) {
        message = data.detail.map((err: any) => err.msg || JSON.stringify(err)).join(', ');
      } else {
        message = JSON.stringify(data.detail);
      }
    }

    if (status === 404) {
      message = message || 'Requested resource could not be found.';
    } else if (status === 429) {
      message = 'Too many requests. Please wait a moment and try again.';
    } else if (status === 503) {
      message = (data && typeof data.detail === 'string' && data.detail.trim()) ? data.detail : 'The AI service or database is temporarily unavailable. Please try again shortly.';
    } else if (status === 504) {
      message = 'The AI response took too long. Please try again.';
    } else if (status >= 500) {
      message = message || 'Server error. Please try again later.';
    }

    throw new ApiError(message, status, requestId, data?.detail);
  }

  return data;
}

export async function streamChatMessage(
  sessionId: string,
  question: string,
  onToken: (token: string) => void,
  onDone: (citations: any[], debugMetadata: any) => void,
  onError: (err: Error) => void
) {
  try {
    const response = await fetch(`${BASE_URL}/api/v1/chats/${sessionId}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Streaming request failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6).trim();
          if (jsonStr) {
            try {
              const data = JSON.parse(jsonStr);
              if (data.token) {
                onToken(data.token);
              }
              if (data.done) {
                onDone(data.citations || [], data.debug_metadata || {});
              }
            } catch {
              // Ignore partial JSON
            }
          }
        }
      }
    }
  } catch (err: any) {
    onError(err);
  }
}
