import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from ocr_pipeline.config import settings
from ocr_pipeline.models.metadata import DocumentMetadata, PageMetadata
from ocr_pipeline.services.metadata_collector import MetadataCollector
from ocr_pipeline.services.ocr_engine import OCREngine
from ocr_pipeline.services.output_validator import OutputValidator, ValidationStatus
from ocr_pipeline.services.output_writer import OutputWriter
from ocr_pipeline.services.page_analyzer import PageAnalyzer
from ocr_pipeline.services.pdf_renderer import PDFRenderer
from ocr_pipeline.services.script_detector import ScriptAnalysis, ScriptDetector, ScriptDirection
from ocr_pipeline.services.text_cleaner import TextCleaner


class BatchProcessor:
    """
    Main orchestrator: processes PDFs page-by-page with retry logic,
    validation, script detection, metadata collection, and progress events.
    """

    def __init__(self, event_callback=None, strip_refs: bool = False):
        self.ocr_engine = OCREngine()
        self.renderer = PDFRenderer()
        self.analyzer = PageAnalyzer()
        self.validator = OutputValidator()
        self.cleaner = TextCleaner()
        self.script_detector = ScriptDetector()
        self.metadata_collector = MetadataCollector(model_name=settings.model_name)
        self.writer = OutputWriter()
        self.event_callback = event_callback
        self.strip_refs = strip_refs

    async def _emit(self, event: dict):
        if self.event_callback:
            await self.event_callback(event)

    async def extract_with_retry(
        self,
        image,
        page_num: int,
        max_retries: int = 2,
    ) -> tuple[str, int, str]:
        """
        Extract text with automatic retry on validation failure.

        Strategy progression:
        1. First try: "markdown" mode (structured extraction)
        2. Retry 1: "free_ocr" mode (simpler, less prone to looping)
        3. Retry 2: "free_ocr" with tighter NGram params

        Returns: (cleaned_text, attempt_number, mode_used)
        """
        strategies = [
            {"mode": "markdown", "ngram_size": 30, "window_size": 90},
            {"mode": "free_ocr", "ngram_size": 30, "window_size": 90},
            {"mode": "free_ocr", "ngram_size": 8, "window_size": 256},
        ]

        text = ""
        result = None
        attempt = 0

        for attempt, strategy in enumerate(strategies[: max_retries + 1]):
            text = await self.ocr_engine.extract_page(
                image,
                mode=strategy["mode"],
                ngram_size=strategy["ngram_size"],
                window_size=strategy["window_size"],
            )
            text = self.cleaner.clean(text, strip_refs=self.strip_refs)
            result = self.validator.validate(text, page_num)

            if result.status in (ValidationStatus.PASS, ValidationStatus.WARN):
                if attempt > 0:
                    result.issues.append(
                        f"Succeeded on attempt {attempt + 1} with "
                        f"strategy: {strategy['mode']}"
                    )
                return text, attempt + 1, strategy["mode"]

            # Emit retry event
            if attempt < max_retries:
                next_strategy = strategies[attempt + 1]
                await self._emit(
                    {
                        "type": "page_retry",
                        "page": page_num,
                        "attempt": attempt + 2,
                        "reason": "; ".join(result.issues),
                        "new_strategy": next_strategy["mode"],
                    }
                )

        return text, attempt + 1, strategies[min(attempt, len(strategies) - 1)]["mode"]

    async def process_document(
        self,
        pdf_path: Path,
        output_dir: Path | None = None,
    ) -> DocumentMetadata:
        """Process a single PDF document end-to-end."""
        output_dir = output_dir or settings.output_dir
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        filename = pdf_path.name
        file_size = (await asyncio.to_thread(pdf_path.stat)).st_size
        started_at = datetime.now(timezone.utc).isoformat()
        page_profiles = await asyncio.to_thread(self.analyzer.analyze_document, pdf_path)
        total_pages = len(page_profiles)
        pdf_meta = await asyncio.to_thread(self.metadata_collector.extract_pdf_metadata, pdf_path)

        pages_text: list[str] = []
        pages_metadata: list[PageMetadata] = []
        pages_script: list[ScriptAnalysis] = []
        total_processing_ms = 0.0

        for profile in page_profiles:
            page_num = profile.page_num
            dpi = profile.recommended_dpi
            mode = profile.recommended_mode

            await self._emit(
                {
                    "type": "page_start",
                    "document": filename,
                    "page": page_num,
                    "total_pages": total_pages,
                    "dpi": dpi,
                    "mode": mode,
                }
            )
            image = await asyncio.to_thread(self.renderer.render_page, pdf_path, page_num, dpi)
            t0 = time.perf_counter()
            text, attempt, mode_used = await self.extract_with_retry(
                image, page_num, max_retries=settings.max_retries
            )
            processing_ms = (time.perf_counter() - t0) * 1000
            total_processing_ms += processing_ms

            validation = self.validator.validate(text, page_num)

            script_analysis = self.script_detector.analyze_text(text)

            page_meta = self.metadata_collector.build_page_metadata(
                page_num=page_num,
                text=text,
                processing_time_ms=processing_ms,
                mode=mode_used,
                attempt=attempt,
                dpi=dpi,
                script_analysis=script_analysis,
                validation_result=validation,
                page_profile=profile,
            )

            pages_text.append(text)
            pages_metadata.append(page_meta)
            pages_script.append(script_analysis)

            progress = page_num / total_pages

            await self._emit(
                {
                    "type": "page_complete",
                    "document": filename,
                    "page": page_num,
                    "total_pages": total_pages,
                    "processing_time_ms": round(processing_ms, 1),
                    "validation_status": validation.status.value,
                    "script_direction": script_analysis.direction.value,
                    "primary_script": script_analysis.primary_script.value,
                    "text_length": len(text),
                    "token_count": page_meta.token_count_cl100k,
                    "progress": round(progress, 3),
                }
            )

        completed_at = datetime.now(timezone.utc).isoformat()

        total_chars = sum(m.text_length_chars for m in pages_metadata)
        total_words = sum(m.text_length_words for m in pages_metadata)
        total_tokens = sum(m.token_count_cl100k for m in pages_metadata)
        pages_pass = sum(1 for m in pages_metadata if m.validation_status == ValidationStatus.PASS.value)
        pages_warn = sum(1 for m in pages_metadata if m.validation_status == ValidationStatus.WARN.value)
        pages_fail = sum(1 for m in pages_metadata if m.validation_status == ValidationStatus.FAIL.value)
        pages_empty = sum(1 for m in pages_metadata if m.validation_status == ValidationStatus.EMPTY.value)
        pages_ltr = sum(1 for m in pages_metadata if m.script_direction == ScriptDirection.LTR.value)
        pages_rtl = sum(1 for m in pages_metadata if m.script_direction == ScriptDirection.RTL.value)
        pages_mixed = sum(1 for m in pages_metadata if m.script_direction == ScriptDirection.MIXED.value)

        direction_counts = {"ltr": pages_ltr, "rtl": pages_rtl, "mixed": pages_mixed}
        dominant_direction = max(direction_counts, key=lambda k: direction_counts[k])

        script_counts: dict[str, int] = {}
        for m in pages_metadata:
            script_counts[m.primary_script] = script_counts.get(m.primary_script, 0) + 1
        dominant_script = max(script_counts, key=lambda k: direction_counts.get(k, 0))
        

        all_langs: set[str] = set()
        for m in pages_metadata:
            all_langs.update(m.detected_languages)

        doc_metadata = DocumentMetadata(
            filename=filename,
            file_path=str(pdf_path),
            file_size_bytes=file_size,
            total_pages=total_pages,
            pdf_title=pdf_meta.get("title"),
            pdf_author=pdf_meta.get("author"),
            pdf_creation_date=pdf_meta.get("creation_date"),
            pdf_producer=pdf_meta.get("producer"),
            total_chars=total_chars,
            total_words=total_words,
            total_tokens_cl100k=total_tokens,
            total_processing_time_ms=round(total_processing_ms, 1),
            avg_time_per_page_ms=round(total_processing_ms / total_pages, 1) if total_pages else 0,
            dominant_direction=dominant_direction,
            dominant_script=dominant_script,
            pages_ltr=pages_ltr,
            pages_rtl=pages_rtl,
            pages_mixed=pages_mixed,
            languages_detected=sorted(all_langs),
            pages_pass=pages_pass,
            pages_warn=pages_warn,
            pages_fail=pages_fail,
            pages_empty=pages_empty,
            started_at=started_at,
            completed_at=completed_at,
            pipeline_version=settings.pipeline_version,
            model_used=settings.model_name,
            pages=pages_metadata,
        )

        await asyncio.to_thread(
            self.writer.write_markdown,
            output_dir, filename, pages_text, pages_metadata, pages_script, doc_metadata,
        )
        await asyncio.to_thread(
            self.writer.write_metadata, output_dir, filename, doc_metadata,
        )

        await self._emit(
            {
                "type": "document_complete",
                "document": filename,
                "total_pages": total_pages,
                "pages_pass": pages_pass,
                "pages_warn": pages_warn,
                "pages_fail": pages_fail,
                "total_time_ms": round(total_processing_ms, 1),
                "output_path": str(output_dir / f"{Path(filename).stem}.md"),
            }
        )

        return doc_metadata
