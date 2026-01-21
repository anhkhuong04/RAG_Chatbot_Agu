"""
Rate Limiting Middleware for RAG Chatbot
Bảo vệ API khỏi spam và DDoS attacks
"""
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading
import time
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitEntry:
    """Track request count for a client"""
    request_count: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    
    def is_window_expired(self, window_seconds: int) -> bool:
        """Check if the current window has expired"""
        return datetime.utcnow() > self.window_start + timedelta(seconds=window_seconds)
    
    def reset(self):
        """Reset the counter for a new window"""
        self.request_count = 0
        self.window_start = datetime.utcnow()


class RateLimiter:
    """
    In-memory rate limiter using sliding window algorithm
    
    Features:
    - Per-IP rate limiting
    - Configurable limits per endpoint
    - Thread-safe operations
    - Auto cleanup of expired entries
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_limit: int = 10,
        burst_window_seconds: int = 1
    ):
        """
        Initialize rate limiter
        
        Args:
            requests_per_minute: Max requests per minute per IP
            requests_per_hour: Max requests per hour per IP
            burst_limit: Max requests in burst window
            burst_window_seconds: Burst window duration
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_limit = burst_limit
        self.burst_window_seconds = burst_window_seconds
        
        # Storage for different windows
        self._minute_entries: Dict[str, RateLimitEntry] = {}
        self._hour_entries: Dict[str, RateLimitEntry] = {}
        self._burst_entries: Dict[str, RateLimitEntry] = {}
        
        self._lock = threading.RLock()
        
        # Cleanup interval
        self._last_cleanup = datetime.utcnow()
        self._cleanup_interval = timedelta(minutes=5)
    
    def _get_client_id(self, request: Request) -> str:
        """
        Get unique client identifier from request
        Uses X-Forwarded-For header if behind proxy, otherwise client IP
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Get the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()
        
        return request.client.host if request.client else "unknown"
    
    def _maybe_cleanup(self):
        """Periodically cleanup expired entries"""
        if datetime.utcnow() - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = datetime.utcnow()
    
    def _cleanup_expired(self):
        """Remove expired entries from all windows"""
        with self._lock:
            # Cleanup minute entries
            expired_minute = [
                k for k, v in self._minute_entries.items()
                if v.is_window_expired(60)
            ]
            for k in expired_minute:
                del self._minute_entries[k]
            
            # Cleanup hour entries
            expired_hour = [
                k for k, v in self._hour_entries.items()
                if v.is_window_expired(3600)
            ]
            for k in expired_hour:
                del self._hour_entries[k]
            
            # Cleanup burst entries
            expired_burst = [
                k for k, v in self._burst_entries.items()
                if v.is_window_expired(self.burst_window_seconds)
            ]
            for k in expired_burst:
                del self._burst_entries[k]
            
            if expired_minute or expired_hour or expired_burst:
                logger.debug(
                    "Rate limiter cleanup",
                    context={
                        "expired_minute": len(expired_minute),
                        "expired_hour": len(expired_hour),
                        "expired_burst": len(expired_burst)
                    }
                )
    
    def is_allowed(self, request: Request) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Check if request is allowed under rate limits
        
        Returns:
            Tuple of (is_allowed, limit_type, retry_after_seconds)
        """
        client_id = self._get_client_id(request)
        
        with self._lock:
            self._maybe_cleanup()
            
            # Check burst limit
            if client_id not in self._burst_entries:
                self._burst_entries[client_id] = RateLimitEntry()
            
            burst_entry = self._burst_entries[client_id]
            if burst_entry.is_window_expired(self.burst_window_seconds):
                burst_entry.reset()
            
            if burst_entry.request_count >= self.burst_limit:
                return False, "burst", self.burst_window_seconds
            
            # Check minute limit
            if client_id not in self._minute_entries:
                self._minute_entries[client_id] = RateLimitEntry()
            
            minute_entry = self._minute_entries[client_id]
            if minute_entry.is_window_expired(60):
                minute_entry.reset()
            
            if minute_entry.request_count >= self.requests_per_minute:
                remaining = 60 - (datetime.utcnow() - minute_entry.window_start).seconds
                return False, "minute", max(1, remaining)
            
            # Check hour limit
            if client_id not in self._hour_entries:
                self._hour_entries[client_id] = RateLimitEntry()
            
            hour_entry = self._hour_entries[client_id]
            if hour_entry.is_window_expired(3600):
                hour_entry.reset()
            
            if hour_entry.request_count >= self.requests_per_hour:
                remaining = 3600 - (datetime.utcnow() - hour_entry.window_start).seconds
                return False, "hour", max(1, remaining)
            
            # Increment counters
            burst_entry.request_count += 1
            minute_entry.request_count += 1
            hour_entry.request_count += 1
            
            return True, None, None
    
    def get_remaining(self, request: Request) -> Dict[str, int]:
        """Get remaining requests for all windows"""
        client_id = self._get_client_id(request)
        
        with self._lock:
            minute_entry = self._minute_entries.get(client_id, RateLimitEntry())
            hour_entry = self._hour_entries.get(client_id, RateLimitEntry())
            
            return {
                "minute_remaining": max(0, self.requests_per_minute - minute_entry.request_count),
                "hour_remaining": max(0, self.requests_per_hour - hour_entry.request_count)
            }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting
    """
    
    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        exclude_paths: Optional[list] = None
    ):
        """
        Initialize middleware
        
        Args:
            app: FastAPI application
            rate_limiter: RateLimiter instance
            exclude_paths: Paths to exclude from rate limiting
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.exclude_paths = exclude_paths or ["/", "/health", "/docs", "/openapi.json"]
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request through rate limiter"""
        
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Check rate limit
        is_allowed, limit_type, retry_after = self.rate_limiter.is_allowed(request)
        
        if not is_allowed:
            logger.warning(
                "Rate limit exceeded",
                context={
                    "client": request.client.host if request.client else "unknown",
                    "path": request.url.path,
                    "limit_type": limit_type,
                    "retry_after": retry_after
                }
            )
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Please retry after {retry_after} seconds.",
                    "details": {
                        "limit_type": limit_type,
                        "retry_after_seconds": retry_after
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit-Type": limit_type
                }
            )
        
        # Add rate limit headers to response
        response = await call_next(request)
        
        remaining = self.rate_limiter.get_remaining(request)
        response.headers["X-RateLimit-Remaining-Minute"] = str(remaining["minute_remaining"])
        response.headers["X-RateLimit-Remaining-Hour"] = str(remaining["hour_remaining"])
        
        return response


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        from app.config import settings
        _rate_limiter = RateLimiter(
            requests_per_minute=getattr(settings, 'RATE_LIMIT_PER_MINUTE', 30),
            requests_per_hour=getattr(settings, 'RATE_LIMIT_PER_HOUR', 500),
            burst_limit=getattr(settings, 'RATE_LIMIT_BURST', 5),
            burst_window_seconds=1
        )
    return _rate_limiter
