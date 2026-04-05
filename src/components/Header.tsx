import { useSession } from '@/contexts/SessionContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { MessageSquare, Plus, Trash2, Clock, FileText } from 'lucide-react';
import { useState } from 'react';

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function getTimeColor(seconds: number): string {
  if (seconds < 300) return 'text-red-500'; // Less than 5 minutes
  if (seconds < 600) return 'text-yellow-500'; // Less than 10 minutes
  return 'text-green-500';
}

export function Header() {
  const { session, timeRemaining, createSession, terminateSession, documents } = useSession();
  const [isTerminateDialogOpen, setIsTerminateDialogOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-700 z-50">
      <div className="h-full max-w-7xl mx-auto px-4 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <span className="text-xl font-bold text-white">Panda</span>
        </div>

        {/* Session Info */}
        <div className="flex items-center gap-4">
          {session ? (
            <>
              {/* Timer */}
              <div className="flex items-center gap-2">
                <Clock className={`w-4 h-4 ${getTimeColor(timeRemaining)}`} />
                <span className={`text-sm font-mono ${getTimeColor(timeRemaining)}`}>
                  {formatTime(timeRemaining)}
                </span>
              </div>

              {/* Document Count */}
              <Badge variant="secondary" className="bg-slate-800 text-slate-300">
                <FileText className="w-3 h-3 mr-1" />
                {documents.length} doc{documents.length !== 1 ? 's' : ''}
              </Badge>

              {/* Session ID */}
              <Badge variant="outline" className="border-slate-600 text-slate-400 text-xs">
                {session.session_id.slice(0, 8)}...
              </Badge>

              {/* Terminate Button */}
              <Dialog open={isTerminateDialogOpen} onOpenChange={setIsTerminateDialogOpen}>
                <DialogTrigger asChild>
                  <Button 
                    variant="destructive" 
                    size="sm"
                    className="bg-red-600/20 text-red-400 hover:bg-red-600/30 border border-red-600/30"
                  >
                    <Trash2 className="w-4 h-4 mr-1" />
                    End
                  </Button>
                </DialogTrigger>
                <DialogContent className="bg-slate-800 border-slate-700">
                  <DialogHeader>
                    <DialogTitle className="text-white">End Session?</DialogTitle>
                    <DialogDescription className="text-slate-400">
                      This will permanently delete all uploaded documents, chat history, 
                      and vector embeddings. This action cannot be undone.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button 
                      variant="outline" 
                      onClick={() => setIsTerminateDialogOpen(false)}
                      className="border-slate-600 text-slate-300"
                    >
                      Cancel
                    </Button>
                    <Button 
                      variant="destructive"
                      onClick={() => {
                        terminateSession();
                        setIsTerminateDialogOpen(false);
                      }}
                    >
                      End Session
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          ) : (
            <Button 
              onClick={createSession}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              <Plus className="w-4 h-4 mr-1" />
              New Session
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}