"""
Session Manager for RAG Chatbot
Quản lý conversation sessions cho multiple users
"""
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading
import uuid
from llama_index.core.memory import ChatMemoryBuffer

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    """Represents a chat session"""
    session_id: str
    created_at: datetime
    last_accessed: datetime
    memory: ChatMemoryBuffer
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, ttl_minutes: int = 60) -> bool:
        """Check if session has expired"""
        expiry_time = self.last_accessed + timedelta(minutes=ttl_minutes)
        return datetime.utcnow() > expiry_time
    
    def touch(self):
        """Update last accessed time"""
        self.last_accessed = datetime.utcnow()


class SessionManager:
    """
    Thread-safe session manager for handling multiple conversations
    
    Features:
    - Create/retrieve sessions by ID
    - Auto-cleanup expired sessions
    - Memory isolation per session
    - Thread-safe operations
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global session manager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        session_ttl_minutes: int = 60,
        memory_token_limit: int = 3000,
        max_sessions: int = 1000
    ):
        """
        Initialize session manager
        
        Args:
            session_ttl_minutes: Session expiry time in minutes
            memory_token_limit: Token limit for chat memory
            max_sessions: Maximum concurrent sessions
        """
        if self._initialized:
            return
            
        self._sessions: Dict[str, Session] = {}
        self._sessions_lock = threading.RLock()
        self.session_ttl_minutes = session_ttl_minutes
        self.memory_token_limit = memory_token_limit
        self.max_sessions = max_sessions
        self._initialized = True
        
        logger.info(
            "SessionManager initialized",
            context={
                "ttl_minutes": session_ttl_minutes,
                "memory_token_limit": memory_token_limit,
                "max_sessions": max_sessions
            }
        )
    
    def create_session(self, session_id: Optional[str] = None) -> Session:
        """
        Create a new session
        
        Args:
            session_id: Optional custom session ID. If None, generates UUID.
            
        Returns:
            New Session object
        """
        with self._sessions_lock:
            # Cleanup if at capacity
            if len(self._sessions) >= self.max_sessions:
                self._cleanup_expired_sessions()
                
                # If still at capacity, remove oldest sessions
                if len(self._sessions) >= self.max_sessions:
                    self._remove_oldest_sessions(count=self.max_sessions // 10)
            
            # Generate ID if not provided
            if session_id is None:
                session_id = str(uuid.uuid4())
            
            # Check if session already exists
            if session_id in self._sessions:
                logger.warning(f"Session {session_id} already exists, returning existing")
                return self._sessions[session_id]
            
            # Create new session with fresh memory
            now = datetime.utcnow()
            session = Session(
                session_id=session_id,
                created_at=now,
                last_accessed=now,
                memory=ChatMemoryBuffer.from_defaults(
                    token_limit=self.memory_token_limit
                )
            )
            
            self._sessions[session_id] = session
            
            logger.info(
                "Session created",
                context={
                    "session_id": session_id,
                    "total_sessions": len(self._sessions)
                }
            )
            
            return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get existing session by ID
        
        Args:
            session_id: Session ID to retrieve
            
        Returns:
            Session object or None if not found/expired
        """
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            
            if session is None:
                logger.debug(f"Session not found: {session_id}")
                return None
            
            # Check expiry
            if session.is_expired(self.session_ttl_minutes):
                logger.info(f"Session expired, removing: {session_id}")
                del self._sessions[session_id]
                return None
            
            # Update access time
            session.touch()
            return session
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> Session:
        """
        Get existing session or create new one
        
        Args:
            session_id: Session ID. If None, creates new session.
            
        Returns:
            Session object
        """
        if session_id is None:
            return self.create_session()
        
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)
        
        return session
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        with self._sessions_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session deleted: {session_id}")
                return True
            return False
    
    def reset_session(self, session_id: str) -> bool:
        """
        Reset session memory (clear chat history)
        
        Args:
            session_id: Session ID to reset
            
        Returns:
            True if reset, False if not found
        """
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session:
                session.memory.reset()
                session.touch()
                logger.info(f"Session memory reset: {session_id}")
                return True
            return False
    
    def get_session_count(self) -> int:
        """Get number of active sessions"""
        with self._sessions_lock:
            return len(self._sessions)
    
    def get_all_session_ids(self) -> list:
        """Get list of all session IDs"""
        with self._sessions_lock:
            return list(self._sessions.keys())
    
    def _cleanup_expired_sessions(self):
        """Remove all expired sessions"""
        with self._sessions_lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired(self.session_ttl_minutes)
            ]
            
            for sid in expired:
                del self._sessions[sid]
            
            if expired:
                logger.info(
                    "Cleaned up expired sessions",
                    context={"count": len(expired)}
                )
    
    def _remove_oldest_sessions(self, count: int):
        """Remove oldest sessions by last_accessed time"""
        with self._sessions_lock:
            if not self._sessions:
                return
            
            # Sort by last_accessed and remove oldest
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].last_accessed
            )
            
            to_remove = sorted_sessions[:count]
            for sid, _ in to_remove:
                del self._sessions[sid]
            
            logger.info(
                "Removed oldest sessions",
                context={"count": len(to_remove)}
            )
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get session information without updating access time"""
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session:
                return {
                    "session_id": session.session_id,
                    "created_at": session.created_at.isoformat(),
                    "last_accessed": session.last_accessed.isoformat(),
                    "is_expired": session.is_expired(self.session_ttl_minutes),
                    "metadata": session.metadata
                }
            return None


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get global session manager instance"""
    global _session_manager
    if _session_manager is None:
        from app.config import settings
        _session_manager = SessionManager(
            session_ttl_minutes=getattr(settings, 'SESSION_TTL_MINUTES', 60),
            memory_token_limit=getattr(settings, 'MEMORY_TOKEN_LIMIT', 3000),
            max_sessions=getattr(settings, 'MAX_SESSIONS', 1000)
        )
    return _session_manager


def reset_session_manager():
    """Reset session manager (for testing)"""
    global _session_manager
    _session_manager = None
