from functools import lru_cache

from qdrant_client import QdrantClient

from src.core.config import QDRANT_API_KEY, QDRANT_URL


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Create a shared Qdrant client for the configured server."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
