import { useState, useRef, useEffect } from 'react';
import { useSession } from '@/contexts/SessionContext';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export function ChatInput() {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, isLoading, session, documents } = useSession();

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [message]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    
    if (!message.trim() || isLoading) return;
    
    const msg = message.trim();
    setMessage('');
    
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    
    await sendMessage(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = session && documents.length > 0 && message.trim() && !isLoading;

  return (
    <form onSubmit={handleSubmit} className="relative">
      <div
        className={cn(
          'flex items-end gap-2 p-3 rounded-xl border transition-all duration-200',
          'bg-slate-800 border-slate-700',
          'focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500/30'
        )}
      >
        <Textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            !session
              ? 'Create a session to start chatting...'
              : documents.length === 0
              ? 'Upload documents to start chatting...'
              : 'Ask a question about your documents...'
          }
          disabled={!session || documents.length === 0 || isLoading}
          className={cn(
            'flex-1 min-h-[44px] max-h-[200px] resize-none',
            'bg-transparent border-0 focus-visible:ring-0 focus-visible:ring-offset-0',
            'text-white placeholder:text-slate-500',
            'py-2 px-0'
          )}
          rows={1}
        />
        
        <Button
          type="submit"
          disabled={!canSend}
          className={cn(
            'h-10 w-10 p-0 rounded-lg transition-all duration-200',
            canSend
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
          )}
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </Button>
      </div>
      
      <p className="mt-2 text-xs text-slate-500 text-center">
        Press Enter to send, Shift+Enter for new line
      </p>
    </form>
  );
}