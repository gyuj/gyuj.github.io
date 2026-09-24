"""Central configuration for the Satellite Vision Intelligence Platform.

Uses pydantic-settings for environment-variable-driven configuration
with sensible defaults for local development.
"""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class S3Settings(BaseSettings):
    """AWS S3 storage configuration."""

    model_config = SettingsConfigDict(env_prefix="S3_")

    bucket: str = Field(default="satellite-vision-data", description="Primary S3 bucket name")
    region: str = Field(default="us-east-1", description="AWS region")
    endpoint_url: str | None = Field(default=None, description="Custom endpoint for S3-compatible stores (e.g. MinIO)")
    access_key_id: str | None = Field(default=None, description="AWS access key (falls back to env chain)")
    secret_access_key: str | None = Field(default=None, description="AWS secret key (falls back to env chain)")

    prefix_raw: str = Field(default="raw/", description="Prefix for raw uploaded imagery")
    prefix_processed: str = Field(default="processed/", description="Prefix for processed outputs")
    prefix_tiles: str = Field(default="tiles/", description="Prefix for image tile cache")
    prefix_embeddings: str = Field(default="embeddings/", description="Prefix for serialised embeddings")
    prefix_reports: str = Field(default="reports/", description="Prefix for generated reports")

    presigned_url_expiry: int = Field(default=3600, description="Presigned URL expiry in seconds")


class QdrantSettings(BaseSettings):
    """Qdrant vector database configuration."""

    model_config = SettingsConfigDict(env_prefix="QDRANT_")

    host: str = Field(default="localhost", description="Qdrant server host")
    port: int = Field(default=6333, description="Qdrant REST port")
    grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    api_key: str | None = Field(default=None, description="Qdrant API key (cloud deployments)")
    https: bool = Field(default=False, description="Use HTTPS for Qdrant connection")

    collection_image_embeddings: str = Field(
        default="satellite_image_embeddings",
        description="Collection name for image tile embeddings",
    )
    collection_text_embeddings: str = Field(
        default="satellite_text_embeddings",
        description="Collection name for text / analysis embeddings",
    )
    image_embedding_dim: int = Field(default=768, description="Dimensionality of Prithvi image embeddings")
    text_embedding_dim: int = Field(default=384, description="Dimensionality of sentence-transformer text embeddings")


class ModelSettings(BaseSettings):
    """Computer-vision model configuration."""

    model_config = SettingsConfigDict(env_prefix="MODEL_")

    prithvi_model_path: str = Field(
        default="ibm-nasa-geospatial/Prithvi-100M",
        description="HuggingFace model ID or local path for the Prithvi foundation model",
    )
    device: str = Field(default="cpu", description="Torch device (cpu | cuda | mps)")
    batch_size: int = Field(default=8, description="Inference batch size for tiling")
    tile_size: int = Field(default=224, description="Tile height/width in pixels")
    tile_overlap: int = Field(default=32, description="Overlap between adjacent tiles in pixels")
    change_threshold: float = Field(
        default=0.5,
        description="Default probability threshold for binary change mask",
    )
    num_workers: int = Field(default=4, description="DataLoader workers for tile batching")


class LLMSettings(BaseSettings):
    """LLM / Claude API configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    model_name: str = Field(default="claude-sonnet-4-20250514", description="Claude model to use for RAG / reports")
    max_tokens: int = Field(default=4096, description="Max tokens for LLM generation")
    temperature: float = Field(default=0.3, description="Sampling temperature")


class APISettings(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8000, description="Bind port")
    debug: bool = Field(default=False, description="Enable debug mode")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins",
    )
    title: str = Field(default="Satellite Vision Intelligence Platform")
    version: str = Field(default="0.1.0")


class Settings(BaseSettings):
    """Top-level settings aggregator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    s3: S3Settings = Field(default_factory=S3Settings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    api: APISettings = Field(default_factory=APISettings)


# Module-level singleton – import this everywhere.
settings = Settings()
