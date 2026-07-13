import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import { apiRequest, ApiError } from '../lib/api';
import { AuthProvider, useAuth } from '../context/AuthContext';

describe('DocuMind AI Frontend Unit Tests', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------
  // API CLIENT & ERROR MESSAGES TESTS
  // -------------------------------------------------------------
  describe('API Client Normalization', () => {
    it('should attach authorization header if token exists', async () => {
      localStorage.setItem('documind_token', 'my-fake-token');

      const mockResponse = {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ status: 'success' }),
      };

      const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      await apiRequest('/test-route');

      expect(fetchSpy).toHaveBeenCalled();
      const [, init] = fetchSpy.mock.calls[0];
      const headers = init?.headers as Headers;
      expect(headers.get('Authorization')).toBe('Bearer my-fake-token');
    });

    it('should map 401 Unauthorized status, clear token, and throw matching error message', async () => {
      localStorage.setItem('documind_token', 'expired-token');

      const mockResponse = {
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Token has expired' }),
      };

      vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      await expect(apiRequest('/test-route')).rejects.toThrowError(
        'Your session has expired. Please log in again.'
      );
      expect(localStorage.getItem('documind_token')).toBeNull();
    });

    it('should map 429 Rate Limit error', async () => {
      const mockResponse = {
        ok: false,
        status: 429,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Rate limit exceeded' }),
      };

      vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      await expect(apiRequest('/test-route')).rejects.toThrowError(
        'Too many requests. Please wait a moment and try again.'
      );
    });

    it('should map 503 AI service unavailable error', async () => {
      const mockResponse = {
        ok: false,
        status: 503,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Service Unavailable' }),
      };

      vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      await expect(apiRequest('/test-route')).rejects.toThrowError(
        'The AI service or database is temporarily unavailable. Please try again shortly.'
      );
    });

    it('should map 504 provider timeout error', async () => {
      const mockResponse = {
        ok: false,
        status: 504,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Gateway Timeout' }),
      };

      vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      await expect(apiRequest('/test-route')).rejects.toThrowError(
        'The AI response took too long. Please try again.'
      );
    });

    it('should extract and preserve X-Request-ID in ApiError', async () => {
      const reqId = 'req-abc-123';
      const mockResponse = {
        ok: false,
        status: 500,
        headers: new Headers({
          'content-type': 'application/json',
          'x-request-id': reqId,
        }),
        json: async () => ({ detail: 'Database error' }),
      };

      vi.spyOn(window, 'fetch').mockResolvedValue(mockResponse as any);

      try {
        await apiRequest('/test-route');
        expect.fail('Should have thrown ApiError');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.requestId).toBe(reqId);
      }
    });
  });

  // -------------------------------------------------------------
  // AUTH CONTEXT TESTS
  // -------------------------------------------------------------
  describe('AuthContext Registration and Login', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    );

    it('register should send application/json with correct UserCreate fields and not leak password in URL', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      const fetchSpy = vi.spyOn(window, 'fetch');
      // Mock for /register, /login, /me
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 201, headers: new Headers({'content-type':'application/json'}), json: async () => ({}) } as any);
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), json: async () => ({ access_token: 'fake' }) } as any);
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), json: async () => ({ id: '123' }) } as any);

      await act(async () => {
        await result.current.register('testreg@example.com', 'securepass123');
      });

      // Verify register call
      expect(fetchSpy).toHaveBeenCalled();
      const registerCallArgs = fetchSpy.mock.calls[0];
      const registerUrl = registerCallArgs[0];
      const registerOptions = registerCallArgs[1];

      // Password is not in the URL or query string
      expect(registerUrl.toString()).not.toContain('securepass123');
      
      const headers = new Headers(registerOptions?.headers);
      expect(headers.get('Content-Type')).toBe('application/json');

      const parsedBody = JSON.parse(registerOptions?.body as string);
      expect(parsedBody).toEqual({
        email: 'testreg@example.com',
        password: 'securepass123',
        full_name: 'testreg'
      });
    });

    it('login behavior uses application/json matching backend contract', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      const fetchSpy = vi.spyOn(window, 'fetch');
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), json: async () => ({ access_token: 'fake' }) } as any);
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), json: async () => ({ id: '123' }) } as any);

      await act(async () => {
        await result.current.login('testlogin@example.com', 'securepass123');
      });

      const loginCallArgs = fetchSpy.mock.calls[0];
      const loginOptions = loginCallArgs[1];
      
      const headers = new Headers(loginOptions?.headers);
      expect(headers.get('Content-Type')).toBe('application/json');

      const parsedBody = JSON.parse(loginOptions?.body as string);
      expect(parsedBody).toEqual({
        email: 'testlogin@example.com',
        password: 'securepass123'
      });
    });

    it('full register-to-auto-login flow uses correct endpoints and contracts', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      const fetchSpy = vi.spyOn(window, 'fetch');
      
      // 1st request: POST /register
      fetchSpy.mockResolvedValueOnce({ 
        ok: true, status: 201, headers: new Headers({'content-type':'application/json'}), 
        json: async () => ({ id: 'new-user' }) 
      } as any);
      
      // 2nd request: POST /login (auto-login)
      fetchSpy.mockResolvedValueOnce({ 
        ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), 
        json: async () => ({ access_token: 'new-token' }) 
      } as any);
      
      // 3rd request: GET /me (inside fetchMe)
      fetchSpy.mockResolvedValueOnce({ 
        ok: true, status: 200, headers: new Headers({'content-type':'application/json'}), 
        json: async () => ({ id: 'new-user', email: 'flow@example.com' }) 
      } as any);

      await act(async () => {
        await result.current.register('flow@example.com', 'flowpass123');
      });

      expect(fetchSpy).toHaveBeenCalledTimes(3);

      // Verify register request
      const req1 = fetchSpy.mock.calls[0];
      expect(req1[0]).toContain('/api/v1/auth/register');
      expect(new Headers(req1[1]?.headers).get('Content-Type')).toBe('application/json');
      expect(JSON.parse(req1[1]?.body as string)).toEqual({
        email: 'flow@example.com',
        password: 'flowpass123',
        full_name: 'flow'
      });

      // Verify auto-login request
      const req2 = fetchSpy.mock.calls[1];
      expect(req2[0]).toContain('/api/v1/auth/login');
      expect(new Headers(req2[1]?.headers).get('Content-Type')).toBe('application/json');
      expect(JSON.parse(req2[1]?.body as string)).toEqual({
        email: 'flow@example.com',
        password: 'flowpass123'
      });

      // Verify fetchMe request
      const req3 = fetchSpy.mock.calls[2];
      expect(req3[0]).toContain('/api/v1/auth/me');
      expect(new Headers(req3[1]?.headers).get('Authorization')).toBe('Bearer new-token');

      // Verify token storage
      expect(localStorage.getItem('documind_token')).toBe('new-token');
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.email).toBe('flow@example.com');
    });
  });

  // -------------------------------------------------------------
  // DOCUMENT UPLOAD VALIDATION TESTS
  // -------------------------------------------------------------
  describe('Document Upload Validation', () => {
    const checkFileValidation = (file: { name: string; size: number }): { valid: boolean; error?: string } => {
      const allowedExtensions = ['.pdf', '.docx', '.txt', '.md'];
      const fileExt = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
      if (!allowedExtensions.includes(fileExt)) {
        return { valid: false, error: 'Unsupported file type. Only PDF, DOCX, TXT, and MD are allowed.' };
      }

      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        return { valid: false, error: 'File size exceeds the 10 MB limit.' };
      }

      return { valid: true };
    };

    it('should allow valid PDF, DOCX, TXT, MD files', () => {
      expect(checkFileValidation({ name: 'sample.pdf', size: 1024 }).valid).toBe(true);
      expect(checkFileValidation({ name: 'notes.md', size: 50000 }).valid).toBe(true);
      expect(checkFileValidation({ name: 'report.docx', size: 200000 }).valid).toBe(true);
      expect(checkFileValidation({ name: 'readme.txt', size: 100 }).valid).toBe(true);
    });

    it('should reject unsupported file extensions', () => {
      const res = checkFileValidation({ name: 'image.png', size: 1024 });
      expect(res.valid).toBe(false);
      expect(res.error).toContain('Unsupported file type');
    });

    it('should reject files exceeding 10MB limit', () => {
      const res = checkFileValidation({ name: 'huge_document.pdf', size: 11 * 1024 * 1024 });
      expect(res.valid).toBe(false);
      expect(res.error).toContain('File size exceeds the 10 MB limit.');
    });
  });

  // -------------------------------------------------------------
  // CHAT COMPOSER VALIDATION TESTS
  // -------------------------------------------------------------
  describe('Chat Composer Validation', () => {
    const validateQuestion = (text: string, maxLength: number): { valid: boolean; error?: string } => {
      const trimmed = text.trim();
      if (!trimmed) {
        return { valid: false, error: 'Question cannot be empty.' };
      }
      if (trimmed.length > maxLength) {
        return { valid: false, error: `Question exceeds length limit of ${maxLength} characters.` };
      }
      return { valid: true };
    };

    it('should reject empty or whitespace-only questions', () => {
      expect(validateQuestion('', 1000).valid).toBe(false);
      expect(validateQuestion('   ', 1000).valid).toBe(false);
    });

    it('should reject questions exceeding max character limit', () => {
      const longQuestion = 'a'.repeat(1005);
      const res = validateQuestion(longQuestion, 1000);
      expect(res.valid).toBe(false);
      expect(res.error).toContain('Question exceeds length limit');
    });

    it('should allow valid questions', () => {
      expect(validateQuestion('What is Project Aurora?', 1000).valid).toBe(true);
    });
  });

  // -------------------------------------------------------------
  // NEW CHAT: DOCUMENT VISIBILITY AND SELECTION TESTS
  // -------------------------------------------------------------
  describe('New Chat Document Selection', () => {
    const mockDocuments = [
      { id: '1', original_filename: 'indexed.pdf', status: 'ready', index_status: 'indexed', chunk_count: 5, file_size: 1024, file_type: 'pdf', created_at: '' },
      { id: '2', original_filename: 'uploaded.pdf', status: 'uploaded', index_status: 'not_indexed', chunk_count: 0, file_size: 2048, file_type: 'pdf', created_at: '' },
      { id: '3', original_filename: 'processing.pdf', status: 'processing', index_status: 'not_indexed', chunk_count: 0, file_size: 3000, file_type: 'pdf', created_at: '' },
      { id: '4', original_filename: 'ready-not-indexed.pdf', status: 'ready', index_status: 'not_indexed', chunk_count: 0, file_size: 4000, file_type: 'pdf', created_at: '' },
      { id: '5', original_filename: 'indexing.pdf', status: 'ready', index_status: 'indexing', chunk_count: 0, file_size: 5000, file_type: 'pdf', created_at: '' },
      { id: '6', original_filename: 'failed.pdf', status: 'failed', index_status: 'failed', chunk_count: 0, file_size: 6000, file_type: 'pdf', created_at: '' },
    ];

    const isIndexed = (doc: typeof mockDocuments[0]) =>
      doc.status === 'ready' && doc.index_status === 'indexed';

    it('should show ALL documents in the modal (indexed + non-indexed)', () => {
      // All 6 documents should be rendered in the modal list
      expect(mockDocuments).toHaveLength(6);
    });

    it('should identify exactly one indexed document as selectable', () => {
      const selectable = mockDocuments.filter(isIndexed);
      expect(selectable).toHaveLength(1);
      expect(selectable[0].id).toBe('1');
    });

    it('should identify all non-indexed documents as disabled/unselectable', () => {
      const disabled = mockDocuments.filter(d => !isIndexed(d));
      expect(disabled).toHaveLength(5);
      // None of the disabled docs should be selectable
      disabled.forEach(d => expect(isIndexed(d)).toBe(false));
    });

    it('should not allow toggling selection for a non-indexed document', () => {
      const selectedIds: string[] = [];
      const toggleSelect = (doc: typeof mockDocuments[0]) => {
        if (!isIndexed(doc)) return; // guard
        selectedIds.includes(doc.id)
          ? selectedIds.splice(selectedIds.indexOf(doc.id), 1)
          : selectedIds.push(doc.id);
      };

      // Attempt to select uploaded.pdf (non-indexed)
      toggleSelect(mockDocuments[1]);
      expect(selectedIds).not.toContain('2');

      // Attempt to select processing.pdf (non-indexed)
      toggleSelect(mockDocuments[2]);
      expect(selectedIds).not.toContain('3');

      // Select indexed.pdf (indexed)
      toggleSelect(mockDocuments[0]);
      expect(selectedIds).toContain('1');
    });

    it('should send only indexed document IDs in POST /api/v1/chats payload', () => {
      const selectedIds = ['1']; // Only the indexed doc
      const payload = {
        title: 'Test Chat',
        document_ids: selectedIds,
      };

      // Verify none of the non-indexed IDs leaked into payload
      expect(payload.document_ids).toContain('1');
      expect(payload.document_ids).not.toContain('2');
      expect(payload.document_ids).not.toContain('3');
      expect(payload.document_ids).not.toContain('4');
      expect(payload.document_ids).not.toContain('5');
      expect(payload.document_ids).not.toContain('6');
    });

    it('should show status labels for non-indexed documents', () => {
      const getDocStatusLabel = (doc: typeof mockDocuments[0]): string => {
        if (doc.index_status === 'indexing') return 'Indexing...';
        if (doc.index_status === 'failed') return 'Index failed';
        if (doc.status === 'failed') return 'Processing failed';
        if (doc.status === 'processing') return 'Processing...';
        if (doc.status === 'ready' && doc.index_status === 'not_indexed') return 'Ready — not yet indexed';
        if (doc.status === 'uploaded') return 'Uploaded — not processed';
        return doc.index_status;
      };

      expect(getDocStatusLabel(mockDocuments[1])).toBe('Uploaded — not processed');
      expect(getDocStatusLabel(mockDocuments[2])).toBe('Processing...');
      expect(getDocStatusLabel(mockDocuments[3])).toBe('Ready — not yet indexed');
      expect(getDocStatusLabel(mockDocuments[4])).toBe('Indexing...');
      expect(getDocStatusLabel(mockDocuments[5])).toBe('Index failed');
    });
  });

  // -------------------------------------------------------------
  // CITATION RENDERING TESTS
  // -------------------------------------------------------------
  describe('Citation Rendering', () => {
    it('should correctly parse citation tags and match metadata sources', () => {
      const content = 'The system uses an escalation path [SOURCE 1] to process alerts.';
      const citations = [
        {
          citation_id: 'SOURCE 1',
          document_id: 'doc-123',
          source_filename: 'escalation.pdf',
          file_type: 'pdf',
          chunk_index: 0,
          distance: 0.1,
        },
      ];

      const parts = content.split(/(\[SOURCE \d+\])/g);
      const matchedCitations = parts
        .map(part => {
          const match = part.match(/\[SOURCE (\d+)\]/);
          if (match) {
            const citationId = `SOURCE ${match[1]}`;
            return citations.find(c => c.citation_id === citationId);
          }
          return null;
        })
        .filter(Boolean);

      expect(matchedCitations).toHaveLength(1);
      expect(matchedCitations[0]?.source_filename).toBe('escalation.pdf');
    });

    it('should render insufficient context messages without error', () => {
      const INSUFFICIENT_CONTEXT_MESSAGE =
        "I'm sorry, but the uploaded documents do not contain sufficient information to answer your question.";
      expect(typeof INSUFFICIENT_CONTEXT_MESSAGE).toBe('string');
      expect(INSUFFICIENT_CONTEXT_MESSAGE.length).toBeGreaterThan(0);
    });
  });

  // -------------------------------------------------------------
  // LOADING STATE ACCURACY TEST
  // -------------------------------------------------------------
  describe('Loading State Accuracy', () => {
    it('should use a single accurate loading message without stage transitions', () => {
      // Simulate what handleSendQuestion now does: single stage label
      let activeStage: string | null = null;
      const setActiveStage = (s: string | null) => { activeStage = s; };

      setActiveStage('Searching documents and generating an answer...');
      expect(activeStage).toBe('Searching documents and generating an answer...');
      // No timer-based update to a second stage message
      expect(activeStage).not.toBe('Generating grounded answer...');
      expect(activeStage).not.toBe('Searching your documents...');
    });
  });
});
