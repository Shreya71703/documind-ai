import React, { useState } from 'react';
import { FileText, Loader2, AlertCircle, CheckCircle, Trash2, RefreshCw } from 'lucide-react';
import { apiRequest } from '../lib/api';

export interface DocumentItem {
  id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: string;
  index_status: string;
  chunk_count: number;
  created_at: string;
}

interface DocumentListProps {
  documents: DocumentItem[];
  onRefresh: () => void;
}

export const DocumentList: React.FC<DocumentListProps> = ({ documents, onRefresh }) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this document from your knowledge base?')) return;
    try {
      setDeletingId(id);
      await apiRequest(`/api/v1/documents/${id}`, { method: 'DELETE' });
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Failed to delete document.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleRetryPipeline = async (id: string, currentStatus: string, currentIdxStatus: string) => {
    try {
      setRetryingId(id);
      
      if (currentStatus === 'failed') {
        await apiRequest(`/api/v1/documents/${id}/process`, { method: 'POST' });
      }
      
      if (currentIdxStatus !== 'indexed') {
        await apiRequest(`/api/v1/documents/${id}/index`, { method: 'POST' });
      }
      
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Pipeline retry failed.');
    } finally {
      setRetryingId(null);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (documents.length === 0) {
    return (
      <div className="text-center py-8 px-4 border border-dashed border-slate-800 rounded-xl bg-slate-900/20">
        <FileText className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-300">Build your knowledge base</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-[240px] mx-auto">
          Upload a document to start asking grounded questions.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {documents.map((doc) => {
        const isFailed = doc.status === 'failed' || doc.index_status === 'failed';
        const isIndexing = doc.index_status === 'indexing';
        const isProcessing = doc.status === 'processing';
        const isReady = doc.status === 'ready' && doc.index_status === 'indexed';

        return (
          <div
            key={doc.id}
            className="p-3 bg-slate-900/60 border border-slate-800/80 rounded-xl flex items-center justify-between gap-3 group hover:border-slate-700/80 transition-all duration-200"
          >
            <div className="flex items-center gap-3 min-w-0">
              <div className="p-2 bg-slate-800 rounded-lg text-slate-400">
                <FileText className="w-5 h-5 shrink-0" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-200 truncate pr-2">
                  {doc.original_filename}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] text-slate-500 font-medium">
                    {formatSize(doc.file_size)}
                  </span>
                  <span className="text-[10px] text-slate-600 font-bold">•</span>
                  <div className="flex items-center gap-1">
                    {isReady ? (
                      <span className="inline-flex items-center gap-0.5 text-[10px] text-emerald-400 font-medium">
                        <CheckCircle className="w-3 h-3" />
                        Indexed ({doc.chunk_count} chunks)
                      </span>
                    ) : isFailed ? (
                      <span className="inline-flex items-center gap-0.5 text-[10px] text-red-400 font-medium">
                        <AlertCircle className="w-3 h-3" />
                        Failed
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-0.5 text-[10px] text-violet-400 font-medium">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        {isProcessing ? 'Processing...' : isIndexing ? 'Indexing...' : 'Uploaded'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              {isFailed && (
                <button
                  disabled={retryingId === doc.id}
                  onClick={() => handleRetryPipeline(doc.id, doc.status, doc.index_status)}
                  className="p-1.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors duration-150"
                  aria-label="Retry failed pipeline stage"
                >
                  {retryingId === doc.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <RefreshCw className="w-4 h-4" aria-hidden="true" />
                  )}
                </button>
              )}
              
              <button
                disabled={deletingId === doc.id}
                onClick={() => handleDelete(doc.id)}
                className="p-1.5 text-slate-400 hover:text-red-400 bg-slate-800 hover:bg-slate-800/80 rounded-lg transition-colors duration-150"
                aria-label={`Delete ${doc.original_filename}`}
              >
                {deletingId === doc.id ? (
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
