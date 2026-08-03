import React, { useState, useEffect, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useNavigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  FileText,
  Sparkles,
  ChevronRight,
  Plus,
  Send,
  Loader2,
  Pin,
  Trash2,
  FolderOpen,
  MessageSquare,
  AlertCircle,
  PinOff,
  X,
  Zap,
  ShieldCheck,
  Search,
  BookOpen
} from 'lucide-react';

const RAG_MAX_QUESTION_CHARS = 4000;

import { apiRequest, streamChatMessage } from './lib/api';
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
// Premium Modern Landing Page Component
// -------------------------------------------------------------
const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  const handleGetStarted = () => {
    navigate('/dashboard');
  };

  return (
    <div className="relative min-h-screen flex flex-col justify-between overflow-hidden bg-slate-950 text-slate-100 selection:bg-violet-500 selection:text-white">
      {/* Dynamic Background Glowing Orbs */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-violet-600/10 blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-indigo-600/10 blur-[140px] pointer-events-none" />

      {/* Top Navigation */}
      <header className="w-full max-w-7xl mx-auto px-6 py-6 flex justify-between items-center z-10 border-b border-slate-900/80 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-2xl bg-gradient-to-tr from-violet-600 to-indigo-500 text-white flex items-center justify-center shadow-lg shadow-violet-500/25">
            <Bot className="w-6 h-6" />
          </div>
          <span className="font-extrabold text-xl tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-300">
            DocuMind AI
          </span>
        </div>
        
        <div className="flex items-center gap-4">
          <button
            onClick={handleGetStarted}
            className="px-5 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white transition-all shadow-lg shadow-violet-500/20 flex items-center gap-2 group"
          >
            Get Started
            <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>
      </header>

      {/* Main Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center max-w-5xl mx-auto px-6 text-center z-10 py-16 sm:py-24">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-bold uppercase tracking-widest mb-8 shadow-inner">
          <Sparkles className="w-4 h-4 animate-pulse text-violet-400" />
          Next-Gen Grounded RAG Knowledge Assistant
        </div>
        
        <h1 className="text-4xl sm:text-7xl font-extrabold tracking-tight mb-6 text-white leading-[1.1]">
          Turn Your Documents Into <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-400 via-indigo-300 to-cyan-400">
            Intelligent Answers
          </span>
        </h1>
        
        <p className="text-slate-400 text-lg sm:text-xl max-w-3xl mb-12 leading-relaxed font-light">
          Upload PDFs, Markdown, and text files. Extract instant, grounded answers back-referenced with interactive source citations. No login required.
        </p>

        {/* Primary CTA */}
        <div className="flex flex-col sm:flex-row gap-4 items-center justify-center w-full max-w-md mb-16">
          <button
            onClick={handleGetStarted}
            className="w-full sm:w-auto px-8 py-4 rounded-2xl text-sm font-extrabold bg-gradient-to-r from-violet-600 via-indigo-600 to-violet-500 hover:from-violet-500 hover:to-indigo-500 text-white transition-all shadow-xl shadow-violet-600/30 flex items-center justify-center gap-3 group transform hover:-translate-y-0.5"
          >
            <Zap className="w-5 h-5 fill-current text-violet-200" />
            Get Started Free
            <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
        </div>

        {/* Interactive Feature Highlights Preview Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-5 w-full mt-8 max-w-4xl text-left">
          <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-violet-500/30 transition-colors space-y-2 backdrop-blur-sm shadow-xl">
            <div className="p-2 w-fit rounded-xl bg-violet-500/10 text-violet-400">
              <FileText className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-100">Multi-Format Support</h4>
            <p className="text-xs text-slate-400 leading-normal">Seamlessly upload and process PDF, DOCX, TXT, and Markdown documents.</p>
          </div>

          <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-violet-500/30 transition-colors space-y-2 backdrop-blur-sm shadow-xl">
            <div className="p-2 w-fit rounded-xl bg-indigo-500/10 text-indigo-400">
              <Search className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-100">Semantic Search</h4>
            <p className="text-xs text-slate-400 leading-normal">High-dimensional vector embeddings match precise meaning across your knowledge base.</p>
          </div>

          <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-violet-500/30 transition-colors space-y-2 backdrop-blur-sm shadow-xl">
            <div className="p-2 w-fit rounded-xl bg-cyan-500/10 text-cyan-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-100">Zero Hallucinations</h4>
            <p className="text-xs text-slate-400 leading-normal">Strictly grounded context guarantees factual, accurate AI-synthesized responses.</p>
          </div>

          <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-violet-500/30 transition-colors space-y-2 backdrop-blur-sm shadow-xl">
            <div className="p-2 w-fit rounded-xl bg-emerald-500/10 text-emerald-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-100">Source Citations</h4>
            <p className="text-xs text-slate-400 leading-normal">Clickable source chips map directly back to exact page numbers and document chunks.</p>
          </div>
        </div>

        {/* Live Interface Preview Mockup */}
        <div className="w-full max-w-4xl mt-16 p-4 rounded-3xl bg-slate-900/60 border border-slate-800/80 shadow-2xl backdrop-blur-md">
          <div className="flex items-center gap-2 pb-3 border-b border-slate-800/60 px-2">
            <div className="w-3 h-3 rounded-full bg-red-500/80" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
            <div className="w-3 h-3 rounded-full bg-green-500/80" />
            <span className="text-[11px] font-medium text-slate-400 ml-2">DocuMind AI Knowledge Workspace</span>
          </div>
          <div className="p-6 text-left space-y-4">
            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-850 text-xs text-slate-300">
              <span className="font-bold text-violet-400">User:</span> What are the key architecture requirements outlined in Section 3?
            </div>
            <div className="bg-violet-950/20 p-4 rounded-xl border border-violet-500/20 text-xs text-slate-200 space-y-2">
              <div className="font-bold text-violet-400 flex items-center gap-1.5">
                <Bot className="w-4 h-4" /> DocuMind AI:
              </div>
              <p className="leading-relaxed">
                Section 3 specifies that the system must utilize a high-performance vector retrieval store with chunk overlaps of 200 characters <span className="inline-block px-1.5 py-0.5 text-[10px] font-bold text-violet-300 bg-violet-500/20 border border-violet-500/30 rounded">Source 1</span> and guarantee sub-second vector search latency across knowledge collections <span className="inline-block px-1.5 py-0.5 text-[10px] font-bold text-violet-300 bg-violet-500/20 border border-violet-500/30 rounded">Source 2</span>.
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full max-w-7xl mx-auto px-6 py-6 flex flex-col sm:flex-row justify-between items-center z-10 border-t border-slate-900 text-slate-500 text-xs gap-2">
        <div>&copy; {new Date().getFullYear()} DocuMind AI. All rights reserved.</div>
        <div className="flex items-center gap-4 text-slate-400">
          <span className="hover:text-white cursor-pointer" onClick={handleGetStarted}>Open Workspace</span>
        </div>
      </footer>
    </div>
  );
};

// -------------------------------------------------------------
// Main App Workspace Layout (/dashboard)
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
  debug_metadata?: any;
}

const WorkspacePage: React.FC = () => {
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

  // Lightweight polling: refresh document list every 5s while any doc is still indexing/processing.
  // This shows updated statuses without triggering new pipeline calls.
  useEffect(() => {
    const hasPending = documents.some(
      (d) => d.index_status === 'indexing' || d.status === 'processing' || d.status === 'uploaded'
    );
    if (!hasPending) return;
    const timer = setInterval(() => {
      apiRequest('/api/v1/documents')
        .then((refreshed) => setDocuments(refreshed))
        .catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [documents]);

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
    navigate(`/dashboard/chat/${id}`);
  };

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this chat session?')) return;
    try {
      await apiRequest(`/api/v1/chats/${id}`, { method: 'DELETE' });
      fetchSessions();
      if (sessionId === id) {
        navigate('/dashboard');
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
    setActiveStage('Searching vector index & generating streaming answer...');

    const userMsgOptimistic: MessageItem = {
      id: crypto.randomUUID(),
      role: 'user',
      content: queryText
    };

    const assistantMsgId = crypto.randomUUID();
    const assistantMsgOptimistic: MessageItem = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      sources: [],
      debug_metadata: undefined
    };

    setMessages((prev) => [...prev, userMsgOptimistic, assistantMsgOptimistic]);

    await streamChatMessage(
      sessionId,
      queryText,
      (token) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, content: m.content + token } : m))
        );
      },
      (citations, debugMetadata) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, sources: citations, debug_metadata: debugMetadata }
              : m
          )
        );
        setIsAsking(false);
        setActiveStage(null);
      },
      (err) => {
        setAskError(err.message || 'Failed to generate response.');
        setIsAsking(false);
        setActiveStage(null);
      }
    );
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
                  onClick={() => navigate(`/dashboard/chat/${sess.id}`)}
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
                          className="w-full bg-slate-950 border border-violet-500 text-xs text-white px-1.5 py-0.5 rounded outline-none"
                        />
                      </form>
                    ) : (
                      <span className="truncate text-xs font-medium">{sess.title}</span>
                    )}
                  </div>

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      title={sess.is_pinned ? 'Unpin chat' : 'Pin chat'}
                      onClick={(e) => handleTogglePin(sess, e)}
                      className="p-1 hover:text-white text-slate-500"
                    >
                      {sess.is_pinned ? (
                        <PinOff className="w-3.5 h-3.5 text-violet-400" />
                      ) : (
                        <Pin className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      title="Rename chat"
                      onClick={(e) => handleStartRename(sess, e)}
                      className="p-1 hover:text-white text-slate-500 text-[10px]"
                    >
                      ✎
                    </button>
                    <button
                      title="Delete chat"
                      onClick={(e) => handleDeleteSession(sess.id, e)}
                      className="p-1 hover:text-red-400 text-slate-500"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* 2. Middle Column - Chat & Conversation Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-slate-950">
        {/* Header */}
        <header className="h-14 px-4 border-b border-slate-900 flex items-center justify-between bg-slate-950/80 backdrop-blur z-20">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
              className="lg:hidden p-2 rounded-lg bg-slate-900 text-slate-400 hover:text-white"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
            
            <div className="min-w-0">
              <h1 className="font-bold text-sm text-white truncate">
                {activeSession ? activeSession.title : 'DocuMind AI Knowledge Workspace'}
              </h1>
              <p className="text-[10px] text-slate-500 truncate">
                {activeSession
                  ? `${activeSession.document_ids?.length || 0} indexed document(s) attached`
                  : 'Select or create a conversation to query your documents'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setMobileDocsOpen(!mobileDocsOpen)}
              className="xl:hidden p-2 rounded-lg bg-slate-900 text-slate-400 hover:text-white flex items-center gap-1 text-xs font-semibold"
            >
              <FolderOpen className="w-4 h-4 text-violet-400" />
              <span>Docs</span>
            </button>
          </div>
        </header>

        {/* Message Log viewport */}
        <div className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-6">
          {!sessionId ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto space-y-4 py-12">
              <div className="p-4 rounded-3xl bg-violet-600/10 border border-violet-500/20 text-violet-400">
                <Sparkles className="w-10 h-10" />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-bold text-white">Welcome to DocuMind AI</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Start a new conversation, attach uploaded documents, and ask grounded questions with citation back-references.
                </p>
              </div>
              <button
                onClick={() => setIsNewChatOpen(true)}
                className="px-5 py-2.5 rounded-xl font-bold bg-violet-600 hover:bg-violet-500 text-white flex items-center gap-2 shadow-lg shadow-violet-500/20"
              >
                <Plus className="w-4 h-4" />
                Start New Chat
              </button>
            </div>
          ) : isLoadingMessages ? (
            <div className="flex justify-center items-center h-48">
              <Loader2 className="w-6 h-6 text-violet-500 animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-2 text-slate-500 py-16">
              <MessageSquare className="w-8 h-8 text-slate-600" />
              <p className="font-semibold text-xs text-slate-300">No messages in this chat session</p>
              <p className="text-[11px] text-slate-500">Type a question below to query attached documents.</p>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 max-w-3xl ${isUser ? 'ml-auto flex-row-reverse' : ''}`}
                >
                  <div
                    className={`w-7 h-7 rounded-xl flex items-center justify-center shrink-0 ${
                      isUser
                        ? 'bg-slate-800 text-slate-200'
                        : 'bg-violet-600 text-white shadow-md shadow-violet-500/20'
                    }`}
                  >
                    {isUser ? 'U' : <Bot className="w-4 h-4" />}
                  </div>

                  <div
                    className={`space-y-2 p-4 rounded-2xl text-xs leading-relaxed max-w-xl ${
                      isUser
                        ? 'bg-violet-600 text-white font-medium rounded-tr-none'
                        : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none'
                    }`}
                  >
                    {isUser ? (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <>
                        <MessageContent content={msg.content} citations={msg.sources || []} />
                        {msg.debug_metadata && (
                          <details className="mt-3 text-[10px] text-slate-400 bg-slate-950/80 rounded-xl p-3 border border-slate-800/80">
                            <summary className="cursor-pointer font-bold text-violet-400 hover:text-violet-300 flex items-center gap-1.5 select-none">
                              <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                              <span>RAG Debug Metrics</span>
                            </summary>
                            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 pt-2 border-t border-slate-800/60 font-mono text-[10px]">
                              <div><span className="text-slate-500">Provider:</span> {msg.debug_metadata.provider_used}</div>
                              <div><span className="text-slate-500">Chat Model:</span> {msg.debug_metadata.chat_model}</div>
                              <div><span className="text-slate-500">Embedding Model:</span> {msg.debug_metadata.embedding_model}</div>
                              <div><span className="text-slate-500">Retrieved Chunks:</span> {msg.debug_metadata.retrieved_chunks}</div>
                              <div><span className="text-slate-500">Similarity Scores:</span> {JSON.stringify(msg.debug_metadata.similarity_scores)}</div>
                              <div><span className="text-slate-500">Response Time:</span> {msg.debug_metadata.response_time_ms} ms</div>
                              <div><span className="text-slate-500">Prompt Tokens:</span> ~{msg.debug_metadata.prompt_tokens}</div>
                              <div><span className="text-slate-500">Completion Tokens:</span> ~{msg.debug_metadata.completion_tokens}</div>
                              <div><span className="text-slate-500">Context Length:</span> {msg.debug_metadata.context_length} chars</div>
                              <div><span className="text-slate-500">Streaming:</span> {msg.debug_metadata.streaming_enabled ? 'Enabled' : 'Disabled'}</div>
                            </div>
                          </details>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Active Generation Indicator */}
          {isAsking && (
            <div className="flex gap-3 max-w-3xl">
              <div className="w-7 h-7 rounded-xl bg-violet-600 text-white flex items-center justify-center shrink-0 shadow-md shadow-violet-500/20">
                <Bot className="w-4 h-4 animate-spin" />
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl rounded-tl-none text-xs text-slate-400 space-y-2">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin" />
                  <span className="font-semibold text-slate-200">{activeStage}</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messageEndRef} />
        </div>

        {/* Question Prompt Input Box */}
        {sessionId && (
          <div className="p-4 border-t border-slate-900 bg-slate-950">
            <form onSubmit={handleSendQuestion} className="max-w-4xl mx-auto space-y-2">
              {askError && (
                <div className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{askError}</span>
                  </div>
                  <button type="button" onClick={() => setAskError(null)}>
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              <div className="relative flex items-center">
                <input
                  type="text"
                  placeholder="Ask a question about your documents..."
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={isAsking}
                  className="w-full pl-4 pr-12 py-3 bg-slate-900/60 border border-slate-800 focus:border-violet-500 focus:outline-none rounded-2xl text-xs text-slate-100 placeholder-slate-500 transition-colors"
                />
                <button
                  type="submit"
                  disabled={!question.trim() || isAsking}
                  className="absolute right-2 p-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-40 transition-all"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </form>
          </div>
        )}
      </main>

      {/* 3. Right Sidebar - Knowledge Base Documents */}
      <aside className="hidden xl:flex flex-col w-80 bg-slate-900/40 border-l border-slate-900 shrink-0">
        <div className="p-4 border-b border-slate-900 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-violet-400" />
            <h2 className="font-bold text-xs text-white">Knowledge Base</h2>
            {isLoadingDocs && <Loader2 className="w-3 h-3 text-slate-500 animate-spin ml-auto" />}
          </div>
        </div>

        <div className="p-4 border-b border-slate-900 space-y-3">
          <DocumentUpload onUploadSuccess={fetchDocs} />
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <DocumentList documents={documents} onRefresh={fetchDocs} />
        </div>
      </aside>

      {/* Modals & Drawers */}
      {isNewChatOpen && (
        <NewChatModal
          isOpen={isNewChatOpen}
          documents={documents}
          onClose={() => setIsNewChatOpen(false)}
          onChatCreated={handleChatCreated}
        />
      )}

      {/* Mobile Drawer - Sessions */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={() => setMobileSidebarOpen(false)} />
          <div className="relative flex flex-col w-72 max-w-full bg-slate-900 border-r border-slate-800 z-10">
            <div className="p-4 border-b border-slate-800 flex justify-between items-center">
              <span className="font-bold text-white text-sm">Conversations</span>
              <button onClick={() => setMobileSidebarOpen(false)}>
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>
            <div className="p-3">
              <button
                onClick={() => {
                  setMobileSidebarOpen(false);
                  setIsNewChatOpen(true);
                }}
                className="w-full py-2 rounded-xl font-bold bg-violet-600 text-white flex items-center justify-center gap-1 text-xs"
              >
                <Plus className="w-4 h-4" /> New Chat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {sessions.map((sess) => (
                <div
                  key={sess.id}
                  onClick={() => {
                    navigate(`/dashboard/chat/${sess.id}`);
                    setMobileSidebarOpen(false);
                  }}
                  className="p-2 rounded-xl hover:bg-slate-800 text-slate-300 text-xs flex items-center gap-2 cursor-pointer"
                >
                  <MessageSquare className="w-4 h-4 text-slate-500" />
                  <span className="truncate">{sess.title}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Drawer - Documents */}
      {mobileDocsOpen && (
        <div className="fixed inset-0 z-50 xl:hidden flex justify-end">
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={() => setMobileDocsOpen(false)} />
          <div className="relative flex flex-col w-80 max-w-full bg-slate-900 border-l border-slate-800 z-10">
            <div className="p-4 border-b border-slate-800 flex justify-between items-center">
              <span className="font-bold text-white text-sm">Knowledge Base</span>
              <button onClick={() => setMobileDocsOpen(false)}>
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>
            <div className="p-4 border-b border-slate-800">
              <DocumentUpload onUploadSuccess={fetchDocs} />
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
      <Router>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/dashboard" element={<WorkspacePage />} />
          <Route path="/dashboard/chat/:sessionId" element={<WorkspacePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </QueryClientProvider>
  );
};

export default App;
