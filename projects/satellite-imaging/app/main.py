"""FastAPI application entry point for the Satellite Vision Intelligence Platform.

Provides:
- Lifespan handler that initialises S3, Qdrant and model resources on startup.
- CORS middleware.
- Router registration for images, analysis, search, and reports.
- Health-check endpoint.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import aioboto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient

from config import settings
from app.services.detection import ChangeDetectionService
from app.services.embeddings import EmbeddingService
from app.services.s3 import S3Service
from app.services.vectordb import VectorDBService
from app.services.rag import RAGPipeline
from app.services.report import ReportService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared application state — populated during lifespan startup
# ---------------------------------------------------------------------------
_state: Dict[str, Any] = {}


def get_s3_service() -> S3Service:
    return _state["s3"]


def get_vectordb_service() -> VectorDBService:
    return _state["vectordb"]


def get_detection_service() -> ChangeDetectionService:
    return _state["detection"]


def get_embedding_service() -> EmbeddingService:
    return _state["embeddings"]


def get_rag_pipeline() -> RAGPipeline:
    return _state["rag"]


def get_report_service() -> ReportService:
    return _state["report"]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup; tear them down on shutdown."""

    logger.info("Starting Satellite Vision Intelligence Platform ...")

    # --- S3 ------------------------------------------------------------------
    session = aioboto3.Session()
    s3_kwargs: Dict[str, Any] = {
        "region_name": settings.s3.region,
    }
    if settings.s3.endpoint_url:
        s3_kwargs["endpoint_url"] = settings.s3.endpoint_url
    if settings.s3.access_key_id:
        s3_kwargs["aws_access_key_id"] = settings.s3.access_key_id
        s3_kwargs["aws_secret_access_key"] = settings.s3.secret_access_key

    s3_client_ctx = session.client("s3", **s3_kwargs)
    s3_client = await s3_client_ctx.__aenter__()
    s3_service = S3Service(client=s3_client, settings=settings.s3)
    _state["s3"] = s3_service
    logger.info("S3 client initialised (bucket=%s)", settings.s3.bucket)

    # --- Qdrant --------------------------------------------------------------
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant.host,
        port=settings.qdrant.port,
        api_key=settings.qdrant.api_key,
        https=settings.qdrant.https,
    )
    vectordb_service = VectorDBService(client=qdrant_client, settings=settings.qdrant)
    await vectordb_service.init_collections()
    _state["vectordb"] = vectordb_service
    logger.info("Qdrant client initialised (host=%s)", settings.qdrant.host)

    # --- Embedding service ---------------------------------------------------
    embedding_service = EmbeddingService(
        model_settings=settings.model,
        qdrant_settings=settings.qdrant,
        vectordb=vectordb_service,
    )
    _state["embeddings"] = embedding_service
    logger.info("Embedding service ready (device=%s)", settings.model.device)

    # --- Change detection model ----------------------------------------------
    detection_service = ChangeDetectionService(
        model_settings=settings.model,
        s3_service=s3_service,
        embedding_service=embedding_service,
    )
    _state["detection"] = detection_service
    logger.info("Change detection service ready")

    # --- RAG pipeline --------------------------------------------------------
    rag_pipeline = RAGPipeline(
        vectordb=vectordb_service,
        embedding_service=embedding_service,
        llm_settings=settings.llm,
    )
    _state["rag"] = rag_pipeline

    # --- Report service ------------------------------------------------------
    report_service = ReportService(
        s3_service=s3_service,
        rag_pipeline=rag_pipeline,
        llm_settings=settings.llm,
    )
    _state["report"] = report_service
    logger.info("All services initialised — ready to serve requests.")

    yield  # ---- application runs here ----

    # --- Shutdown ------------------------------------------------------------
    logger.info("Shutting down ...")
    await qdrant_client.close()
    await s3_client_ctx.__aexit__(None, None, None)
    _state.clear()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title=settings.api.title,
        version=settings.api.version,
        lifespan=lifespan,
    )

    # -- CORS -----------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Routers --------------------------------------------------------------
    from app.routers import images, analysis, search, reports  # noqa: local import to avoid circular deps

    app.include_router(images.router, prefix="/api/v1/images", tags=["images"])
    app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])

    # -- Health check ---------------------------------------------------------
    @app.get("/health", tags=["system"])
    async def health_check() -> Dict[str, str]:
        return {
            "status": "healthy",
            "version": settings.api.version,
        }

    return app


app = create_app()
