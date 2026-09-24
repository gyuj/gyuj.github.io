"""Change detection service.

Provides end-to-end satellite image change detection:
  1. Load GeoTIFF image pairs from S3.
  2. Tile each image into 224x224 patches with configurable overlap.
  3. Run the Prithvi foundation model encoder on tile pairs to produce
     per-pixel change probability maps.
  4. Stitch tiles back into a full-resolution probability map.
  5. Threshold to binary mask and compute change statistics.
  6. Persist results (GeoTIFF mask + PNG preview) back to S3.
"""

from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
import torch
import torch.nn.functional as F
from scipy import ndimage

from config import ModelSettings
from app.models.schemas import (
    BoundingBox,
    ChangeDetectionResult,
    ChangedRegion,
    ImageMetadata,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tile dataclass
# ---------------------------------------------------------------------------

@dataclass
class Tile:
    """A spatial tile extracted from an image."""
    row: int
    col: int
    y_start: int
    x_start: int
    data: np.ndarray  # (C, H, W)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ChangeDetectionService:
    """Orchestrates satellite change detection with Prithvi."""

    def __init__(
        self,
        model_settings: ModelSettings,
        s3_service: "S3Service",  # forward ref
        embedding_service: "EmbeddingService",
    ) -> None:
        self._settings = model_settings
        self._s3 = s3_service
        self._embedding_service = embedding_service
        self._device = torch.device(model_settings.device)
        self._model: Optional[torch.nn.Module] = None
        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load the Prithvi model from HuggingFace or a local path."""
        try:
            from transformers import AutoModel

            logger.info(
                "Loading Prithvi model from %s onto %s ...",
                self._settings.prithvi_model_path,
                self._device,
            )
            self._model = AutoModel.from_pretrained(
                self._settings.prithvi_model_path,
                trust_remote_code=True,
            )
            self._model.eval()
            self._model.to(self._device)
            logger.info("Prithvi model loaded successfully.")
        except Exception as exc:
            logger.warning(
                "Could not load Prithvi model (%s). "
                "Change detection will fall back to pixel-differencing.",
                exc,
            )
            self._model = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect_changes(
        self,
        metadata_before: ImageMetadata,
        metadata_after: ImageMetadata,
        threshold: float | None = None,
    ) -> ChangeDetectionResult:
        """Run change detection on two images referenced by their metadata."""
        threshold = threshold or self._settings.change_threshold
        result_id = str(uuid.uuid4())

        # 1. Download images from S3
        bytes_before = await self._s3.download_image(metadata_before.s3_key)
        bytes_after = await self._s3.download_image(metadata_after.s3_key)

        # 2. Read as numpy arrays via rasterio
        arr_before, profile_before = self._read_geotiff(bytes_before)
        arr_after, profile_after = self._read_geotiff(bytes_after)

        # 3. Normalise bands to [0, 1]
        arr_before = self._normalize(arr_before)
        arr_after = self._normalize(arr_after)

        # 4. Tile both images
        tile_size = self._settings.tile_size
        overlap = self._settings.tile_overlap
        tiles_before = self._tile_image(arr_before, tile_size, overlap)
        tiles_after = self._tile_image(arr_after, tile_size, overlap)

        # 5. Run inference on tile pairs -> change probability map
        prob_map = self._infer_change_map(
            tiles_before, tiles_after, arr_before.shape, tile_size, overlap,
        )

        # 6. Threshold -> binary mask
        change_mask = (prob_map >= threshold).astype(np.uint8)

        # 7. Statistics
        change_pct = float(change_mask.sum()) / float(change_mask.size) * 100.0
        confidence = float(prob_map[change_mask == 1].mean()) if change_mask.any() else 0.0
        regions = self._extract_regions(change_mask, profile_before)

        # 8. Persist GeoTIFF mask
        mask_tiff_bytes = self._write_geotiff_mask(change_mask, profile_before)
        mask_key = f"processed/change_detection/{result_id}/change_mask.tif"
        await self._s3.upload_artifact(mask_tiff_bytes, mask_key, content_type="image/tiff")

        # 9. Persist PNG preview
        png_bytes = self._mask_to_png(change_mask)
        png_key = f"processed/change_detection/{result_id}/change_mask.png"
        await self._s3.upload_artifact(png_bytes, png_key, content_type="image/png")

        return ChangeDetectionResult(
            id=result_id,
            image_id_before=metadata_before.id,
            image_id_after=metadata_after.id,
            change_mask_s3_key=mask_key,
            change_mask_png_s3_key=png_key,
            change_percentage=round(change_pct, 4),
            changed_regions=regions,
            confidence=round(confidence, 4),
        )

    # ------------------------------------------------------------------
    # GeoTIFF I/O
    # ------------------------------------------------------------------

    @staticmethod
    def _read_geotiff(raw: bytes) -> Tuple[np.ndarray, dict]:
        """Read a GeoTIFF from bytes -> (C, H, W) numpy array + rasterio profile."""
        with rasterio.open(io.BytesIO(raw)) as src:
            arr = src.read()  # (bands, H, W)
            profile = dict(src.profile)
            profile["transform"] = src.transform
            profile["bounds"] = src.bounds
        return arr, profile

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        """Min-max normalise each band independently to [0, 1]."""
        arr = arr.astype(np.float32)
        for b in range(arr.shape[0]):
            band = arr[b]
            bmin, bmax = band.min(), band.max()
            if bmax - bmin > 0:
                arr[b] = (band - bmin) / (bmax - bmin)
            else:
                arr[b] = 0.0
        return arr

    # ------------------------------------------------------------------
    # Tiling
    # ------------------------------------------------------------------

    @staticmethod
    def _tile_image(
        arr: np.ndarray,
        tile_size: int,
        overlap: int,
    ) -> List[Tile]:
        """Split (C, H, W) array into overlapping tiles of (C, tile_size, tile_size)."""
        _, h, w = arr.shape
        stride = tile_size - overlap
        tiles: List[Tile] = []

        for row_idx, y in enumerate(range(0, h, stride)):
            for col_idx, x in enumerate(range(0, w, stride)):
                y_end = min(y + tile_size, h)
                x_end = min(x + tile_size, w)
                y_start = y_end - tile_size if y_end - y < tile_size else y
                x_start = x_end - tile_size if x_end - x < tile_size else x

                tile_data = arr[:, y_start : y_start + tile_size, x_start : x_start + tile_size]

                # Pad if still smaller than tile_size (image smaller than one tile)
                if tile_data.shape[1] < tile_size or tile_data.shape[2] < tile_size:
                    padded = np.zeros(
                        (arr.shape[0], tile_size, tile_size), dtype=arr.dtype,
                    )
                    padded[:, : tile_data.shape[1], : tile_data.shape[2]] = tile_data
                    tile_data = padded

                tiles.append(
                    Tile(row=row_idx, col=col_idx, y_start=y_start, x_start=x_start, data=tile_data)
                )
        return tiles

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _infer_change_map(
        self,
        tiles_before: List[Tile],
        tiles_after: List[Tile],
        image_shape: Tuple[int, ...],
        tile_size: int,
        overlap: int,
    ) -> np.ndarray:
        """Produce a full-resolution change probability map from tile pairs.

        When the Prithvi model is available the encoder features of each tile
        pair are compared via cosine distance.  Otherwise a simple per-pixel
        Euclidean distance is computed as a fallback.
        """
        _, h, w = image_shape
        prob_map = np.zeros((h, w), dtype=np.float32)
        weight_map = np.zeros((h, w), dtype=np.float32)

        batch_size = self._settings.batch_size

        for batch_start in range(0, len(tiles_before), batch_size):
            batch_b = tiles_before[batch_start : batch_start + batch_size]
            batch_a = tiles_after[batch_start : batch_start + batch_size]

            probs = self._infer_batch(batch_b, batch_a)  # list of (tile_size, tile_size)

            for tile_b, tile_prob in zip(batch_b, probs):
                ys = tile_b.y_start
                xs = tile_b.x_start
                ye = min(ys + tile_size, h)
                xe = min(xs + tile_size, w)
                th = ye - ys
                tw = xe - xs
                prob_map[ys:ye, xs:xe] += tile_prob[:th, :tw]
                weight_map[ys:ye, xs:xe] += 1.0

        # Average overlapping regions
        weight_map = np.maximum(weight_map, 1.0)
        prob_map /= weight_map
        return prob_map

    def _infer_batch(
        self,
        batch_before: List[Tile],
        batch_after: List[Tile],
    ) -> List[np.ndarray]:
        """Run inference on a batch of tile pairs.

        Returns a list of (H, W) change probability arrays in [0, 1].
        """
        tile_size = self._settings.tile_size

        if self._model is not None:
            return self._infer_batch_prithvi(batch_before, batch_after)

        # Fallback: per-pixel L2 distance normalised to [0, 1]
        results: List[np.ndarray] = []
        for tb, ta in zip(batch_before, batch_after):
            diff = np.linalg.norm(ta.data - tb.data, axis=0)  # (H, W)
            max_diff = diff.max() if diff.max() > 0 else 1.0
            results.append((diff / max_diff).astype(np.float32))
        return results

    def _infer_batch_prithvi(
        self,
        batch_before: List[Tile],
        batch_after: List[Tile],
    ) -> List[np.ndarray]:
        """Prithvi-based change detection via feature-space cosine distance."""
        assert self._model is not None

        def _stack(tiles: List[Tile]) -> torch.Tensor:
            arrays = [t.data for t in tiles]
            tensor = torch.from_numpy(np.stack(arrays, axis=0)).float()  # (B, C, H, W)
            # Prithvi expects 6-band input; replicate or truncate as needed
            c = tensor.shape[1]
            if c < 6:
                tensor = tensor.repeat(1, (6 // c) + 1, 1, 1)[:, :6, :, :]
            elif c > 6:
                tensor = tensor[:, :6, :, :]
            return tensor.to(self._device)

        with torch.no_grad():
            t_before = _stack(batch_before)
            t_after = _stack(batch_after)

            feat_before = self._model(t_before).last_hidden_state  # (B, N, D)
            feat_after = self._model(t_after).last_hidden_state

            # Reshape spatial tokens to 2-D feature maps
            b, n, d = feat_before.shape
            side = int(n ** 0.5)
            fb = feat_before[:, :side * side, :].reshape(b, side, side, d).permute(0, 3, 1, 2)
            fa = feat_after[:, :side * side, :].reshape(b, side, side, d).permute(0, 3, 1, 2)

            # Cosine distance per spatial location
            cos_sim = F.cosine_similarity(fb, fa, dim=1)  # (B, side, side) in [-1, 1]
            change_prob = (1.0 - cos_sim) / 2.0  # map to [0, 1]

            # Upsample to tile size
            change_prob = F.interpolate(
                change_prob.unsqueeze(1),
                size=(self._settings.tile_size, self._settings.tile_size),
                mode="bilinear",
                align_corners=False,
            ).squeeze(1)

        return [change_prob[i].cpu().numpy() for i in range(change_prob.shape[0])]

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_regions(
        mask: np.ndarray,
        profile: dict,
    ) -> List[ChangedRegion]:
        """Label connected components in the binary mask and extract metadata."""
        labelled, num_features = ndimage.label(mask)
        bounds = profile.get("bounds")
        transform = profile.get("transform")
        h, w = mask.shape

        regions: List[ChangedRegion] = []
        for region_id in range(1, num_features + 1):
            component = (labelled == region_id)
            pixel_area = int(component.sum())
            if pixel_area < 4:
                continue  # skip tiny noise

            ys, xs = np.where(component)
            y_min, y_max = int(ys.min()), int(ys.max())
            x_min, x_max = int(xs.min()), int(xs.max())
            cy, cx = float(ys.mean()), float(xs.mean())

            # Convert pixel coords to geographic coords if transform is available
            if bounds is not None:
                lon_min = bounds.left + (x_min / w) * (bounds.right - bounds.left)
                lon_max = bounds.left + ((x_max + 1) / w) * (bounds.right - bounds.left)
                lat_max = bounds.top - (y_min / h) * (bounds.top - bounds.bottom)
                lat_min = bounds.top - ((y_max + 1) / h) * (bounds.top - bounds.bottom)
                clon = bounds.left + (cx / w) * (bounds.right - bounds.left)
                clat = bounds.top - (cy / h) * (bounds.top - bounds.bottom)
            else:
                lon_min, lon_max = float(x_min), float(x_max)
                lat_min, lat_max = float(y_min), float(y_max)
                clon, clat = cx, cy

            regions.append(
                ChangedRegion(
                    region_id=region_id,
                    bbox=BoundingBox(
                        min_lon=lon_min, min_lat=lat_min,
                        max_lon=lon_max, max_lat=lat_max,
                    ),
                    pixel_area=pixel_area,
                    centroid_lon=round(clon, 6),
                    centroid_lat=round(clat, 6),
                )
            )

        # Sort largest first
        regions.sort(key=lambda r: r.pixel_area, reverse=True)
        return regions

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_geotiff_mask(mask: np.ndarray, profile: dict) -> bytes:
        """Write a single-band uint8 mask to an in-memory GeoTIFF."""
        h, w = mask.shape
        out_profile = {
            "driver": "GTiff",
            "dtype": "uint8",
            "count": 1,
            "height": h,
            "width": w,
            "compress": "lzw",
        }
        if "crs" in profile:
            out_profile["crs"] = profile["crs"]
        if "transform" in profile and profile["transform"] is not None:
            out_profile["transform"] = profile["transform"]
        elif "bounds" in profile and profile["bounds"] is not None:
            b = profile["bounds"]
            out_profile["transform"] = from_bounds(b.left, b.bottom, b.right, b.top, w, h)

        buf = io.BytesIO()
        with rasterio.open(buf, "w", **out_profile) as dst:
            dst.write(mask, 1)
        return buf.getvalue()

    @staticmethod
    def _mask_to_png(mask: np.ndarray) -> bytes:
        """Convert a binary mask (0/1 uint8) to a red-overlay PNG."""
        h, w = mask.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[mask == 1] = [255, 0, 0, 180]  # red with some transparency
        rgba[mask == 0] = [0, 0, 0, 0]
        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
