"""
Health Check Endpoints
Deep health checks for all dependencies
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
from datetime import datetime
import time

from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def check_vector_store() -> Dict[str, Any]:
    """Check Qdrant vector store health"""
    start = time.time()
    try:
        from app.core.vector_store import get_vector_store
        storage_context = get_vector_store()
        
        # Try to get collection info
        client = storage_context.vector_store.client
        collections = client.get_collections()
        
        duration_ms = (time.time() - start) * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(duration_ms, 2),
            "collections_count": len(collections.collections),
            "details": {
                "type": "qdrant",
                "mode": "local"
            }
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error(f"Vector store health check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round(duration_ms, 2),
            "error": str(e)
        }


async def check_redis() -> Dict[str, Any]:
    """Check Redis cache health"""
    start = time.time()
    try:
        from app.config import settings
        
        if not settings.REDIS_ENABLED:
            return {
                "status": "disabled",
                "latency_ms": 0,
                "details": {"message": "Redis caching is disabled"}
            }
        
        from app.core.cache import get_cache_manager
        cache = get_cache_manager()
        
        if not cache.enabled or not cache.redis_client:
            return {
                "status": "unavailable",
                "latency_ms": 0,
                "details": {"message": "Redis client not initialized"}
            }
        
        # Ping Redis
        cache.redis_client.ping()
        
        # Get some stats
        info = cache.redis_client.info("memory")
        
        duration_ms = (time.time() - start) * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(duration_ms, 2),
            "details": {
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", "unknown")
            }
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round(duration_ms, 2),
            "error": str(e)
        }


async def check_llm() -> Dict[str, Any]:
    """Check LLM API health (without making actual call)"""
    start = time.time()
    try:
        from app.config import settings
        
        # Check if API key is configured
        if not settings.OPENAI_API_KEY:
            return {
                "status": "unconfigured",
                "latency_ms": 0,
                "error": "OPENAI_API_KEY not set"
            }
        
        # Just verify settings are loaded (don't make actual API call)
        duration_ms = (time.time() - start) * 1000
        
        return {
            "status": "configured",
            "latency_ms": round(duration_ms, 2),
            "details": {
                "model": settings.LLM_MODEL,
                "embedding_model": settings.EMBEDDING_MODEL
            }
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error(f"LLM health check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round(duration_ms, 2),
            "error": str(e)
        }


async def check_session_manager() -> Dict[str, Any]:
    """Check session manager health"""
    start = time.time()
    try:
        from app.core.session import get_session_manager
        
        session_manager = get_session_manager()
        session_count = session_manager.get_session_count()
        
        duration_ms = (time.time() - start) * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(duration_ms, 2),
            "details": {
                "active_sessions": session_count,
                "max_sessions": session_manager.max_sessions,
                "session_ttl_minutes": session_manager.session_ttl_minutes
            }
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error(f"Session manager health check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round(duration_ms, 2),
            "error": str(e)
        }


@router.get("/health")
async def health_check():
    """
    Basic health check - quick response
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "rag-chatbot-api"
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verify all dependencies are ready
    Used by Kubernetes/load balancers to determine if service can accept traffic
    """
    start = time.time()
    
    # Check all dependencies
    vector_store = await check_vector_store()
    redis = await check_redis()
    llm = await check_llm()
    sessions = await check_session_manager()
    
    total_duration = (time.time() - start) * 1000
    
    # Determine overall status
    # Service is ready if vector store and LLM are healthy/configured
    critical_healthy = (
        vector_store["status"] == "healthy" and
        llm["status"] in ["healthy", "configured"]
    )
    
    overall_status = "ready" if critical_healthy else "not_ready"
    status_code = status.HTTP_200_OK if critical_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    response = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_check_duration_ms": round(total_duration, 2),
        "checks": {
            "vector_store": vector_store,
            "redis": redis,
            "llm": llm,
            "session_manager": sessions
        }
    }
    
    if overall_status != "ready":
        logger.warning("Readiness check failed", context=response)
    
    return JSONResponse(
        status_code=status_code,
        content=response
    )


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check - verify service is alive
    Used by Kubernetes to determine if service needs restart
    """
    try:
        # Basic checks that service is functioning
        from app.core.session import get_session_manager
        get_session_manager()  # Just verify it doesn't crash
        
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "dead",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "error": str(e)
            }
        )


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check with full diagnostics
    """
    from app.config import settings
    
    start = time.time()
    
    # Check all dependencies
    vector_store = await check_vector_store()
    redis = await check_redis()
    llm = await check_llm()
    sessions = await check_session_manager()
    
    total_duration = (time.time() - start) * 1000
    
    return {
        "status": "healthy" if all(
            c["status"] in ["healthy", "configured", "disabled"]
            for c in [vector_store, redis, llm, sessions]
        ) else "degraded",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "total_check_duration_ms": round(total_duration, 2),
        "dependencies": {
            "vector_store": vector_store,
            "redis_cache": redis,
            "llm_api": llm,
            "session_manager": sessions
        },
        "configuration": {
            "query_transformation": settings.USE_QUERY_TRANSFORMATION,
            "transform_strategy": settings.QUERY_TRANSFORM_STRATEGY,
            "reranking": settings.USE_RERANKING,
            "reranker_type": settings.RERANKER_TYPE,
            "redis_enabled": settings.REDIS_ENABLED,
            "metrics_enabled": settings.METRICS_ENABLED
        }
    }
