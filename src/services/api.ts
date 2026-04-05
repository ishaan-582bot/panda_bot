import type { Session, Document, QueryResponse, UploadResponse } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

class ApiService {
  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Session Management
  async createSession(): Promise<{ session_id: string; status: string; expires_at: string; time_remaining_seconds: number }> {
    return this.fetch('/session/initiate', {
      method: 'POST',
    });
  }

  async getSessionStatus(sessionId: string): Promise<Session> {
    return this.fetch(`/session/${sessionId}/status`);
  }

  async terminateSession(sessionId: string): Promise<{ session_id: string; status: string; message: string }> {
    return this.fetch(`/session/${sessionId}/terminate`, {
      method: 'DELETE',
    });
  }

  // Document Management
  async uploadFiles(sessionId: string, files: File[]): Promise<UploadResponse> {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    return this.fetch(`/session/${sessionId}/upload`, {
      method: 'POST',
      body: formData,
    });
  }

  async getDocuments(sessionId: string): Promise<{ session_id: string; documents: Document[]; total_documents: number }> {
    return this.fetch(`/session/${sessionId}/documents`);
  }

  // Query
  async sendQuery(
    sessionId: string, 
    question: string,
    options?: { max_chunks?: number; temperature?: number }
  ): Promise<QueryResponse> {
    return this.fetch(`/session/${sessionId}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        ...options,
      }),
    });
  }

  // Health Check
  async healthCheck(): Promise<{ status: string; active_sessions: number }> {
    return this.fetch('/health');
  }
}

export const apiService = new ApiService();