"""FastAPI router for semantic search and RAG-powered Q&A.

Delegates to EmbeddingService, VectorDBService, and RAGPipeline.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.models.schemas import (
    ImageMetadata,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Extra schemas for Q&A and image search
# ---------------------------------------------------------------------------


class QARequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class QAResponse(BaseModel):
    question: str
    answer: str
    sources: List[dict]
    num_sources: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/text", response_model=SearchResponse, summary="Semantic text search")
async def text_search(req: SearchRequest) -> SearchResponse:
    from app.main import get_embedding_service, get_vectordb_service
    from config import settings

    embeddings = get_embedding_service()
    vectordb = get_vectordb_service()

    query_vector = embeddings.generate_single_text_embedding(req.query).tolist()

    filters = None
    if req.filters:
        filters = {}
        if req.filters.capture_date_from:
            filters["capture_date_from"] = req.filters.capture_date_from.isoformat()
        if req.filters.capture_date_to:
            filters["capture_date_to"] = req.filters.capture_date_to.isoformat()

    results = await vectordb.search(
        collection=settings.qdrant.collection_text_embeddings,
        query_vector=query_vector,
        top_k=req.top_k,
        filters=filters,
    )

    search_results = []
    for r in results:
        payload = r.get("payload", {})
        meta = ImageMetadata(
            filename=payload.get("filename", "unknown"),
            s3_key=payload.get("s3_key", ""),
        )
        if "image_id" in payload:
            meta.id = payload["image_id"]
        search_results.append(
            SearchResult(
                image_id=payload.get("image_id", str(r["id"])),
                score=r.get("score", 0.0),
                metadata=meta,
                snippet=payload.get("text", ""),
            )
        )

    return SearchResponse(query=req.query, results=search_results, total=len(search_results))


@router.post("/hybrid", response_model=SearchResponse, summary="Hybrid text + image search")
async def hybrid_search(req: SearchRequest) -> SearchResponse:
    from app.main import get_embedding_service, get_vectordb_service

    embeddings = get_embedding_service()
    vectordb = get_vectordb_service()

    text_vector = embeddings.generate_single_text_embedding(req.query).tolist()

    results = await vectordb.hybrid_search(
        text_query_vector=text_vector,
        image_query_vector=None,
        text_weight=0.6,
        image_weight=0.4,
        top_k=req.top_k,
    )

    search_results = []
    for r in results:
        payload = r.get("payload", {})
        meta = ImageMetadata(
            filename=payload.get("filename", "unknown"),
            s3_key=payload.get("s3_key", ""),
        )
        if "image_id" in payload:
            meta.id = payload["image_id"]
        search_results.append(
            SearchResult(
                image_id=payload.get("image_id", str(r["id"])),
                score=r.get("score", 0.0),
                metadata=meta,
                snippet=payload.get("text", ""),
            )
        )

    return SearchResponse(query=req.query, results=search_results, total=len(search_results))


@router.post("/qa", response_model=QAResponse, summary="RAG-powered Q&A about imagery")
async def question_answer(req: QARequest) -> QAResponse:
    from app.main import get_rag_pipeline

    rag = get_rag_pipeline()
    result = await rag.query(req.question, top_k=req.top_k)

    return QAResponse(
        question=req.question,
        answer=result["answer"],
        sources=result["context_items"],
        num_sources=result["num_context_items"],
    )
