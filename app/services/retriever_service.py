import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy singletons — initialized on first use to avoid slowing startup
_embedding_model = None
_qdrant_client = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model BAAI/bge-small-en-v1.5 ...")
        _embedding_model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
        logger.info("Embedding model loaded.")
    return _embedding_model


def _get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        logger.info(f"Connecting to Qdrant at {settings.QDRANT_URL} ...")
        kwargs = {"url": settings.QDRANT_URL}
        if settings.QDRANT_API_KEY:
            kwargs["api_key"] = settings.QDRANT_API_KEY
        _qdrant_client = QdrantClient(**kwargs)
        logger.info("Qdrant client ready.")
    return _qdrant_client


def embed_query(query: str) -> List[float]:
    model = _get_embedding_model()
    vector = model.encode(query, normalize_embeddings=True)
    return vector.tolist()


def _build_filter(filters: Optional[Dict[str, Any]]):
    if not filters:
        return None
    from qdrant_client.http import models as qm
    conditions = [
        qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
        for k, v in filters.items()
        if v is not None
    ]
    return qm.Filter(must=conditions) if conditions else None


def retrieve(
    query: str,
    jurisdiction: str = None,
    top_k: int = None,
    score_threshold: float = None,
) -> Dict[str, Any]:
    """
    Embed the query and retrieve the top-k most relevant legal chunks from Qdrant.
    Returns a structured dict with results and metadata.
    """
    jurisdiction = jurisdiction or settings.JURISDICTION_DEFAULT
    top_k = top_k or settings.TOP_K_FINAL
    score_threshold = score_threshold or settings.SCORE_THRESHOLD

    try:
        client = _get_qdrant_client()
        query_vector = embed_query(query)

        filters = {"jurisdiction": jurisdiction, "document_type": "law"}
        qfilter = _build_filter(filters)

        response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
            with_vectors=False,
        )

        hits = []
        for point in response.points:
            score = float(point.score)
            if score < score_threshold:
                continue
            payload = point.payload or {}
            hits.append({
                "doc_id": payload.get("doc_id"),
                "score": round(score, 4),
                "text": payload.get("text", ""),
                "metadata": {
                    "citation": payload.get("citation", "Unknown Source"),
                    "act_title": payload.get("act_title"),
                    "section_number": payload.get("section_number"),
                    "section_title": payload.get("section_title"),
                    "act_link": payload.get("act_link"),
                },
            })

        hits.sort(key=lambda x: x["score"], reverse=True)
        logger.debug(f"Retrieved {len(hits)} chunks for query: {query[:60]}...")

        return {
            "query": query,
            "result_count": len(hits),
            "results": hits,
        }

    except Exception as e:
        logger.error(f"Retrieval failed: {e}", exc_info=True)
        return {"query": query, "result_count": 0, "results": [], "error": str(e)}
