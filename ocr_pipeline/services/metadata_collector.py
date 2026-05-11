from pathlib import Path

import fitz
import tiktoken

from ocr_pipeline.models.metadata import PageMetadata
from ocr_pipeline.services.script_detector import ScriptAnalysis
from ocr_pipeline.services.output_validator import ValidationResult
from ocr_pipeline.services.page_analyzer import PageProfile


class MetadataCollector:
    """Builds metadata during extraction."""

    def __init__(self, model_name: str = "deepseek-ai/DeepSeek-OCR-2"):
        self.model_name = model_name
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._tokenizer = None

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken cl100k_base encoding."""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        return int(len(text.split()) * 1.3)  # Fallback: rough estimate

    def build_page_metadata(
        self,
        page_num: int,
        text: str,
        processing_time_ms: float,
        mode: str,
        attempt: int,
        dpi: int,
        script_analysis: ScriptAnalysis,
        validation_result: ValidationResult,
        page_profile: PageProfile,
    ) -> PageMetadata:
        words = text.split()
        lines = [line for line in text.split("\n") if line.strip()]
        token_count = self.count_tokens(text)

        return PageMetadata(
            page_num=page_num,
            processing_time_ms=round(processing_time_ms, 1),
            extraction_mode=mode,
            extraction_attempt=attempt,
            dpi_used=dpi,
            text_length_chars=len(text),
            text_length_words=len(words),
            text_length_lines=len(lines),
            token_count_cl100k=token_count,
            token_count_approx=int(len(words) * 1.3),
            script_direction=script_analysis.direction.value,
            primary_script=script_analysis.primary_script.value,
            detected_languages=script_analysis.detected_languages,
            ltr_ratio=script_analysis.ltr_ratio,
            rtl_ratio=script_analysis.rtl_ratio,
            arabic_char_count=script_analysis.arabic_char_count,
            latin_char_count=script_analysis.latin_char_count,
            has_diacritics=script_analysis.has_diacritics,
            validation_status=validation_result.status.value,
            validation_issues=validation_result.issues,
            repetition_ratio=validation_result.metrics.get("repetition_ratio", 0),
            has_embedded_text=page_profile.has_embedded_text,
            is_image_only=not page_profile.has_embedded_text
            and page_profile.has_images,
            page_width=page_profile.width,
            page_height=page_profile.height,
            image_count=page_profile.image_count,
            estimated_complexity=page_profile.estimated_complexity,
            quality_flags=validation_result.metrics.get("quality_flags", []),
        )

    def extract_pdf_metadata(self, pdf_path: Path) -> dict:
        """Extract PDF-level metadata using PyMuPDF."""
        doc = fitz.open(str(pdf_path))
        meta = doc.metadata or {}
        result = {
            "total_pages": len(doc),
            "title": meta.get("title"),
            "author": meta.get("author"),
            "creation_date": meta.get("creationDate"),
            "producer": meta.get("producer"),
        }
        doc.close()
        return result
