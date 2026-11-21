import uuid

from sqlalchemy.orm import Session

from src.core.config import SCHEMA_INDEX_BATCH_SIZE
from src.embeddings.service import embed_documents
from src.metadata.document_builder import build_schema_documents
from src.vector_store.repository import upsert_documents


def index_database_schema(
    db: Session,
    tenant_id: uuid.UUID,
    database_id: uuid.UUID,
    *,
    batch_size: int = SCHEMA_INDEX_BATCH_SIZE,
) -> dict[str, int]:
    """Build, embed, and upsert selected table and column documents in batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    offset = 0
    indexed_documents = 0
    batches = 0
    while True:
        documents = build_schema_documents(
            db,
            tenant_id,
            database_id,
            offset=offset,
            limit=batch_size,
        )
        if not documents:
            break

        vectors = embed_documents([document.page_content for document in documents])
        indexed_documents += upsert_documents(documents, vectors)
        batches += 1
        # The builder paginates over tables, while each page now returns one
        # table document plus zero or more column documents per table.
        offset += batch_size

    return {"indexed_documents": indexed_documents, "batches": batches}
