import os
import logging
from dotenv import load_dotenv


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
)


if not JWT_SECRET_KEY:
    # Keep configuration importable for tooling such as Alembic and app discovery.
    # Token creation will require JWT_SECRET_KEY to be set in the environment.
    pass

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "tenant_schema_metadata")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
SCHEMA_INDEX_BATCH_SIZE = int(os.getenv("SCHEMA_INDEX_BATCH_SIZE", "64"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ACCESS_SCOPE_CACHE_TTL_SECONDS = int(os.getenv("ACCESS_SCOPE_CACHE_TTL_SECONDS", "86400"))
