import { useSession } from '@/contexts/SessionContext';
import { Button } from '@/components/ui/button';
import { 
  MessageSquare, 
  Shield, 
  Clock, 
  FileText, 
  Brain,
  Lock,
  Zap,
  Plus
} from 'lucide-react';

const features = [
  {
    icon: Shield,
    title: 'Privacy First',
    description: 'All data stays in memory only. No persistence, no logs, no caching.',
  },
  {
    icon: Clock,
    title: 'Auto-Cleanup',
    description: 'Sessions automatically expire after 30 minutes of inactivity.',
  },
  {
    icon: FileText,
    title: 'Multiple Formats',
    description: 'Support for PDF, DOCX, TXT, CSV, JSON, and images with OCR.',
  },
  {
    icon: Brain,
    title: 'Smart Retrieval',
    description: 'Vector-based semantic search for accurate answers.',
  },
  {
    icon: Lock,
    title: 'Isolated Sessions',
    description: 'Each session is completely isolated with its own vector store.',
  },
  {
    icon: Zap,
    title: 'Fast Processing',
    description: 'In-memory processing for quick responses.',
  },
];

export function WelcomeScreen() {
  const { createSession, isLoading } = useSession();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
          <MessageSquare className="w-10 h-10 text-white" />
        </div>
        
        <h1 className="text-4xl font-bold text-white mb-4">
          Welcome to <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">Panda</span>
        </h1>
        
        <p className="text-lg text-slate-400 max-w-lg mx-auto mb-8">
          Chat with your documents in complete privacy. 
          Upload files, ask questions, and get answers with source citations.
        </p>
        
        <Button
          onClick={createSession}
          disabled={isLoading}
          size="lg"
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-6 text-lg rounded-xl shadow-lg shadow-indigo-500/20 transition-all duration-300 hover:scale-105"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Creating Session...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Start New Session
            </span>
          )}
        </Button>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-4xl w-full">
        {features.map((feature, index) => (
          <div
            key={index}
            className="p-6 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-indigo-500/50 transition-all duration-300 hover:bg-slate-800"
          >
            <div className="w-10 h-10 rounded-lg bg-indigo-500/20 flex items-center justify-center mb-4">
              <feature.icon className="w-5 h-5 text-indigo-400" />
            </div>
            <h3 className="text-white font-semibold mb-2">{feature.title}</h3>
            <p className="text-slate-400 text-sm">{feature.description}</p>
          </div>
        ))}
      </div>

      {/* Security Notice */}
      <div className="mt-12 p-4 rounded-lg bg-slate-800/30 border border-slate-700/50 max-w-2xl">
        <div className="flex items-start gap-3">
          <Lock className="w-5 h-5 text-green-400 mt-0.5" />
          <div>
            <h4 className="text-white font-medium mb-1">Your Data is Secure</h4>
            <p className="text-slate-400 text-sm">
              All uploaded documents, extracted text, vector embeddings, and chat history 
              are stored only in memory. When your session ends or times out, all data is 
              cryptographically erased with no traces left behind.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}