"""FastAPI router for change detection analysis.

Delegates heavy lifting to ChangeDetectionService initialised during
application lifespan.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.models.schemas import (
    AnalysisRecord,
    AnalysisStatus,
    AnalysisType,
    ChangeDetectionRequest,
    ChangeDetectionResult,
)

router = APIRouter()

# In-memory record store (swap for a real DB in production)
_analysis_store: dict[str, AnalysisRecord] = {}


@router.post(
    "/change-detection",
    response_model=AnalysisRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Run change detection between two images",
)
async def create_change_detection(req: ChangeDetectionRequest) -> AnalysisRecord:
    from app.main import get_detection_service, get_s3_service

    s3 = get_s3_service()
    detection = get_detection_service()

    # Look up image metadata
    images = await s3.list_images(limit=1000)
    meta_map = {img.id: img for img in images}

    if req.image_id_before not in meta_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Before image not found")
    if req.image_id_after not in meta_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="After image not found")

    record = AnalysisRecord(type=AnalysisType.CHANGE_DETECTION, status=AnalysisStatus.RUNNING)
    _analysis_store[record.id] = record

    try:
        result = await detection.detect_changes(
            meta_map[req.image_id_before],
            meta_map[req.image_id_after],
            threshold=req.threshold,
        )
        record.status = AnalysisStatus.COMPLETED
        record.updated_at = datetime.utcnow()
        record.result = result.model_dump()
    except Exception as exc:
        record.status = AnalysisStatus.FAILED
        record.updated_at = datetime.utcnow()
        record.error = str(exc)

    return record


@router.get("/{analysis_id}", response_model=AnalysisRecord, summary="Get analysis status and results")
async def get_analysis(analysis_id: str) -> AnalysisRecord:
    if analysis_id not in _analysis_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return _analysis_store[analysis_id]


@router.get("/", response_model=List[AnalysisRecord], summary="List analyses")
async def list_analyses(
    status_filter: Optional[AnalysisStatus] = Query(None, alias="status"),
    analysis_type: Optional[AnalysisType] = Query(None, alias="type"),
) -> List[AnalysisRecord]:
    results = list(_analysis_store.values())
    if status_filter:
        results = [r for r in results if r.status == status_filter]
    if analysis_type:
        results = [r for r in results if r.type == analysis_type]
    return results
