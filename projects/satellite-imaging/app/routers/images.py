"""FastAPI router for satellite image management.

Delegates to the shared S3Service and EmbeddingService initialised during
application lifespan.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

import rasterio
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.models.schemas import BoundingBox, ImageMetadata, ImageUploadResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_rasterio_metadata(file_bytes: bytes) -> dict:
    """Open a GeoTIFF from bytes and extract geospatial metadata."""
    with rasterio.open(io.BytesIO(file_bytes)) as src:
        bounds = src.bounds
        res = src.res
        band_descriptions = list(src.descriptions) if src.descriptions else []
        band_names = [d for d in band_descriptions if d] or [f"B{i+1}" for i in range(src.count)]
        bbox = BoundingBox(
            min_lon=bounds.left,
            min_lat=bounds.bottom,
            max_lon=bounds.right,
            max_lat=bounds.top,
        ) if src.crs else None

        return {
            "width": src.width,
            "height": src.height,
            "bands": band_names,
            "crs": str(src.crs) if src.crs else None,
            "resolution_m": res[0] if res else None,
            "bbox": bbox,
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a satellite image (GeoTIFF)",
)
async def upload_image(
    file: UploadFile = File(...),
    capture_date: Optional[str] = Form(None),
) -> ImageUploadResponse:
    from app.main import get_s3_service

    if not file.filename or not file.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only GeoTIFF files (.tif / .tiff) are accepted.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        geo_meta = _extract_rasterio_metadata(file_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to read GeoTIFF metadata: {exc}",
        )

    metadata = ImageMetadata(
        filename=file.filename,
        s3_key="",  # set by service
        capture_date=datetime.fromisoformat(capture_date) if capture_date else None,
        **geo_meta,
    )

    s3 = get_s3_service()
    s3_key = await s3.upload_image(file_bytes, metadata)
    url = await s3.generate_presigned_url(s3_key)

    return ImageUploadResponse(metadata=metadata, presigned_url=url)


@router.get("/", response_model=List[ImageMetadata], summary="List images with optional filters")
async def list_images(
    prefix: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> List[ImageMetadata]:
    from app.main import get_s3_service

    s3 = get_s3_service()
    return await s3.list_images(prefix=prefix, limit=limit)


@router.get("/{image_id}/presigned-url", summary="Get a presigned download URL")
async def get_presigned_url(image_id: str) -> dict:
    from app.main import get_s3_service

    s3 = get_s3_service()
    images = await s3.list_images(limit=500)
    for img in images:
        if img.id == image_id:
            url = await s3.generate_presigned_url(img.s3_key)
            return {"url": url, "image_id": image_id}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
