"""
Satellite Vision Intelligence Platform — API Integration Tests
================================================================
Tests for the FastAPI endpoints: upload, change detection, search, and reports.
Run with:  pytest tests/test_api.py -v
"""

import io
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# We import the FastAPI app lazily inside the fixture so that missing
# optional dependencies (torch, etc.) don't blow up collection.
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Provide safe default settings for testing."""
    return {
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": 6333,
        "S3_ENDPOINT_URL": "http://localhost:4566",
        "S3_BUCKET_NAME": "test-bucket",
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "ANTHROPIC_MODEL": "claude-sonnet-4-20250514",
    }


@pytest.fixture
def app(mock_settings):
    """
    Create a FastAPI TestClient with mocked service dependencies.
    We patch heavy services (S3, Qdrant, model inference) so tests
    run quickly without GPU or network access.
    """
    with (
        patch("app.services.storage.S3Client") as MockS3,
        patch("app.services.vector_db.QdrantService") as MockQdrant,
        patch("app.services.detection.ChangeDetectionService") as MockDetection,
        patch("app.services.embeddings.EmbeddingService") as MockEmbedding,
        patch("app.services.report.ReportService") as MockReport,
    ):
        # Configure mock return values
        MockS3.return_value.upload = AsyncMock(return_value="s3://test-bucket/images/test.tif")
        MockS3.return_value.generate_presigned_url = AsyncMock(
            return_value="https://localhost:4566/test-bucket/images/test.tif?signed=1"
        )

        MockQdrant.return_value.search = AsyncMock(return_value=[
            {"id": "img-001", "score": 0.95, "metadata": {"filename": "scene_a.tif"}},
            {"id": "img-002", "score": 0.88, "metadata": {"filename": "scene_b.tif"}},
        ])
        MockQdrant.return_value.upsert = AsyncMock(return_value=True)

        MockDetection.return_value.detect = AsyncMock(return_value={
            "change_mask_url": "s3://test-bucket/masks/change_001.png",
            "statistics": {
                "total_pixels": 65536,
                "changed_pixels": 4200,
                "change_percentage": 6.41,
                "categories": {"vegetation_loss": 2100, "new_construction": 1500, "water_change": 600},
            },
        })

        MockEmbedding.return_value.embed_image = AsyncMock(
            return_value=np.random.rand(384).tolist()
        )

        MockReport.return_value.generate = AsyncMock(return_value={
            "report_url": "s3://test-bucket/reports/report_001.pdf",
            "summary": "Detected 6.41% land cover change in the region.",
        })

        from app.main import app as fastapi_app

        client = TestClient(fastapi_app)
        yield client


# ===========================================================================
# Helper: create a fake GeoTIFF-like upload payload
# ===========================================================================

def _make_fake_tiff(width: int = 64, height: int = 64, bands: int = 3) -> io.BytesIO:
    """Return a BytesIO that pretends to be a GeoTIFF (just random bytes)."""
    rng = np.random.default_rng(42)
    data = rng.integers(0, 255, size=(bands, height, width), dtype=np.uint8)
    buf = io.BytesIO(data.tobytes())
    buf.name = "test_scene.tif"
    buf.seek(0)
    return buf


# ===========================================================================
# 1. Image Upload
# ===========================================================================

class TestImageUpload:
    """Tests for POST /api/v1/images/upload"""

    def test_upload_success(self, app):
        buf = _make_fake_tiff()
        response = app.post(
            "/api/v1/images/upload",
            files={"file": ("test_scene.tif", buf, "image/tiff")},
            data={"metadata": '{"region": "amazon", "date": "2025-06-15"}'},
        )
        assert response.status_code == 200
        body = response.json()
        assert "image_id" in body
        assert "s3_url" in body

    def test_upload_missing_file(self, app):
        response = app.post("/api/v1/images/upload")
        assert response.status_code == 422  # Unprocessable Entity

    def test_upload_invalid_format(self, app):
        buf = io.BytesIO(b"this is not a tiff")
        response = app.post(
            "/api/v1/images/upload",
            files={"file": ("bad.txt", buf, "text/plain")},
        )
        # Expect 400 or 415 depending on validation implementation
        assert response.status_code in (400, 415, 422)


# ===========================================================================
# 2. Change Detection
# ===========================================================================

class TestChangeDetection:
    """Tests for POST /api/v1/detection/change"""

    def test_change_detection_success(self, app):
        response = app.post(
            "/api/v1/detection/change",
            json={
                "image_before_id": "img-001",
                "image_after_id": "img-002",
                "threshold": 0.3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "change_mask_url" in body
        assert "statistics" in body
        stats = body["statistics"]
        assert "change_percentage" in stats
        assert 0.0 <= stats["change_percentage"] <= 100.0

    def test_change_detection_missing_images(self, app):
        response = app.post(
            "/api/v1/detection/change",
            json={"image_before_id": "img-001"},
        )
        assert response.status_code == 422

    def test_change_detection_invalid_threshold(self, app):
        response = app.post(
            "/api/v1/detection/change",
            json={
                "image_before_id": "img-001",
                "image_after_id": "img-002",
                "threshold": 5.0,  # should be 0-1
            },
        )
        assert response.status_code in (400, 422)


# ===========================================================================
# 3. Search Endpoints
# ===========================================================================

class TestSearch:
    """Tests for GET/POST /api/v1/search"""

    def test_vector_search(self, app):
        response = app.post(
            "/api/v1/search/similar",
            json={"image_id": "img-001", "top_k": 5},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert isinstance(results, list)
        assert len(results) <= 5

    def test_text_search(self, app):
        response = app.post(
            "/api/v1/search/text",
            json={"query": "deforestation near river", "top_k": 3},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert isinstance(results, list)

    def test_search_empty_query(self, app):
        response = app.post(
            "/api/v1/search/text",
            json={"query": "", "top_k": 3},
        )
        assert response.status_code in (400, 422)


# ===========================================================================
# 4. Report Generation
# ===========================================================================

class TestReportGeneration:
    """Tests for POST /api/v1/reports/generate"""

    def test_generate_report_success(self, app):
        response = app.post(
            "/api/v1/reports/generate",
            json={
                "detection_id": "det-001",
                "include_summary": True,
                "format": "pdf",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "report_url" in body
        assert "summary" in body

    def test_generate_report_missing_detection(self, app):
        response = app.post(
            "/api/v1/reports/generate",
            json={},
        )
        assert response.status_code == 422

    def test_generate_report_invalid_format(self, app):
        response = app.post(
            "/api/v1/reports/generate",
            json={
                "detection_id": "det-001",
                "format": "docx",  # unsupported
            },
        )
        assert response.status_code in (400, 422)


# ===========================================================================
# 5. Health Check
# ===========================================================================

class TestHealth:
    """Tests for GET /health"""

    def test_health_ok(self, app):
        response = app.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
