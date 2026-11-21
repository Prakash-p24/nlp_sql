from qdrant_client import models

from src.core.config import EMBEDDING_DIMENSION, QDRANT_COLLECTION
from src.vector_store.client import get_qdrant_client

PAYLOAD_KEYWORD_FIELDS = (
    "tenant_id",
    "database_id",
    "schema_id",
    "schema_name",
    "table_id",
    "table_name",
    "column_id",
    "column_name",
    "qualified_table_name",
    "document_type",
)


def ensure_schema_collection() -> None:
    """Create the schema collection and indexes used for filters and keywords."""
    client = get_qdrant_client()
    if not client.collection_exists(QDRANT_COLLECTION):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=models.Distance.COSINE,
                )
            },
        )

    # Keyword indexes make tenant/database/table filters efficient. The text
    # index supports lexical matching on the generated schema document.
    for field_name in PAYLOAD_KEYWORD_FIELDS:
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    client.create_payload_index(
        collection_name=QDRANT_COLLECTION,
        field_name="text",
        field_schema=models.PayloadSchemaType.TEXT,
    )
