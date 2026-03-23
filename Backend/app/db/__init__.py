"""
Database connections package.
Provides centralized MongoDB and Qdrant client singletons.
"""
from app.db.mongo import (
    get_mongo_client,
    get_database,
    get_chat_sessions_collection,
)
from app.db.qdrant import get_qdrant_client

__all__ = [
    "get_mongo_client",
    "get_database",
    "get_chat_sessions_collection",
    "get_qdrant_client",
]
