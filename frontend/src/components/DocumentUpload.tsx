import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, AlertCircle, RefreshCw, Loader2 } from 'lucide-react';
import { apiRequest } from '../lib/api';

interface DocumentUploadProps {
  onUploadSuccess: () => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUploadSuccess }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  
  // Track failure states to allow recovery
  const [failedDocId, setFailedDocId] = useState<string | null>(null);
  const [failedStage, setFailedStage] = useState<'process' | 'index' | null>(null);

  const runPipeline = useCallback(async (docId: string, startStage: 'process' | 'index' = 'process') => {
    try {
      setFailedDocId(null);
      setFailedStage(null);
      setErrorMsg(null);

      if (startStage === 'process') {
        setStatusMsg('Processing document content...');
        await apiRequest(`/api/v1/documents/${docId}/process`, { method: 'POST' });
      }

      setStatusMsg('Indexing vectors...');
      await apiRequest(`/api/v1/documents/${docId}/index`, { method: 'POST' });

      setStatusMsg(null);
      onUploadSuccess();
    } catch (err: any) {
      setFailedDocId(docId);
      setFailedStage(startStage);
      setErrorMsg(err.message || 'Pipeline stage execution failed.');
      setStatusMsg(null);
    }
  }, [onUploadSuccess]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    const file = acceptedFiles[0];

    // Client-side extension validation
    const allowedExtensions = ['.pdf', '.docx', '.txt', '.md'];
    const fileExt = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.includes(fileExt)) {
      setErrorMsg('Unsupported file type. Only PDF, DOCX, TXT, and MD are allowed.');
      return;
    }

    // Client-side size validation (10MB limit)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      setErrorMsg('File size exceeds the 10 MB limit.');
      return;
    }

    setIsUploading(true);
    setErrorMsg(null);
    setStatusMsg('Uploading file...');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const data = await apiRequest('/api/v1/documents/upload', {
        method: 'POST',
        // Fetch will automatically omit content-type header when FormData is passed, allowing boundaries to be set
        body: formData,
      });

      setIsUploading(false);
      await runPipeline(data.id, 'process');
    } catch (err: any) {
      setIsUploading(false);
      setErrorMsg(err.message || 'File upload failed.');
      setStatusMsg(null);
    }
  }, [runPipeline]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    disabled: isUploading || !!statusMsg,
  });

  const handleRetry = () => {
    if (failedDocId && failedStage) {
      runPipeline(failedDocId, failedStage);
    }
  };

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? 'border-violet-500 bg-violet-500/5'
            : 'border-slate-800 hover:border-slate-700 bg-slate-900/50'
        } ${(isUploading || statusMsg) ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center space-y-2">
          {isUploading || statusMsg ? (
            <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
          ) : (
            <UploadCloud className="w-8 h-8 text-slate-400 group-hover:text-slate-300" />
          )}
          
          <p className="text-sm font-medium text-slate-200">
            {statusMsg || (isDragActive ? 'Drop the file here' : 'Drag & drop a file here, or click to browse')}
          </p>
          <p className="text-xs text-slate-500">
            PDF, DOCX, TXT, or MD up to 10 MB
          </p>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2">
            <p className="text-xs text-red-200">{errorMsg}</p>
            {failedDocId && (
              <button
                onClick={handleRetry}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-red-500/20 text-red-200 hover:bg-red-500/30 rounded transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Retry {failedStage === 'process' ? 'Processing' : 'Indexing'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
