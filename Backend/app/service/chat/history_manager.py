"""
Chat History Manager.

Handles all MongoDB operations for chat session history:
  - Load recent messages
  - Save messages
  - Get/clear/list sessions

Extracted from ChatService._load_chat_history, _save_to_history,
get_session_history, clear_session, get_all_sessions.
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict

from pymongo.collection import Collection
from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    """Manages chat session history in MongoDB."""

    def __init__(self, collection: Collection):
        self.chat_sessions = collection

    def load_history(self, session_id: str, limit: int = 5) -> List[ChatMessage]:
        """
        Load the last N messages from MongoDB and convert to LlamaIndex ChatMessage objects.

        Args:
            session_id: The chat session ID
            limit: Maximum number of messages to retrieve (default: 5)

        Returns:
            List of ChatMessage objects for LlamaIndex
        """
        try:
            session = self.chat_sessions.find_one({"session_id": session_id})
            if not session or "messages" not in session:
                return []

            # Get the last N messages
            messages = session["messages"][-limit:]

            # Convert to LlamaIndex ChatMessage objects
            chat_messages = []
            for msg in messages:
                role = MessageRole.USER if msg["role"] == "user" else MessageRole.ASSISTANT
                chat_messages.append(ChatMessage(role=role, content=msg["content"]))

            return chat_messages

        except Exception as e:
            logger.warning(f"Could not load chat history: {e}")
            return []

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: Optional[List[str]] = None,
    ):
        """
        Save a message to MongoDB chat history.

        Args:
            session_id: The chat session ID
            role: "user" or "assistant"
            content: Message content
            sources: Optional list of source filenames (for assistant RAG responses)
        """
        try:
            message_doc = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow(),
            }

            # Add sources if provided (for RAG responses)
            if sources:
                message_doc["sources"] = sources

            # Update or create session document
            self.chat_sessions.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": message_doc},
                    "$set": {"last_activity": datetime.utcnow()},
                    "$setOnInsert": {"created_at": datetime.utcnow()},
                },
                upsert=True,
            )

        except Exception as e:
            logger.warning(f"Could not save to history: {e}")

    def get_session_history(self, session_id: str) -> List[Dict]:
        """
        Get full conversation history for a session.

        Args:
            session_id: The chat session ID

        Returns:
            List of message dictionaries
        """
        try:
            session = self.chat_sessions.find_one({"session_id": session_id})
            if session:
                return session.get("messages", [])
            return []
        except Exception as e:
            logger.warning(f"Could not get session history: {e}")
            return []

    def clear_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        try:
            result = self.chat_sessions.delete_one({"session_id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.warning(f"Could not clear session: {e}")
            return False

    def get_all_sessions(self, limit: int = 20) -> List[Dict]:
        """Get recent sessions with their last message."""
        try:
            sessions = (
                self.chat_sessions.find(
                    {},
                    {
                        "session_id": 1,
                        "created_at": 1,
                        "last_activity": 1,
                        "messages": {"$slice": -1},
                    },
                )
                .sort("last_activity", -1)
                .limit(limit)
            )
            return list(sessions)
        except Exception as e:
            logger.warning(f"Could not get sessions: {e}")
            return []
