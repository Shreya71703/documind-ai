import React, { useState, useEffect, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useNavigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  FileText,
  Sparkles,
  LogIn,
  Key,
  ChevronRight,
  Plus,
  Send,
  Loader2,
  LogOut,
  Pin,
  Trash2,
  FolderOpen,
  MessageSquare,
  AlertCircle,
  PinOff,
  X
} from 'lucide-react';

const RAG_MAX_QUESTION_CHARS = 4000;

import { AuthProvider, useAuth } from './context/AuthContext';
import { apiRequest } from './lib/api';
import { DocumentUpload } from './components/DocumentUpload';
import { DocumentList, DocumentItem } from './components/DocumentList';
import { NewChatModal } from './components/NewChatModal';
import { CitationPopover } from './components/CitationPopover';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// -------------------------------------------------------------
// Interactive Citation Chip Component
// -------------------------------------------------------------
interface RetrievedSource {
  citation_id: string;
  document_id: string;
  source_filename: string;
  file_type: string;
  page_number?: number | null;
  chunk_index: number;
  distance: number;
}

const CitationChip: React.FC<{ digit: string; citation: RetrievedSource }> = ({ digit, citation }) => {
  const [showPopover, setShowPopover] = useState(false);
  const chipRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (showPopover && chipRef.current && !chipRef.current.contains(e.target as Node)) {
        setShowPopover(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showPopover) setShowPopover(false);
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [showPopover]);

  return (
    <span ref={chipRef} className="relative inline-block mx-0.5">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setShowPopover(!showPopover);
        }}
        className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold text-violet-400 bg-violet-500/10 border border-violet-500/20 hover:bg-violet-500/20 rounded transition-all duration-150"
      >
        Source {digit}
      </button>
      {showPopover && (
        <div className="absolute bottom-full left-0 mb-2 origin-bottom-left shadow-2xl z-50">
          <CitationPopover citation={citation} onClose={() => setShowPopover(false)} />
        </div>
      )}
    </span>
  );
};

// Custom parser to map [SOURCE X] into React components
const MessageContent: React.FC<{ content: string; citations: RetrievedSource[] }> = ({ content, citations }) => {
  const renderTextWithCitations = (text: string) => {
    const parts = text.split(/(\[SOURCE \d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/\[SOURCE (\d+)\]/);
      if (match) {
        const digit = match[1];
        const citationId = `SOURCE ${digit}`;
        const citation = citations.find((c) => c.citation_id === citationId);
        if (citation) {
          return <CitationChip key={idx} digit={digit} citation={citation} />;
        }
        return null;
      }
      return part;
    });
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => {
          return (
            <p className="leading-relaxed mb-3">
              {React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                  return renderTextWithCitations(child);
                }
                return child;
              })}
            </p>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

// -------------------------------------------------------------
// Protected Route Guard
// -------------------------------------------------------------
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-slate-100">
        <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
      </div>
    );
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};

// -------------------------------------------------------------
// Landing Page Page
// -------------------------------------------------------------
const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="relative min-h-screen flex flex-col justify-between overflow-hidden bg-slate-950 text-slate-100">
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-violet-600/5 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[500px] h-[500px] rounded-full bg-indigo-600/5 blur-[120px] pointer-events-none" />

      <header className="w-full max-w-7xl mx-auto px-6 py-6 flex justify-between items-center z-10 border-b border-slate-900">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-violet-600 text-white flex items-center justify-center shadow-lg shadow-violet-500/20">
            <Bot className="w-5 h-5" />
          </div>
          <span className="font-extrabold text-lg tracking-tight text-white">DocuMind AI</span>
        </div>
        
        <div className="flex items-center gap-4">
          {isAuthenticated ? (
            <button
              onClick={() => navigate('/app')}
              className="px-5 py-2.5 rounded-xl text-xs font-semibold bg-violet-600 hover:bg-violet-500 text-white transition-all shadow-lg shadow-violet-500/10"
            >
              Go to Workspace
            </button>
          ) : (
            <>
              <Link to="/login" className="text-xs font-semibold text-slate-400 hover:text-white transition-colors">
                Sign In
              </Link>
              <Link
                to="/register"
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-850 text-white transition-all"
              >
                Get Started
              </Link>
            </>
          )}
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center max-w-4xl mx-auto px-6 text-center z-10 py-16">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-[10px] font-bold uppercase tracking-wider mb-6">
          <Sparkles className="w-3 h-3 animate-pulse" />
          Grounded RAG AI Assistant
        </div>
        
        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight mb-5 text-white leading-[1.15]">
          DocuMind AI
        </h1>
        
        <p className="text-sm font-medium text-violet-400 uppercase tracking-widest mb-6">
          Grounded AI answers from your documents.
        </p>
        
        <p className="text-slate-400 text-base max-w-2xl mb-10 leading-relaxed font-light">
          Upload your documents, build a searchable knowledge base, and ask questions with source-backed answers.
        </p>

        <div className="flex gap-4 items-center">
          {isAuthenticated ? (
            <button
              onClick={() => navigate('/app')}
              className="px-6 py-3 rounded-xl text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white transition-all shadow-lg shadow-violet-500/20 flex items-center gap-1.5 group"
            >
              Start Chatting
              <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </button>
          ) : (
            <button
              onClick={() => navigate('/register')}
              className="px-6 py-3 rounded-xl text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white transition-all shadow-lg shadow-violet-500/20 flex items-center gap-1.5 group"
            >
              Get Started Free
              <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </button>
          )}
        </div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 w-full mt-16 max-w-3xl">
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900 text-left space-y-1">
            <h4 className="text-xs font-bold text-slate-200">Multi-Format</h4>
            <p className="text-[11px] text-slate-500">PDF, DOCX, TXT, and Markdown upload.</p>
          </div>
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900 text-left space-y-1">
            <h4 className="text-xs font-bold text-slate-200">Semantic Search</h4>
            <p className="text-[11px] text-slate-500">Retrieval matching based on meaning.</p>
          </div>
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900 text-left space-y-1">
            <h4 className="text-xs font-bold text-slate-200">Grounded Answers</h4>
            <p className="text-[11px] text-slate-500">Answers generated from context only.</p>
          </div>
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900 text-left space-y-1">
            <h4 className="text-xs font-bold text-slate-200">Citations</h4>
            <p className="text-[11px] text-slate-500">Chips mapping to precise file segments.</p>
          </div>
        </div>
      </main>

      <footer className="w-full max-w-7xl mx-auto px-6 py-6 flex flex-col sm:flex-row justify-between items-center z-10 border-t border-slate-900 text-slate-600 text-[10px] gap-2">
        <div>&copy; {new Date().getFullYear()} DocuMind AI. All rights reserved.</div>
        <div className="text-[10px] text-slate-700">Token storage limitation: Bearer JWTs are stored in local storage.</div>
      </footer>
    </div>
  );
};

// -------------------------------------------------------------
// Auth Pages (Login / Register)
// -------------------------------------------------------------
const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg('Please fill in all fields.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      await login(email, password);
      navigate('/app');
    } catch (err: any) {
      setErrorMsg(err.message || 'Invalid credentials or login failed.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 p-4">
      <div className="w-full max-w-sm bg-slate-900/50 border border-slate-800 p-6 rounded-2xl shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <Link to="/" className="inline-flex items-center gap-2 text-white font-extrabold text-lg">
            <Bot className="w-6 h-6 text-violet-500" />
            DocuMind AI
          </Link>
          <h2 className="text-sm font-bold text-slate-200">Sign In</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-xs font-semibold text-slate-400">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-850 focus:border-violet-500 focus:outline-none rounded-xl text-xs text-slate-200 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="block text-xs font-semibold text-slate-400">
              Password
            </label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-850 focus:border-violet-500 focus:outline-none rounded-xl text-xs text-slate-200 transition-colors"
            />
          </div>

          {errorMsg && (
            <p className="text-xs text-red-400 font-medium">{errorMsg}</p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 rounded-xl text-xs font-bold bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50 transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-violet-500/10"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
            Sign In
          </button>
        </form>

        <p className="text-center text-xs text-slate-500">
          Don't have an account?{' '}
          <Link to="/register" className="text-violet-400 hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
};

const RegisterPage: React.FC = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !confirmPassword) {
      setErrorMsg('Please fill in all fields.');
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      await register(email, password);
      navigate('/app');
    } catch (err: any) {
      setErrorMsg(err.message || 'Registration failed.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 p-4">
      <div className="w-full max-w-sm bg-slate-900/50 border border-slate-800 p-6 rounded-2xl shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <Link to="/" className="inline-flex items-center gap-2 text-white font-extrabold text-lg">
            <Bot className="w-6 h-6 text-violet-500" />
            DocuMind AI
          </Link>
          <h2 className="text-sm font-bold text-slate-200">Create Account</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-xs font-semibold text-slate-400">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-850 focus:border-violet-500 focus:outline-none rounded-xl text-xs text-slate-200 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="block text-xs font-semibold text-slate-400">
              Password
            </label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-850 focus:border-violet-500 focus:outline-none rounded-xl text-xs text-slate-200 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="confirmPassword" className="block text-xs font-semibold text-slate-400">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-850 focus:border-violet-500 focus:outline-none rounded-xl text-xs text-slate-200 transition-colors"
            />
          </div>

          {errorMsg && (
            <p className="text-xs text-red-400 font-medium">{errorMsg}</p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 rounded-xl text-xs font-bold bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50 transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-violet-500/10"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
            Register
          </button>
        </form>

        <p className="text-center text-xs text-slate-500">
          Already have an account?{' '}
          <Link to="/login" className="text-violet-400 hover:underline">
            Sign In
          </Link>
        </p>
      </div>
    </div>
  );
};

// -------------------------------------------------------------
// App Workspace Layout
// -------------------------------------------------------------
interface ChatSessionItem {
  id: string;
  title: string;
  is_pinned: boolean;
  document_ids: string[];
}

interface MessageItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: RetrievedSource[] | null;
}

const WorkspacePage: React.FC = () => {
  const { user, logout } = useAuth();
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  // Documents state
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  // Chat sessions state
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [activeSession, setActiveSession] = useState<ChatSessionItem | null>(null);

  // Messages log
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);

  // Layout modals/drawers
  const [isNewChatOpen, setIsNewChatOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileDocsOpen, setMobileDocsOpen] = useState(false);

  // Message input state
  const [question, setQuestion] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<string | null>(null);

  // Pinned session updates
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState('');

  const messageEndRef = useRef<HTMLDivElement>(null);

  const fetchDocs = async () => {
    try {
      setIsLoadingDocs(true);
      const data = await apiRequest('/api/v1/documents');
      setDocuments(data);
    } catch (err: any) {
      console.error('Failed to load documents: ', err.message);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  const fetchSessions = async () => {
    try {
      setIsLoadingSessions(true);
      const data = await apiRequest('/api/v1/chats');
      setSessions(data);
    } catch (err: any) {
      console.error('Failed to load chat history: ', err.message);
    } finally {
      setIsLoadingSessions(false);
    }
  };

  const fetchMessages = async (sid: string) => {
    try {
      setIsLoadingMessages(true);
      const data = await apiRequest(`/api/v1/chats/${sid}`);
      setActiveSession(data.session);
      setMessages(data.messages);
    } catch (err: any) {
      console.error('Failed to load chat history messages: ', err.message);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  useEffect(() => {
    fetchDocs();
    fetchSessions();
  }, []);

  useEffect(() => {
    if (sessionId) {
      fetchMessages(sessionId);
    } else {
      setActiveSession(null);
      setMessages([]);
    }
  }, [sessionId]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAsking]);

  const handleChatCreated = (id: string) => {
    fetchSessions();
    navigate(`/app/chat/${id}`);
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this chat session?')) return;
    try {
      await apiRequest(`/api/v1/chats/${id}`, { method: 'DELETE' });
      fetchSessions();
      if (sessionId === id) {
        navigate('/app');
      }
    } catch (err: any) {
      alert(err.message || 'Failed to delete session.');
    }
  };

  const handleTogglePin = async (sessionItem: ChatSessionItem, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiRequest(`/api/v1/chats/${sessionItem.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ is_pinned: !sessionItem.is_pinned }),
      });
      fetchSessions();
    } catch (err: any) {
      alert(err.message || 'Failed to toggle pin state.');
    }
  };

  const handleStartRename = (sessionItem: ChatSessionItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setRenamingId(sessionItem.id);
    setRenameTitle(sessionItem.title);
  };

  const handleSaveRename = async (id: string, e: React.FormEvent) => {
    e.preventDefault();
    if (!renameTitle.trim()) return;
    try {
      await apiRequest(`/api/v1/chats/${id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: renameTitle.trim() }),
      });
      setRenamingId(null);
      fetchSessions();
      if (sessionId === id) {
        fetchMessages(id);
      }
    } catch (err: any) {
      alert(err.message || 'Failed to rename chat session.');
    }
  };

  const handleSendQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId || !question.trim() || isAsking) return;

    const queryText = question.trim();
    if (queryText.length > RAG_MAX_QUESTION_CHARS) {
      setAskError(`Question exceeds length limit of ${RAG_MAX_QUESTION_CHARS} characters.`);
      return;
    }

    setQuestion('');
    setAskError(null);
    setIsAsking(true);
    setActiveStage('Searching documents and generating an answer...');

    // Optimistically add user message log
    const userMsgOptimistic: MessageItem = {
      id: crypto.randomUUID(),
      role: 'user',
      content: queryText
    };
    setMessages((prev) => [...prev, userMsgOptimistic]);

    try {
      const data = await apiRequest(`/api/v1/chats/${sessionId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: queryText }),
      });

      // Update state logs
      setMessages((prev) => [...prev, data]);
    } catch (err: any) {
      setAskError(err.message || 'Failed to generate response.');
      // Remove the optimistic message on request failures so state remains synced
      setMessages((prev) => prev.filter((m) => m.id !== userMsgOptimistic.id));
    } finally {
      setIsAsking(false);
      setActiveStage(null);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100 font-sans text-xs">
      
      {/* 1. Left Sidebar - Desktop */}
      <aside className="hidden lg:flex flex-col w-64 bg-slate-900/40 border-r border-slate-900 shrink-0">
        {/* Top Header */}
        <div className="p-4 border-b border-slate-900 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-white font-extrabold text-sm">
            <Bot className="w-5 h-5 text-violet-500" />
            DocuMind AI
          </Link>
        </div>

        {/* Action Button */}
        <div className="p-3">
          <button
            onClick={() => setIsNewChatOpen(true)}
            className="w-full py-2.5 rounded-xl font-bold bg-violet-600 hover:bg-violet-500 text-white flex items-center justify-center gap-1.5 shadow-lg shadow-violet-500/10"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto px-2 space-y-1 py-1">
          {isLoadingSessions ? (
            <div className="flex justify-center py-6">
              <Loader2 className="w-5 h-5 text-slate-500 animate-spin" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8 text-slate-500">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 text-slate-600" />
              <p className="text-[11px]">No conversations yet</p>
            </div>
          ) : (
            sessions.map((sess) => {
              const isActive = sessionId === sess.id;
              const isRenaming = renamingId === sess.id;

              return (
                <div
                  key={sess.id}
                  onClick={() => navigate(`/app/chat/${sess.id}`)}
                  className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition-all ${
                    isActive
                      ? 'bg-slate-900 border border-slate-800 text-white'
                      : 'hover:bg-slate-900/50 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <MessageSquare className="w-4 h-4 shrink-0 text-slate-500" />
                    {isRenaming ? (
                      <form
                        onSubmit={(e) => handleSaveRename(sess.id, e)}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1"
                      >
                        <input
                          type="text"
                          value={renameTitle}
                          onChange={(e) => setRenameTitle(e.target.value)}
                          onBlur={(e) => handleSaveRename(sess.id, e)}
                          autoFocus
                          className="w-full bg-slate-950 px-1 py-0.5 border border-violet-500 rounded text-xs text-white"
                        />
                      </form>
                    ) : (
                      <span className="truncate pr-4 text-xs font-medium">{sess.title}</span>
                    )}
                  </div>

                  {!isRenaming && (
                    <div className="absolute right-2 top-2 hidden group-hover:flex items-center gap-1 bg-slate-900/90 pl-2 rounded-md">
                      <button
                        onClick={(e) => handleTogglePin(sess, e)}
                        className="p-1 text-slate-500 hover:text-violet-400"
                        aria-label={sess.is_pinned ? 'Unpin chat' : 'Pin chat'}
                      >
                        {sess.is_pinned ? <PinOff className="w-3 h-3" aria-hidden="true" /> : <Pin className="w-3 h-3" aria-hidden="true" />}
                      </button>
                      <button
                        onClick={(e) => handleStartRename(sess, e)}
                        className="p-1 text-slate-500 hover:text-slate-200"
                        aria-label="Rename chat"
                      >
                        <FileText className="w-3 h-3" aria-hidden="true" />
                      </button>
                      <button
                        onClick={(e) => handleDeleteSession(sess.id, e)}
                        className="p-1 text-slate-500 hover:text-red-400"
                        aria-label="Delete chat"
                      >
                        <Trash2 className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </div>
                  )}

                  {!isRenaming && sess.is_pinned && !isActive && (
                    <Pin className="w-3 h-3 text-violet-400 rotate-45 shrink-0 ml-1.5 group-hover:hidden" />
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer User Section */}
        <div className="p-3 border-t border-slate-900 flex items-center justify-between gap-2 bg-slate-900/10">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200 truncate">{user?.full_name}</p>
            <p className="text-[10px] text-slate-500 truncate">{user?.email}</p>
          </div>
          <button
            onClick={logout}
            className="p-1.5 text-slate-500 hover:text-red-400 bg-slate-900 hover:bg-slate-850 rounded-lg transition-colors"
            aria-label="Log out"
          >
            <LogOut className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </aside>

      {/* 2. Main Content Surface */}
      <main className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden relative">
        {/* Mobile Header */}
        <div className="lg:hidden p-3 border-b border-slate-900 flex items-center justify-between bg-slate-900/20 z-20">
          <button
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Open conversations sidebar"
            className="p-2 bg-slate-900 rounded-lg text-slate-400 hover:text-white"
          >
            <MessageSquare className="w-5 h-5" aria-hidden="true" />
          </button>
          
          <span className="font-extrabold text-sm text-white">DocuMind AI</span>

          <button
            onClick={() => setMobileDocsOpen(true)}
            aria-label="Open knowledge base panel"
            className="p-2 bg-slate-900 rounded-lg text-slate-400 hover:text-white"
          >
            <FolderOpen className="w-5 h-5" />
          </button>
        </div>

        {/* Chat Workspace Area */}
        {!sessionId ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center space-y-4">
            <MessageSquare className="w-12 h-12 text-slate-700" />
            <h2 className="text-base font-bold text-slate-300">No conversations yet</h2>
            <p className="text-xs text-slate-500 max-w-[280px]">
              Create a chat using one or more indexed documents from your knowledge base.
            </p>
            <button
              onClick={() => setIsNewChatOpen(true)}
              className="px-5 py-2.5 rounded-xl font-bold bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/15"
            >
              Start New Chat
            </button>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header chat info */}
            <div className="px-6 py-4 border-b border-slate-900 bg-slate-950 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-200">{activeSession?.title}</h2>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Associated documents: {activeSession?.document_ids.length || 0}
                </p>
              </div>
            </div>

            {/* Chat Logs */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {isLoadingMessages ? (
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
                </div>
              ) : messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-2">
                  <Bot className="w-10 h-10 text-slate-700" />
                  <h3 className="text-sm font-semibold text-slate-400">New conversation started</h3>
                  <p className="text-xs text-slate-500 max-w-[240px]">
                    Ask a question to see source-backed answers from your indexed documents.
                  </p>
                </div>
              ) : (
                messages.map((msg) => {
                  const isUser = msg.role === 'user';
                  return (
                    <div
                      key={msg.id}
                      className={`flex gap-4 max-w-3xl ${isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
                    >
                      <div
                        className={`p-2 w-8 h-8 rounded-lg shrink-0 flex items-center justify-center ${
                          isUser ? 'bg-indigo-650 text-white' : 'bg-violet-600 text-white'
                        }`}
                      >
                        {isUser ? <Key className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                      </div>
                      
                      <div className="space-y-1">
                        <div
                          className={`p-4 rounded-2xl border text-xs max-w-full text-slate-200 leading-relaxed ${
                            isUser
                              ? 'bg-slate-900 border-slate-800 rounded-tr-none'
                              : 'bg-slate-950 border-slate-900 rounded-tl-none'
                          }`}
                        >
                          {isUser ? (
                            <p>{msg.content}</p>
                          ) : (
                            <MessageContent content={msg.content} citations={msg.sources || []} />
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}

              {/* Loader response state */}
              {isAsking && (
                <div className="flex gap-4 max-w-3xl mr-auto">
                  <div className="p-2 w-8 h-8 rounded-lg shrink-0 bg-violet-600 text-white flex items-center justify-center">
                    <Loader2 className="w-4 h-4 animate-spin" />
                  </div>
                  <div className="p-4 rounded-2xl bg-slate-950 border border-slate-900 rounded-tl-none text-xs text-slate-400 flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-violet-400 animate-pulse" />
                    <span>{activeStage}</span>
                  </div>
                </div>
              )}

              <div ref={messageEndRef} />
            </div>

            {/* Composer Input Area */}
            <div className="p-4 border-t border-slate-900 bg-slate-950">
              <form onSubmit={handleSendQuestion} className="max-w-3xl mx-auto space-y-3">
                <div className="relative border border-slate-800 rounded-xl bg-slate-900 focus-within:border-violet-500 transition-colors flex items-center pr-3">
                  <textarea
                    rows={1}
                    placeholder="Ask a question about the selected documents..."
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSendQuestion(e);
                      }
                    }}
                    disabled={isAsking}
                    className="flex-1 px-4 py-3 bg-transparent text-xs text-slate-200 placeholder-slate-500 focus:outline-none resize-none"
                  />
                  <button
                    type="submit"
                    disabled={!question.trim() || isAsking}
                    className="p-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg disabled:opacity-30 disabled:hover:bg-violet-600 transition-all shadow"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>

                {askError && (
                  <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 p-2.5 rounded-lg">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{askError}</span>
                  </div>
                )}
              </form>
            </div>
          </div>
        )}
      </main>

      {/* 3. Right Sidebar Panel - Desktop */}
      <aside className="hidden lg:flex flex-col w-72 bg-slate-900/40 border-l border-slate-900 shrink-0">
        <div className="p-4 border-b border-slate-900">
          <h2 className="text-sm font-bold text-slate-200">Knowledge Base</h2>
        </div>
        
        <div className="p-4 border-b border-slate-900">
          <DocumentUpload onUploadSuccess={fetchDocs} />
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoadingDocs ? (
            <div className="flex justify-center py-6">
              <Loader2 className="w-5 h-5 text-slate-500 animate-spin" />
            </div>
          ) : (
            <DocumentList documents={documents} onRefresh={fetchDocs} />
          )}
        </div>
      </aside>

      {/* 4. New Chat Modal Dialog */}
      <NewChatModal
        isOpen={isNewChatOpen}
        onClose={() => setIsNewChatOpen(false)}
        documents={documents}
        onChatCreated={handleChatCreated}
      />

      {/* 5. Mobile Sidebar Drawer */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <div className="fixed inset-0 bg-black/80" onClick={() => setMobileSidebarOpen(false)} />
          <div className="relative w-64 max-w-xs bg-slate-950 border-r border-slate-900 flex flex-col h-full z-10">
            {/* Same left sidebar content */}
            <div className="p-4 border-b border-slate-900 flex items-center justify-between">
              <span className="font-extrabold text-sm text-white">Conversations</span>
              <button
                onClick={() => setMobileSidebarOpen(false)}
                aria-label="Close conversations sidebar"
                className="p-1 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>
            
            <div className="p-3">
              <button
                onClick={() => {
                  setMobileSidebarOpen(false);
                  setIsNewChatOpen(true);
                }}
                className="w-full py-2.5 rounded-xl font-bold bg-violet-600 hover:bg-violet-500 text-white flex items-center justify-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                New Chat
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-2 space-y-1">
              {sessions.map((sess) => (
                <div
                  key={sess.id}
                  onClick={() => {
                    setMobileSidebarOpen(false);
                    navigate(`/app/chat/${sess.id}`);
                  }}
                  className={`p-2.5 rounded-xl cursor-pointer ${
                    sessionId === sess.id ? 'bg-slate-900 text-white' : 'text-slate-400'
                  }`}
                >
                  <span className="truncate block text-xs">{sess.title}</span>
                </div>
              ))}
            </div>

            <div className="p-3 border-t border-slate-900 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-200 truncate">{user?.full_name}</p>
              </div>
              <button onClick={logout} className="p-1.5 text-slate-500 hover:text-red-400">
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. Mobile Knowledge Base Drawer */}
      {mobileDocsOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex flex-row-reverse">
          <div className="fixed inset-0 bg-black/80" onClick={() => setMobileDocsOpen(false)} />
          <div className="relative w-80 max-w-xs bg-slate-950 border-l border-slate-900 flex flex-col h-full z-10">
            <div className="p-4 border-b border-slate-900 flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-200">Knowledge Base</h2>
              <button
                onClick={() => setMobileDocsOpen(false)}
                aria-label="Close knowledge base panel"
                className="p-1 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>
            
            <div className="p-4 border-b border-slate-900">
              <DocumentUpload
                onUploadSuccess={() => {
                  fetchDocs();
                  setMobileDocsOpen(false);
                }}
              />
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <DocumentList documents={documents} onRefresh={fetchDocs} />
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

// -------------------------------------------------------------
// Root App Router Wrapper
// -------------------------------------------------------------
const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <WorkspacePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/chat/:sessionId"
              element={
                <ProtectedRoute>
                  <WorkspacePage />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
