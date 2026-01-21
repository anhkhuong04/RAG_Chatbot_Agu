"""
FastAPI Dependencies
Reusable dependencies for dependency injection
"""
from typing import Optional, Generator
from fastapi import Depends, HTTPException, status, Request

from app.core.session import get_session_manager, Session, SessionManager
from app.core.engine import get_engine_factory, ChatEngineFactory
from app.core.cache import get_cache_manager, CacheManager
from app.core.logger import get_logger
from app.core.exceptions import SessionNotFoundError
from app.config import settings

logger = get_logger(__name__)


# ==========================================
# SESSION DEPENDENCIES
# ==========================================

def get_session_manager_dep() -> SessionManager:
    """
    Dependency to get session manager instance
    """
    return get_session_manager()


def get_optional_session(
    conversation_id: Optional[str] = None,
    session_manager: SessionManager = Depends(get_session_manager_dep)
) -> Optional[Session]:
    """
    Get session if conversation_id provided, otherwise None
    Used for endpoints that optionally continue a conversation
    """
    if conversation_id is None:
        return None
    
    session = session_manager.get_session(conversation_id)
    return session


def get_required_session(
    conversation_id: str,
    session_manager: SessionManager = Depends(get_session_manager_dep)
) -> Session:
    """
    Get session or raise 404 if not found
    Used for endpoints that require an existing conversation
    """
    session = session_manager.get_session(conversation_id)
    
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Conversation not found: {conversation_id}",
                "details": {"conversation_id": conversation_id}
            }
        )
    
    return session


# ==========================================
# ENGINE DEPENDENCIES
# ==========================================

def get_engine_factory_dep() -> ChatEngineFactory:
    """
    Dependency to get engine factory instance
    """
    return get_engine_factory()


# ==========================================
# CACHE DEPENDENCIES
# ==========================================

def get_cache_manager_dep() -> CacheManager:
    """
    Dependency to get cache manager instance
    """
    return get_cache_manager()


# ==========================================
# SETTINGS DEPENDENCIES
# ==========================================

def get_settings():
    """
    Dependency to get settings
    """
    return settings


# ==========================================
# REQUEST VALIDATION DEPENDENCIES
# ==========================================

def validate_message_length(max_length: int = 4000):
    """
    Factory for message length validation dependency
    """
    def validator(message: str) -> str:
        if len(message) > max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "MESSAGE_TOO_LONG",
                    "message": f"Message exceeds maximum length of {max_length} characters",
                    "details": {
                        "max_length": max_length,
                        "actual_length": len(message)
                    }
                }
            )
        return message
    
    return validator


# ==========================================
# RATE LIMITING DEPENDENCIES
# ==========================================

async def check_rate_limit(request: Request):
    """
    Dependency to check rate limit
    Can be used on specific endpoints for custom limits
    """
    from app.middleware.rate_limiter import get_rate_limiter
    
    rate_limiter = get_rate_limiter()
    is_allowed, limit_type, retry_after = rate_limiter.is_allowed(request)
    
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": f"Too many requests. Please retry after {retry_after} seconds.",
                "details": {
                    "limit_type": limit_type,
                    "retry_after_seconds": retry_after
                }
            },
            headers={"Retry-After": str(retry_after)}
        )


# ==========================================
# COMMON DEPENDENCY COMBINATIONS
# ==========================================

class ChatDependencies:
    """
    Combined dependencies for chat endpoints
    """
    def __init__(
        self,
        session_manager: SessionManager = Depends(get_session_manager_dep),
        engine_factory: ChatEngineFactory = Depends(get_engine_factory_dep),
        cache_manager: CacheManager = Depends(get_cache_manager_dep)
    ):
        self.session_manager = session_manager
        self.engine_factory = engine_factory
        self.cache_manager = cache_manager
