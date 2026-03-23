"""
Qdrant connection singleton.

Provides a single QdrantClient instance shared across services.
"""
import logging
import threading
from qdrant_client import QdrantClient
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_qdrant_client: QdrantClient | None = None
_qdrant_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    with _qdrant_lock:
        if _qdrant_client is not None:
            return _qdrant_client

        url = get_settings().database.qdrant_url
        _qdrant_client = QdrantClient(url=url)
        logger.info("✅ Qdrant client initialized")

    return _qdrant_client
