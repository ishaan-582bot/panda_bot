import { useState, useCallback } from 'react';
import { useSession } from '@/contexts/SessionContext';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Upload, File, X, Check, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UploadingFile {
  file: File;
  id: string;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  error?: string;
}

const ALLOWED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/csv',
  'application/json',
  'image/png',
  'image/jpeg',
  'image/tiff',
  'image/bmp',
];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export function FileUpload() {
  const { uploadFiles, isUploading, session } = useSession();
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return 'File type not supported';
    }
    if (file.size > MAX_FILE_SIZE) {
      return 'File too large (max 50MB)';
    }
    return null;
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    if (!session) return;

    const files = Array.from(e.dataTransfer.files);
    await processFiles(files);
  }, [session]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!session || !e.target.files) return;

    const files = Array.from(e.target.files);
    await processFiles(files);
    e.target.value = ''; // Reset input
  }, [session]);

  const processFiles = async (files: File[]) => {
    // Validate files
    const validFiles: File[] = [];
    const newUploadingFiles: UploadingFile[] = [];

    for (const file of files) {
      const error = validateFile(file);
      const id = Math.random().toString(36).substring(7);
      
      newUploadingFiles.push({
        file,
        id,
        progress: 0,
        status: error ? 'error' : 'pending',
        error: error || undefined,
      });

      if (!error) {
        validFiles.push(file);
      }
    }

    setUploadingFiles(prev => [...prev, ...newUploadingFiles]);

    if (validFiles.length > 0) {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadingFiles(prev =>
          prev.map(f =>
            f.status === 'pending' && validFiles.includes(f.file)
              ? { ...f, progress: Math.min(f.progress + 10, 90), status: 'uploading' }
              : f
          )
        );
      }, 200);

      try {
        await uploadFiles(validFiles);
        
        clearInterval(progressInterval);
        
        setUploadingFiles(prev =>
          prev.map(f =>
            validFiles.includes(f.file)
              ? { ...f, progress: 100, status: 'success' }
              : f
          )
        );
      } catch (error) {
        clearInterval(progressInterval);
        
        setUploadingFiles(prev =>
          prev.map(f =>
            validFiles.includes(f.file)
              ? { ...f, status: 'error', error: 'Upload failed' }
              : f
          )
        );
      }
    }

    // Clear completed files after 3 seconds
    setTimeout(() => {
      setUploadingFiles(prev => prev.filter(f => f.status === 'uploading' || f.status === 'pending'));
    }, 3000);
  };

  const removeFile = (id: string) => {
    setUploadingFiles(prev => prev.filter(f => f.id !== id));
  };

  if (!session) {
    return (
      <div className="p-6 border-2 border-dashed border-slate-700 rounded-xl bg-slate-800/50">
        <div className="text-center text-slate-500">
          <Upload className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>Create a session to upload files</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'relative p-8 border-2 border-dashed rounded-xl transition-all duration-300',
          'flex flex-col items-center justify-center gap-4',
          isDragOver
            ? 'border-indigo-500 bg-indigo-500/10 scale-[1.02]'
            : 'border-slate-600 bg-slate-800/50 hover:border-slate-500 hover:bg-slate-800'
        )}
      >
        <input
          type="file"
          multiple
          accept={ALLOWED_TYPES.join(',')}
          onChange={handleFileSelect}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isUploading}
        />
        
        <div className={cn(
          'w-12 h-12 rounded-full flex items-center justify-center transition-colors',
          isDragOver ? 'bg-indigo-500' : 'bg-slate-700'
        )}>
          <Upload className={cn(
            'w-6 h-6 transition-colors',
            isDragOver ? 'text-white' : 'text-slate-400'
          )} />
        </div>
        
        <div className="text-center">
          <p className="text-white font-medium">
            {isDragOver ? 'Drop files here' : 'Drag & drop files here'}
          </p>
          <p className="text-slate-400 text-sm mt-1">
            or click to browse
          </p>
        </div>
        
        <div className="text-xs text-slate-500 text-center">
          <p>Supported: PDF, DOCX, TXT, CSV, JSON, Images</p>
          <p>Max 50MB per file, 100MB total</p>
        </div>
      </div>

      {/* Uploading Files List */}
      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          {uploadingFiles.map(file => (
            <div
              key={file.id}
              className={cn(
                'flex items-center gap-3 p-3 rounded-lg border',
                file.status === 'error'
                  ? 'bg-red-500/10 border-red-500/30'
                  : file.status === 'success'
                  ? 'bg-green-500/10 border-green-500/30'
                  : 'bg-slate-800 border-slate-700'
              )}
            >
              <File className={cn(
                'w-5 h-5',
                file.status === 'error' && 'text-red-400',
                file.status === 'success' && 'text-green-400',
                file.status === 'uploading' && 'text-indigo-400',
                file.status === 'pending' && 'text-slate-400'
              )} />
              
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{file.file.name}</p>
                <p className="text-xs text-slate-500">
                  {(file.file.size / 1024 / 1024).toFixed(2)} MB
                </p>
                
                {file.status === 'uploading' && (
                  <Progress value={file.progress} className="h-1 mt-2" />
                )}
              </div>
              
              {file.status === 'error' && (
                <div className="flex items-center gap-1 text-red-400">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-xs">{file.error}</span>
                </div>
              )}
              
              {file.status === 'success' && (
                <Check className="w-5 h-5 text-green-400" />
              )}
              
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeFile(file.id)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}