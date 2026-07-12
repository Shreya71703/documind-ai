import React, { useState, useEffect, useRef } from 'react';
import { X, FileText, Check, Loader2, Sparkles, MessageSquare, AlertCircle } from 'lucide-react';
import { DocumentItem } from './DocumentList';
import { apiRequest } from '../lib/api';

interface NewChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  documents: DocumentItem[];
  onChatCreated: (chatId: string) => void;
}

function getDocStatusLabel(doc: DocumentItem): string {
  if (doc.index_status === 'indexing') return 'Indexing...';
  if (doc.index_status === 'failed') return 'Index failed';
  if (doc.status === 'failed') return 'Processing failed';
  if (doc.status === 'processing') return 'Processing...';
  if (doc.status === 'ready' && doc.index_status === 'not_indexed') return 'Ready — not yet indexed';
  if (doc.status === 'uploaded') return 'Uploaded — not processed';
  return doc.index_status;
}

export const NewChatModal: React.FC<NewChatModalProps> = ({
  isOpen,
  onClose,
  documents,
  onChatCreated
}) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [chatTitle, setChatTitle] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Focus management: ref for the close button to restore focus later
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // Escape key support
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Move focus into modal on open
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => titleInputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const isIndexed = (doc: DocumentItem) =>
    doc.status === 'ready' && doc.index_status === 'indexed';

  const indexedCount = documents.filter(isIndexed).length;

  const toggleSelect = (doc: DocumentItem) => {
    if (!isIndexed(doc)) return; // guard: never select non-indexed
    setSelectedIds((prev) =>
      prev.includes(doc.id) ? prev.filter((item) => item !== doc.id) : [...prev, doc.id]
    );
  };

  const handleCreateChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIds.length === 0) {
      setErrorMsg('Please select at least one indexed document.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const data = await apiRequest('/api/v1/chats', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: chatTitle.trim() || undefined,
          document_ids: selectedIds,
        }),
      });

      onChatCreated(data.id);
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create chat session.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-chat-modal-title"
        className="relative w-full max-w-lg bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/30">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-violet-400" aria-hidden="true" />
            <h2 id="new-chat-modal-title" className="text-sm font-bold text-slate-200">
              Start Grounded Chat
            </h2>
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleCreateChat} className="p-4 space-y-4">
          <div>
            <label htmlFor="chat-title" className="block text-xs font-semibold text-slate-400 mb-1.5">
              Chat Session Title (Optional)
            </label>
            <input
              id="chat-title"
              ref={titleInputRef}
              type="text"
              placeholder="e.g. Project Aurora Onboarding"
              value={chatTitle}
              onChange={(e) => setChatTitle(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-violet-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-0.5">
              Select Documents
            </label>
            <p className="text-[10px] text-slate-500 mb-2">
              Only indexed documents can be used for grounded AI chat. Other documents are shown but cannot be selected.
            </p>

            {documents.length === 0 ? (
              <div className="text-center py-6 px-4 border border-dashed border-slate-800 rounded-xl bg-slate-900/20">
                <FileText className="w-8 h-8 text-slate-500 mx-auto mb-2" aria-hidden="true" />
                <h3 className="text-xs font-semibold text-slate-400">No documents uploaded yet</h3>
                <p className="text-[10px] text-slate-500 mt-1 max-w-[200px] mx-auto">
                  Upload and index documents from the Knowledge Base panel first.
                </p>
              </div>
            ) : (
              <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
                {documents.map((doc) => {
                  const indexed = isIndexed(doc);
                  const isSelected = selectedIds.includes(doc.id);
                  return (
                    <div
                      key={doc.id}
                      onClick={() => toggleSelect(doc)}
                      role="checkbox"
                      aria-checked={isSelected}
                      aria-disabled={!indexed}
                      tabIndex={indexed ? 0 : -1}
                      onKeyDown={(e) => {
                        if (indexed && (e.key === ' ' || e.key === 'Enter')) {
                          e.preventDefault();
                          toggleSelect(doc);
                        }
                      }}
                      className={`p-3 border rounded-xl flex items-center justify-between transition-all duration-200 ${
                        !indexed
                          ? 'cursor-not-allowed opacity-50 border-slate-800/50 bg-slate-900/20'
                          : isSelected
                          ? 'cursor-pointer border-violet-500 bg-violet-500/5'
                          : 'cursor-pointer border-slate-800 hover:border-slate-700 bg-slate-900/50'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText
                          className={`w-4 h-4 shrink-0 ${
                            !indexed ? 'text-slate-600' : isSelected ? 'text-violet-400' : 'text-slate-500'
                          }`}
                          aria-hidden="true"
                        />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-slate-200 truncate pr-2">
                            {doc.original_filename}
                          </p>
                          <p className={`text-[10px] mt-0.5 ${indexed ? 'text-slate-500' : 'text-amber-500/70'}`}>
                            {indexed ? `${doc.chunk_count} chunks` : getDocStatusLabel(doc)}
                          </p>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-md border flex items-center justify-center flex-shrink-0 transition-all ${
                          !indexed
                            ? 'border-slate-700 bg-slate-900'
                            : isSelected
                            ? 'border-violet-500 bg-violet-500 text-white'
                            : 'border-slate-800 bg-slate-950'
                        }`}
                        aria-hidden="true"
                      >
                        {isSelected && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {indexedCount === 0 && documents.length > 0 && (
              <div className="mt-2 flex items-start gap-2 p-2.5 bg-amber-500/5 border border-amber-500/15 rounded-lg">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
                <p className="text-[10px] text-amber-400">
                  None of your documents are indexed yet. Index a document from the Knowledge Base to start chatting.
                </p>
              </div>
            )}
          </div>

          {errorMsg && (
            <p className="text-xs text-red-400 font-medium" role="alert">{errorMsg}</p>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 border border-slate-800 hover:bg-slate-900 rounded-xl transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || selectedIds.length === 0}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl shadow-lg shadow-violet-500/10 hover:shadow-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  Creating...
                </>
              ) : (
                <>
                  <MessageSquare className="w-4 h-4" aria-hidden="true" />
                  Start Chat
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
