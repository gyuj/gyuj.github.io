"""Async S3 service for satellite image and artifact storage.

Wraps aioboto3 to provide upload, download, listing, and presigned-URL
generation against the configured bucket and prefix layout.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import S3Settings
from app.models.schemas import ImageMetadata

logger = logging.getLogger(__name__)


class S3Service:
    """Async helper around an aioboto3 S3 client."""

    def __init__(self, client: Any, settings: S3Settings) -> None:
        self._client = client
        self._settings = settings
        self._bucket = settings.bucket

    # ------------------------------------------------------------------
    # Image operations
    # ------------------------------------------------------------------

    async def upload_image(
        self,
        file_bytes: bytes,
        metadata: ImageMetadata,
        content_type: str = "image/tiff",
    ) -> str:
        """Upload a satellite image to S3 under the raw prefix.

        Returns the S3 object key.
        """
        s3_key = f"{self._settings.prefix_raw}{metadata.id}/{metadata.filename}"
        metadata.s3_key = s3_key

        meta_dict = {
            "image_id": metadata.id,
            "filename": metadata.filename,
            "uploaded_at": metadata.uploaded_at.isoformat(),
        }
        if metadata.capture_date:
            meta_dict["capture_date"] = metadata.capture_date.isoformat()
        if metadata.bbox:
            meta_dict["bbox"] = metadata.bbox.model_dump_json()
        if metadata.resolution_m is not None:
            meta_dict["resolution_m"] = str(metadata.resolution_m)
        if metadata.bands:
            meta_dict["bands"] = ",".join(metadata.bands)

        await self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            Metadata=meta_dict,
        )

        # Store a sidecar JSON with full metadata
        sidecar_key = f"{self._settings.prefix_raw}{metadata.id}/metadata.json"
        await self._client.put_object(
            Bucket=self._bucket,
            Key=sidecar_key,
            Body=metadata.model_dump_json(indent=2).encode(),
            ContentType="application/json",
        )

        logger.info("Uploaded image %s -> s3://%s/%s", metadata.id, self._bucket, s3_key)
        return s3_key

    async def download_image(self, s3_key: str) -> bytes:
        """Download an object from S3 and return its bytes."""
        resp = await self._client.get_object(Bucket=self._bucket, Key=s3_key)
        body = await resp["Body"].read()
        return body

    async def list_images(
        self,
        prefix: Optional[str] = None,
        limit: int = 100,
    ) -> List[ImageMetadata]:
        """List image metadata objects under a prefix.

        Reads the sidecar ``metadata.json`` files written during upload.
        """
        search_prefix = prefix or self._settings.prefix_raw
        paginator = self._client.get_paginator("list_objects_v2")

        metadata_keys: List[str] = []
        async for page in paginator.paginate(
            Bucket=self._bucket,
            Prefix=search_prefix,
            PaginationConfig={"MaxItems": limit * 2},
        ):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith("metadata.json"):
                    metadata_keys.append(obj["Key"])
                    if len(metadata_keys) >= limit:
                        break
            if len(metadata_keys) >= limit:
                break

        results: List[ImageMetadata] = []
        for key in metadata_keys:
            try:
                raw = await self.download_image(key)
                results.append(ImageMetadata.model_validate_json(raw))
            except Exception:
                logger.warning("Failed to parse metadata from %s", key, exc_info=True)

        return results

    # ------------------------------------------------------------------
    # Artifact operations (processed masks, reports, etc.)
    # ------------------------------------------------------------------

    async def upload_artifact(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
        extra_metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload a generic artifact (change mask, report, etc.) and return its key."""
        kwargs: Dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if extra_metadata:
            kwargs["Metadata"] = extra_metadata

        await self._client.put_object(**kwargs)
        logger.info("Uploaded artifact -> s3://%s/%s", self._bucket, key)
        return key

    async def upload_json_artifact(self, obj: Any, key: str) -> str:
        """Serialise *obj* to JSON and upload."""
        if hasattr(obj, "model_dump_json"):
            raw = obj.model_dump_json(indent=2).encode()
        else:
            raw = json.dumps(obj, default=str, indent=2).encode()
        return await self.upload_artifact(raw, key, content_type="application/json")

    # ------------------------------------------------------------------
    # Presigned URLs
    # ------------------------------------------------------------------

    async def generate_presigned_url(
        self,
        key: str,
        expiry: Optional[int] = None,
        method: str = "get_object",
    ) -> str:
        """Generate a presigned URL for a given object key."""
        expiry = expiry or self._settings.presigned_url_expiry
        url: str = await self._client.generate_presigned_url(
            ClientMethod=method,
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiry,
        )
        return url

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def object_exists(self, key: str) -> bool:
        """Return True if the object exists in the bucket."""
        try:
            await self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.NoSuchKey:
            return False
        except Exception:
            return False

    async def delete_object(self, key: str) -> None:
        await self._client.delete_object(Bucket=self._bucket, Key=key)
