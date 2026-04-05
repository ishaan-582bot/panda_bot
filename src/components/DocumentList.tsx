import { useSession } from '@/contexts/SessionContext';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { FileText, FileSpreadsheet, FileImage, FileCode, File } from 'lucide-react';
import { cn } from '@/lib/utils';

function getFileIcon(fileType: string) {
  switch (fileType) {
    case 'pdf':
      return <FileText className="w-4 h-4 text-red-400" />;
    case 'docx':
      return <FileText className="w-4 h-4 text-blue-400" />;
    case 'csv':
    case 'json':
      return <FileSpreadsheet className="w-4 h-4 text-green-400" />;
    case 'txt':
      return <FileCode className="w-4 h-4 text-slate-400" />;
    case 'png':
    case 'jpg':
    case 'jpeg':
      return <FileImage className="w-4 h-4 text-purple-400" />;
    default:
      return <File className="w-4 h-4 text-slate-400" />;
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-500/20 text-green-400 border-green-500/30';
    case 'processing':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
    case 'error':
      return 'bg-red-500/20 text-red-400 border-red-500/30';
    default:
      return 'bg-slate-700 text-slate-400 border-slate-600';
  }
}

export function DocumentList() {
  const { documents, session } = useSession();

  if (!session) {
    return (
      <div className="p-4 text-center">
        <p className="text-slate-500 text-sm">No active session</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-slate-500 text-sm">No documents uploaded yet</p>
        <p className="text-slate-600 text-xs mt-1">
          Upload files to start chatting
        </p>
      </div>
    );
  }

  return (
    <ScrollArea className="h-[300px]">
      <div className="space-y-2 p-2">
        {documents.map((doc) => (
          <div
            key={doc.document_id}
            className={cn(
              'p-3 rounded-lg border transition-all duration-200',
              'bg-slate-800/50 border-slate-700 hover:border-slate-600'
            )}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5">{getFileIcon(doc.file_type)}</div>
              
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  {doc.filename}
                </p>
                
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-slate-500">
                    {doc.size_mb.toFixed(2)} MB
                  </span>
                  <span className="text-slate-600">•</span>
                  <span className="text-xs text-slate-500">
                    {doc.total_chunks} chunks
                  </span>
                  <span className="text-slate-600">•</span>
                  <span className="text-xs text-slate-500">
                    {doc.total_tokens.toLocaleString()} tokens
                  </span>
                </div>
                
                <div className="mt-2">
                  <Badge 
                    variant="outline" 
                    className={cn('text-xs', getStatusColor(doc.processing_status))}
                  >
                    {doc.processing_status}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}