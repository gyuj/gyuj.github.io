"""Retrieval-Augmented Generation (RAG) pipeline.

Retrieves relevant satellite imagery metadata and analysis records from
Qdrant, formats them into a context window, and calls Claude to produce
grounded analytical answers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import anthropic

from config import LLMSettings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert satellite imagery analyst working within the Satellite Vision \
Intelligence Platform. You have access to a database of satellite images, change \
detection analyses, and geospatial metadata.

When answering questions:
- Ground every claim in the retrieved context provided below.
- Reference specific image IDs, dates, and geographic coordinates where possible.
- If the context is insufficient, clearly state what additional data would be needed.
- Use precise, technical language appropriate for remote-sensing professionals.
- Structure long answers with clear headings and bullet points.
"""


class RAGPipeline:
    """Retrieve context from Qdrant and generate grounded answers via Claude."""

    def __init__(
        self,
        vectordb: "VectorDBService",
        embedding_service: "EmbeddingService",
        llm_settings: LLMSettings,
    ) -> None:
        self._vectordb = vectordb
        self._embeddings = embedding_service
        self._llm_settings = llm_settings
        self._anthropic = anthropic.AsyncAnthropic(api_key=llm_settings.anthropic_api_key)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Qdrant for relevant context using text (and optionally image) embeddings.

        Returns a ranked list of payload dicts from both the text and image
        collections, fused via reciprocal rank fusion.
        """
        text_vector = self._embeddings.generate_single_text_embedding(query).tolist()

        results = await self._vectordb.hybrid_search(
            text_query_vector=text_vector,
            image_query_vector=None,  # pure text query for now
            text_weight=0.6,
            image_weight=0.4,
            top_k=top_k,
            filters=filters,
        )
        return results

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_context(results: List[Dict[str, Any]]) -> str:
        """Format retrieval results into a structured context string for the LLM."""
        if not results:
            return "(No relevant context was retrieved from the database.)"

        sections: List[str] = []
        for idx, result in enumerate(results, start=1):
            payload = result.get("payload", {})
            score = result.get("score", 0.0)

            lines = [f"--- Context Item {idx} (relevance: {score:.4f}) ---"]

            if "text" in payload:
                lines.append(f"Text: {payload['text']}")
            if "image_id" in payload:
                lines.append(f"Image ID: {payload['image_id']}")
            if "capture_date" in payload:
                lines.append(f"Capture Date: {payload['capture_date']}")
            if "bbox" in payload:
                bbox = payload["bbox"]
                if isinstance(bbox, dict):
                    lines.append(
                        f"Bounding Box: [{bbox.get('min_lon')}, {bbox.get('min_lat')}] "
                        f"to [{bbox.get('max_lon')}, {bbox.get('max_lat')}]"
                    )
            if "change_percentage" in payload:
                lines.append(f"Change Percentage: {payload['change_percentage']}%")
            if "analysis_type" in payload:
                lines.append(f"Analysis Type: {payload['analysis_type']}")

            # Include any remaining metadata keys not already printed
            shown_keys = {
                "text", "image_id", "capture_date", "bbox",
                "change_percentage", "analysis_type",
            }
            for key, value in payload.items():
                if key not in shown_keys:
                    lines.append(f"{key}: {value}")

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate_answer(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Call Claude with the retrieved context and user query.

        Returns the model's text response.
        """
        sys = system_prompt or SYSTEM_PROMPT

        user_message = (
            f"## Retrieved Context\n\n{context}\n\n"
            f"## User Question\n\n{query}\n\n"
            "Please provide a thorough, evidence-grounded answer based on the context above."
        )

        response = await self._anthropic.messages.create(
            model=self._llm_settings.model_name,
            max_tokens=self._llm_settings.max_tokens,
            temperature=self._llm_settings.temperature,
            system=sys,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract text from the response
        answer = ""
        for block in response.content:
            if block.type == "text":
                answer += block.text
        return answer

    # ------------------------------------------------------------------
    # Convenience: retrieve + generate in one call
    # ------------------------------------------------------------------

    async def query(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """End-to-end RAG: retrieve context, format, generate answer.

        Returns a dict with ``answer``, ``context_items``, and ``query``.
        """
        results = await self.retrieve_context(query, top_k=top_k, filters=filters)
        context_str = self.format_context(results)
        answer = await self.generate_answer(query, context_str)

        return {
            "query": query,
            "answer": answer,
            "context_items": results,
            "num_context_items": len(results),
        }
