"""
Redis Caching Layer for Advanced RAG
Caches query transformations, retrieval results, and LLM responses
"""
from typing import Optional, Any, Dict, List
import json
import hashlib
import pickle
from datetime import timedelta
from functools import wraps

from .logger import get_logger

logger = get_logger(__name__)

# Flag to track if Redis is available
REDIS_AVAILABLE = False

try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis not installed. Caching will be disabled.")
    Redis = None


class CacheManager:
    """
    Quản lý Redis cache cho RAG system
    
    Cache hierarchy:
    1. Query Transformation Cache: Transformed queries
    2. Retrieval Cache: Retrieved nodes for queries
    3. Response Cache: Final LLM responses
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ttl: int = 3600,  # 1 hour default
        enabled: bool = True
    ):
        """
        Initialize cache manager
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            ttl: Default TTL in seconds
            enabled: Enable/disable caching
        """
        self.enabled = enabled and REDIS_AVAILABLE
        self.ttl = ttl
        self.redis_client: Optional[Redis] = None
        
        if not REDIS_AVAILABLE:
            logger.warning("Redis module not available. Install with: pip install redis")
            self.enabled = False
            return
        
        if self.enabled:
            try:
                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=False,  # We'll handle encoding ourselves
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                # Test connection
                self.redis_client.ping()
                logger.info(f"Redis cache initialized: {host}:{port}/{db}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                logger.warning("Continuing without cache...")
                self.enabled = False
                self.redis_client = None
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from arguments
        
        Args:
            prefix: Key prefix (e.g., "transform", "retrieval", "response")
            args: Positional arguments
            kwargs: Keyword arguments
        
        Returns:
            Cache key string
        """
        # Combine all arguments into a string
        key_data = {
            "args": args,
            "kwargs": kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True)
        
        # Generate hash
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return f"rag:{prefix}:{key_hash}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found
        """
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            data = self.redis_client.get(key)
            if data:
                logger.debug(f"Cache hit: {key}")
                return pickle.loads(data)
            else:
                logger.debug(f"Cache miss: {key}")
                return None
        except Exception as e:
            logger.warning(f"Cache get failed: {str(e)}")
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = use default)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            ttl = ttl or self.ttl
            data = pickle.dumps(value)
            self.redis_client.setex(key, ttl, data)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {str(e)}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(key)
            logger.debug(f"Cache deleted: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed: {str(e)}")
            return False
    
    def clear(self, pattern: str = "rag:*") -> int:
        """
        Clear cache keys matching pattern
        
        Args:
            pattern: Key pattern (default: all rag keys)
        
        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self.redis_client:
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                count = self.redis_client.delete(*keys)
                logger.info(f"Cache cleared: {count} keys deleted")
                return count
            return 0
        except Exception as e:
            logger.error(f"Cache clear failed: {str(e)}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled or not self.redis_client:
            return {"enabled": False}
        
        try:
            info = self.redis_client.info("stats")
            keys_count = len(self.redis_client.keys("rag:*"))
            
            return {
                "enabled": True,
                "connected": True,
                "keys_count": keys_count,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {
                "enabled": True,
                "connected": False,
                "error": str(e)
            }
    
    @staticmethod
    def _calculate_hit_rate(hits: int, misses: int) -> float:
        """Calculate cache hit rate"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)
    
    # Convenience methods for specific cache types
    
    def cache_query_transform(
        self,
        query: str,
        strategy: str,
        transformed: List[str],
        ttl: int = 3600
    ) -> bool:
        """Cache transformed query"""
        key = self._generate_key("transform", query=query, strategy=strategy)
        return self.set(key, transformed, ttl)
    
    def get_cached_transform(
        self,
        query: str,
        strategy: str
    ) -> Optional[List[str]]:
        """Get cached transformed query"""
        key = self._generate_key("transform", query=query, strategy=strategy)
        return self.get(key)
    
    def cache_retrieval(
        self,
        query: str,
        nodes: List[Any],
        ttl: int = 1800  # 30 minutes
    ) -> bool:
        """Cache retrieval results"""
        key = self._generate_key("retrieval", query=query)
        return self.set(key, nodes, ttl)
    
    def get_cached_retrieval(
        self,
        query: str
    ) -> Optional[List[Any]]:
        """Get cached retrieval results"""
        key = self._generate_key("retrieval", query=query)
        return self.get(key)
    
    def cache_response(
        self,
        query: str,
        response: str,
        ttl: int = 7200  # 2 hours
    ) -> bool:
        """Cache LLM response"""
        key = self._generate_key("response", query=query)
        return self.set(key, response, ttl)
    
    def get_cached_response(
        self,
        query: str
    ) -> Optional[str]:
        """Get cached LLM response"""
        key = self._generate_key("response", query=query)
        return self.get(key)


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create global cache manager"""
    global _cache_manager
    
    if _cache_manager is None:
        from app.config import settings
        
        _cache_manager = CacheManager(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD else None,
            ttl=settings.REDIS_TTL,
            enabled=settings.REDIS_ENABLED
        )
    
    return _cache_manager


def cached(
    cache_type: str = "response",
    ttl: Optional[int] = None,
    key_func: Optional[callable] = None
):
    """
    Decorator to cache function results
    
    Args:
        cache_type: Cache type prefix
        ttl: TTL in seconds
        key_func: Function to generate cache key from args
    
    Example:
        @cached(cache_type="custom", ttl=300)
        def my_function(arg1, arg2):
            return expensive_operation(arg1, arg2)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_manager()
            
            if not cache.enabled:
                return func(*args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._generate_key(cache_type, *args, **kwargs)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.info(f"Cache hit for {func.__name__}")
                return result
            
            # Execute function and cache result
            logger.info(f"Cache miss for {func.__name__}, executing...")
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator
