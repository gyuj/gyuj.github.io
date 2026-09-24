"""Streamlit frontend for the Satellite Vision Intelligence Platform.

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
REQUEST_TIMEOUT = 120.0

st.set_page_config(
    page_title="Satellite Vision Intelligence",
    page_icon="🛰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _client() -> httpx.Client:
    """Return a configured httpx client."""
    return httpx.Client(base_url=API_BASE, timeout=REQUEST_TIMEOUT)


def _safe_request(method: str, path: str, **kwargs: Any) -> httpx.Response | None:
    """Make a request and handle connection errors gracefully."""
    try:
        with _client() as c:
            resp = getattr(c, method)(path, **kwargs)
            resp.raise_for_status()
            return resp
    except httpx.ConnectError:
        st.error(
            f"Cannot connect to the API at {API_BASE}. "
            "Make sure the FastAPI server is running."
        )
        return None
    except httpx.HTTPStatusError as exc:
        st.error(f"API error {exc.response.status_code}: {exc.response.text}")
        return None
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

PAGES = {
    "Upload": "upload",
    "Change Detection": "change_detection",
    "Search": "search",
    "Reports": "reports",
    "Chat": "chat",
}

st.sidebar.title("Satellite Vision")
st.sidebar.markdown("---")
selected_page = st.sidebar.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")


# ---------------------------------------------------------------------------
# Page: Upload
# ---------------------------------------------------------------------------


def page_upload() -> None:
    st.header("Upload Satellite Imagery")
    st.markdown(
        "Upload a GeoTIFF file. The system will extract geospatial metadata, "
        "store the image, and generate vector embeddings for search."
    )

    uploaded_file = st.file_uploader(
        "Drag and drop a GeoTIFF (.tif / .tiff)",
        type=["tif", "tiff"],
        accept_multiple_files=False,
    )

    if uploaded_file is not None and st.button("Upload", type="primary"):
        with st.spinner("Uploading and processing..."):
            try:
                with _client() as c:
                    resp = c.post(
                        "/images/upload",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "image/tiff")},
                    )
                    resp.raise_for_status()
                    meta = resp.json()
            except httpx.ConnectError:
                st.error(f"Cannot connect to {API_BASE}. Is the API server running?")
                return
            except httpx.HTTPStatusError as exc:
                st.error(f"Upload failed ({exc.response.status_code}): {exc.response.text}")
                return

        st.success(f"Image uploaded successfully! ID: `{meta['image_id']}`")

        # Display metadata
        st.subheader("Image Metadata")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Width", f"{meta['width']} px")
            st.metric("Height", f"{meta['height']} px")
        with col2:
            st.metric("Bands", meta["bands"])
            st.metric("Data Type", meta["dtype"])
        with col3:
            if meta.get("resolution"):
                st.metric("Resolution", f"{meta['resolution'][0]:.2f} m")
            if meta.get("crs"):
                st.metric("CRS", meta["crs"])

        if meta.get("bbox"):
            st.subheader("Bounding Box")
            bbox = meta["bbox"]
            st.json(
                {
                    "min_lon": bbox[0],
                    "min_lat": bbox[1],
                    "max_lon": bbox[2],
                    "max_lat": bbox[3],
                }
            )

        # Show preview
        st.subheader("Preview")
        preview_resp = _safe_request("get", f"/images/{meta['image_id']}/preview")
        if preview_resp:
            st.image(preview_resp.content, caption="RGB Composite Preview", use_container_width=True)

    # List existing images
    st.markdown("---")
    st.subheader("Existing Images")

    resp = _safe_request("get", "/images/")
    if resp:
        data = resp.json()
        if data["total"] == 0:
            st.info("No images uploaded yet.")
        else:
            for img in data["images"]:
                with st.expander(f"{img['filename']} ({img['image_id'][:8]}...)"):
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.json(img)
                    with cols[1]:
                        if st.button("Delete", key=f"del_{img['image_id']}"):
                            del_resp = _safe_request("delete", f"/images/{img['image_id']}")
                            if del_resp is not None:
                                st.success("Deleted.")
                                st.rerun()


# ---------------------------------------------------------------------------
# Page: Change Detection
# ---------------------------------------------------------------------------


def page_change_detection() -> None:
    st.header("Change Detection")
    st.markdown("Select two images and run spectral change vector analysis.")

    # Fetch images for selection
    resp = _safe_request("get", "/images/")
    if resp is None:
        return

    images = resp.json().get("images", [])
    if len(images) < 2:
        st.warning("Upload at least two images to run change detection.")
        return

    image_options = {f"{img['filename']} ({img['image_id'][:8]})": img["image_id"] for img in images}
    option_list = list(image_options.keys())

    col1, col2 = st.columns(2)
    with col1:
        before_label = st.selectbox("Before Image", option_list, index=0)
    with col2:
        default_after = min(1, len(option_list) - 1)
        after_label = st.selectbox("After Image", option_list, index=default_after)

    threshold = st.slider("Change Threshold", 0.0, 1.0, 0.3, 0.05)

    if st.button("Run Change Detection", type="primary"):
        before_id = image_options[before_label]
        after_id = image_options[after_label]

        if before_id == after_id:
            st.warning("Please select two different images.")
            return

        with st.spinner("Running change detection..."):
            result_resp = _safe_request(
                "post",
                "/analysis/change-detection",
                json={
                    "before_image_id": before_id,
                    "after_image_id": after_id,
                    "threshold": threshold,
                },
            )

        if result_resp is None:
            return

        result = result_resp.json()

        if result["status"] == "failed":
            st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            return

        st.success(f"Analysis complete! ID: `{result['analysis_id']}`")

        # Show statistics
        stats = result.get("statistics", {})
        if stats:
            st.subheader("Change Statistics")
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Changed Pixels", f"{stats['changed_pixels']:,}")
            with m2:
                st.metric("Change %", f"{stats['change_percentage']:.2f}%")
            with m3:
                st.metric("Mean Magnitude", f"{stats['mean_magnitude']:.4f}")

        # Show before / after / change map side by side
        st.subheader("Comparison")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Before**")
            preview = _safe_request("get", f"/images/{before_id}/preview")
            if preview:
                st.image(preview.content, use_container_width=True)
        with c2:
            st.markdown("**After**")
            preview = _safe_request("get", f"/images/{after_id}/preview")
            if preview:
                st.image(preview.content, use_container_width=True)
        with c3:
            st.markdown("**Change Map**")
            cmap = _safe_request("get", f"/analysis/{result['analysis_id']}/change-map")
            if cmap:
                st.image(cmap.content, use_container_width=True)

    # List past analyses
    st.markdown("---")
    st.subheader("Past Analyses")
    analyses_resp = _safe_request("get", "/analysis/")
    if analyses_resp:
        analyses = analyses_resp.json().get("analyses", [])
        if not analyses:
            st.info("No analyses yet.")
        for a in analyses:
            with st.expander(f"Analysis {a['analysis_id'][:8]}... ({a['status']})"):
                st.json(a)


# ---------------------------------------------------------------------------
# Page: Search
# ---------------------------------------------------------------------------


def page_search() -> None:
    st.header("Semantic Search")
    st.markdown("Search across satellite imagery using natural language.")

    query = st.text_input("Search query", placeholder="e.g., urban expansion near coastline")

    search_type = st.radio("Search type", ["Text", "Hybrid"], horizontal=True)

    top_k = st.slider("Number of results", 1, 20, 5)

    if query and st.button("Search", type="primary"):
        with st.spinner("Searching..."):
            if search_type == "Text":
                resp = _safe_request(
                    "post",
                    "/search/text",
                    json={"query": query, "top_k": top_k},
                )
            else:
                text_weight = st.session_state.get("text_weight", 0.5)
                resp = _safe_request(
                    "post",
                    "/search/hybrid",
                    json={
                        "query": query,
                        "top_k": top_k,
                        "text_weight": text_weight,
                        "image_weight": 1.0 - text_weight,
                    },
                )

        if resp is None:
            return

        results = resp.json()
        hits = results.get("hits", [])

        if not hits:
            st.info("No results found.")
            return

        st.subheader(f"Results ({len(hits)})")
        for hit in hits:
            with st.container():
                cols = st.columns([1, 3])
                with cols[0]:
                    # Try to show thumbnail
                    preview = _safe_request("get", f"/images/{hit['image_id']}/preview")
                    if preview:
                        st.image(preview.content, width=150)
                    else:
                        st.markdown("*No preview*")
                with cols[1]:
                    st.markdown(f"**Image ID:** `{hit['image_id']}`")
                    if hit.get("filename"):
                        st.markdown(f"**Filename:** {hit['filename']}")
                    st.markdown(f"**Relevance Score:** {hit['score']:.4f}")
                    if hit.get("metadata"):
                        with st.expander("Metadata"):
                            st.json(hit["metadata"])
                st.markdown("---")

    if search_type == "Hybrid":
        st.sidebar.markdown("### Hybrid Search Weights")
        st.session_state["text_weight"] = st.sidebar.slider("Text weight", 0.0, 1.0, 0.5, 0.1)


# ---------------------------------------------------------------------------
# Page: Reports
# ---------------------------------------------------------------------------


def page_reports() -> None:
    st.header("Reports")
    st.markdown("View and download technical reports generated from change detection analyses.")

    # List existing reports
    resp = _safe_request("get", "/reports/")
    if resp is None:
        return

    reports = resp.json().get("reports", [])

    if not reports:
        st.info("No reports generated yet. Run a change detection analysis and generate a report.")
    else:
        for r in reports:
            with st.expander(f"{r['title']} ({r['status']})"):
                st.markdown(f"**Report ID:** `{r['report_id']}`")
                st.markdown(f"**Analysis ID:** `{r['analysis_id']}`")
                st.markdown(f"**Created:** {r['created_at']}")
                if r.get("word_count"):
                    st.markdown(f"**Word count:** {r['word_count']}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("View Content", key=f"view_{r['report_id']}"):
                        full_resp = _safe_request("get", f"/reports/{r['report_id']}")
                        if full_resp:
                            full = full_resp.json()
                            st.markdown(full.get("content", "*No content available*"))

                with col2:
                    if st.button("Download PDF", key=f"dl_{r['report_id']}"):
                        pdf_resp = _safe_request("get", f"/reports/{r['report_id']}/download")
                        if pdf_resp:
                            st.download_button(
                                label="Save PDF",
                                data=pdf_resp.content,
                                file_name=f"report_{r['report_id'][:8]}.pdf",
                                mime="application/pdf",
                                key=f"save_{r['report_id']}",
                            )

    # Quick generate from sidebar
    st.markdown("---")
    st.subheader("Generate New Report")

    analyses_resp = _safe_request("get", "/analysis/")
    if analyses_resp is None:
        return

    analyses = [
        a for a in analyses_resp.json().get("analyses", []) if a["status"] == "completed"
    ]

    if not analyses:
        st.info("No completed analyses available. Run a change detection first.")
        return

    analysis_options = {
        f"Analysis {a['analysis_id'][:8]}... (change: {a.get('statistics', {}).get('change_percentage', '?')}%)": a[
            "analysis_id"
        ]
        for a in analyses
    }

    selected = st.selectbox("Select analysis", list(analysis_options.keys()))
    custom_title = st.text_input("Report title (optional)")

    if st.button("Generate Report", type="primary"):
        payload: dict[str, Any] = {"analysis_id": analysis_options[selected]}
        if custom_title:
            payload["title"] = custom_title

        with st.spinner("Generating report (this may take a moment)..."):
            gen_resp = _safe_request("post", "/reports/generate", json=payload)

        if gen_resp:
            report = gen_resp.json()
            if report["status"] == "completed":
                st.success(f"Report generated! ID: `{report['report_id']}`")
                st.markdown(report.get("content", ""))
            else:
                st.error(f"Report generation failed: {report.get('error', 'Unknown')}")


# ---------------------------------------------------------------------------
# Page: Chat
# ---------------------------------------------------------------------------


def page_chat() -> None:
    st.header("Chat")
    st.markdown("Ask questions about uploaded imagery and analyses using RAG-powered Q&A.")

    # Initialise chat history in session state
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Display chat history
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("Sources"):
                    for src in msg["sources"]:
                        st.markdown(
                            f"- `{src['image_id']}` "
                            f"({src.get('filename', 'N/A')}) "
                            f"score={src['score']:.4f}"
                        )

    # Chat input
    user_input = st.chat_input("Ask a question about the satellite imagery...")

    if user_input:
        # Show user message
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Call the Q&A endpoint
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = _safe_request(
                    "post",
                    "/search/qa",
                    json={"question": user_input, "top_k": 5},
                )

            if resp:
                data = resp.json()
                answer = data.get("answer", "I could not generate an answer.")
                sources = data.get("sources", [])
                st.markdown(answer)
                if sources:
                    with st.expander("Sources"):
                        for src in sources:
                            st.markdown(
                                f"- `{src['image_id']}` "
                                f"({src.get('filename', 'N/A')}) "
                                f"score={src['score']:.4f}"
                            )
                st.session_state["chat_messages"].append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )
            else:
                fallback = "Sorry, I could not reach the API to answer your question."
                st.markdown(fallback)
                st.session_state["chat_messages"].append(
                    {"role": "assistant", "content": fallback}
                )

    # Sidebar: clear chat
    if st.sidebar.button("Clear Chat History"):
        st.session_state["chat_messages"] = []
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

page_func = {
    "upload": page_upload,
    "change_detection": page_change_detection,
    "search": page_search,
    "reports": page_reports,
    "chat": page_chat,
}

page_func[PAGES[selected_page]]()
