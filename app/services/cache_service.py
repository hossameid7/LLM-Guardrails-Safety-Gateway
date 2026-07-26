"""
Semantic Cache Service.

Provides near-instant (<10 ms) responses for prompts that are semantically
similar to previously answered ones.  Uses **ChromaDB** as the vector store
and ``sentence-transformers`` (``all-MiniLM-L6-v2``) for embedding.

Cache hit threshold: cosine similarity ≥ 0.92 (configurable).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy globals – heavy imports are deferred to first use
# ---------------------------------------------------------------------------
_chroma_client = None
_collection = None
_embedding_model = None

_COLLECTION_NAME = "prompt_cache"
_SIMILARITY_THRESHOLD = 0.92


def _get_embedding_model():
    """Lazily load the sentence-transformer model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformer model: all-MiniLM-L6-v2")
    return _embedding_model


def _get_collection():
    """Lazily initialise the ChromaDB in-memory client and collection."""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        _chroma_client = chromadb.Client()  # ephemeral in-memory store
        _collection = _chroma_client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Initialised ChromaDB in-memory collection: %s", _COLLECTION_NAME)
    return _collection


def _embed(text: str) -> list[float]:
    """Generate a dense embedding for *text*."""
    model = _get_embedding_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def _deterministic_id(text: str) -> str:
    """Create a stable document ID from the prompt text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


@dataclass
class SemanticCacheService:
    """Semantic cache backed by ChromaDB + sentence-transformers.

    Usage::

        cache = SemanticCacheService()
        hit = cache.lookup(prompt)
        if hit:
            response, latency = hit
        else:
            response = await llm_call(prompt)
            cache.store(prompt, response, tokens)
    """

    similarity_threshold: float = field(default=_SIMILARITY_THRESHOLD)
    # In-memory stats
    _hits: int = field(default=0, init=False, repr=False)
    _misses: int = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, prompt: str) -> Optional[Tuple[str, float, int]]:
        """Search the cache for a semantically similar prompt.

        Args:
            prompt: The user prompt to look up.

        Returns:
            ``(cached_response, latency_ms, tokens_used)`` on hit, or
            ``None`` on miss.
        """
        t0 = time.perf_counter()

        try:
            collection = _get_collection()
            if collection.count() == 0:
                self._misses += 1
                return None

            query_embedding = _embed(prompt)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["documents", "metadatas", "distances"],
            )

            if not results["documents"] or not results["documents"][0]:
                self._misses += 1
                return None

            # ChromaDB returns *distance* for cosine space: distance = 1 − similarity
            distance = results["distances"][0][0]
            similarity = 1.0 - distance

            if similarity >= self.similarity_threshold:
                cached_response = results["documents"][0][0]
                metadata = results["metadatas"][0][0] if results["metadatas"] else {}
                tokens = int(metadata.get("tokens_used", 0))
                latency = round((time.perf_counter() - t0) * 1000, 2)
                self._hits += 1
                logger.info(
                    "Cache HIT (similarity=%.4f, latency=%.2fms)", similarity, latency,
                )
                return cached_response, latency, tokens

        except Exception:
            logger.exception("Semantic cache lookup failed – treating as miss")

        self._misses += 1
        return None

    def store(self, prompt: str, response: str, tokens_used: int = 0) -> None:
        """Store a prompt→response pair in the cache.

        Args:
            prompt: The original user prompt.
            response: The LLM-generated response.
            tokens_used: Token count to persist alongside the response.
        """
        try:
            collection = _get_collection()
            doc_id = _deterministic_id(prompt)
            embedding = _embed(prompt)

            collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[response],
                metadatas=[{"prompt": prompt, "tokens_used": tokens_used}],
            )
            logger.info("Cached response for prompt (id=%s)", doc_id)
        except Exception:
            logger.exception("Failed to store response in semantic cache")

    @property
    def stats(self) -> Dict[str, int]:
        """Return basic cache hit/miss statistics."""
        return {"hits": self._hits, "misses": self._misses}
