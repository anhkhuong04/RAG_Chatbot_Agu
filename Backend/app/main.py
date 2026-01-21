import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import chat, metrics, cache
from app.api.endpoints import health
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware, get_rate_limiter
from app.core.logger import setup_logging, get_logger
from app.config import settings

# Setup logging
setup_logging(log_level=settings.LOG_LEVEL)
logger = get_logger(__name__)


# ==========================================
# LIFESPAN MANAGEMENT (Startup/Shutdown)
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # === STARTUP ===
    logger.info("=" * 50)
    logger.info("🚀 Starting RAG Chatbot API...")
    logger.info(f"   Environment: {settings.ENVIRONMENT}")
    logger.info(f"   Query Transformation: {settings.USE_QUERY_TRANSFORMATION}")
    logger.info(f"   Re-ranking: {settings.USE_RERANKING}")
    logger.info(f"   Redis Cache: {settings.REDIS_ENABLED}")
    logger.info("=" * 50)
    
    # Pre-initialize engine factory (load vector store)
    try:
        logger.info("Pre-initializing engine factory...")
        from app.core.engine import get_engine_factory
        get_engine_factory()
        logger.info("✅ Engine factory initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize engine factory: {e}")
        # Don't raise - allow server to start, health check will report unhealthy
    
    # Initialize session manager
    try:
        logger.info("Initializing session manager...")
        from app.core.session import get_session_manager
        get_session_manager()
        logger.info("✅ Session manager initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize session manager: {e}")
    
    # Initialize cache if enabled
    if settings.REDIS_ENABLED:
        try:
            logger.info("Connecting to Redis cache...")
            from app.core.cache import get_cache_manager
            cache = get_cache_manager()
            if cache.enabled:
                logger.info("✅ Redis cache connected")
            else:
                logger.warning("⚠️ Redis cache unavailable")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
    
    logger.info("🎉 Application startup complete!")
    logger.info("=" * 50)
    
    yield  # Application runs here
    
    # === SHUTDOWN ===
    logger.info("=" * 50)
    logger.info("🛑 Shutting down RAG Chatbot API...")
    
    # Cleanup sessions
    try:
        from app.core.session import get_session_manager
        session_manager = get_session_manager()
        session_count = session_manager.get_session_count()
        logger.info(f"   Active sessions at shutdown: {session_count}")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("👋 Goodbye!")
    logger.info("=" * 50)


# ==========================================
# APP CONFIGURATION
# ==========================================

app = FastAPI(
    title="Admissions Chatbot API",
    description="API tư vấn tuyển sinh sử dụng RAG + LlamaIndex với Session Management",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)


# ==========================================
# MIDDLEWARE (Order matters!)
# ==========================================

# 1. Logging middleware (outermost - logs everything)
app.add_middleware(LoggingMiddleware)

# 2. Rate limiting middleware
if settings.ENVIRONMENT == "production" or getattr(settings, 'RATE_LIMIT_ENABLED', True):
    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=get_rate_limiter(),
        exclude_paths=["/", "/health", "/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc"]
    )

# 3. CORS middleware (innermost)
# Configure CORS based on environment
if settings.ENVIRONMENT == "production":
    # Production: restrict origins
    origins = [
        "https://your-production-domain.com",  # TODO: Update with actual domain
    ]
else:
    # Development: allow common dev ports
    origins = [
        "http://localhost:5173",  # Vite default
        "http://localhost:3000",  # CRA default
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if settings.ENVIRONMENT == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# ROUTERS
# ==========================================

# Health check endpoints (no prefix)
app.include_router(health.router, tags=["health"])

# API v1 endpoints
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(cache.router, prefix="/api/v1", tags=["cache"])


# ==========================================
# ROOT ENDPOINT
# ==========================================

@app.get("/", tags=["root"])
def root():
    """
    Root endpoint - basic health check
    """
    return {
        "status": "healthy",
        "message": "RAG Chatbot API is running",
        "version": "2.1.0",
        "docs": "/docs" if settings.ENVIRONMENT == "development" else "disabled"
    }


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level="info"
    )