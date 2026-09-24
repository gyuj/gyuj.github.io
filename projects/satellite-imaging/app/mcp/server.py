"""MCP (Model Context Protocol) server for the Satellite Vision Intelligence Platform.

Provides tools that allow AI agents to search, analyse, and report on satellite
imagery through a stdio-based MCP transport.

Run with:
    python -m app.mcp.server
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("satellite-vision")


def _api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_satellite_images",
            description=(
                "Search for satellite imagery matching a text query, optional date "
                "range, and optional geographic bounding box. Returns a ranked list "
                "of matching images with relevance scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query describing the imagery you want.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "ISO-8601 date lower bound (e.g. '2024-01-01').",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "ISO-8601 date upper bound.",
                    },
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "Geographic bounding box [min_lon, min_lat, max_lon, max_lat].",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="run_change_detection",
            description=(
                "Trigger a change detection analysis between two satellite images. "
                "Returns the analysis ID and initial status. The analysis compares "
                "spectral differences between the before and after images."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "before_image_id": {
                        "type": "string",
                        "description": "Image ID for the earlier time step.",
                    },
                    "after_image_id": {
                        "type": "string",
                        "description": "Image ID for the later time step.",
                    },
                    "threshold": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Change magnitude threshold (0-1). Default 0.3.",
                    },
                },
                "required": ["before_image_id", "after_image_id"],
            },
        ),
        Tool(
            name="get_analysis_results",
            description=(
                "Retrieve the status and results of a change detection analysis, "
                "including change statistics (total/changed pixels, change percentage, "
                "mean/max magnitude)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "analysis_id": {
                        "type": "string",
                        "description": "The analysis ID returned by run_change_detection.",
                    },
                },
                "required": ["analysis_id"],
            },
        ),
        Tool(
            name="semantic_search",
            description=(
                "Perform a semantic search across the satellite image knowledge base. "
                "Uses vector similarity to find images whose content or metadata is "
                "most relevant to the query."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Number of results to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="generate_report",
            description=(
                "Generate a technical report for a completed change detection analysis. "
                "The report includes an executive summary, methodology, statistics, "
                "findings, and recommendations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "analysis_id": {
                        "type": "string",
                        "description": "The analysis ID to generate a report for.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional custom title for the report.",
                    },
                },
                "required": ["analysis_id"],
            },
        ),
        Tool(
            name="ask_question",
            description=(
                "Ask a natural-language question about the satellite imagery and "
                "analyses in the system. Uses RAG (Retrieval-Augmented Generation) "
                "to ground the answer in actual data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to answer.",
                    },
                },
                "required": ["question"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch MCP tool calls to the FastAPI backend."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            if name == "search_satellite_images":
                return await _search_satellite_images(client, arguments)
            elif name == "run_change_detection":
                return await _run_change_detection(client, arguments)
            elif name == "get_analysis_results":
                return await _get_analysis_results(client, arguments)
            elif name == "semantic_search":
                return await _semantic_search(client, arguments)
            elif name == "generate_report":
                return await _generate_report(client, arguments)
            elif name == "ask_question":
                return await _ask_question(client, arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text
            return [
                TextContent(
                    type="text",
                    text=f"API error ({exc.response.status_code}): {error_detail}",
                )
            ]
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


async def _search_satellite_images(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    # First try text search
    payload: dict[str, Any] = {"query": args["query"], "top_k": 10}
    if "date_from" in args:
        payload["date_from"] = args["date_from"]
    if "date_to" in args:
        payload["date_to"] = args["date_to"]

    resp = await client.post(_api_url("/search/text"), json=payload)
    resp.raise_for_status()
    search_results = resp.json()

    # Also fetch the image list with bbox/date filters
    params: dict[str, Any] = {}
    if "date_from" in args:
        params["date_from"] = args["date_from"]
    if "date_to" in args:
        params["date_to"] = args["date_to"]
    if "bbox" in args and len(args["bbox"]) == 4:
        params["min_lon"] = args["bbox"][0]
        params["min_lat"] = args["bbox"][1]
        params["max_lon"] = args["bbox"][2]
        params["max_lat"] = args["bbox"][3]

    list_resp = await client.get(_api_url("/images/"), params=params)
    list_resp.raise_for_status()
    image_list = list_resp.json()

    result = {
        "semantic_results": search_results,
        "filtered_images": image_list,
        "query": args["query"],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _run_change_detection(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    payload = {
        "before_image_id": args["before_image_id"],
        "after_image_id": args["after_image_id"],
        "threshold": args.get("threshold", 0.3),
    }

    resp = await client.post(_api_url("/analysis/change-detection"), json=payload)
    resp.raise_for_status()
    result = resp.json()

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _get_analysis_results(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    analysis_id = args["analysis_id"]
    resp = await client.get(_api_url(f"/analysis/{analysis_id}"))
    resp.raise_for_status()
    result = resp.json()

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _semantic_search(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    payload = {
        "query": args["query"],
        "top_k": args.get("top_k", 5),
    }

    resp = await client.post(_api_url("/search/text"), json=payload)
    resp.raise_for_status()
    result = resp.json()

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _generate_report(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    payload: dict[str, Any] = {"analysis_id": args["analysis_id"]}
    if "title" in args:
        payload["title"] = args["title"]

    resp = await client.post(_api_url("/reports/generate"), json=payload)
    resp.raise_for_status()
    result = resp.json()

    # Truncate content for the MCP response to keep it manageable
    if result.get("content") and len(result["content"]) > 3000:
        result["content"] = result["content"][:3000] + "\n\n[... truncated for brevity ...]"

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _ask_question(
    client: httpx.AsyncClient, args: dict[str, Any]
) -> list[TextContent]:
    payload = {"question": args["question"], "top_k": 5}

    resp = await client.post(_api_url("/search/qa"), json=payload)
    resp.raise_for_status()
    result = resp.json()

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting Satellite Vision MCP server (stdio transport)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
