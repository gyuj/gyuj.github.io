"""Report generation service.

Pulls analysis results, retrieves RAG context, and produces structured
technical reports via Claude.  Reports are saved as Markdown and PDF to S3.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import anthropic

from config import LLMSettings
from app.models.schemas import Report, ReportSection

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """\
You are a senior remote-sensing analyst generating a formal technical report \
for the Satellite Vision Intelligence Platform. The report must be suitable \
for both technical and executive audiences.

Structure your report EXACTLY with these sections (use Markdown headings):

# Executive Summary
A concise overview of the analysis findings and key takeaways.

# Methodology
Describe the change detection approach, models used, and parameters.

# Findings
Detail the observed changes. Reference specific image IDs, coordinates, \
change percentages, and regions. Include references to change maps using \
the S3 keys provided (format as `![Change Map](s3_key)`).

# Statistical Analysis
Summarise quantitative results: change percentages, area affected, \
confidence scores, number of distinct change regions.

# Recommendations
Provide actionable next steps based on the findings.

Use precise, technical language. Reference all data from the context provided.
"""


class ReportService:
    """Generate structured technical reports from analysis results."""

    def __init__(
        self,
        s3_service: "S3Service",
        rag_pipeline: "RAGPipeline",
        llm_settings: LLMSettings,
    ) -> None:
        self._s3 = s3_service
        self._rag = rag_pipeline
        self._llm_settings = llm_settings
        self._anthropic = anthropic.AsyncAnthropic(api_key=llm_settings.anthropic_api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        analysis_id: str,
        analysis_result: Dict[str, Any],
        include_context: bool = True,
    ) -> Report:
        """Generate a full technical report for an analysis.

        Args:
            analysis_id: The unique analysis record ID.
            analysis_result: Serialised analysis result dict (e.g. from
                ``ChangeDetectionResult.model_dump()``).
            include_context: Whether to enrich the report with RAG context.

        Returns:
            A ``Report`` model with S3 keys for the Markdown and PDF outputs.
        """
        report_id = str(uuid.uuid4())

        # Build context string from the analysis result itself
        analysis_context = self._format_analysis_context(analysis_result)

        # Optionally retrieve supplementary RAG context
        rag_context = ""
        if include_context:
            query = self._build_rag_query(analysis_result)
            rag_results = await self._rag.retrieve_context(query, top_k=8)
            rag_context = self._rag.format_context(rag_results)

        full_context = (
            "## Analysis Result Data\n\n"
            f"{analysis_context}\n\n"
            "## Supplementary Context from Knowledge Base\n\n"
            f"{rag_context}"
        )

        # Generate the report body via Claude
        report_markdown = await self._generate_report_text(full_context, analysis_result)

        # Parse sections from the generated markdown
        title, summary, sections = self._parse_report_sections(report_markdown)

        # Save Markdown to S3
        md_key = f"reports/{analysis_id}/{report_id}/report.md"
        await self._s3.upload_artifact(
            data=report_markdown.encode("utf-8"),
            key=md_key,
            content_type="text/markdown",
        )

        # Generate and save PDF
        pdf_bytes = self._markdown_to_pdf(report_markdown)
        pdf_key = f"reports/{analysis_id}/{report_id}/report.pdf"
        await self._s3.upload_artifact(
            data=pdf_bytes,
            key=pdf_key,
            content_type="application/pdf",
        )

        # Collect figure references from sections
        all_figures: List[str] = []
        for section in sections:
            all_figures.extend(section.figures)

        report = Report(
            id=report_id,
            analysis_id=analysis_id,
            title=title,
            summary=summary,
            sections=sections,
            s3_key_md=md_key,
            s3_key_pdf=pdf_key,
        )

        # Persist structured report JSON
        json_key = f"reports/{analysis_id}/{report_id}/report.json"
        await self._s3.upload_json_artifact(report, json_key)

        logger.info("Generated report %s for analysis %s.", report_id, analysis_id)
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_analysis_context(result: Dict[str, Any]) -> str:
        """Convert an analysis result dict to a human-readable context block."""
        lines: List[str] = []
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 5:
                lines.append(f"{key}: [{len(value)} items — first 5 shown]")
                for item in value[:5]:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    @staticmethod
    def _build_rag_query(result: Dict[str, Any]) -> str:
        """Build a natural-language query from an analysis result for RAG retrieval."""
        parts: List[str] = ["satellite change detection analysis"]
        if "image_id_before" in result:
            parts.append(f"comparing images {result['image_id_before']} and {result['image_id_after']}")
        if "change_percentage" in result:
            parts.append(f"with {result['change_percentage']}% change detected")
        if "changed_regions" in result and isinstance(result["changed_regions"], list):
            parts.append(f"across {len(result['changed_regions'])} distinct regions")
        return " ".join(parts)

    async def _generate_report_text(
        self,
        context: str,
        analysis_result: Dict[str, Any],
    ) -> str:
        """Call Claude to generate the full report Markdown."""
        user_message = (
            f"{context}\n\n"
            "Based on the above analysis data and supplementary context, "
            "generate a comprehensive technical report. Follow the section "
            "structure specified in your instructions exactly."
        )

        response = await self._anthropic.messages.create(
            model=self._llm_settings.model_name,
            max_tokens=self._llm_settings.max_tokens,
            temperature=0.2,
            system=REPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text
        return text

    @staticmethod
    def _parse_report_sections(markdown: str) -> tuple[str, str, List[ReportSection]]:
        """Parse generated Markdown into structured sections.

        Returns (title, executive_summary, sections).
        """
        lines = markdown.strip().split("\n")
        title = "Satellite Change Detection Report"
        summary = ""
        sections: List[ReportSection] = []
        current_heading: Optional[str] = None
        current_body_lines: List[str] = []
        current_figures: List[str] = []

        def _flush() -> None:
            nonlocal current_heading, current_body_lines, current_figures
            if current_heading:
                body = "\n".join(current_body_lines).strip()
                sections.append(
                    ReportSection(
                        heading=current_heading,
                        body=body,
                        figures=list(current_figures),
                    )
                )
            current_body_lines = []
            current_figures = []

        for line in lines:
            stripped = line.strip()

            # Detect headings
            if stripped.startswith("# ") and not stripped.startswith("## "):
                _flush()
                heading_text = stripped[2:].strip()
                if heading_text.lower().startswith("executive summary"):
                    current_heading = "Executive Summary"
                else:
                    current_heading = heading_text
                    if not title or title == "Satellite Change Detection Report":
                        title = heading_text
                continue

            # Detect sub-section headings as new sections
            if stripped.startswith("## "):
                _flush()
                current_heading = stripped[3:].strip()
                continue

            # Detect figure references (S3 keys in image markdown syntax)
            if "![" in stripped and "](" in stripped:
                start = stripped.index("](") + 2
                end = stripped.index(")", start) if ")" in stripped[start:] else len(stripped)
                figure_ref = stripped[start:end]
                if figure_ref.startswith(("s3://", "processed/", "reports/", "raw/")):
                    current_figures.append(figure_ref)

            current_body_lines.append(line)

        _flush()

        # Extract executive summary from the first section if it matches
        if sections and sections[0].heading.lower() == "executive summary":
            summary = sections[0].body
        elif sections:
            # Use first paragraph of first section as summary
            summary = sections[0].body.split("\n\n")[0]

        return title, summary, sections

    @staticmethod
    def _markdown_to_pdf(markdown: str) -> bytes:
        """Convert Markdown to PDF bytes.

        Uses fpdf2 for lightweight PDF generation without heavy dependencies.
        Falls back to a simple text-based PDF if fpdf2 is not available.
        """
        try:
            from fpdf import FPDF

            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            pdf.set_font("Helvetica", size=10)

            for line in markdown.split("\n"):
                stripped = line.strip()
                if stripped.startswith("# "):
                    pdf.set_font("Helvetica", "B", 16)
                    pdf.cell(0, 10, stripped[2:], new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", size=10)
                elif stripped.startswith("## "):
                    pdf.set_font("Helvetica", "B", 14)
                    pdf.cell(0, 8, stripped[3:], new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", size=10)
                elif stripped.startswith("### "):
                    pdf.set_font("Helvetica", "B", 12)
                    pdf.cell(0, 7, stripped[4:], new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", size=10)
                elif stripped.startswith("- ") or stripped.startswith("* "):
                    pdf.cell(5)
                    # Use multi_cell for wrapping; encode to latin-1 safely
                    safe_text = stripped.encode("latin-1", errors="replace").decode("latin-1")
                    pdf.multi_cell(0, 5, safe_text)
                elif stripped:
                    safe_text = stripped.encode("latin-1", errors="replace").decode("latin-1")
                    pdf.multi_cell(0, 5, safe_text)
                else:
                    pdf.ln(3)

            return bytes(pdf.output())

        except ImportError:
            logger.warning("fpdf2 not installed; generating a minimal text-based PDF.")
            # Minimal valid PDF with the markdown text
            content = markdown.encode("latin-1", errors="replace").decode("latin-1")
            # Build a bare-bones PDF manually
            lines_per_page = 60
            text_lines = content.split("\n")
            pages: List[str] = []
            for i in range(0, len(text_lines), lines_per_page):
                page_text = "\n".join(text_lines[i : i + lines_per_page])
                pages.append(page_text)

            if not pages:
                pages = ["(empty report)"]

            # Construct PDF objects
            objects: List[str] = []
            offsets: List[int] = []
            pdf_bytes = io.BytesIO()

            def write(s: str) -> None:
                pdf_bytes.write(s.encode("latin-1"))

            write("%PDF-1.4\n")

            # Catalog
            offsets.append(pdf_bytes.tell())
            objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
            write(objects[-1])

            # Pages
            page_refs = " ".join(f"{i + 3} 0 R" for i in range(len(pages)))
            offsets.append(pdf_bytes.tell())
            objects.append(
                f"2 0 obj\n<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>\nendobj\n"
            )
            write(objects[-1])

            obj_num = 3
            for page_text in pages:
                # Stream
                stream_content = f"BT /F1 10 Tf 50 750 Td 12 TL\n"
                for tl in page_text.split("\n"):
                    escaped = tl.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                    stream_content += f"({escaped}) '\n"
                stream_content += "ET\n"

                # Page
                content_obj = obj_num + 1
                offsets.append(pdf_bytes.tell())
                objects.append(
                    f"{obj_num} 0 obj\n"
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {content_obj} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> >> >> >>\n"
                    f"endobj\n"
                )
                write(objects[-1])

                offsets.append(pdf_bytes.tell())
                objects.append(
                    f"{content_obj} 0 obj\n"
                    f"<< /Length {len(stream_content)} >>\n"
                    f"stream\n{stream_content}endstream\n"
                    f"endobj\n"
                )
                write(objects[-1])
                obj_num += 2

            # Cross-ref table
            xref_offset = pdf_bytes.tell()
            write("xref\n")
            write(f"0 {len(objects) + 1}\n")
            write("0000000000 65535 f \n")
            for off in offsets:
                write(f"{off:010d} 00000 n \n")

            write("trailer\n")
            write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n")
            write("startxref\n")
            write(f"{xref_offset}\n")
            write("%%EOF\n")

            return pdf_bytes.getvalue()
