import React from 'react';
import { X, FileText, Bookmark, Info } from 'lucide-react';

interface RetrievedSource {
  citation_id: string;
  document_id: string;
  source_filename: string;
  file_type: string;
  page_number?: number | null;
  chunk_index: number;
  distance: number;
}

interface CitationPopoverProps {
  citation: RetrievedSource;
  onClose: () => void;
}

export const CitationPopover: React.FC<CitationPopoverProps> = ({ citation, onClose }) => {
  return (
    <div className="absolute z-40 w-72 p-4 bg-slate-950 border border-slate-800 rounded-xl shadow-2xl space-y-3 text-left">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full">
          {citation.citation_id}
        </span>
        <button
          onClick={onClose}
          aria-label="Close citation"
          className="p-0.5 text-slate-500 hover:text-slate-300 hover:bg-slate-900 rounded transition-colors"
        >
          <X className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>

      <div className="space-y-2">
        <div className="flex items-start gap-2.5">
          <FileText className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200 truncate" title={citation.source_filename}>
              {citation.source_filename}
            </p>
            <p className="text-[10px] text-slate-500 capitalize">
              {citation.file_type} File
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-900">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
            <Bookmark className="w-3.5 h-3.5 text-slate-500" />
            <span>
              Page: {citation.page_number !== undefined && citation.page_number !== null ? citation.page_number : 'N/A'}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
            <Info className="w-3.5 h-3.5 text-slate-500" />
            <span>Chunk: {citation.chunk_index}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
