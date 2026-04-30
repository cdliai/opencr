import json

from ocr_pipeline.models.metadata import DocumentMetadata, PageMetadata
from ocr_pipeline.services.run_storage import ArtifactPaths
from ocr_pipeline.services.script_detector import ScriptAnalysis, wrap_with_direction


PAGE_BREAK = "\n\f\n"


class OutputWriter:
    """Writes per-document artifacts to caller-supplied paths."""

    def write_markdown(
        self,
        paths: ArtifactPaths,
        pages_text: list[str],
        pages_metadata: list[PageMetadata],
        pages_script: list[ScriptAnalysis],
        doc_metadata: DocumentMetadata,
    ) -> None:
        front_matter = (
            "---\n"
            f"source: {doc_metadata.filename}\n"
            f"pages: {doc_metadata.total_pages}\n"
            f"extracted: {doc_metadata.completed_at}\n"
            f"model: {doc_metadata.model_used}\n"
            f"pipeline_version: {doc_metadata.pipeline_version}\n"
            f"dominant_script: {doc_metadata.dominant_script}\n"
            f"dominant_direction: {doc_metadata.dominant_direction}\n"
            f"languages: {json.dumps(doc_metadata.languages_detected)}\n"
            f"total_tokens: {doc_metadata.total_tokens_cl100k}\n"
            "generator: cdli.ai/opencr\n"
            "---\n"
        )

        sections: list[str] = []
        for text, meta, script in zip(pages_text, pages_metadata, pages_script):
            header = (
                f"<!-- Page {meta.page_num} | direction: {meta.script_direction} "
                f"| script: {meta.primary_script} | tokens: {meta.token_count_cl100k} "
                f"| status: {meta.validation_status} -->"
            )
            sections.append(f"{header}\n{wrap_with_direction(text, script)}")

        paths.markdown.write_text(front_matter + "\n\n---\n\n".join(sections), encoding="utf-8")

    def write_all(
        self,
        paths: ArtifactPaths,
        raw_pages_text: list[str],
        clean_pages_text: list[str],
        pages_metadata: list[PageMetadata],
        pages_script: list[ScriptAnalysis],
        doc_metadata: DocumentMetadata,
    ) -> None:
        paths.raw_txt.write_text(PAGE_BREAK.join(raw_pages_text), encoding="utf-8")
        paths.clean_txt.write_text(PAGE_BREAK.join(clean_pages_text), encoding="utf-8")
        self.write_markdown(paths, clean_pages_text, pages_metadata, pages_script, doc_metadata)
        paths.meta_json.write_text(doc_metadata.to_json(), encoding="utf-8")
