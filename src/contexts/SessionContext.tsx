import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import type { Session, Document, ChatMessage } from '@/types';
import { apiService } from '@/services/api';
import { toast } from 'sonner';

interface SessionContextType {
  session: Session | null;
  documents: Document[];
  messages: ChatMessage[];
  isLoading: boolean;
  isUploading: boolean;
  timeRemaining: number;
  createSession: () => Promise<void>;
  terminateSession: () => Promise<void>;
  uploadFiles: (files: File[]) => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  refreshSession: () => Promise<void>;
  clearMessages: () => void;
}

const SessionContext = createContext<SessionContextType | undefined>(undefined);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(0);
  
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Timer countdown
  useEffect(() => {
    if (session && session.status === 'active') {
      setTimeRemaining(session.time_remaining_seconds);
      
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      
      timerRef.current = setInterval(() => {
        setTimeRemaining(prev => {
          if (prev <= 1) {
            // Session expired
            setSession(null);
            setDocuments([]);
            toast.error('Session expired');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [session]);

  const createSession = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await apiService.createSession();
      
      // Fetch full session status
      const sessionData = await apiService.getSessionStatus(response.session_id);
      setSession(sessionData);
      setDocuments([]);
      setMessages([]);
      
      toast.success('New session created');
    } catch (error) {
      toast.error('Failed to create session');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const terminateSession = useCallback(async () => {
    if (!session) return;
    
    try {
      setIsLoading(true);
      await apiService.terminateSession(session.session_id);
      setSession(null);
      setDocuments([]);
      setMessages([]);
      
      toast.success('Session terminated. All data erased.');
    } catch (error) {
      toast.error('Failed to terminate session');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [session]);

  const refreshSession = useCallback(async () => {
    if (!session) return;
    
    try {
      const sessionData = await apiService.getSessionStatus(session.session_id);
      setSession(sessionData);
      
      // Also refresh documents
      const docsData = await apiService.getDocuments(session.session_id);
      setDocuments(docsData.documents);
    } catch (error) {
      console.error('Failed to refresh session:', error);
    }
  }, [session]);

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!session) {
      toast.error('No active session');
      return;
    }
    
    try {
      setIsUploading(true);
      const response = await apiService.uploadFiles(session.session_id, files);
      
      setDocuments(prev => [...prev, ...response.documents]);
      
      // Refresh session to update stats
      await refreshSession();
      
      if (response.errors && response.errors.length > 0) {
        toast.warning(`Uploaded with ${response.errors.length} error(s)`);
      } else {
        toast.success(`Uploaded ${response.documents_processed} file(s)`);
      }
    } catch (error) {
      toast.error('Failed to upload files');
      console.error(error);
    } finally {
      setIsUploading(false);
    }
  }, [session, refreshSession]);

  const sendMessage = useCallback(async (message: string) => {
    if (!session) {
      toast.error('No active session');
      return;
    }
    
    if (documents.length === 0) {
      toast.error('Please upload documents first');
      return;
    }
    
    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    
    // Add loading message
    const loadingId = (Date.now() + 1).toString();
    const loadingMessage: ChatMessage = {
      id: loadingId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };
    
    setMessages(prev => [...prev, loadingMessage]);
    setIsLoading(true);
    
    try {
      const response = await apiService.sendQuery(session.session_id, message);
      
      // Replace loading message with actual response
      setMessages(prev => 
        prev.map(msg => 
          msg.id === loadingId
            ? {
                id: loadingId,
                role: 'assistant',
                content: response.answer,
                sources: response.sources,
                confidence: response.confidence,
                timestamp: new Date(),
              }
            : msg
        )
      );
      
      // Update session stats
      await refreshSession();
    } catch (error) {
      // Replace loading with error
      setMessages(prev => 
        prev.map(msg => 
          msg.id === loadingId
            ? {
                id: loadingId,
                role: 'assistant',
                content: 'Sorry, I encountered an error processing your request. Please try again.',
                timestamp: new Date(),
              }
            : msg
        )
      );
      toast.error('Failed to get response');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [session, documents, refreshSession]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <SessionContext.Provider
      value={{
        session,
        documents,
        messages,
        isLoading,
        isUploading,
        timeRemaining,
        createSession,
        terminateSession,
        uploadFiles,
        sendMessage,
        refreshSession,
        clearMessages,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (context === undefined) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}