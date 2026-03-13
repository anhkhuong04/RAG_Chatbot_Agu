"""
Qdrant connection singleton.

Provides a single QdrantClient instance shared across services.
"""
import os
import logging
import threading
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_qdrant_client: QdrantClient | None = None
_qdrant_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    """
    Get or create the singleton QdrantClient.
    Thread-safe via double-checked locking.
    """
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    with _qdrant_lock:
        if _qdrant_client is not None:
            return _qdrant_client

        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        _qdrant_client = QdrantClient(url=url)
        logger.info("✅ Qdrant client initialized")

    return _qdrant_client
