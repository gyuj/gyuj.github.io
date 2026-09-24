"""Pydantic models (schemas) for the Satellite Vision Intelligence Platform.

These schemas are used across the API layer, service layer, and for
serialisation into the vector DB and S3 metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Image metadata
# ---------------------------------------------------------------------------

class BoundingBox(BaseModel):
    """Geographic bounding box in WGS-84 decimal degrees."""
    min_lon: float = Field(..., description="Western longitude")
    min_lat: float = Field(..., description="Southern latitude")
    max_lon: float = Field(..., description="Eastern longitude")
    max_lat: float = Field(..., description="Northern latitude")


class ImageMetadata(BaseModel):
    """Metadata for a single uploaded satellite image."""
    id: str = Field(default_factory=_uuid4_str, description="Unique image identifier")
    filename: str = Field(..., description="Original filename")
    s3_key: str = Field(..., description="Full S3 object key")
    capture_date: Optional[datetime] = Field(default=None, description="Date the image was captured")
    bbox: Optional[BoundingBox] = Field(default=None, description="Geographic extent")
    resolution_m: Optional[float] = Field(default=None, description="Ground sampling distance in metres")
    bands: List[str] = Field(default_factory=list, description="Band names (e.g. ['B02','B03','B04'])")
    width: Optional[int] = Field(default=None, description="Image width in pixels")
    height: Optional[int] = Field(default=None, description="Image height in pixels")
    crs: Optional[str] = Field(default=None, description="Coordinate reference system (e.g. EPSG:4326)")
    uploaded_at: datetime = Field(default_factory=_utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ImageUploadResponse(BaseModel):
    metadata: ImageMetadata
    presigned_url: str


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

class ChangedRegion(BaseModel):
    """A connected-component region where change was detected."""
    region_id: int = Field(..., description="Sequential region identifier")
    bbox: BoundingBox = Field(..., description="Bounding box of the changed region")
    pixel_area: int = Field(..., description="Number of changed pixels in this region")
    centroid_lon: float
    centroid_lat: float


class ChangeDetectionRequest(BaseModel):
    image_id_before: str = Field(..., description="Image ID of the earlier capture")
    image_id_after: str = Field(..., description="Image ID of the later capture")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Change probability threshold")


class ChangeDetectionResult(BaseModel):
    id: str = Field(default_factory=_uuid4_str)
    image_id_before: str
    image_id_after: str
    change_mask_s3_key: str = Field(..., description="S3 key for the binary change mask (GeoTIFF)")
    change_mask_png_s3_key: str = Field(default="", description="S3 key for a PNG preview of the mask")
    change_percentage: float = Field(..., description="Percentage of image area flagged as changed")
    changed_regions: List[ChangedRegion] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Mean model confidence across changed pixels")
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchFilters(BaseModel):
    """Optional filters applied during vector search."""
    capture_date_from: Optional[datetime] = None
    capture_date_to: Optional[datetime] = None
    bbox: Optional[BoundingBox] = None
    min_resolution_m: Optional[float] = None
    max_resolution_m: Optional[float] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language search query")
    top_k: int = Field(default=10, ge=1, le=100)
    filters: Optional[SearchFilters] = None


class SearchResult(BaseModel):
    image_id: str
    score: float
    metadata: ImageMetadata
    snippet: str = Field(default="", description="Short text snippet explaining relevance")


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportSection(BaseModel):
    heading: str
    body: str
    figures: List[str] = Field(default_factory=list, description="S3 keys of referenced figures/maps")


class ReportRequest(BaseModel):
    analysis_id: str = Field(..., description="ID of the analysis to report on")
    include_context: bool = Field(default=True, description="Whether to enrich the report with RAG context")


class Report(BaseModel):
    id: str = Field(default_factory=_uuid4_str)
    analysis_id: str
    title: str
    summary: str = Field(..., description="Executive summary")
    sections: List[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    s3_key_md: str = Field(default="", description="S3 key for Markdown report")
    s3_key_pdf: str = Field(default="", description="S3 key for PDF report")


# ---------------------------------------------------------------------------
# Analysis records (generic wrapper)
# ---------------------------------------------------------------------------

class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisType(str, Enum):
    CHANGE_DETECTION = "change_detection"
    EMBEDDING_GENERATION = "embedding_generation"
    REPORT_GENERATION = "report_generation"


class AnalysisRecord(BaseModel):
    id: str = Field(default_factory=_uuid4_str)
    type: AnalysisType
    status: AnalysisStatus = AnalysisStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
