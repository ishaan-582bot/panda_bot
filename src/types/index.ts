export interface Session {
  session_id: string;
  status: 'active' | 'expired' | 'terminated';
  created_at: string;
  last_activity: string;
  expires_at: string;
  time_remaining_seconds: number;
  documents_loaded: number;
  total_size_mb: number;
  total_tokens_used: number;
  config: {
    max_file_size_mb: number;
    max_total_size_mb: number;
    session_timeout_minutes: number;
  };
}

export interface Document {
  document_id: string;
  filename: string;
  file_type: string;
  size_mb: number;
  total_chunks: number;
  total_tokens: number;
  uploaded_at: string;
  processing_status: 'pending' | 'processing' | 'completed' | 'error';
}

export interface SourceCitation {
  file: string;
  page?: number;
  section?: string;
  text: string;
  chunk_index: number;
  relevance_score: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceCitation[];
  confidence?: 'high' | 'medium' | 'low';
  timestamp: Date;
  isLoading?: boolean;
}

export interface QueryResponse {
  answer: string;
  sources: SourceCitation[];
  confidence: 'high' | 'medium' | 'low';
  session_id: string;
  tokens_used: number;
  processing_time_ms: number;
  query: string;
}

export interface UploadResponse {
  session_id: string;
  documents_processed: number;
  documents: Document[];
  total_size_mb: number;
  total_chunks: number;
  total_tokens: number;
  message: string;
  errors?: Array<{ file: string; error: string }>;
}