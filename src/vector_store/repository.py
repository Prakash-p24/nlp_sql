import uuid

from langchain_core.documents import Document
from qdrant_client import models

from src.core.config import EMBEDDING_DIMENSION, QDRANT_COLLECTION
from src.vector_store.client import get_qdrant_client
from src.vector_store.collections import ensure_schema_collection


def stable_document_id(document: Document) -> str:
    """Make re-indexing upsert the same table document instead of duplicating it."""
    metadata = document.metadata
    identity = ":".join(
        (
            metadata["tenant_id"],
            metadata["database_id"],
            metadata["table_id"],
            metadata["document_type"],
        )
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def upsert_documents(
    documents: list[Document],
    vectors: list[list[float]],
) -> int:
    """Save embedded documents and searchable metadata to Qdrant."""
    if len(documents) != len(vectors):
        raise ValueError("Each document must have exactly one embedding vector")
    if not documents:
        return 0

    ensure_schema_collection()
    points = []
    for document, vector in zip(documents, vectors, strict=True):
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, "
                f"received {len(vector)}"
            )
        payload = {**document.metadata, "text": document.page_content}
        points.append(
            models.PointStruct(
                id=stable_document_id(document),
                vector={"dense": vector},
                payload=payload,
            )
        )

    get_qdrant_client().upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )
    return len(points)
