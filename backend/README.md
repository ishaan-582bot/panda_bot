# Panda Bot Backend v2.0

Privacy-first RAG chatbot backend with local LLM support, chat memory, and 8GB RAM optimization.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start server
./start.sh
```

## 🔧 Configuration

### Environment Variables

```bash
# LLM Provider (Priority: Ollama > OpenAI > Local)
OPENAI_API_KEY=                    # Optional - for OpenAI
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.2:3b       # or phi4
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Performance (for 8GB RAM)
DOCUMENT_BATCH_SIZE=3
MAX_CONCURRENT_REQUESTS=3

# Chat Memory
MAX_CHAT_HISTORY_TURNS=7
CONVERSATION_SUMMARY_THRESHOLD=10

# RAG
RELEVANCE_THRESHOLD=0.7
ENABLE_HYBRID_SEARCH=true
BM25_WEIGHT=0.3
```

## 📡 API Endpoints

### Session Management
- `POST /api/v1/session/initiate` - Create new session
- `DELETE /api/v1/session/{id}/terminate` - End session
- `GET /api/v1/session/{id}/status` - Get session status

### Documents
- `POST /api/v1/session/{id}/upload` - Upload files
- `GET /api/v1/session/{id}/documents` - List documents

### Chat
- `POST /api/v1/session/{id}/query` - Send query

### Persistence
- `POST /api/v1/session/{id}/export` - Export session
- `POST /api/v1/session/import` - Import session

### System
- `GET /api/v1/health` - Health check with memory usage

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
├─────────────────────────────────────────────────────────────┤
│  API Routes → Session Manager → Retrieval Service           │
│                    ↓                    ↓                   │
│              Embedding Registry    FAISS + BM25             │
│                    ↓                    ↓                   │
│         ┌─────────┴─────────┐    Per-Session Lock           │
│         ↓                   ↓                               │
│   OpenAI/Ollama/Local   Thread-Safe                       │
│         ↓                                                   │
│   Model Cache (Global)                                      │
└─────────────────────────────────────────────────────────────┘
```

## 🔒 Thread Safety

| Component | Lock | Notes |
|-----------|------|-------|
| EmbeddingRegistry | Immutable | Locked at startup |
| ModelCache | threading.Lock | Global singleton |
| RetrievalService | asyncio.Lock | Per-session |
| SessionManager | asyncio.Lock | Global |

## 📊 Performance

- **Embedding generation**: 5 concurrent requests (Ollama)
- **Document processing**: Batch size of 3 pages
- **Concurrent requests**: Max 3 simultaneous
- **Memory monitoring**: Real-time in health endpoint

## 🐛 Critical Fixes in v2.0

1. **Dimension Mismatch** - Locked dimension at startup prevents FAISS crashes
2. **Thread Safety** - Per-session locks for FAISS operations
3. **Event Loop Blocking** - Pure async patterns throughout
4. **Context Overflow** - Prompt compression for 3B models
5. **Sequential Embeddings** - Concurrent Ollama requests
6. **BM25 Rebuild** - Incremental updates
7. **Tiktoken Memory** - Global encoder cache
8. **Ollama Retry** - Exponential backoff
9. **Model Caching** - Global embedding model cache
10. **Dynamic Threshold** - Adaptive relevance scoring

## 📁 File Structure

```
backend/
├── app/
│   ├── api/routes.py           # API endpoints
│   ├── core/
│   │   ├── config.py           # Settings
│   │   ├── session_manager.py  # Session management
│   │   ├── embedding_registry.py  # Dimension locking
│   │   └── model_cache.py      # Global model cache
│   ├── models/                 # Pydantic models
│   ├── services/
│   │   ├── document_processor.py
│   │   ├── embedding_service.py
│   │   ├── llm_service.py
│   │   ├── ollama_service.py
│   │   └── retrieval_service.py
│   └── utils/                  # Utilities
├── requirements.txt
├── .env.example
└── start.sh
```

## 🧪 Testing

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Create session
curl -X POST http://localhost:8000/api/v1/session/initiate

# Upload file
curl -X POST -F "files=@document.pdf" \
  http://localhost:8000/api/v1/session/{session_id}/upload

# Query
curl -X POST -H "Content-Type: application/json" \
  -d '{"question": "What is this document about?"}' \
  http://localhost:8000/api/v1/session/{session_id}/query
```

## 📄 License

Private use - Privacy-first local RAG system
