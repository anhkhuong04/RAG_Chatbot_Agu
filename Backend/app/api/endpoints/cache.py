"""
Cache Management API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from app.core.cache import get_cache_manager
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class CacheStatsResponse(BaseModel):
    """Cache statistics response"""
    enabled: bool
    stats: Dict[str, Any]


class CacheClearResponse(BaseModel):
    """Cache clear response"""
    success: bool
    keys_deleted: int
    message: str


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Get cache statistics
    
    Returns cache hit rate, keys count, and other stats
    """
    try:
        cache = get_cache_manager()
        stats = cache.get_stats()
        
        return CacheStatsResponse(
            enabled=cache.enabled,
            stats=stats
        )
    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache stats: {str(e)}"
        )


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(pattern: str = "rag:*"):
    """
    Clear cache keys matching pattern
    
    Args:
        pattern: Key pattern to match (default: rag:* for all keys)
    
    Examples:
        - rag:* - Clear all RAG cache
        - rag:transform:* - Clear only transformation cache
        - rag:response:* - Clear only response cache
    """
    try:
        cache = get_cache_manager()
        
        if not cache.enabled:
            return CacheClearResponse(
                success=False,
                keys_deleted=0,
                message="Cache is not enabled"
            )
        
        count = cache.clear(pattern)
        
        logger.info(f"Cache cleared: {count} keys deleted", pattern=pattern)
        
        return CacheClearResponse(
            success=True,
            keys_deleted=count,
            message=f"Successfully deleted {count} keys matching pattern '{pattern}'"
        )
    except Exception as e:
        logger.error(f"Failed to clear cache: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/cache/health")
async def cache_health():
    """
    Check cache health status
    
    Returns connection status and basic info
    """
    try:
        cache = get_cache_manager()
        
        if not cache.enabled:
            return {
                "status": "disabled",
                "message": "Redis caching is not enabled"
            }
        
        stats = cache.get_stats()
        
        if stats.get("connected"):
            return {
                "status": "healthy",
                "message": "Redis cache is connected and operational",
                "keys_count": stats.get("keys_count", 0)
            }
        else:
            return {
                "status": "unhealthy",
                "message": "Redis cache is enabled but not connected",
                "error": stats.get("error", "Unknown error")
            }
    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
