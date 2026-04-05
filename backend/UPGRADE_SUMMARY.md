# Panda Bot Backend - Upgrade Summary

This document summarizes all the upgrades made to the FastAPI backend for panda_bot.

## 🐛 Critical Bug Fixes

### 1. Tenacity Decorator Bug (FIXED)
**File:** `app/services/llm_service.py`

**Problem:** The original code used `retry.if_exception_type` which fails because `retry` is the decorator function, not the module.

**Solution:** Import `retry_if_not_exception_type` from tenacity and use it correctly:

```python
from tenacity import retry_if_not_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(OpenAIRateLimitError)  # FIXED
)
```

### 2. Embedding Fallback (FIXED)
**File:** `app/services/embedding_service.py`

**Problem:** The original code used `np.random.seed()` which creates random vectors with no semantic meaning.

**Solution:** Implemented proper semantic embeddings using sentence-transformers with `all-MiniLM-L6-v2` model:
- Only 80MB model size
- 384 dimensions
- Fits comfortably in 8GB RAM
- Lazy-loaded only when no API key is present

## 🧠 "The Brain" Upgrades - Fully Local & Free

### 3. Ollama Integration
**File:** `app/services/ollama_service.py` (NEW)

Created a complete OllamaService class that:
- Mirrors the LLMService interface
- Calls `http://localhost:11434/api/generate` for LLM
- Calls `http://localhost:11434/api/embeddings` for embeddings
- Auto-detects if Ollama is running
- Supports `llama3.2:3b` or `phi4` (3B parameters, fits in 8GB RAM)
- Uses `nomic-embed-text` for embeddings

### 4. Auto-Detection Priority
**Files:** `app/services/llm_service.py`, `app/services/embedding_service.py`

The system now auto-detects available providers in this priority:
1. **Ollama** (local) - if running at `localhost:11434`
2. **OpenAI** (cloud) - if `OPENAI_API_KEY` is set
3. **Local embeddings** (MiniLM) - fallback when neither is available
4. **Mock responses** - final fallback for LLM only

### 5. Provider Detection in Health Check
**File:** `app/api/routes.py`

The `/health` endpoint now returns:
```json
{
  "providers": {
    "openai": {"available": true/false, "model": "..."},
    "ollama": {"available": true/false, "llm_model": "...", "embedding_model": "..."},
    "local_embeddings": {"available": true, "model": "all-MiniLM-L6-v2"}
  }
}
```

## 💬 Real Chat Memory (Context Awareness)

### 6. Chat History in LLM Context
**Files:** `app/models/session.py`, `app/services/llm_service.py`

- Modified `generate_response()` to include last 5-7 conversation turns
- Alternating user/assistant roles in the prompt
- Configurable via `MAX_CHAT_HISTORY_TURNS` setting

### 7. Conversation Summarization
**Files:** `app/models/session.py`, `app/services/llm_service.py`

- When history exceeds 10 turns, older context is summarized
- Summary stored in `Session.conversation_summary`
- Uses the LLM to generate a concise summary
- Maintains continuity while saving tokens

### 8. Session Model Updates
**File:** `app/models/session.py`

Added new fields:
- `conversation_summary`: Running summary of older conversations
- `summary_turns_count`: Number of turns included in summary

New methods:
- `add_chat_message()`: Add message with timestamp
- `get_recent_chat_history()`: Get last N turns
- `should_summarize()`: Check if summarization needed
- `update_conversation_summary()`: Update summary
- `get_conversation_context()`: Get full context
- `to_export_dict()`: Export session data

## 🔍 Smart RAG Improvements

### 9. Hybrid Search (FAISS + BM25)
**File:** `app/services/retrieval_service.py`

Implemented hybrid search combining:
- **FAISS vector similarity** (semantic search)
- **BM25 keyword scoring** (lexical search)

Weighted combination:
```python
combined_score = (0.7 * vector_score) + (0.3 * bm25_score)
```

### 10. Relevance Threshold
**File:** `app/services/retrieval_service.py`

- If top retrieved chunk has similarity score below 0.7
- Returns "I don't have enough information" instead of hallucinating
- Configurable via `RELEVANCE_THRESHOLD` setting

### 11. Enhanced Source Citations
**Files:** `app/services/llm_service.py`, `app/services/ollama_service.py`

- Source citations now include relevance scores
- Prompt modified to make LLM cite document chunks
- Chunk metadata returned to frontend

## 💾 Session Persistence

### 12. Export Session Endpoint
**File:** `app/api/routes.py`

New endpoint: `POST /api/v1/session/{session_id}/export`
- Saves FAISS index + chat history to JSON
- Stores in `backups/` folder
- Filename includes timestamp
- Maintains privacy-first local-only approach

### 13. Import Session Endpoint
**File:** `app/api/routes.py`

New endpoint: `POST /api/v1/session/import`
- Resumes from exported JSON
- Creates new session ID
- Restores chat history and summary
- Documents need re-upload (embeddings not stored)

## ⚡ Performance Optimizations for 8GB RAM

### 14. Async Batch Processing for Uploads
**File:** `app/services/document_processor.py`

- PDF pages processed in chunks of 3
- Memory pressure monitoring between batches
- Async processing with `asyncio.gather()`
- Configurable via `DOCUMENT_BATCH_SIZE`

### 15. Request Queue Management
**File:** `app/api/routes.py`

- Semaphore-based concurrency control
- Max 3 concurrent requests (configurable)
- Prevents memory spikes from simultaneous requests

### 16. Memory Usage Monitoring
**Files:** `app/utils/memory_monitor.py` (NEW), `app/api/routes.py`

New `/health` endpoint returns:
```json
{
  "memory": {
    "system": {
      "total_gb": 8.0,
      "available_gb": 4.5,
      "used_gb": 3.5,
      "percent": 43.75,
      "status": "healthy"
    },
    "process": {
      "rss_mb": 256.5,
      "vms_mb": 1024.0
    }
  }
}
```

## 📦 New Dependencies

**File:** `requirements.txt`

Added:
- `rank-bm25==0.2.2` - For hybrid search
- `psutil==5.9.8` - For memory monitoring
- `httpx==0.26.0` - For Ollama API calls

## ⚙️ New Configuration Options

**File:** `app/core/config.py`

New settings:
```python
# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_LLM_MODEL = "llama3.2:3b"
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_ENABLED = True

# Local embeddings
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Chat memory
MAX_CHAT_HISTORY_TURNS = 7
CONVERSATION_SUMMARY_THRESHOLD = 10
MAX_SUMMARY_TOKENS = 500

# RAG
RELEVANCE_THRESHOLD = 0.7
ENABLE_HYBRID_SEARCH = True
BM25_WEIGHT = 0.3

# Performance
DOCUMENT_BATCH_SIZE = 3
MAX_CONCURRENT_REQUESTS = 3

# Persistence
BACKUP_DIR = "backups"
ENABLE_SESSION_PERSISTENCE = True
```

## 🔄 API Changes

### New Endpoints
- `POST /api/v1/session/{session_id}/export` - Export session
- `POST /api/v1/session/import` - Import session

### Enhanced Endpoints
- `POST /api/v1/session/{session_id}/query` - Now includes chat memory
- `GET /api/v1/health` - Now includes memory usage and provider status
- `POST /api/v1/session/{session_id}/upload` - Now uses batch processing

### Enhanced Responses
- `QueryResponse` now includes sources with relevance scores
- Session status includes chat turns and summary status

## 🚀 Usage Instructions

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Install Ollama (Optional but Recommended)
```bash
# Install Ollama from https://ollama.com

# Pull recommended models
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env to set your preferences
```

### 4. Start the Server
```bash
./start.sh
```

### 5. Verify Setup
```bash
curl http://localhost:8000/api/v1/health
```

## 📝 Notes

- All changes maintain the existing React frontend API contract
- CORS remains strict as configured
- Session-based isolation is preserved
- Memory wiping on session termination still works
- Works completely offline with Ollama

## 🔒 Privacy-First Design

The upgraded backend maintains the privacy-first approach:
- No data leaves your machine when using Ollama
- Session data is memory-only (except explicit exports)
- Cryptographic erasure on session termination
- Optional session persistence is local-only
