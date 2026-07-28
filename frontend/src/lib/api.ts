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

// Support VITE_API_BASE_URL, VITE_API_URL, and NEXT_PUBLIC_API_URL
let rawBaseUrl = (import.meta as any).env.VITE_API_BASE_URL ||
                 (import.meta as any).env.VITE_API_URL ||
                 (import.meta as any).env.NEXT_PUBLIC_API_URL ||
                 'https://documind-backend-j6el.onrender.com';

// Ensure protocol is present
if (rawBaseUrl && !rawBaseUrl.startsWith('http://') && !rawBaseUrl.startsWith('https://')) {
  rawBaseUrl = `https://${rawBaseUrl}`;
}

// Normalize default localhost or un-suffixed backend URLs on production to the live backend
if (rawBaseUrl.includes('localhost') || (rawBaseUrl.includes('documind-backend') && !rawBaseUrl.includes('documind-backend-j6el'))) {
  rawBaseUrl = 'https://documind-backend-j6el.onrender.com';
}

// Strip trailing slashes and normalize /api/v1 prefix
rawBaseUrl = rawBaseUrl.replace(/\/+$/, '');
if (rawBaseUrl.endsWith('/api/v1')) {
  rawBaseUrl = rawBaseUrl.slice(0, -7);
} else if (rawBaseUrl.endsWith('/api')) {
  rawBaseUrl = rawBaseUrl.slice(0, -4);
}

const BASE_URL = rawBaseUrl;

export async function apiRequest(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  const token = localStorage.getItem('documind_token');
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const fullUrl = `${BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(fullUrl, {
      ...options,
      headers,
    });
  } catch (err: any) {
    // Intercept native browser fetch failures
    const isLocal = BASE_URL.includes('localhost') || BASE_URL.includes('127.0.0.1');
    const userMessage = isLocal
      ? `Unable to connect to the local backend service at ${BASE_URL}. Please ensure your FastAPI server is running.`
      : 'Unable to reach the backend API server. The service may be starting up, offline, or experiencing network issues. Please try again shortly.';

    throw new ApiError(userMessage, 0, undefined, { originalError: err?.message, url: fullUrl });
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

    if (status === 401) {
      localStorage.removeItem('documind_token');
      message = 'Your session has expired. Please log in again.';
    } else if (status === 404) {
      message = message || 'Requested resource could not be found.';
    } else if (status === 429) {
      message = 'Too many requests. Please wait a moment and try again.';
    } else if (status === 503) {
      message = 'The AI service or database is temporarily unavailable. Please try again shortly.';
    } else if (status === 504) {
      message = 'The AI response took too long. Please try again.';
    } else if (status >= 500) {
      message = message || 'A server error occurred. Please try again later.';
    }

    throw new ApiError(message, status, requestId, data?.detail);
  }

  return data;
}
