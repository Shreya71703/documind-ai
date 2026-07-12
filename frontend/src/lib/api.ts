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

const BASE_URL = (import.meta as any).env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function apiRequest(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  const token = localStorage.getItem('documind_token');
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

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
      message = JSON.stringify(data.detail);
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
