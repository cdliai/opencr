import json
from pathlib import Path

from ocr_pipeline.models.metadata import DocumentMetadata, PageMetadata
from ocr_pipeline.services.script_detector import ScriptAnalysis, ScriptDirection, wrap_with_direction


class OutputWriter:
    """Writes .md and .meta.json output files."""

    def write_markdown(
        self,
        output_dir: Path,
        filename: str,
        pages_text: list[str],
        pages_metadata: list[PageMetadata],
        pages_script: list[ScriptAnalysis],
        doc_metadata: DocumentMetadata,
    ) -> Path:
        """Write the Markdown output file with YAML frontmatter and per-page sections."""
        stem = Path(filename).stem
        md_path = output_dir / f"{stem}.md"

        lines: list[str] = []

        lines.append("---")
        lines.append(f"source: {filename}")
        lines.append(f"pages: {doc_metadata.total_pages}")
        lines.append(f"extracted: {doc_metadata.completed_at}")
        lines.append(f"model: {doc_metadata.model_used}")
        lines.append(f"pipeline_version: {doc_metadata.pipeline_version}")
        lines.append(f"dominant_script: {doc_metadata.dominant_script}")
        lines.append(f"dominant_direction: {doc_metadata.dominant_direction}")
        lines.append(f"languages: {json.dumps(doc_metadata.languages_detected)}")
        lines.append(f"total_tokens: {doc_metadata.total_tokens_cl100k}")
        lines.append("---")
        lines.append("")

        for i, (text, meta, script) in enumerate(
            zip(pages_text, pages_metadata, pages_script)
        ):
            page_num = meta.page_num
            direction = meta.script_direction
            script_name = meta.primary_script
            tokens = meta.token_count_cl100k
            status = meta.validation_status

            lines.append(
                f"<!-- Page {page_num} | direction: {direction} "
                f"| script: {script_name} | tokens: {tokens} "
                f"| status: {status} -->"
            )

            # Wrap with direction hints
            # NOT tthe LTR - RTL thing
            wrapped = wrap_with_direction(text, script)
            lines.append(wrapped)

            if i < len(pages_text) - 1:
                lines.append("")
                lines.append("---")
                lines.append("")

        md_path.write_text("\n".join(lines), encoding="utf-8")
        return md_path

    def write_metadata(
        self,
        output_dir: Path,
        filename: str,
        doc_metadata: DocumentMetadata,
    ) -> Path:
        """Write the .meta.json file."""
        stem = Path(filename).stem
        json_path = output_dir / f"{stem}.meta.json"
        json_path.write_text(doc_metadata.to_json(), encoding="utf-8")
        return json_path
