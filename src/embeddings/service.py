from src.embeddings.model import get_embedding_model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of schema documents using the configured model."""
    if not texts:
        return []
    vectors = get_embedding_model().embed_documents(texts)
    if any(len(vector) == 0 for vector in vectors):
        raise RuntimeError("The embedding model returned an empty vector")
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed one retrieval query using the same model as indexed documents."""
    return get_embedding_model().embed_query(text)
