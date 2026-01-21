"""
Custom Exceptions for RAG Chatbot
Centralized error handling với proper error codes
"""
from typing import Optional, Dict, Any


class RAGChatbotError(Exception):
    """Base exception for RAG Chatbot"""
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ==========================================
# SESSION ERRORS
# ==========================================

class SessionError(RAGChatbotError):
    """Base exception for session-related errors"""
    pass


class SessionNotFoundError(SessionError):
    """Session not found or expired"""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session not found or expired: {session_id}",
            error_code="SESSION_NOT_FOUND",
            details={"session_id": session_id}
        )


class SessionExpiredError(SessionError):
    """Session has expired"""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session has expired: {session_id}",
            error_code="SESSION_EXPIRED",
            details={"session_id": session_id}
        )


class SessionLimitExceededError(SessionError):
    """Maximum session limit reached"""
    
    def __init__(self, max_sessions: int):
        super().__init__(
            message=f"Maximum session limit ({max_sessions}) exceeded",
            error_code="SESSION_LIMIT_EXCEEDED",
            details={"max_sessions": max_sessions}
        )


# ==========================================
# ENGINE ERRORS  
# ==========================================

class EngineError(RAGChatbotError):
    """Base exception for engine-related errors"""
    pass


class EngineNotInitializedError(EngineError):
    """Chat engine not initialized"""
    
    def __init__(self):
        super().__init__(
            message="Chat engine has not been initialized",
            error_code="ENGINE_NOT_INITIALIZED"
        )


class VectorStoreError(EngineError):
    """Vector store connection/query error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        details = {}
        if original_error:
            details["original_error"] = str(original_error)
        
        super().__init__(
            message=f"Vector store error: {message}",
            error_code="VECTOR_STORE_ERROR",
            details=details
        )


class LLMError(EngineError):
    """LLM API error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        details = {}
        if original_error:
            details["original_error"] = str(original_error)
        
        super().__init__(
            message=f"LLM error: {message}",
            error_code="LLM_ERROR",
            details=details
        )


class RetrievalError(EngineError):
    """Document retrieval error"""
    
    def __init__(self, message: str, query: Optional[str] = None):
        details = {}
        if query:
            details["query"] = query[:100]  # Truncate for safety
        
        super().__init__(
            message=f"Retrieval error: {message}",
            error_code="RETRIEVAL_ERROR",
            details=details
        )


# ==========================================
# QUERY TRANSFORMATION ERRORS
# ==========================================

class QueryTransformError(RAGChatbotError):
    """Query transformation error"""
    
    def __init__(self, message: str, strategy: Optional[str] = None):
        details = {}
        if strategy:
            details["strategy"] = strategy
        
        super().__init__(
            message=f"Query transformation failed: {message}",
            error_code="QUERY_TRANSFORM_ERROR",
            details=details
        )


# ==========================================
# CACHE ERRORS
# ==========================================

class CacheError(RAGChatbotError):
    """Cache operation error"""
    
    def __init__(self, message: str, operation: Optional[str] = None):
        details = {}
        if operation:
            details["operation"] = operation
        
        super().__init__(
            message=f"Cache error: {message}",
            error_code="CACHE_ERROR",
            details=details
        )


class CacheConnectionError(CacheError):
    """Cache connection error"""
    
    def __init__(self, host: str, port: int):
        super().__init__(
            message=f"Failed to connect to cache at {host}:{port}",
            operation="connect"
        )
        self.details.update({"host": host, "port": port})


# ==========================================
# VALIDATION ERRORS
# ==========================================

class ValidationError(RAGChatbotError):
    """Input validation error"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field
        
        super().__init__(
            message=f"Validation error: {message}",
            error_code="VALIDATION_ERROR",
            details=details
        )


class EmptyQueryError(ValidationError):
    """Empty or invalid query"""
    
    def __init__(self):
        super().__init__(
            message="Query cannot be empty",
            field="message"
        )


class QueryTooLongError(ValidationError):
    """Query exceeds maximum length"""
    
    def __init__(self, max_length: int, actual_length: int):
        super().__init__(
            message=f"Query exceeds maximum length of {max_length} characters",
            field="message"
        )
        self.details.update({
            "max_length": max_length,
            "actual_length": actual_length
        })


# ==========================================
# RATE LIMITING ERRORS
# ==========================================

class RateLimitError(RAGChatbotError):
    """Rate limit exceeded"""
    
    def __init__(self, retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            error_code="RATE_LIMIT_EXCEEDED",
            details=details
        )
