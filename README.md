# Panda - Session-Based Private Document Chat

A privacy-first chatbot that allows users to upload documents and ask questions based solely on their uploaded data. All data is stored in memory only and erased when the session ends.

**⚠️ Security Notice**: This implementation provides best-effort cryptographic erasure. Due to Python's memory model (immutable strings, garbage collection, memory pooling), complete memory wiping cannot be guaranteed. For applications requiring absolute data destruction, consider using a language with manual memory management (Rust, C, C++).

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React Frontend │────▶│  FastAPI Backend │────▶│  In-Memory Store│
│   (Chat UI)      │     │  (Session Mgmt)  │     │  (No Persistence)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Document Proc  │
                        │  - PDF/DOCX/TXT │
                        │  - OCR (Images) │
                        └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Vector Store   │
                        │  (FAISS)        │
                        │  Per-Session    │
                        └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  LLM Service    │
                        │  (OpenAI)       │
                        │  Strict Context │
                        └─────────────────┘
```

## Security Features

### Implemented
- ✅ **Strict CORS whitelist** - No wildcard origins
- ✅ **Filename sanitization** - Path traversal protection
- ✅ **Magic number validation** - Content-based file type detection
- ✅ **Rate limiting** - Per-endpoint rate limits
- ✅ **Incremental FAISS indexing** - O(n) instead of O(n²)
- ✅ **Async OpenAI client** - Non-blocking I/O
- ✅ **Proper exception handling** - Specific exception types
- ✅ **Accurate token counting** - Using tiktoken
- ✅ **Streaming CSV processing** - Memory-efficient

### Known Limitations
- ⚠️ **Cryptographic erasure** is best-effort in Python (see Security Notice above)
- ⚠️ **Memory pooling** - Python's allocator may retain freed memory
- ⚠️ **Swap risk** - OS may swap memory to disk

## API Endpoints

### Session Management
```
POST   /api/v1/session/initiate          → Create new session (5/min limit)
DELETE /api/v1/session/{id}/terminate    → End session, erase data
GET    /api/v1/session/{id}/status       → Get session status
```

### Document Management
```
POST   /api/v1/session/{id}/upload       → Upload files (10/min limit, magic number check)
GET    /api/v1/session/{id}/documents    → List uploaded documents
```

### Query
```
POST   /api/v1/session/{id}/query        → Ask question (60/min limit)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | None | Required for embeddings/LLM |
| `LLM_MODEL` | gpt-4o-mini | LLM model |
| `EMBEDDING_MODEL` | text-embedding-3-small | Embedding model |
| `SESSION_TIMEOUT_MINUTES` | 30 | Session TTL |
| `MAX_FILE_SIZE_MB` | 50 | Per-file limit |
| `MAX_TOTAL_SIZE_MB` | 100 | Session total limit |
| `CORS_ORIGINS` | localhost | **CRITICAL**: Set to your frontend domain |

### CORS Configuration

**⚠️ NEVER use `allow_origins=["*"]` in production!**

Set `CORS_ORIGINS` to your frontend domain:
```bash
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

## Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- OpenAI API key (optional, for full functionality)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start server
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Project Structure

```
app/
├── backend/
│   ├── app/
│   │   ├── api/routes.py           # REST endpoints with rate limiting
│   │   ├── core/
│   │   │   ├── config.py           # Settings with strict CORS
│   │   │   └── session_manager.py  # Session lifecycle with locking
│   │   ├── models/                 # Pydantic v2 models
│   │   ├── services/
│   │   │   ├── document_processor.py  # Streaming CSV processing
│   │   │   ├── embedding_service.py   # Async OpenAI client
│   │   │   ├── retrieval_service.py   # Incremental FAISS indexing
│   │   │   └── llm_service.py         # Proper tiktoken counting
│   │   └── utils/
│   │       ├── file_validation.py     # Magic number checking
│   │       ├── memory_wipe.py         # Best-effort erasure
│   │       └── rate_limiter.py        # Rate limiting
│   └── requirements.txt
│
├── src/                  # React + TypeScript frontend
└── README.md
```

## Anti-Patterns Avoided

| Pattern | Status |
|---------|--------|
| Wildcard CORS origins | ❌ Fixed - strict whitelist |
| Path traversal vulnerability | ❌ Fixed - filename sanitization |
| Extension-only validation | ❌ Fixed - magic number checking |
| No rate limiting | ❌ Fixed - per-endpoint limits |
| Singleton race conditions | ❌ Fixed - proper async locking |
| Shared service state | ❌ Fixed - per-session services |
| O(n²) FAISS rebuilding | ❌ Fixed - incremental indexing |
| Bare except clauses | ❌ Fixed - specific exceptions |
| Crude token counting | ❌ Fixed - tiktoken |
| CSV memory explosion | ❌ Fixed - streaming processing |
| Pydantic v1 syntax | ❌ Fixed - model_config |
| Synchronous OpenAI | ❌ Fixed - AsyncOpenAI |

## License

MIT License