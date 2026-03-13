"""
MongoDB connection singleton.

Provides a single MongoClient instance shared across services,
avoiding repeated MongoClient(...) instantiation.
"""
import os
import logging
import threading
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None
_mongo_lock = threading.Lock()


def get_mongo_client() -> MongoClient:
    """
    Get or create the singleton MongoClient.
    Thread-safe via double-checked locking.
    """
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    with _mongo_lock:
        if _mongo_client is not None:
            return _mongo_client

        uri = os.getenv("MONGO_URI", "mongodb://admin:admin123@localhost:27018/?authSource=admin")
        _mongo_client = MongoClient(uri)
        logger.info("✅ MongoDB client initialized")

    return _mongo_client


def get_database(db_name: str = "university_db") -> Database:
    """Get a MongoDB database instance."""
    return get_mongo_client()[db_name]


def get_chat_sessions_collection() -> Collection:
    """Get the chat_sessions collection (convenience shortcut)."""
    return get_database()["chat_sessions"]
