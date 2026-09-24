# Satellite Vision Intelligence Platform

A multimodal computer-vision system for satellite image change detection, combining NASA/IBM's Prithvi vision foundation model with an S3-backed image repository and RAG pipeline for research-grounded analysis. Includes REST API and MCP interfaces for image retrieval, semantic search, model analysis, and automated technical reporting.

## Architecture

```
USER
  │
  ├──────────────────────────────────────┐
  ▼                                      ▼
┌─────────────┐                    ┌───────────┐
│  Streamlit   │ ← Interactive UI  │ MCP Agent │ ← AI agent interface
│  (8501)      │                   │           │
└──────┬──────┘                    └─────┬─────┘
       │                                 │
       └──────────────┬──────────────────┘
                      ▼
               ┌─────────────┐
               │   FastAPI    │  ← REST API (8000)
               │   /api/v1    │
               └──────┬──────┘
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ▼              ▼              ▼
   ┌────────┐   ┌──────────┐   ┌─────────┐
   │ Images │   │ Analysis │   │ Search  │
   │ Router │   │ Router   │   │ Router  │
   └───┬────┘   └────┬─────┘   └────┬────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────┐
│              Service Layer                   │
│                                              │
│  S3Service     ChangeDetectionService        │
│  EmbeddingService   VectorDBService          │
│  RAGPipeline        ReportService            │
└──────────────────────┬──────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌──────────┐
   │  AWS S3  │   │ Qdrant  │   │  Claude  │
   │ (images, │   │ (vector │   │  (RAG,   │
   │  reports)│   │  search)│   │  reports)│
   └─────────┘   └─────────┘   └──────────┘
                       │
                  ┌────┴─────┐
                  │  Prithvi │  ← NASA/IBM geospatial
                  │  (PyTorch)│    foundation model
                  └──────────┘
```

### MCP Agent Tools

```
      MCP Server (stdio transport)
            │
            ▼
      ┌───────────┐
      │  6 Tools  │
      └─────┬─────┘
            │
  ┌─────────┼──────────┬──────────────┐
  ▼         ▼          ▼              ▼
Search   Detect    Analyze        Research
Images   Changes   Results     (RAG Q&A + Reports)
```

- **search_satellite_images** — find imagery by location, date, or keyword
- **run_change_detection** — trigger Prithvi-based analysis on image pairs
- **get_analysis_results** — retrieve change maps and statistics
- **semantic_search** — vector search across imagery and analysis records
- **generate_report** — create structured technical reports via Claude
- **ask_question** — RAG-powered Q&A grounded in retrieved context

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Streamlit | Interactive UI — upload, visualize, search, chat |
| Backend API | FastAPI | Async REST API with OpenAPI docs |
| Change Detection | PyTorch + Prithvi (ibm-nasa-geospatial/Prithvi-100M) | Vision foundation model for multi-spectral satellite imagery |
| Embeddings | Prithvi (image) + sentence-transformers/all-MiniLM-L6-v2 (text) | Dual embedding pipeline for hybrid search |
| Vector DB | Qdrant | Semantic search, hybrid retrieval, ANN indexing |
| LLM | Claude (Anthropic API) | RAG answers, report generation |
| Storage | AWS S3 (LocalStack for dev) | Raw imagery, processed outputs, tiles, reports |
| Agent Interface | MCP (Model Context Protocol) | Standardized tool interface for AI agents |
| Infrastructure | Docker Compose | Local dev stack (API + Streamlit + Qdrant + LocalStack) |

## Project Structure

```
satellite-imaging/
├── config.py                        # Pydantic-settings config
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Multi-stage build with GDAL
├── docker-compose.yml               # Full stack (API, Streamlit, Qdrant, LocalStack)
├── .env.example                     # Environment variable template
│
├── app/
│   ├── main.py                      # FastAPI entry point with lifespan init
│   ├── streamlit_app.py             # 5-page Streamlit UI
│   │
│   ├── models/
│   │   └── schemas.py               # Pydantic models
│   │
│   ├── routers/
│   │   ├── images.py                # POST/GET/DELETE /api/v1/images
│   │   ├── analysis.py              # POST/GET /api/v1/analysis
│   │   ├── search.py                # POST /api/v1/search (text, image, hybrid, QA)
│   │   └── reports.py               # POST/GET /api/v1/reports
│   │
│   ├── services/
│   │   ├── s3.py                    # Async S3 client (aioboto3)
│   │   ├── detection.py             # Prithvi change detection pipeline
│   │   ├── embeddings.py            # Image + text embedding generation
│   │   ├── vectordb.py              # Qdrant client with hybrid search
│   │   ├── rag.py                   # RAG pipeline (retrieve → augment → generate)
│   │   └── report.py                # Technical report generation (Markdown + PDF)
│   │
│   └── mcp/
│       └── server.py                # MCP server with 6 tools
│
├── tests/
│   ├── test_api.py                  # Integration tests
│   └── test_detection.py            # Unit tests for detection pipeline
│
└── study/
    └── architecture-notes.md        # Lecture-style architecture & learning notes
```

## Pipeline

```
1. INGEST          Upload GeoTIFF → extract metadata (bands, CRS, bbox) → store in S3
                   │
2. EMBED & INDEX   Generate Prithvi image embeddings → store in Qdrant with metadata
                   │
3. DETECT          Select image pair → tile (224x224) → Prithvi inference →
                   stitch → threshold → binary change mask + statistics
                   │
4. SEARCH          Text/image/hybrid query → Qdrant ANN search → ranked results
                   │
5. RAG + REPORT    Retrieve context from Qdrant → Claude generates grounded analysis →
                   structured technical report (Markdown + PDF) → store in S3
                   │
6. AGENT           MCP server exposes all steps as tools for AI agent access
```

## API Endpoints

### Images
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/images/upload` | Upload GeoTIFF, extract metadata, generate embeddings |
| GET | `/api/v1/images/` | List images with date/bbox/resolution filters |
| GET | `/api/v1/images/{id}` | Get image metadata |
| GET | `/api/v1/images/{id}/preview` | Download RGB preview PNG |
| DELETE | `/api/v1/images/{id}` | Remove image and embeddings |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analysis/change-detection` | Run change detection on image pair |
| GET | `/api/v1/analysis/{id}` | Get analysis status and results |
| GET | `/api/v1/analysis/{id}/change-map` | Download change map PNG |
| GET | `/api/v1/analysis/` | List all analyses |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/search/text` | Semantic text search |
| POST | `/api/v1/search/image` | Image similarity search |
| POST | `/api/v1/search/hybrid` | Combined text + image search |
| POST | `/api/v1/search/qa` | RAG-powered Q&A |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/reports/generate` | Generate technical report for an analysis |
| GET | `/api/v1/reports/{id}` | Get report content |
| GET | `/api/v1/reports/{id}/download` | Download report as PDF |
| GET | `/api/v1/reports/` | List all reports |

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for full stack)
- Anthropic API key (for RAG and report generation)

### Option 1: Docker Compose (recommended)

```bash
# Copy environment template and add your API key
cp .env.example .env

# Start all services
docker compose up -d

# API available at http://localhost:8000
# Streamlit UI at http://localhost:8501
# Qdrant dashboard at http://localhost:6333/dashboard
```

### Option 2: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start Qdrant (needs Docker)
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant

# Start LocalStack for S3
docker run -d -p 4566:4566 -e SERVICES=s3 localstack/localstack

# Set environment variables
export S3_ENDPOINT_URL=http://localhost:4566
export QDRANT_HOST=localhost
export LLM_ANTHROPIC_API_KEY=your-key-here

# Start the API
uvicorn app.main:app --reload --port 8000

# In a separate terminal, start the Streamlit UI
streamlit run app/streamlit_app.py --server.port 8501
```

### MCP Server

```bash
# Run as an MCP server (stdio transport) for AI agent integration
python -m app.mcp.server
```

### Tests

```bash
pytest tests/ -v
```

## Configuration

All configuration is driven by environment variables (see `.env.example`). Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ANTHROPIC_API_KEY` | — | Anthropic API key for Claude |
| `MODEL_PRITHVI_MODEL_PATH` | `ibm-nasa-geospatial/Prithvi-100M` | Prithvi model (HuggingFace ID or local path) |
| `MODEL_DEVICE` | `cpu` | Torch device (`cpu`, `cuda`, `mps`) |
| `MODEL_TILE_SIZE` | `224` | Tile size for image processing |
| `MODEL_CHANGE_THRESHOLD` | `0.5` | Default change detection threshold |
| `S3_BUCKET` | `satellite-vision-data` | S3 bucket name |
| `QDRANT_HOST` | `localhost` | Qdrant server host |

## Learning Notes

See [`study/architecture-notes.md`](study/architecture-notes.md) for comprehensive lecture-style notes covering:
- Tech stack tradeoffs (why FastAPI, Streamlit, PyTorch, Qdrant, S3, MCP)
- Vision foundation models for satellite imagery (Prithvi architecture, change detection)
- RAG pipeline deep dive (embeddings, ANN search, hybrid retrieval, prompt engineering)
- REST API design patterns (async, dependency injection, background tasks)
- MCP protocol explained (tools, resources, transports)
- Cloud architecture and S3 patterns
- Docker and deployment strategies

## Status

In progress
