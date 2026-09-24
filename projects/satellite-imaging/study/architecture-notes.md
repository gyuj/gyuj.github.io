# Satellite Vision Intelligence Platform — Architecture & Learning Notes
## A Graduate-Level Course Reader

> **Purpose**: These notes serve as a comprehensive technical reference for every
> major design decision, algorithm, and infrastructure component in the Satellite
> Vision Intelligence Platform.  They are written in lecture-note style — start
> from first principles, build intuition, then dive into implementation details.

---

## Table of Contents

1. [Why This Tech Stack](#section-1-why-this-tech-stack)
2. [Vision Foundation Models for Satellite Imagery](#section-2-vision-foundation-models-for-satellite-imagery)
3. [RAG Pipeline Deep Dive](#section-3-rag-pipeline-deep-dive)
4. [REST API Design](#section-4-rest-api-design)
5. [MCP (Model Context Protocol)](#section-5-mcp-model-context-protocol)
6. [Cloud Architecture & S3](#section-6-cloud-architecture--s3)
7. [Docker & Deployment](#section-7-docker--deployment)
8. [Resources](#resources)

---

# Section 1: Why This Tech Stack

Every technology choice in a system reflects a set of tradeoffs.  In this section
we justify each major component by comparing it against realistic alternatives,
using concrete criteria: performance, developer experience, ecosystem maturity,
operational cost, and alignment with the problem domain.


## 1.1 Why FastAPI over Flask or Django

### The Landscape

| Criterion               | Flask               | Django              | FastAPI              |
|--------------------------|---------------------|---------------------|----------------------|
| Async support            | Bolt-on (Quart)     | Partial (3.1+)      | Native (ASGI)        |
| Auto-generated API docs  | No (needs Flask-RESTx) | No (needs DRF)   | Yes (OpenAPI/Swagger) |
| Type validation          | Manual              | Serializers (DRF)   | Pydantic (automatic)  |
| Performance (req/s)      | ~2,000              | ~1,800              | ~9,000+              |
| Learning curve           | Low                 | Medium              | Low-Medium           |
| ORM / DB toolkit         | SQLAlchemy (add-on) | Built-in            | SQLAlchemy (add-on)  |

### Why FastAPI Wins for This Project

**1. Async I/O is critical.**  The platform makes concurrent calls to S3, Qdrant,
and the Anthropic API.  In a synchronous framework each call blocks the event
loop.  FastAPI is built on Starlette/ASGI so every endpoint can be `async def`
natively:

```python
@app.post("/api/v1/detection/change")
async def detect_change(request: ChangeRequest):
    # These run concurrently — total wall time is max(t1, t2), not t1 + t2
    image_a, image_b = await asyncio.gather(
        s3.download(request.image_before_id),
        s3.download(request.image_after_id),
    )
    result = await detection_service.detect(image_a, image_b)
    return result
```

**2. Pydantic validation eliminates boilerplate.**  Request and response models
are declared once and FastAPI validates incoming data, generates OpenAPI docs,
and provides IDE autocompletion:

```python
class ChangeRequest(BaseModel):
    image_before_id: str
    image_after_id: str
    threshold: float = Field(ge=0.0, le=1.0, default=0.3)
```

**3. Auto-generated OpenAPI spec.**  The Streamlit frontend and MCP server both
consume the API.  Having an always-up-to-date spec at `/docs` eliminates
documentation drift.

**4. Performance.**  TechEmpower benchmarks show FastAPI (on uvicorn) handling
4-5x more requests per second than Flask for JSON serialization workloads.
For an ML inference API where we want to saturate GPU utilization, this matters.

**When would you NOT choose FastAPI?**
- If you need a batteries-included admin panel (Django wins).
- If your team is deeply invested in Flask extensions.
- If the project is a simple script with 2 endpoints (Flask is simpler to start).


## 1.2 Why Streamlit over React / Next.js

### The Core Tradeoff: Speed-to-Ship vs. UI Polish

Streamlit lets a single Python developer go from zero to interactive dashboard
in hours.  React/Next.js gives pixel-perfect control but requires a JavaScript
toolchain, state management, and a separate build pipeline.

| Criterion                | Streamlit            | React / Next.js      |
|--------------------------|----------------------|----------------------|
| Language                 | Python only          | JS/TS + Python API   |
| Time to first prototype  | Hours                | Days-Weeks           |
| Custom components        | Limited              | Unlimited            |
| Real-time updates        | Polling (re-run)     | WebSockets / SSE     |
| Data-science widgets     | Built-in (charts, maps, dataframes) | Add libraries |
| Production scale         | Moderate             | High                 |
| SEO / SSR               | No                   | Yes (Next.js)        |

**Why Streamlit fits here:**
- The primary users are analysts / researchers, not consumers.
- We need interactive map displays, file uploaders, and result tables —
  all of which Streamlit provides out of the box.
- The entire team writes Python.  Adding a JS build step doubles the
  maintenance surface.
- Streamlit's `st.image()`, `st.map()`, and `st.download_button()` map
  directly to our use cases (display satellite imagery, show change masks,
  download PDF reports).

**When to switch to React:**
- When the product needs custom drag-and-drop annotation tools.
- When there are >1,000 concurrent users (Streamlit's re-run model doesn't
  scale as well).
- When SEO or public landing pages matter.


## 1.3 Why PyTorch over TensorFlow

### Historical Context

TensorFlow (Google, 2015) dominated early deep learning production.  PyTorch
(Meta, 2016) won the research community.  By 2024, the gap has closed — but
ecosystem momentum matters.

| Criterion                  | PyTorch              | TensorFlow           |
|----------------------------|----------------------|----------------------|
| Research paper implementations | ~80% use PyTorch  | ~20%                |
| HuggingFace model hub     | Primary framework    | Secondary            |
| Dynamic computation graph  | Yes (eager by default)| Yes (tf.function)   |
| Production serving         | TorchServe, Triton   | TF Serving, Triton   |
| Mobile deployment          | PyTorch Mobile       | TF Lite (more mature) |
| Debugging                  | Standard Python pdb  | Requires tf.debugging|

**Why PyTorch wins for this project:**

1. **Prithvi is a PyTorch model.**  The NASA/IBM Prithvi foundation model is
   published as PyTorch weights on HuggingFace.  Using TensorFlow would require
   a lossy conversion.

2. **HuggingFace Transformers ecosystem.**  `transformers`, `sentence-transformers`,
   `datasets` — all are PyTorch-first.  Our entire inference pipeline (Prithvi
   for change detection, sentence-transformers for embeddings) lives in this
   ecosystem.

3. **Dynamic graphs simplify debugging.**  When a change detection model
   produces unexpected output, you can drop into pdb and inspect intermediate
   tensors.  This is invaluable during development.

4. **Community momentum.**  If you search for "satellite image change detection
   PyTorch" you will find 10x more tutorials, papers, and pretrained checkpoints
   than the TensorFlow equivalent.


## 1.4 Why Prithvi over Other Models

### What is Prithvi?

Prithvi is a **geospatial foundation model** developed by NASA and IBM.  It is
a Vision Transformer (ViT) pre-trained on Harmonized Landsat Sentinel-2 (HLS)
satellite data using a Masked Autoencoder (MAE) objective.

### Comparison with Alternatives

```
+------------------+----------------+-------------------+---------------------+
| Model            | Pre-training   | Spectral Bands    | Key Advantage       |
|                  | Data           |                   |                     |
+------------------+----------------+-------------------+---------------------+
| Prithvi-100M     | HLS (NASA)     | 6 bands (visible  | Trained on actual   |
|                  |                | + NIR + SWIR)     | satellite data by   |
|                  |                |                   | NASA/IBM            |
+------------------+----------------+-------------------+---------------------+
| SatMAE           | fMoW, SEN12MS  | RGB + multi-spec  | Temporal positional |
|                  |                |                   | encoding            |
+------------------+----------------+-------------------+---------------------+
| SpectralGPT      | Various        | Hyperspectral     | Handles 100+ bands |
+------------------+----------------+-------------------+---------------------+
| ResNet/U-Net     | ImageNet       | RGB only          | Well-understood,    |
| (traditional)    | (natural imgs) |                   | easy to train       |
+------------------+----------------+-------------------+---------------------+
| Random Forest    | N/A            | Any (pixel-level) | No GPU needed,      |
| (classical ML)   |                |                   | interpretable       |
+------------------+----------------+-------------------+---------------------+
```

**Why Prithvi is the best fit:**

1. **Domain-specific pre-training.**  A model trained on ImageNet learned to
   recognize cats, cars, and coffee cups.  Prithvi learned to recognize
   vegetation indices, water bodies, urban sprawl, and cloud shadows — exactly
   what we need.

2. **Multi-spectral awareness.**  Sentinel-2 imagery has 13 spectral bands.
   Prithvi natively consumes 6 of the most informative bands.  A standard
   ResNet expects 3-channel RGB and throws away critical information (Near-IR
   is essential for vegetation health).

3. **Foundation model advantages.**  Pre-training on 1TB+ of satellite data
   means Prithvi has learned general geospatial representations.  Fine-tuning
   for change detection requires far less labeled data than training from
   scratch.

4. **Institutional backing.**  NASA and IBM maintain and improve the model.
   This provides long-term viability and access to domain experts.

**When Prithvi is NOT the right choice:**
- Hyperspectral data (>20 bands): consider SpectralGPT.
- Very high resolution (<1m) commercial imagery: may need models fine-tuned
  on that specific resolution.
- Edge deployment on satellites themselves: need smaller models.


## 1.5 Why Qdrant over Pinecone / Weaviate / Chroma

### Vector Database Comparison

| Criterion          | Qdrant           | Pinecone         | Weaviate         | Chroma           |
|--------------------|------------------|------------------|------------------|------------------|
| Open source        | Yes (Apache 2.0) | No (SaaS only)   | Yes (BSD-3)      | Yes (Apache 2.0) |
| Language           | Rust             | Unknown (managed) | Go               | Python           |
| Payload filtering  | Rich (nested)    | Basic metadata    | GraphQL filters  | Basic            |
| Hybrid search      | Dense + sparse   | Dense only        | Dense + BM25     | Dense only       |
| Performance (1M vectors) | ~5ms p99   | ~10ms p99         | ~8ms p99         | ~15ms p99        |
| Self-hosted        | Yes              | No               | Yes              | Yes              |
| Disk-backed index  | Yes (mmap)       | N/A              | Yes              | No (in-memory)   |
| Production maturity| High             | High             | Medium           | Low              |

**Why Qdrant wins:**

1. **Rust performance.**  Qdrant is written in Rust, giving near-C++ speed with
   memory safety.  For real-time search over satellite metadata embeddings,
   low latency matters.

2. **Rich payload filtering.**  Satellite images have structured metadata
   (coordinates, date, cloud cover, sensor type).  Qdrant's filtering lets us
   combine vector similarity with metadata predicates:

   ```python
   results = await qdrant.search(
       collection_name="satellite_embeddings",
       query_vector=query_embedding,
       query_filter=Filter(
           must=[
               FieldCondition(key="cloud_cover", range=Range(lte=0.2)),
               FieldCondition(key="date", range=Range(gte="2025-01-01")),
           ]
       ),
       limit=10,
   )
   ```

3. **Open source & self-hosted.**  We run Qdrant in our Docker Compose stack.
   No vendor lock-in, no per-query pricing, full data sovereignty.

4. **Hybrid search.**  Combining dense (semantic) and sparse (keyword) vectors
   in a single query improves retrieval quality for geospatial metadata that
   contains both natural language descriptions and technical codes.

**When to choose alternatives:**
- Pinecone: if you want zero infrastructure management and have budget.
- Weaviate: if you need GraphQL-native queries.
- Chroma: for quick prototyping (it is the simplest to start).


## 1.6 Why S3 for Storage

Amazon S3 (Simple Storage Service) is the de facto standard for object storage.
For satellite imagery (files ranging from 50MB to 2GB per scene), S3 offers:

1. **99.999999999% (11 nines) durability.**  You will not lose data.
2. **Cost efficiency.**  ~$0.023/GB/month for standard.  Satellite data
   accumulates fast — lifecycle policies move old data to Glacier ($0.004/GB).
3. **Presigned URLs.**  Let the Streamlit frontend download images directly
   from S3 without proxying through our API.
4. **Multipart upload.**  Large GeoTIFFs can be uploaded in parallel chunks.
5. **Ecosystem integration.**  Every ML tool speaks S3 (rasterio, GDAL,
   PyTorch dataloaders).

For local development we use **LocalStack**, which emulates S3 (and other AWS
services) in a Docker container.  The application code stays identical — only
the endpoint URL changes.


## 1.7 Why RAG over Fine-Tuning

### The Question

We want Claude to answer questions about satellite analysis results grounded in
our data.  Two approaches:

1. **Fine-tune** Claude on our data (not possible with Anthropic's API anyway,
   but conceptually).
2. **RAG**: retrieve relevant context at query time and inject it into the
   prompt.

### Comparison

| Criterion              | RAG                      | Fine-Tuning              |
|------------------------|--------------------------|--------------------------|
| Data freshness         | Real-time (always current)| Stale (needs retraining) |
| Cost                   | Retrieval infra only     | GPU hours for training   |
| Hallucination control  | High (grounded in docs)  | Medium (can still hallucinate) |
| Flexibility            | Change data anytime      | Must retrain             |
| Attribution            | Can cite source docs     | Cannot trace answers     |
| Domain adaptation      | Moderate                 | Strong                   |
| Setup complexity       | Vector DB + embeddings   | Training pipeline        |

**RAG wins because:**
- Our satellite analysis results change constantly (new images every day).
  Fine-tuning would be perpetually stale.
- We NEED citations — when the system says "deforestation increased 12%,"
  analysts must trace that to a specific detection run.
- RAG cost is predictable (embedding + retrieval), whereas fine-tuning
  requires periodic retraining.


## 1.8 Why MCP for the Agent Interface

### What Problem Does MCP Solve?

Before MCP, every AI application that wanted to use tools had to implement
custom function-calling integration.  LangChain, LlamaIndex, and others each
invented their own abstractions.  MCP (Model Context Protocol) is a standard
protocol — like HTTP for AI tool use.

| Criterion          | MCP               | Custom Function Calling | LangChain Tools   |
|--------------------|--------------------|------------------------|-------------------|
| Standardized       | Yes (open spec)    | No                     | No (proprietary)  |
| Transport          | stdio, HTTP/SSE    | HTTP only              | In-process only   |
| Discovery          | Built-in           | Manual                 | Manual            |
| Composability      | First-class        | Ad-hoc                 | Chain-dependent   |
| Multi-model support| Any MCP client     | Model-specific         | LangChain only    |

**Why MCP fits here:**
- Claude Desktop and Claude Code are MCP clients.  By exposing our satellite
  tools as an MCP server, any Claude-based agent can search images, run
  change detection, and generate reports without custom integration.
- The protocol separates tool DEFINITION from tool INVOCATION.  We define
  tools once; any MCP-compatible client can use them.
- Resources (satellite images, reports) and Prompts (analysis templates) are
  first-class concepts in MCP, mapping naturally to our domain.


---

# Section 2: Vision Foundation Models for Satellite Imagery

## 2.1 What Are Foundation Models?

A **foundation model** is a large neural network trained on broad data at scale
such that it can be adapted (fine-tuned) to a wide range of downstream tasks.

```
                    FOUNDATION MODEL PARADIGM

    +---------------------+          +--------------------+
    |   MASSIVE DATASET   |          |  DOWNSTREAM TASK   |
    | (unlabeled or       |          | (labeled, small)   |
    | self-supervised)    |          |                    |
    +----------+----------+          +---------+----------+
               |                               |
               v                               v
    +----------+----------+          +---------+----------+
    |   PRE-TRAINING      |          |   FINE-TUNING      |
    | (learn general      |--------->| (adapt to specific |
    |  representations)   |          |  task)             |
    +---------------------+          +--------------------+
                                               |
                                               v
                                     +---------+----------+
                                     |  TASK-SPECIFIC     |
                                     |  MODEL             |
                                     | (change detection, |
                                     |  segmentation,     |
                                     |  classification)   |
                                     +--------------------+
```

**Key insight:**  Pre-training is expensive (weeks on hundreds of GPUs) but
happens once.  Fine-tuning is cheap (hours on one GPU) and happens many times.
This amortizes the cost of learning general representations.

### The Analogy

Think of pre-training as a medical student learning anatomy, physiology, and
biochemistry over 4 years.  Fine-tuning is the residency — specializing in
cardiology or dermatology.  The foundational knowledge transfers.


## 2.2 Self-Supervised Learning on Satellite Data

Traditional supervised learning requires labeled data:  "this pixel is forest,
this pixel is water."  Labeling satellite imagery is extremely expensive — you
need domain experts examining millions of pixels.

**Self-supervised learning (SSL)** creates labels from the data itself.

### The Masked Autoencoder (MAE) Approach

This is the pre-training strategy used by Prithvi.

```
    MASKED AUTOENCODER (MAE) — Training Process

    Input Image (6 bands, 224x224):
    +--------+--------+--------+--------+
    |  P1    |  P2    |  P3    |  P4    |
    +--------+--------+--------+--------+
    |  P5    |  P6    |  P7    |  P8    |
    +--------+--------+--------+--------+
    |  P9    |  P10   |  P11   |  P12   |
    +--------+--------+--------+--------+
    |  P13   |  P14   |  P15   |  P16   |
    +--------+--------+--------+--------+
                     |
                     v  (mask 75% of patches)
    +--------+--------+--------+--------+
    |  P1    | MASKED |  P3    | MASKED |
    +--------+--------+--------+--------+
    | MASKED | MASKED |  P7    | MASKED |
    +--------+--------+--------+--------+
    | MASKED |  P10   | MASKED | MASKED |
    +--------+--------+--------+--------+
    |  P13   | MASKED | MASKED |  P16   |
    +--------+--------+--------+--------+
                     |
                     v  (encoder processes visible patches)
              +------+------+
              |   ENCODER   |
              |  (ViT)      |
              +------+------+
                     |
                     v  (decoder reconstructs masked patches)
              +------+------+
              |   DECODER   |
              +------+------+
                     |
                     v
    +--------+--------+--------+--------+
    |  P1'   |  P2'   |  P3'   |  P4'   |  <-- reconstructed
    +--------+--------+--------+--------+
    |  P5'   |  P6'   |  P7'   |  P8'   |
    +--------+--------+--------+--------+
    |  P9'   |  P10'  |  P11'  |  P12'  |
    +--------+--------+--------+--------+
    |  P13'  |  P14'  |  P15'  |  P16'  |
    +--------+--------+--------+--------+

    Loss = MSE(original masked patches, reconstructed patches)
```

**Why 75% masking?**  If you only mask 10%, the model can interpolate from
neighboring patches without understanding semantics.  At 75%, the model MUST
learn the structure of satellite scenes — "if I see a river bank on the left,
the adjacent patch probably contains water or riparian vegetation."

**What the model learns:**
- Spectral relationships (vegetation has high NIR reflectance)
- Spatial patterns (roads are linear, forests are textured, water is smooth)
- Temporal dynamics (if given multi-temporal input, seasonal changes)

After pre-training, the ENCODER has learned rich representations.  The decoder
is thrown away.  The encoder becomes the foundation for downstream tasks.


## 2.3 Prithvi Architecture

```
    PRITHVI-100M ARCHITECTURE

    Input: (B, T, C, H, W)
           B = batch size
           T = temporal frames (1-3)
           C = 6 spectral bands (Blue, Green, Red, NIR, SWIR1, SWIR2)
           H, W = 224 x 224 pixels

    +--------------------------------------------------+
    |            Patch Embedding Layer                   |
    |  (C x patch_size x patch_size) --> D-dimensional  |
    |  patch_size = 16, D = 768                         |
    +--------------------------------------------------+
                           |
                           v
    +--------------------------------------------------+
    | Positional Encoding (spatial + temporal)           |
    | - 2D sinusoidal for spatial position              |
    | - Learned embeddings for temporal position        |
    +--------------------------------------------------+
                           |
                           v
    +--------------------------------------------------+
    |         Transformer Encoder (12 layers)            |
    |                                                    |
    |  For each layer:                                   |
    |    1. Multi-Head Self-Attention (12 heads)         |
    |       - each patch attends to every other patch   |
    |    2. Layer Normalization                          |
    |    3. MLP (Feed-Forward Network)                  |
    |       - 768 --> 3072 --> 768                      |
    |    4. Layer Normalization                          |
    |    5. Residual connections                         |
    +--------------------------------------------------+
                           |
                           v
    +--------------------------------------------------+
    |              Output Embeddings                     |
    |  (num_patches, 768) per image                     |
    |  These are the "foundation" representations       |
    +--------------------------------------------------+
```

**Key architectural decisions:**

1. **Multi-spectral patch embedding.**  Instead of 3-channel (RGB) Conv2d,
   Prithvi uses a 6-channel Conv2d as the patch embedding layer.  This
   preserves all spectral information.

2. **Temporal awareness.**  Prithvi can accept multiple time steps as input.
   Temporal positional encodings let the model understand "this is January,
   this is July" — critical for distinguishing seasonal change from real
   land-cover change.

3. **100M parameters.**  Relatively modest by LLM standards (GPT-3 has 175B),
   but appropriate for the information density of satellite patches.  Larger
   isn't always better when data diversity is limited.


## 2.4 How Change Detection Works with Foundation Models

### The Siamese Approach

For change detection, we process two images (before and after) through the
same encoder and compare the resulting feature maps.

```
    CHANGE DETECTION PIPELINE

    Image (t1)                    Image (t2)
    +----------+                  +----------+
    |          |                  |          |
    | Before   |                  | After    |
    |          |                  |          |
    +-----+----+                  +-----+----+
          |                             |
          v                             v
    +-----+----+                  +-----+----+
    | Prithvi  |                  | Prithvi  |   <-- shared weights
    | Encoder  |                  | Encoder  |       (siamese)
    +-----+----+                  +-----+----+
          |                             |
          v                             v
    Features (t1)                 Features (t2)
    [f1, f2, ..., fn]            [g1, g2, ..., gn]
          |                             |
          +----------+   +--------------+
                     |   |
                     v   v
              +------+---+------+
              | Feature          |
              | Differencing     |
              | |fi - gi|        |
              +------+-----------+
                     |
                     v
              +------+-----------+
              | Change Detection |
              | Head (MLP)       |
              | --> per-pixel    |
              | change probability|
              +------+-----------+
                     |
                     v
              +------+-----------+
              | Threshold &      |
              | Post-processing  |
              +-----------------+
                     |
                     v
              Binary Change Mask
```

**Feature differencing:**  The simplest approach computes the L2 distance
between feature vectors at each spatial position.  More sophisticated
approaches concatenate the features and learn the comparison:

```python
# Simple differencing
diff = torch.abs(features_t1 - features_t2)  # (B, D, H', W')

# Learned comparison (more parameters, often better)
combined = torch.cat([features_t1, features_t2, features_t1 - features_t2], dim=1)
change_logits = change_head(combined)  # (B, 1, H', W')
change_probs = torch.sigmoid(change_logits)
```

**Why foundation models beat traditional approaches:**
- Traditional pixel-differencing is noisy (illumination changes, sensor drift,
  atmospheric effects all trigger false positives).
- Foundation model features are SEMANTIC — they capture "this is a building"
  vs "this is bare soil" rather than "this pixel is bright."
- This dramatically reduces false positives from seasonal variation, cloud
  shadows, and registration errors.


## 2.5 Model Comparison for Satellite Change Detection

```
+-------------------+-------------+-----------+--------+-------------------+
| Method            | F1 Score    | Training  | GPU    | Requires Labeled  |
|                   | (benchmark) | Data Need | Memory | Change Pairs?     |
+-------------------+-------------+-----------+--------+-------------------+
| Pixel Differencing|   0.55      | None      | 0      | No                |
| Random Forest     |   0.65      | Small     | 0      | Yes (pixels)      |
| U-Net (scratch)   |   0.78      | Large     | 8 GB   | Yes (masks)       |
| U-Net (ImageNet)  |   0.82      | Medium    | 8 GB   | Yes (masks)       |
| Prithvi (fine-tuned)| 0.88     | Small     | 16 GB  | Yes (few-shot OK) |
| SatMAE (fine-tuned)|  0.86     | Small     | 16 GB  | Yes (few-shot OK) |
+-------------------+-------------+-----------+--------+-------------------+
```

*Benchmark values are approximate and based on published results on the
LEVIR-CD and xBD datasets.*

The foundation model approaches (Prithvi, SatMAE) achieve the highest accuracy
with the smallest fine-tuning dataset, because they leverage pre-training on
millions of satellite scenes.


## 2.6 Transfer Learning and Domain Adaptation

### The Freezing Strategy

When fine-tuning Prithvi for change detection, we have a choice:

```
    Layer Freezing Strategies

    STRATEGY A: Freeze encoder, train head only (few-shot, fast)
    +------------------+
    | Encoder (frozen)  |  <-- weights fixed from pre-training
    +------------------+
    | Change Head       |  <-- trained on your labeled data
    +------------------+

    STRATEGY B: Fine-tune everything (more data needed, best results)
    +------------------+
    | Encoder (unfrozen)|  <-- weights updated with small learning rate
    +------------------+
    | Change Head       |  <-- trained with normal learning rate
    +------------------+

    STRATEGY C: Progressive unfreezing (balance)
    Epoch 1-5:   freeze encoder, train head
    Epoch 6-10:  unfreeze last 4 encoder layers
    Epoch 11-15: unfreeze all layers with discriminative learning rates
```

**Practical advice:**
- Start with Strategy A.  If accuracy is sufficient, stop — you get fast
  training and less risk of catastrophic forgetting.
- If accuracy plateaus, move to Strategy C.  This is the most robust approach
  for medium-sized datasets (1,000-10,000 image pairs).
- Strategy B only when you have very large labeled datasets (>50,000 pairs)
  and the domain is significantly different from the pre-training data.

### Domain Adaptation Challenges

Prithvi was pre-trained on Harmonized Landsat Sentinel-2 (HLS) data at 30m
resolution.  If your target data is:

- **Same sensor, same resolution (HLS):**  Minimal adaptation needed.
- **Different resolution (e.g., 10m Sentinel-2 native):**  Moderate.  The
  model needs to adjust to finer spatial detail.
- **Different sensor (e.g., Planet 3m RGB):**  Significant.  Missing spectral
  bands means the model loses information it was trained to use.
- **SAR data (radar):**  Major.  Completely different physics.  Consider a
  SAR-specific foundation model instead.


---

# Section 3: RAG Pipeline Deep Dive

## 3.1 Vector Embeddings Explained

### What Is an Embedding?

An embedding is a dense, fixed-length numerical vector that captures the
*meaning* of an input.  Similar inputs produce vectors that are close together
in vector space.

```
    EMBEDDING SPACE (2D projection for illustration)

                         "deforestation in Amazon"
                              *
                    *  "forest loss Brazil"
                              *  "rainforest destruction"



         "urban expansion Delhi"  *
                       * "city growth India"



                                       "flood damage Bangladesh"  *
                                              *  "water level rise"
```

In reality, embedding vectors have hundreds of dimensions (384 for
MiniLM-L6-v2, 768 for larger models).  The key property is that
**semantic similarity maps to geometric proximity**.

### How Embeddings Are Created

**Text embeddings** (sentence-transformers):
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embedding = model.encode("deforestation near river basin")
# --> numpy array of shape (384,)
```

The model is a transformer (BERT variant) trained with a contrastive loss:
- Semantically similar sentence pairs are pushed close together.
- Dissimilar pairs are pushed apart.

**Image embeddings** (for satellite imagery):
```python
# Using Prithvi encoder as feature extractor
features = prithvi_encoder(image_tensor)  # (1, num_patches, 768)
image_embedding = features.mean(dim=1)     # global average pool --> (1, 768)
```

We can also use CLIP-style models that project images and text into the
same embedding space, enabling cross-modal search (search images by text
queries).


## 3.2 How Vector Databases Work

### The Naive Approach

Given a query vector q and a database of N vectors, the brute-force approach
computes the distance from q to every vector:

```
Distance computation: O(N * D)
    where N = number of vectors, D = dimensionality

For N = 10,000,000 and D = 384:
    = 3.84 billion floating-point operations per query
    = ~100ms on modern CPU
    = too slow for interactive search
```

### Approximate Nearest Neighbor (ANN) Search

ANN algorithms trade a small amount of accuracy for massive speed improvements.

#### HNSW (Hierarchical Navigable Small World)

This is the algorithm Qdrant uses.  It's currently the best general-purpose
ANN algorithm.

```
    HNSW — Multi-Layer Graph Structure

    Layer 2 (sparse):     A -------- D -------- G
                          |                     |
    Layer 1 (medium):     A --- B --- D --- F --- G
                          |    |     |    |     |
    Layer 0 (dense):      A - B - C - D - E - F - G - H - I - J
                             (all points present at layer 0)

    Search for query Q:
    1. Enter at Layer 2, start at random entry point A
    2. Greedily move to neighbor closest to Q on Layer 2 --> land on D
    3. Drop to Layer 1, starting at D
    4. Greedily navigate Layer 1 --> land on F
    5. Drop to Layer 0, starting at F
    6. Greedily navigate Layer 0 --> find nearest neighbor E

    Complexity: O(log N) distance computations instead of O(N)
```

**HNSW parameters:**
- **M** (max connections per node): Higher = more accurate, more memory.
  Default: 16.
- **ef_construction** (beam width during build): Higher = better graph quality,
  slower build.  Default: 200.
- **ef_search** (beam width during query): Higher = more accurate, slower
  search.  Default: 128.

**Performance characteristics:**
```
+---------+-------------+-----------+------------------+
| N       | Brute Force | HNSW      | Recall@10        |
+---------+-------------+-----------+------------------+
| 100K    | 5ms         | 0.5ms     | 99.5%            |
| 1M      | 50ms        | 1ms       | 99.2%            |
| 10M     | 500ms       | 3ms       | 98.8%            |
| 100M    | 5,000ms     | 5ms       | 98.5%            |
+---------+-------------+-----------+------------------+
```


## 3.3 The RAG Architecture

```
    RAG PIPELINE — End to End

    User Query: "What deforestation occurred in sector A7 last month?"
          |
          v
    +-----+--------+
    | Query Encoder |
    | (sentence-    |
    |  transformers)|
    +-----+--------+
          |
          v  query embedding (384-dim vector)
    +-----+---------+
    | Vector Search  |
    | (Qdrant)       |   <-- also filters by date, region
    +-----+---------+
          |
          v  top-k relevant documents
    +-----+---------+
    | Context        |
    | Assembly       |
    | - detection    |
    |   results      |
    | - metadata     |
    | - statistics   |
    +-----+---------+
          |
          v  augmented prompt
    +-----+---------+
    | LLM (Claude)   |
    | "Based on the  |
    |  following      |
    |  satellite      |
    |  analysis       |
    |  data..."       |
    +-----+---------+
          |
          v
    Grounded Answer:
    "Based on detection run #DET-2025-0612, sector A7 experienced
     4.2% forest cover loss between June 1-30, primarily in the
     northeast quadrant near coordinates (-3.45, -62.12).  The
     change detection confidence score was 0.87."
```

### Step-by-Step Walkthrough

**1. Query Encoding:**
```python
query = "What deforestation occurred in sector A7 last month?"
query_embedding = embedding_model.encode(query)  # (384,)
```

**2. Retrieval from Qdrant:**
```python
results = await qdrant.search(
    collection_name="satellite_embeddings",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(key="region", match=MatchValue(value="A7")),
            FieldCondition(key="date", range=Range(gte="2025-06-01", lte="2025-06-30")),
        ]
    ),
    limit=5,
)
```

**3. Context Assembly:**
```python
context_chunks = []
for result in results:
    chunk = f"""
    Detection Run: {result.payload['detection_id']}
    Date: {result.payload['date']}
    Region: {result.payload['region']}
    Change Percentage: {result.payload['change_pct']}%
    Categories: {result.payload['categories']}
    Coordinates: {result.payload['bbox']}
    Confidence: {result.payload['confidence']}
    """
    context_chunks.append(chunk)

context = "\n---\n".join(context_chunks)
```

**4. Augmented Prompt to Claude:**
```python
prompt = f"""You are a satellite imagery analyst. Answer the user's question
based ONLY on the following satellite analysis data. If the data doesn't
contain the answer, say so. Always cite detection run IDs.

SATELLITE ANALYSIS DATA:
{context}

USER QUESTION: {query}

ANSWER:"""

response = await anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
)
```


## 3.4 Chunking Strategies for Geospatial Metadata

Unlike RAG for documents (where you chunk paragraphs), geospatial RAG requires
domain-specific chunking:

### Strategy 1: Per-Detection-Run Chunks

Each change detection run becomes one document:
```
{
    "detection_id": "DET-2025-0612-A7",
    "text": "Change detection analysis of sector A7, performed 2025-06-12.
             Detected 4.2% land cover change.  Primary change type:
             deforestation (3.1%) and new construction (1.1%).
             Confidence score: 0.87.",
    "metadata": {
        "date": "2025-06-12",
        "region": "A7",
        "bbox": [-3.5, -62.2, -3.4, -62.1],
        "change_pct": 4.2,
        "sensor": "Sentinel-2"
    }
}
```

### Strategy 2: Temporal Summaries

Aggregate multiple detection runs into weekly/monthly summaries:
```
{
    "summary_id": "SUM-2025-06-A7",
    "text": "Monthly summary for sector A7, June 2025.  12 detection runs
             performed.  Average change: 3.8%.  Trend: increasing.
             Hotspot: northeast quadrant.  Flagged for review.",
    "metadata": { ... }
}
```

### Strategy 3: Spatial Grid Chunks

Divide the study area into a grid; each cell gets its own document with
cumulative change history.

**Best practice:**  Use all three strategies simultaneously.  Retrieval will
surface the most relevant chunks regardless of granularity.


## 3.5 Hybrid Search: Dense + Sparse

**Dense search** (vector similarity) captures semantic meaning but can miss
exact terms.  "HLS scene LC08_L1TP_042034" won't match semantically with
anything — it's a unique identifier.

**Sparse search** (BM25 / keyword matching) finds exact terms but misses
paraphrases.  "deforestation" won't match "forest loss."

**Hybrid search** combines both:

```python
# Qdrant supports named vectors for hybrid search
results = await qdrant.search(
    collection_name="satellite_embeddings",
    query_vector=NamedVector(name="dense", vector=dense_embedding),
    # Qdrant also supports sparse vectors for BM25-style search
    limit=10,
)
```

The scoring formula typically uses Reciprocal Rank Fusion (RRF):

```
RRF_score(doc) = sum over all rankers r:
    1 / (k + rank_r(doc))

where k = 60 (constant to prevent division by small numbers)
```

This gives documents that rank highly in BOTH dense and sparse results a
combined score that is much higher than either alone.


## 3.6 Prompt Engineering for Grounded Generation

### Principles

1. **Explicitly instruct the model to use only provided context.**
   "Answer based ONLY on the following data."

2. **Require citations.**
   "Always reference the detection run ID when making claims."

3. **Define the output format.**
   "Respond with a structured analysis containing: Summary, Key Findings,
   Recommendations."

4. **Handle missing information gracefully.**
   "If the provided data does not contain information to answer the question,
   state that clearly instead of speculating."

### Anti-Hallucination Techniques

```python
SYSTEM_PROMPT = """You are a satellite imagery analyst assistant.

RULES:
1. ONLY use information from the provided SATELLITE ANALYSIS DATA.
2. NEVER invent statistics, coordinates, or detection IDs.
3. If asked about a region or time period not covered by the data,
   respond: "The available data does not cover this region/time period."
4. Always prefix numerical claims with the source detection run ID.
5. Distinguish between high-confidence (>0.8) and low-confidence (<0.8)
   findings explicitly.
"""
```


## 3.7 Evaluation Metrics

### Retrieval Quality

| Metric     | Definition                                           | Target |
|------------|------------------------------------------------------|--------|
| Recall@k   | Fraction of relevant docs in top-k results           | >0.90  |
| MRR        | Mean Reciprocal Rank of first relevant result         | >0.80  |
| NDCG@k     | Normalized Discounted Cumulative Gain                 | >0.85  |
| Precision@k| Fraction of top-k results that are relevant           | >0.70  |

### Generation Quality

| Metric          | How to Measure                                      |
|-----------------|-----------------------------------------------------|
| Faithfulness    | Does the answer contradict the context? (LLM judge) |
| Relevance       | Does the answer address the question? (LLM judge)   |
| Groundedness    | Can every claim be traced to context? (manual)       |
| Completeness    | Were all relevant context chunks used? (overlap)     |

Tools like **RAGAS** automate RAG evaluation using LLM-as-judge.


---

# Section 4: REST API Design

## 4.1 RESTful Principles

REST (Representational State Transfer) is an architectural style, not a
standard.  Key constraints:

1. **Resources are nouns.**  `/images`, `/detections`, `/reports` — not
   `/getImage` or `/runDetection`.

2. **HTTP verbs express actions:**

   | Verb   | Action   | Idempotent | Safe | Example                    |
   |--------|----------|------------|------|----------------------------|
   | GET    | Read     | Yes        | Yes  | GET /api/v1/images/123     |
   | POST   | Create   | No         | No   | POST /api/v1/images/upload |
   | PUT    | Replace  | Yes        | No   | PUT /api/v1/images/123     |
   | PATCH  | Update   | No         | No   | PATCH /api/v1/images/123   |
   | DELETE | Delete   | Yes        | No   | DELETE /api/v1/images/123  |

3. **Status codes convey outcome:**

   | Code | Meaning                | When to Use                     |
   |------|------------------------|---------------------------------|
   | 200  | OK                     | Successful GET, PUT, PATCH      |
   | 201  | Created                | Successful POST that creates    |
   | 202  | Accepted               | Long-running task started       |
   | 204  | No Content             | Successful DELETE               |
   | 400  | Bad Request            | Validation failure              |
   | 401  | Unauthorized           | Missing/invalid auth            |
   | 404  | Not Found              | Resource doesn't exist          |
   | 415  | Unsupported Media Type | Wrong file format               |
   | 422  | Unprocessable Entity   | Semantic validation failure     |
   | 500  | Internal Server Error  | Unexpected crash                |
   | 503  | Service Unavailable    | Dependency down (Qdrant, S3)    |

4. **Stateless.**  Each request carries all information needed to process it
   (no server-side sessions).

### Our API Resource Map

```
    /api/v1/
    +-- images/
    |   +-- POST   /upload          Upload a new satellite image
    |   +-- GET    /{image_id}      Get image metadata
    |   +-- DELETE /{image_id}      Remove image and embeddings
    |
    +-- detection/
    |   +-- POST   /change          Run change detection on two images
    |   +-- GET    /{detection_id}  Get detection results
    |
    +-- search/
    |   +-- POST   /similar         Find similar images (vector search)
    |   +-- POST   /text            Search by text query
    |
    +-- reports/
    |   +-- POST   /generate        Generate PDF report
    |   +-- GET    /{report_id}     Download report
    |
    +-- /health                     Health check
```


## 4.2 FastAPI Dependency Injection

FastAPI's `Depends()` system is one of its most powerful features.  It lets
you declare shared logic (authentication, database connections, service
instances) that gets injected into endpoint functions.

```python
# --- Define dependencies ---

async def get_s3_client() -> S3Client:
    """Lazy-initialized, cached S3 client."""
    client = S3Client(endpoint_url=settings.S3_ENDPOINT_URL)
    try:
        yield client
    finally:
        await client.close()


async def get_qdrant_service() -> QdrantService:
    service = QdrantService(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return service


async def get_detection_service(
    s3: S3Client = Depends(get_s3_client),
    qdrant: QdrantService = Depends(get_qdrant_service),
) -> ChangeDetectionService:
    """Dependencies can depend on other dependencies."""
    return ChangeDetectionService(s3=s3, qdrant=qdrant)


# --- Use in endpoints ---

@app.post("/api/v1/detection/change")
async def detect_change(
    request: ChangeRequest,
    detection: ChangeDetectionService = Depends(get_detection_service),
):
    result = await detection.detect(
        before_id=request.image_before_id,
        after_id=request.image_after_id,
        threshold=request.threshold,
    )
    return result
```

**Why this matters:**
- **Testability:**  In tests, override `get_s3_client` with a mock.
- **Lifecycle management:**  The `yield` pattern ensures cleanup (closing
  connections) even if the endpoint raises an exception.
- **Composition:**  Dependencies compose — `get_detection_service` depends on
  `get_s3_client` and `get_qdrant_service`, building the dependency graph
  automatically.


## 4.3 Async/Await in Python

### The Event Loop

Python's `asyncio` event loop is a single-threaded concurrency mechanism.
It runs one coroutine at a time, switching between them at `await` points.

```
    SYNCHRONOUS vs ASYNCHRONOUS Execution

    Synchronous (blocking):
    +-----------+-----------+-----------+
    | S3 upload | Qdrant    | Claude    |    Total: 3 seconds
    | (1 sec)   | search    | API call  |
    |           | (1 sec)   | (1 sec)   |
    +-----------+-----------+-----------+

    Asynchronous (concurrent):
    +-----------+
    | S3 upload |
    +-----------+
    +-----------+
    | Qdrant    |                            Total: 1 second
    | search    |
    +-----------+
    +-----------+
    | Claude    |
    | API call  |
    +-----------+
```

**When async helps:**  I/O-bound operations (network calls, file reads, database
queries).  Our application makes many such calls per request.

**When async does NOT help:**  CPU-bound operations (model inference, image
processing).  For these, use `run_in_executor` to offload to a thread pool:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=4)

async def run_inference(image: np.ndarray) -> np.ndarray:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        _sync_inference,  # regular function, runs in separate process
        image,
    )
    return result
```

### Common Pitfalls

1. **Blocking the event loop:**
   ```python
   # BAD — blocks all concurrent requests
   @app.get("/process")
   async def process():
       time.sleep(5)      # NEVER do this in an async function
       return {"done": True}

   # GOOD — yields control to event loop
   @app.get("/process")
   async def process():
       await asyncio.sleep(5)
       return {"done": True}
   ```

2. **Forgetting to await:**
   ```python
   # BAD — creates coroutine but doesn't execute it
   result = s3.upload(file)     # result is a coroutine object, not the actual result

   # GOOD
   result = await s3.upload(file)
   ```


## 4.4 API Versioning Strategies

| Strategy        | Example                   | Pros                | Cons                |
|-----------------|---------------------------|---------------------|---------------------|
| URL path        | `/api/v1/images`          | Explicit, easy      | URL changes         |
| Query param     | `/api/images?version=1`   | Clean URLs          | Easy to forget      |
| Header          | `Accept: application/vnd.sat.v1+json` | RESTful   | Hidden, hard to test|
| Content negotiation | Same URL, different response | Most RESTful | Complex             |

**We use URL path versioning** (`/api/v1/...`) because it is the most explicit
and easiest to reason about.  When we need v2, we create new routes and
deprecate v1 with a sunset header.


## 4.5 File Upload Handling

Satellite images can be hundreds of megabytes.  FastAPI handles this with
streaming uploads:

```python
from fastapi import UploadFile, File

@app.post("/api/v1/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
):
    # Validate file type
    if file.content_type not in ("image/tiff", "image/geotiff"):
        raise HTTPException(status_code=415, detail="Only GeoTIFF files accepted")

    # Stream to S3 in chunks (don't load entire file into memory)
    s3_key = f"images/{uuid4()}/{file.filename}"
    await s3_client.upload_fileobj(
        file.file,     # SpooledTemporaryFile — streams from disk
        bucket,
        s3_key,
    )

    return {"image_id": image_id, "s3_url": f"s3://{bucket}/{s3_key}"}
```

**Important:**  By default, `UploadFile` spools to disk after 1MB.  This
prevents memory exhaustion from large uploads.


## 4.6 Background Tasks for Long-Running Operations

Change detection can take 30-60 seconds.  We don't want the HTTP request to
block that long.

```python
from fastapi import BackgroundTasks

@app.post("/api/v1/detection/change", status_code=202)
async def detect_change(
    request: ChangeRequest,
    background_tasks: BackgroundTasks,
    detection: ChangeDetectionService = Depends(get_detection_service),
):
    detection_id = str(uuid4())

    # Start the detection in the background
    background_tasks.add_task(
        detection.run_async,
        detection_id=detection_id,
        before_id=request.image_before_id,
        after_id=request.image_after_id,
        threshold=request.threshold,
    )

    # Return immediately with a reference
    return {
        "detection_id": detection_id,
        "status": "processing",
        "status_url": f"/api/v1/detection/{detection_id}",
    }


@app.get("/api/v1/detection/{detection_id}")
async def get_detection_status(detection_id: str):
    result = await detection_store.get(detection_id)
    if result is None:
        raise HTTPException(404, "Detection not found")
    return result
```

The client polls `GET /api/v1/detection/{detection_id}` until the status
changes from `"processing"` to `"completed"`.  For production, consider
WebSockets or Server-Sent Events for real-time updates.


---

# Section 5: MCP (Model Context Protocol)

## 5.1 What Is MCP and Why It Exists

Before MCP, integrating AI models with external tools looked like this:

```
    PRE-MCP: Every integration is custom

    Claude App <--custom code--> Weather API
    Claude App <--custom code--> Database
    Claude App <--custom code--> File System
    Claude App <--custom code--> Satellite Platform   (us)

    N models * M tools = N*M integration points
```

MCP standardizes the interface:

```
    WITH MCP: Standard protocol

    Claude App
        |
        v
    MCP Client (standard)
        |
        v
    MCP Server (Satellite)  -->  Our FastAPI backend
    MCP Server (Weather)     -->  Weather API
    MCP Server (Database)    -->  PostgreSQL
    MCP Server (Files)       -->  Local filesystem

    N models * 1 protocol + M servers = N + M integration points
```

This is the same pattern as USB — before USB, every device needed its own
proprietary connector.  USB standardized the physical and logical interface.


## 5.2 MCP Architecture

```
    MCP Architecture

    +-------------------+          +-------------------+
    |    MCP CLIENT     |          |    MCP SERVER     |
    | (Claude Desktop,  |  stdio   | (our application) |
    |  Claude Code,     |<-------->|                   |
    |  custom app)      |  or SSE  |                   |
    +-------------------+          +---+---+---+-------+
                                   |   |   |   |
                                Tools  Resources  Prompts
                                   |   |   |   |
                                   v   v   v   v
                            +------+---+---+------+
                            | search_images()     |
                            | detect_change()     |
                            | generate_report()   |
                            | satellite://img/123 |
                            | analysis_template   |
                            +---------------------+
```

### Transport Mechanisms

**stdio:**  The MCP client spawns the server as a child process and
communicates over stdin/stdout.  Simple, works locally, no network needed.

```
Claude Desktop --stdin/stdout--> python mcp_server.py
```

**HTTP + Server-Sent Events (SSE):**  For remote servers.  Client sends
requests over HTTP POST, server streams responses over SSE.

```
Claude App --HTTP POST--> https://satellite-mcp.example.com/mcp
           <--SSE-------- (streaming responses)
```


## 5.3 Tools vs Resources vs Prompts

MCP defines three primitive types:

### Tools

Functions the AI can invoke.  They have names, descriptions, and typed
parameters.

```python
@mcp_server.tool()
async def search_satellite_images(
    query: str,
    region: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    """Search satellite imagery by text description, region, and date range.

    Args:
        query: Natural language description of what to search for
        region: Geographic region identifier (e.g., "A7", "amazon-west")
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        max_results: Maximum number of results to return

    Returns:
        List of matching satellite image records with metadata
    """
    results = await api_client.search(query, region, date_from, date_to, max_results)
    return results
```

### Resources

Data the AI can read.  Think of them as files or documents the AI can access.

```python
@mcp_server.resource("satellite://images/{image_id}")
async def get_image_metadata(image_id: str) -> dict:
    """Get metadata for a specific satellite image."""
    return await api_client.get_image(image_id)


@mcp_server.resource("satellite://reports/{report_id}")
async def get_report(report_id: str) -> str:
    """Get the text content of a generated report."""
    return await api_client.get_report_text(report_id)
```

### Prompts

Reusable prompt templates for common workflows.

```python
@mcp_server.prompt()
def analyze_region(region: str, time_period: str) -> str:
    """Generate a comprehensive analysis prompt for a geographic region."""
    return f"""Analyze satellite imagery for region {region} over {time_period}.

    Steps:
    1. Search for all available imagery in this region and time period.
    2. Run change detection between the earliest and most recent images.
    3. Summarize the key changes detected.
    4. Generate a PDF report with visualizations.
    5. Highlight any areas of concern (rapid deforestation, flooding, etc.)

    Be thorough and cite specific detection run IDs."""
```


## 5.4 Designing Good Tool Interfaces for AI Agents

### Principles

1. **Descriptive names.**  `search_satellite_images` not `search`.
2. **Rich docstrings.**  The AI reads the description to decide WHEN and HOW
   to use the tool.
3. **Typed parameters with defaults.**  Optional parameters should have sane
   defaults.
4. **Bounded output.**  Return at most N results.  Don't dump megabytes of
   data — the AI has a context window.
5. **Error messages for the AI.**  Return human-readable errors, not stack
   traces.
6. **Composable.**  Design tools that chain naturally:
   `search_images -> detect_change -> generate_report`

### Anti-Patterns

```
BAD:  def do_stuff(json_blob: str)     # opaque, untyped
GOOD: def search_images(query: str, region: str = None, limit: int = 5)

BAD:  Returns entire 100MB GeoTIFF as base64
GOOD: Returns URL / reference that the user can download separately

BAD:  def analyze_everything()         # too broad, unclear behavior
GOOD: Separate tools for search, detect, report  # composable primitives
```


## 5.5 MCP vs Function Calling vs LangChain Tools

| Feature              | MCP                  | Function Calling      | LangChain Tools      |
|----------------------|----------------------|-----------------------|----------------------|
| Standardized         | Yes (open spec)      | Model-specific        | Framework-specific   |
| Transport            | stdio, HTTP/SSE      | In API request        | In-process           |
| Discovery            | `list_tools()`       | Defined in prompt     | Defined in code      |
| Multi-model          | Yes                  | One model at a time   | LangChain models     |
| Resources (data)     | First-class          | Not supported         | Retriever concept    |
| Prompts (templates)  | First-class          | Not supported         | PromptTemplate       |
| Ecosystem            | Growing              | Mature (OpenAI, Anthropic)| Large           |
| Overhead             | Process/network      | None (inline)         | In-process           |
| Best for             | Multi-tool agents    | Simple tool use       | Complex chains       |

**Our choice:**  MCP for the external interface (Claude Desktop, other agents),
plus standard Anthropic function calling for the internal RAG pipeline (where
the overhead of MCP's transport layer isn't justified).


---

# Section 6: Cloud Architecture & S3

## 6.1 Object Storage vs Block Storage vs File Storage

```
    STORAGE TYPES COMPARISON

    +------------------+-------------------+-------------------+
    | Block Storage    | File Storage      | Object Storage    |
    | (EBS, SAN)       | (EFS, NFS)        | (S3)              |
    +------------------+-------------------+-------------------+
    | Fixed-size blocks| Hierarchical      | Flat namespace    |
    | /dev/sda1        | /mnt/share/a/b.txt| bucket/key        |
    | Fastest I/O      | POSIX semantics   | HTTP API          |
    | Attached to 1 VM | Shared across VMs | Global access     |
    | $/GB: $$$        | $/GB: $$          | $/GB: $           |
    | Use: databases,  | Use: shared home  | Use: images,      |
    | OS disks         | dirs, legacy apps | videos, backups,  |
    |                  |                   | ML datasets       |
    +------------------+-------------------+-------------------+
```

**Why object storage (S3) for satellite imagery:**
- Satellite scenes are write-once, read-many — S3's immutability model fits.
- No directory traversal needed — we access by key (image ID).
- Cost is 10-50x lower than block storage per GB.
- Built-in redundancy (11 nines of durability).
- Global access via HTTP (presigned URLs).


## 6.2 S3 Design Patterns for ML Pipelines

```
    S3 BUCKET LAYOUT

    satellite-images/
    +-- raw/                         # Original uploads
    |   +-- 2025/06/12/
    |       +-- scene_001.tif        # Full resolution GeoTIFF
    |       +-- scene_001_meta.json  # Metadata sidecar
    |
    +-- processed/                   # Analysis-ready data
    |   +-- tiles/
    |   |   +-- scene_001_tile_0_0.npy
    |   |   +-- scene_001_tile_0_1.npy
    |   +-- thumbnails/
    |       +-- scene_001_thumb.png
    |
    +-- artifacts/                   # Model outputs
    |   +-- detections/
    |   |   +-- DET-2025-0612-001/
    |   |       +-- change_mask.png
    |   |       +-- statistics.json
    |   |       +-- features.npy
    |   +-- reports/
    |       +-- RPT-2025-0612-001.pdf
    |
    +-- models/                      # Model weights (optional)
        +-- prithvi-100m/
        +-- sentence-transformer/
```

### Key Design Decisions:

1. **Date-partitioned raw data.**  Makes lifecycle policies easy (archive data
   older than 1 year).

2. **Separate raw from processed.**  Raw data is sacred — never modify it.
   Processed data can be regenerated.

3. **Artifacts reference raw data.**  A detection result always points back to
   the source images.


## 6.3 Presigned URLs

A presigned URL grants temporary access to a private S3 object without
exposing your AWS credentials.

```python
import boto3
from botocore.config import Config

s3_client = boto3.client(
    "s3",
    endpoint_url="http://localhost:4566",  # LocalStack
    config=Config(signature_version="s3v4"),
)

# Generate a URL valid for 1 hour
presigned_url = s3_client.generate_presigned_url(
    "get_object",
    Params={"Bucket": "satellite-images", "Key": "raw/2025/06/12/scene_001.tif"},
    ExpiresIn=3600,
)

# Result: http://localhost:4566/satellite-images/raw/2025/.../scene_001.tif
#         ?X-Amz-Algorithm=AWS4-HMAC-SHA256
#         &X-Amz-Credential=...
#         &X-Amz-Date=...
#         &X-Amz-Expires=3600
#         &X-Amz-Signature=...
```

**In our architecture:**  The FastAPI backend generates presigned URLs and
returns them to the Streamlit frontend.  Streamlit then fetches images
directly from S3, avoiding a bandwidth bottleneck through the API server.

```
    Streamlit ----GET metadata----> FastAPI
    Streamlit <---presigned URL---- FastAPI
    Streamlit ----GET image-------> S3 (direct download)
```


## 6.4 Cost Optimization

### Storage Classes

| Class                | $/GB/month | Retrieval   | Use Case              |
|----------------------|------------|-------------|-----------------------|
| S3 Standard          | $0.023     | Instant     | Active imagery        |
| S3 Infrequent Access | $0.0125    | Instant     | Older analysis results|
| S3 Glacier Instant   | $0.004     | Milliseconds| Archive, rare access  |
| S3 Glacier Deep      | $0.00099   | 12 hours    | Compliance archive    |

### Lifecycle Policy Example

```json
{
  "Rules": [
    {
      "ID": "archive-old-raw",
      "Filter": { "Prefix": "raw/" },
      "Transitions": [
        { "Days": 90,  "StorageClass": "STANDARD_IA" },
        { "Days": 365, "StorageClass": "GLACIER_IR" }
      ],
      "Status": "Enabled"
    },
    {
      "ID": "delete-old-thumbnails",
      "Filter": { "Prefix": "processed/thumbnails/" },
      "Expiration": { "Days": 180 },
      "Status": "Enabled"
    }
  ]
}
```


## 6.5 Local Development with LocalStack

LocalStack emulates AWS services locally.  In our docker-compose:

```yaml
localstack:
  image: localstack/localstack:latest
  ports:
    - "4566:4566"
  environment:
    - SERVICES=s3
```

The application code uses `S3_ENDPOINT_URL`:

```python
# In production: endpoint_url is None (uses real AWS)
# In development: endpoint_url = "http://localhost:4566"
session = aioboto3.Session()
async with session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
    await s3.create_bucket(Bucket="satellite-images")
    await s3.upload_fileobj(file, "satellite-images", key)
```

**Zero code changes between local and production.**  Only the environment
variable differs.


---

# Section 7: Docker & Deployment

## 7.1 Container Basics for ML Applications

### Why Containers for ML?

ML applications have complex, fragile dependency chains:

```
    THE DEPENDENCY HELL

    Python 3.11
      +-- PyTorch 2.1 (needs CUDA 12.1)
      |     +-- cuDNN 8.9
      +-- rasterio 1.3.9
      |     +-- GDAL 3.7
      |           +-- libproj 9.3
      |           +-- libgeos 3.12
      +-- numpy 1.26
      +-- Pillow 10.1

    "Works on my machine" is not a deployment strategy.
```

Containers package the entire dependency tree into a portable, reproducible
image.  If it works in the container, it works in production.

### Image Anatomy

```
    DOCKER IMAGE LAYERS

    +---------------------------+
    | CMD uvicorn app:main      |  <-- runtime command
    +---------------------------+
    | COPY . /app               |  <-- your code (changes often)
    +---------------------------+
    | pip install -r req.txt    |  <-- Python packages (changes sometimes)
    +---------------------------+
    | apt-get install gdal...   |  <-- system packages (changes rarely)
    +---------------------------+
    | python:3.11-slim          |  <-- base image (changes very rarely)
    +---------------------------+

    Docker caches layers from bottom up.  If requirements.txt hasn't changed,
    the pip install layer is cached.  Only the COPY layer and above rebuild.
```

**Best practice:**  Copy `requirements.txt` BEFORE copying the full source code.
This maximizes cache hits.


## 7.2 Multi-Stage Builds

### The Problem

Build tools (compilers, header files) are needed during `pip install` but not
at runtime.  A single-stage build includes all of them in the final image:

```
Single-stage image:  1.8 GB
    - python:3.11-slim base:        120 MB
    - build-essential, GDAL headers: 400 MB  <-- not needed at runtime!
    - Python packages:               800 MB
    - Application code:              5 MB
```

### The Solution: Multi-Stage

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder
RUN apt-get install -y build-essential libgdal-dev  # compilers + headers
RUN pip install -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime
RUN apt-get install -y libgdal32  # runtime libraries only (no headers)
COPY --from=builder /opt/venv /opt/venv  # copy installed packages
COPY . /app
```

```
Multi-stage image:  950 MB
    - python:3.11-slim base:        120 MB
    - runtime GDAL libraries:       80 MB
    - Python packages:              740 MB
    - Application code:             5 MB

Savings: ~850 MB (47% reduction)
```

The builder stage has compilers and header files.  The runtime stage has only
shared libraries.  The `COPY --from=builder` instruction copies artifacts
between stages.


## 7.3 Docker Compose for Local Development

Our `docker-compose.yml` orchestrates four services:

```
    +------------------------------------------------------------------+
    |                      satellite-net (bridge)                       |
    |                                                                  |
    |  +----------+   +----------+   +---------+   +------------+     |
    |  |   API    |   | Streamlit|   |  Qdrant |   | LocalStack |     |
    |  | :8000    |   | :8501    |   | :6333   |   | :4566      |     |
    |  +----+-----+   +----+-----+   +----+----+   +-----+------+     |
    |       |              |              |               |            |
    |       +--------------+--------------+---------------+            |
    |                                                                  |
    +------------------------------------------------------------------+
```

**Key docker-compose features used:**

1. **`depends_on` with `condition: service_healthy`:**  The API doesn't start
   until Qdrant and LocalStack pass their health checks.

2. **Volume mounts for hot reload:**  `./app:/app/app` maps your local source
   into the container.  Combined with `uvicorn --reload`, code changes apply
   instantly without rebuilding.

3. **Named volumes for persistence:**  `qdrant-data` persists vector database
   data across container restarts.

4. **Shared network:**  All services communicate by name (`qdrant`, `localstack`)
   on the `satellite-net` bridge network.


## 7.4 GPU Passthrough for Model Inference

For production inference with Prithvi, you need GPU access inside the container.

### NVIDIA Container Toolkit

```yaml
# docker-compose.gpu.yml (override file)
services:
  api:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - CUDA_VISIBLE_DEVICES=0
```

Run with:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

### GPU Memory Management

Prithvi-100M requires approximately:
- **Weights:**  ~400 MB GPU memory
- **Inference (single image):**  ~2 GB GPU memory
- **Inference (batch of 8):**  ~8 GB GPU memory

```python
# In your inference service
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)

# Use mixed precision to halve memory usage
with torch.cuda.amp.autocast():
    features = model(input_tensor.to(device))
```

**For development without GPU:**  The model runs on CPU (much slower but
functional).  Set `device = "cpu"` and use smaller tile sizes.


## 7.5 Production Considerations

### Health Checks

Our Dockerfile includes a health check:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

The `/health` endpoint should check all dependencies:

```python
@app.get("/health")
async def health_check():
    checks = {}

    # Check Qdrant
    try:
        await qdrant_client.get_collections()
        checks["qdrant"] = "ok"
    except Exception:
        checks["qdrant"] = "error"

    # Check S3
    try:
        await s3_client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        checks["s3"] = "ok"
    except Exception:
        checks["s3"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "version": "1.0.0",
    }
```

### Structured Logging

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            # Add request context if available
            "request_id": getattr(record, "request_id", None),
        })
```

JSON logs are machine-parseable — essential for log aggregation tools
(ELK stack, CloudWatch, Datadog).

### Monitoring Metrics

Key metrics to track:

| Metric                          | What It Tells You                    |
|---------------------------------|--------------------------------------|
| `api_request_duration_seconds`  | Is the API getting slower?           |
| `model_inference_duration_seconds` | Is GPU inference degrading?       |
| `qdrant_search_duration_seconds`| Is vector search slowing down?       |
| `s3_upload_duration_seconds`    | Are uploads bottlenecked?            |
| `active_detection_jobs`         | How many jobs are running?           |
| `gpu_memory_used_bytes`         | Are we approaching OOM?              |
| `api_error_rate`                | Overall system health                |

Use Prometheus + Grafana or similar for dashboards and alerting.

### Scaling Considerations

```
    SCALING ARCHITECTURE

    Load Balancer (nginx / ALB)
          |
    +-----+-----+-----+
    |     |     |     |
    API   API   API   API    <-- horizontal scale (stateless)
    :8000 :8000 :8000 :8000
          |
    +-----+-----+
    |           |
    Qdrant      S3           <-- managed services scale independently
    (cluster)   (infinite)
```

- **API servers** scale horizontally — they are stateless.
- **Qdrant** can be clustered for larger datasets.
- **S3** scales infinitely by design.
- **GPU inference** is the bottleneck — consider a separate inference service
  with its own scaling policy (e.g., Triton Inference Server, or AWS
  SageMaker endpoints).


---

# Resources

## Official Documentation

- **Prithvi Geospatial Foundation Model**
  - HuggingFace: Search "ibm-nasa-geospatial/Prithvi-100M" on https://huggingface.co/
  - Paper: "Foundation Models for Generalist Geospatial Artificial Intelligence" (2023)

- **Qdrant Vector Database**
  - Documentation: https://qdrant.tech/documentation/
  - Tutorials: https://qdrant.tech/documentation/tutorials/

- **FastAPI**
  - Documentation: https://fastapi.tiangolo.com/
  - Tutorial: https://fastapi.tiangolo.com/tutorial/

- **MCP (Model Context Protocol)**
  - Specification: https://modelcontextprotocol.io/
  - Python SDK: https://github.com/modelcontextprotocol/python-sdk

- **Streamlit**
  - Documentation: https://docs.streamlit.io/
  - Gallery: https://streamlit.io/gallery

- **Rasterio (Geospatial Raster I/O)**
  - Documentation: https://rasterio.readthedocs.io/

- **Anthropic Claude API**
  - Documentation: https://docs.anthropic.com/
  - Python SDK: https://github.com/anthropics/anthropic-sdk-python

- **RAG Concepts**
  - Search "retrieval augmented generation tutorial" for comprehensive guides
  - Original RAG paper: Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (2020)

## YouTube Search Terms

For each major topic, search YouTube for these terms to find video explanations:

| Topic                        | YouTube Search Term                                      |
|------------------------------|----------------------------------------------------------|
| Foundation Models            | "foundation models explained"                            |
| Vision Transformers          | "vision transformer ViT explained"                       |
| Masked Autoencoders          | "masked autoencoder MAE deep learning"                   |
| Satellite Change Detection   | "satellite image change detection deep learning"         |
| Prithvi Model                | "NASA IBM Prithvi geospatial foundation model"           |
| Vector Databases             | "vector database explained HNSW"                         |
| RAG Pipeline                 | "retrieval augmented generation tutorial"                |
| FastAPI                      | "FastAPI full tutorial"                                  |
| Async Python                 | "python asyncio explained"                               |
| MCP Protocol                 | "model context protocol MCP anthropic"                   |
| Docker Multi-Stage           | "docker multi-stage build tutorial"                      |
| Docker Compose               | "docker compose tutorial full stack"                     |
| S3 Presigned URLs            | "AWS S3 presigned URLs tutorial"                         |
| HNSW Algorithm               | "HNSW approximate nearest neighbor"                      |
| Sentence Transformers        | "sentence transformers embeddings tutorial"              |
| Prompt Engineering for RAG   | "prompt engineering RAG grounded generation"             |

## Papers

1. Lewis, P., et al. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." NeurIPS 2020.
2. He, K., et al. "Masked Autoencoders Are Scalable Vision Learners." CVPR 2022.
3. Dosovitskiy, A., et al. "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale." ICLR 2021.
4. Jakubik, J., et al. "Foundation Models for Generalist Geospatial Artificial Intelligence." arXiv 2310.18660, 2023.
5. Malkov, Y., & Yashunin, D. "Efficient and Robust Approximate Nearest Neighbor Using Hierarchical Navigable Small World Graphs." IEEE TPAMI, 2020.
6. Caye Daudt, R., et al. "Fully Convolutional Siamese Networks for Change Detection." IEEE ICIP, 2018.

## Books

- "Deep Learning for the Earth Sciences" — Camps-Valls, Tuia, Zhu, Reichstein (Wiley, 2021)
- "Designing Data-Intensive Applications" — Martin Kleppmann (O'Reilly, 2017) — for distributed systems fundamentals
- "Building Machine Learning Powered Applications" — Emmanuel Ameisen (O'Reilly, 2020)
- "Designing Machine Learning Systems" — Chip Huyen (O'Reilly, 2022)
