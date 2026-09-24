"""Qdrant vector database client.

Manages collections for satellite image embeddings and text embeddings,
and provides search (single-modal) and hybrid search (cross-modal).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from config import QdrantSettings

logger = logging.getLogger(__name__)


class VectorDBService:
    """Async wrapper around Qdrant for satellite vision embeddings."""

    def __init__(self, client: AsyncQdrantClient, settings: QdrantSettings) -> None:
        self._client = client
        self._settings = settings

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def init_collections(self) -> None:
        """Ensure required collections exist, creating them if necessary."""
        await self._ensure_collection(
            name=self._settings.collection_image_embeddings,
            dim=self._settings.image_embedding_dim,
        )
        await self._ensure_collection(
            name=self._settings.collection_text_embeddings,
            dim=self._settings.text_embedding_dim,
        )
        logger.info("Qdrant collections verified / created.")

    async def _ensure_collection(self, name: str, dim: int) -> None:
        collections = await self._client.get_collections()
        existing_names = {c.name for c in collections.collections}
        if name not in existing_names:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d).", name, dim)
        else:
            logger.info("Qdrant collection '%s' already exists.", name)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def upsert_embeddings(
        self,
        collection: str,
        ids: List[str],
        embeddings: List[List[float]],
        payloads: List[Dict[str, Any]],
        batch_size: int = 128,
    ) -> None:
        """Insert or update embedding points in a collection.

        Handles batching automatically to stay within Qdrant size limits.
        """
        total = len(ids)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            points = [
                PointStruct(id=ids[i], vector=embeddings[i], payload=payloads[i])
                for i in range(start, end)
            ]
            await self._client.upsert(collection_name=collection, points=points)
        logger.debug("Upserted %d points into '%s'.", total, collection)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Single-collection vector search with optional payload filters.

        ``filters`` is a convenience dict that is translated into Qdrant
        filter conditions.  Supported keys:

        - ``image_id`` (str): exact match on image_id payload field.
        - ``capture_date_from`` / ``capture_date_to`` (str ISO dates): range
          filter on the ``capture_date`` payload field.
        """
        qdrant_filter = self._build_filter(filters) if filters else None

        hits = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )

        results: List[Dict[str, Any]] = []
        for hit in hits:
            results.append(
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload or {},
                }
            )
        return results

    async def hybrid_search(
        self,
        text_query_vector: Optional[List[float]],
        image_query_vector: Optional[List[float]],
        text_weight: float = 0.5,
        image_weight: float = 0.5,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Combine text and image search results via reciprocal rank fusion.

        When only one modality is provided the search degrades gracefully
        to single-modal.
        """
        text_results: List[Dict[str, Any]] = []
        image_results: List[Dict[str, Any]] = []

        if text_query_vector is not None:
            text_results = await self.search(
                collection=self._settings.collection_text_embeddings,
                query_vector=text_query_vector,
                top_k=top_k * 2,
                filters=filters,
            )

        if image_query_vector is not None:
            image_results = await self.search(
                collection=self._settings.collection_image_embeddings,
                query_vector=image_query_vector,
                top_k=top_k * 2,
                filters=filters,
            )

        # Reciprocal rank fusion (RRF) with k=60
        rrf_k = 60
        scores: Dict[str, float] = {}
        payload_map: Dict[str, Dict[str, Any]] = {}

        for rank, res in enumerate(text_results):
            key = str(res["id"])
            rrf_score = text_weight / (rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            payload_map[key] = res["payload"]

        for rank, res in enumerate(image_results):
            key = str(res["id"])
            rrf_score = image_weight / (rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in payload_map:
                payload_map[key] = res["payload"]

        sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]

        return [
            {"id": uid, "score": scores[uid], "payload": payload_map[uid]}
            for uid in sorted_ids
        ]

    # ------------------------------------------------------------------
    # Filter building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter(filters: Dict[str, Any]) -> Filter:
        """Translate a convenience filter dict to a Qdrant Filter object."""
        conditions: List[Any] = []

        if "image_id" in filters:
            conditions.append(
                FieldCondition(key="image_id", match=MatchValue(value=filters["image_id"]))
            )

        if "capture_date_from" in filters or "capture_date_to" in filters:
            range_kwargs: Dict[str, Any] = {}
            if "capture_date_from" in filters:
                range_kwargs["gte"] = filters["capture_date_from"]
            if "capture_date_to" in filters:
                range_kwargs["lte"] = filters["capture_date_to"]
            conditions.append(
                FieldCondition(key="capture_date", range=Range(**range_kwargs))
            )

        if "min_resolution_m" in filters or "max_resolution_m" in filters:
            range_kwargs_res: Dict[str, Any] = {}
            if "min_resolution_m" in filters:
                range_kwargs_res["gte"] = filters["min_resolution_m"]
            if "max_resolution_m" in filters:
                range_kwargs_res["lte"] = filters["max_resolution_m"]
            conditions.append(
                FieldCondition(key="resolution_m", range=Range(**range_kwargs_res))
            )

        return Filter(must=conditions) if conditions else Filter()
