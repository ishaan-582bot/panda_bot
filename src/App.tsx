import { useSession } from '@/contexts/SessionContext';
import { Header } from '@/components/Header';
import { WelcomeScreen } from '@/components/WelcomeScreen';
import { FileUpload } from '@/components/FileUpload';
import { DocumentList } from '@/components/DocumentList';
import { ChatMessage } from '@/components/ChatMessage';
import { ChatInput } from '@/components/ChatInput';
import { ScrollArea } from '@/components/ui/scroll-area';

import { Separator } from '@/components/ui/separator';
import { FileText, MessageSquare } from 'lucide-react';
import { useEffect, useRef } from 'react';

function ChatInterface() {
  const { messages, session } = useSession();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  if (!session) {
    return <WelcomeScreen />;
  }

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Sidebar */}
      <aside className="w-80 bg-slate-900 border-r border-slate-700 flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-400" />
            Documents
          </h2>
        </div>
        
        <div className="flex-1 overflow-hidden">
          <DocumentList />
        </div>
        
        <Separator className="bg-slate-700" />
        
        <div className="p-4">
          <FileUpload />
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col bg-slate-950">
        {/* Messages */}
        <div className="flex-1 overflow-hidden">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center p-8">
              <div className="w-16 h-16 rounded-full bg-indigo-500/20 flex items-center justify-center mb-4">
                <MessageSquare className="w-8 h-8 text-indigo-400" />
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">
                Start Chatting
              </h3>
              <p className="text-slate-400 text-center max-w-md">
                Upload documents and ask questions. I'll provide answers based only on your uploaded data.
              </p>
            </div>
          ) : (
            <ScrollArea className="h-full p-4">
              <div className="space-y-4 max-w-4xl mx-auto">
                {messages.map((message) => (
                  <ChatMessage key={message.id} message={message} />
                ))}
                <div ref={scrollRef} />
              </div>
            </ScrollArea>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/50">
          <div className="max-w-4xl mx-auto">
            <ChatInput />
          </div>
        </div>
      </main>
    </div>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-slate-950">
      <Header />
      <ChatInterface />
    </div>
  );
}

export default App;