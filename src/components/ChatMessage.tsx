import { useState } from 'react';
import type { ChatMessage as ChatMessageType } from '@/types';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { 
  Bot, 
  User, 
  ChevronDown, 
  ChevronUp, 
  FileText, 
  Sparkles,
  AlertCircle,
  CheckCircle2,
  HelpCircle
} from 'lucide-react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';

interface ChatMessageProps {
  message: ChatMessageType;
}

function getConfidenceIcon(confidence: string) {
  switch (confidence) {
    case 'high':
      return <CheckCircle2 className="w-3 h-3 text-green-400" />;
    case 'medium':
      return <HelpCircle className="w-3 h-3 text-yellow-400" />;
    case 'low':
      return <AlertCircle className="w-3 h-3 text-red-400" />;
    default:
      return null;
  }
}

function getConfidenceColor(confidence: string): string {
  switch (confidence) {
    case 'high':
      return 'bg-green-500/20 text-green-400 border-green-500/30';
    case 'medium':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
    case 'low':
      return 'bg-red-500/20 text-red-400 border-red-500/30';
    default:
      return 'bg-slate-700 text-slate-400 border-slate-600';
  }
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-4 p-4 rounded-xl transition-all duration-300',
        isUser 
          ? 'bg-slate-800/50 ml-8' 
          : 'bg-slate-800 mr-8'
      )}
    >
      {/* Avatar */}
      <Avatar className={cn(
        'w-8 h-8 border-2',
        isUser 
          ? 'bg-indigo-600 border-indigo-400' 
          : 'bg-purple-600 border-purple-400'
      )}>
        <AvatarFallback>
          {isUser ? (
            <User className="w-4 h-4 text-white" />
          ) : (
            <Bot className="w-4 h-4 text-white" />
          )}
        </AvatarFallback>
      </Avatar>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <span className="font-medium text-white">
            {isUser ? 'You' : 'Assistant'}
          </span>
          <span className="text-xs text-slate-500">
            {message.timestamp.toLocaleTimeString([], { 
              hour: '2-digit', 
              minute: '2-digit' 
            })}
          </span>
          
          {!isUser && message.confidence && (
            <Badge 
              variant="outline" 
              className={cn('text-xs', getConfidenceColor(message.confidence))}
            >
              {getConfidenceIcon(message.confidence)}
              <span className="ml-1 capitalize">{message.confidence}</span>
            </Badge>
          )}
        </div>

        {/* Message Content */}
        <div className="text-slate-200 prose prose-invert prose-sm max-w-none">
          {message.isLoading ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Sparkles className="w-4 h-4 animate-pulse" />
              <span>Thinking...</span>
            </div>
          ) : isUser ? (
            <p className="m-0">{message.content}</p>
          ) : (
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="m-0 mb-2 last:mb-0">{children}</p>,
                code: ({ children }) => (
                  <code className="bg-slate-900 px-1.5 py-0.5 rounded text-sm font-mono text-indigo-300">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-slate-900 p-3 rounded-lg overflow-x-auto text-sm">
                    {children}
                  </pre>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <Collapsible open={showSources} onOpenChange={setShowSources}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="mt-3 text-slate-400 hover:text-white hover:bg-slate-700"
              >
                <FileText className="w-4 h-4 mr-1" />
                {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
                {showSources ? (
                  <ChevronUp className="w-4 h-4 ml-1" />
                ) : (
                  <ChevronDown className="w-4 h-4 ml-1" />
                )}
              </Button>
            </CollapsibleTrigger>
            
            <CollapsibleContent>
              <div className="mt-3 space-y-2">
                {message.sources.map((source, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-slate-900/50 border border-slate-700 text-sm"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="w-4 h-4 text-indigo-400" />
                      <span className="font-medium text-white">{source.file}</span>
                      {source.page && (
                        <Badge variant="secondary" className="text-xs bg-slate-700">
                          Page {source.page}
                        </Badge>
                      )}
                      <Badge 
                        variant="outline" 
                        className="text-xs border-slate-600 text-slate-400"
                      >
                        Score: {(source.relevance_score * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <p className="text-slate-400 text-xs line-clamp-3">
                      {source.text}
                    </p>
                  </div>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    </div>
  );
}