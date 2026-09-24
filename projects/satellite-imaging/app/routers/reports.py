"""FastAPI router for technical report generation.

Delegates to ReportService initialised during application lifespan.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.models.schemas import Report, ReportRequest

router = APIRouter()

# In-memory store (swap for a real DB in production)
_report_store: dict[str, Report] = {}


@router.post(
    "/generate",
    response_model=Report,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a technical report for an analysis",
)
async def generate_report(req: ReportRequest) -> Report:
    from app.main import get_report_service
    from app.routers.analysis import _analysis_store

    report_svc = get_report_service()

    # Look up the analysis record
    record = _analysis_store.get(req.analysis_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {req.analysis_id} not found.",
        )

    if record.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot generate report for an analysis that is not completed.",
        )

    analysis_result = record.result or {"analysis_id": req.analysis_id}

    report = await report_svc.generate_report(
        analysis_id=req.analysis_id,
        analysis_result=analysis_result,
        include_context=req.include_context,
    )

    _report_store[report.id] = report
    return report


@router.get("/{report_id}", response_model=Report, summary="Get report by ID")
async def get_report(report_id: str) -> Report:
    if report_id not in _report_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return _report_store[report_id]


@router.get("/", response_model=List[Report], summary="List all reports")
async def list_reports(
    analysis_id: Optional[str] = Query(None),
) -> List[Report]:
    results = list(_report_store.values())
    if analysis_id:
        results = [r for r in results if r.analysis_id == analysis_id]
    return results


@router.get("/{report_id}/presigned-urls", summary="Get presigned URLs for report files")
async def get_report_urls(report_id: str) -> dict:
    from app.main import get_s3_service

    if report_id not in _report_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    report = _report_store[report_id]
    s3 = get_s3_service()

    urls = {}
    if report.s3_key_md:
        urls["markdown"] = await s3.generate_presigned_url(report.s3_key_md)
    if report.s3_key_pdf:
        urls["pdf"] = await s3.generate_presigned_url(report.s3_key_pdf)

    return {"report_id": report_id, "urls": urls}
