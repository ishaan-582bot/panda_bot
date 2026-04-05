"""
Panda API - Session-based custom data chatbot with privacy-first architecture.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import get_settings
from .core.session_manager import session_manager
from .core.embedding_registry import embedding_registry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("Starting Panda API...")
    logger.info("IMPORTANT: Cryptographic erasure is best-effort in Python.")
    logger.info("For true memory wiping, use a language with manual memory management.")
    logger.info(f"Session timeout: {settings.SESSION_TIMEOUT_MINUTES} minutes")
    logger.info(f"Max file size: {settings.MAX_FILE_SIZE_MB}MB")
    logger.info(f"Max total size: {settings.MAX_TOTAL_SIZE_MB}MB")
    logger.info(f"CORS origins: {settings.CORS_ORIGINS}")
    
    # Initialize embedding registry (locks dimension for all sessions)
    embedding_config = await embedding_registry.initialize()
    logger.info(
        f"Embedding registry initialized: {embedding_config['provider']} "
        f"with dimension {embedding_config['dimension']}"
    )
    
    # Initialize session manager
    await session_manager._async_init()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Panda API...")
    await session_manager.shutdown()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Session-based custom data chatbot with isolated memory-only storage",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS with STRICT whitelist
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }
