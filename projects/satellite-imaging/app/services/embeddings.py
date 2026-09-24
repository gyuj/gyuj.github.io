"""Embedding service for satellite imagery and text.

Generates:
- Image embeddings from satellite tiles using the Prithvi vision encoder.
- Text embeddings using sentence-transformers (all-MiniLM-L6-v2).

Supports batch processing and stores results in Qdrant via VectorDBService.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from config import ModelSettings, QdrantSettings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Unified embedding generation for images and text."""

    def __init__(
        self,
        model_settings: ModelSettings,
        qdrant_settings: QdrantSettings,
        vectordb: "VectorDBService",  # forward ref
    ) -> None:
        self._model_settings = model_settings
        self._qdrant_settings = qdrant_settings
        self._vectordb = vectordb
        self._device = torch.device(model_settings.device)

        # Vision encoder (Prithvi)
        self._vision_model: Optional[torch.nn.Module] = None
        self._load_vision_model()

        # Text encoder
        logger.info("Loading sentence-transformer text encoder ...")
        self._text_model = SentenceTransformer("all-MiniLM-L6-v2", device=model_settings.device)
        logger.info("Text encoder loaded (dim=%d).", self._text_model.get_sentence_embedding_dimension())

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_vision_model(self) -> None:
        try:
            from transformers import AutoModel

            self._vision_model = AutoModel.from_pretrained(
                self._model_settings.prithvi_model_path,
                trust_remote_code=True,
            )
            self._vision_model.eval()
            self._vision_model.to(self._device)
            logger.info("Prithvi vision encoder loaded for embedding generation.")
        except Exception as exc:
            logger.warning("Could not load Prithvi encoder (%s). Image embeddings will be unavailable.", exc)
            self._vision_model = None

    # ------------------------------------------------------------------
    # Image embeddings
    # ------------------------------------------------------------------

    def generate_image_embeddings(
        self,
        tiles: np.ndarray,
    ) -> np.ndarray:
        """Generate embeddings for a batch of image tiles.

        Args:
            tiles: Array of shape (N, C, H, W) with pixel values in [0, 1].

        Returns:
            Embeddings of shape (N, D).
        """
        if self._vision_model is None:
            raise RuntimeError("Vision model is not loaded; cannot generate image embeddings.")

        tensor = torch.from_numpy(tiles).float().to(self._device)

        # Prithvi expects 6 bands — replicate/truncate
        c = tensor.shape[1]
        if c < 6:
            tensor = tensor.repeat(1, (6 // c) + 1, 1, 1)[:, :6, :, :]
        elif c > 6:
            tensor = tensor[:, :6, :, :]

        batch_size = self._model_settings.batch_size
        all_embeddings: List[np.ndarray] = []

        with torch.no_grad():
            for start in range(0, tensor.shape[0], batch_size):
                batch = tensor[start : start + batch_size]
                output = self._vision_model(batch)

                # Mean-pool over spatial tokens to get a single vector per tile
                hidden = output.last_hidden_state  # (B, num_tokens, D)
                pooled = hidden.mean(dim=1)  # (B, D)
                all_embeddings.append(pooled.cpu().numpy())

        return np.concatenate(all_embeddings, axis=0)

    # ------------------------------------------------------------------
    # Text embeddings
    # ------------------------------------------------------------------

    def generate_text_embeddings(
        self,
        texts: List[str],
        batch_size: int = 32,
    ) -> np.ndarray:
        """Encode a list of text strings into embeddings.

        Returns:
            Array of shape (N, 384).
        """
        embeddings = self._text_model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embeddings  # type: ignore[return-value]

    def generate_single_text_embedding(self, text: str) -> np.ndarray:
        """Convenience method for a single text string."""
        return self.generate_text_embeddings([text])[0]

    # ------------------------------------------------------------------
    # Indexing (store in Qdrant)
    # ------------------------------------------------------------------

    async def index_image_tiles(
        self,
        image_id: str,
        tiles: np.ndarray,
        tile_coords: List[Dict[str, int]],
        capture_date: Optional[datetime] = None,
        bbox: Optional[Dict[str, float]] = None,
    ) -> int:
        """Generate embeddings for tiles and store them in Qdrant.

        Args:
            image_id: Parent image identifier.
            tiles: (N, C, H, W) tile data.
            tile_coords: List of dicts with keys ``row``, ``col``, ``y_start``, ``x_start``.
            capture_date: Optional capture date to attach as metadata.
            bbox: Optional geographic bounding box dict.

        Returns:
            Number of embeddings stored.
        """
        embeddings = self.generate_image_embeddings(tiles)

        ids: List[str] = []
        payloads: List[Dict[str, Any]] = []
        for idx, coord in enumerate(tile_coords):
            point_id = str(uuid.uuid4())
            ids.append(point_id)
            payload: Dict[str, Any] = {
                "image_id": image_id,
                "tile_row": coord["row"],
                "tile_col": coord["col"],
                "y_start": coord["y_start"],
                "x_start": coord["x_start"],
            }
            if capture_date:
                payload["capture_date"] = capture_date.isoformat()
            if bbox:
                payload["bbox"] = bbox
            payloads.append(payload)

        await self._vectordb.upsert_embeddings(
            collection=self._qdrant_settings.collection_image_embeddings,
            ids=ids,
            embeddings=embeddings.tolist(),
            payloads=payloads,
        )
        logger.info("Indexed %d image tile embeddings for image %s.", len(ids), image_id)
        return len(ids)

    async def index_text(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> int:
        """Embed and store text chunks in Qdrant.

        Returns:
            Number of embeddings stored.
        """
        embeddings = self.generate_text_embeddings(texts)

        ids = [str(uuid.uuid4()) for _ in texts]
        payloads = []
        for text, meta in zip(texts, metadatas):
            payload = {**meta, "text": text}
            payloads.append(payload)

        await self._vectordb.upsert_embeddings(
            collection=self._qdrant_settings.collection_text_embeddings,
            ids=ids,
            embeddings=embeddings.tolist(),
            payloads=payloads,
        )
        logger.info("Indexed %d text embeddings.", len(ids))
        return len(ids)
