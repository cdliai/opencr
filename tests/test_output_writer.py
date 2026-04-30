import json

from ocr_pipeline.models.metadata import DocumentMetadata, PageMetadata
from ocr_pipeline.services.output_writer import OutputWriter, PAGE_BREAK
from ocr_pipeline.services.run_storage import RunStorage
from ocr_pipeline.services.script_detector import (
    ScriptAnalysis,
    ScriptDirection,
    ScriptFamily,
)


def build_page(page_num: int) -> PageMetadata:
    return PageMetadata(
        page_num=page_num,
        processing_time_ms=125.0,
        extraction_mode="markdown",
        extraction_attempt=1,
        dpi_used=200,
        text_length_chars=20,
        text_length_words=4,
        text_length_lines=2,
        token_count_cl100k=12,
        token_count_approx=5,
        script_direction="ltr",
        primary_script="latin",
        detected_languages=["en"],
        ltr_ratio=1.0,
        rtl_ratio=0.0,
        arabic_char_count=0,
        latin_char_count=18,
        has_diacritics=False,
        validation_status="pass",
        validation_issues=[],
        repetition_ratio=0.0,
        has_embedded_text=True,
        is_image_only=False,
        page_width=612.0,
        page_height=792.0,
        image_count=0,
        estimated_complexity="simple",
    )


def build_script() -> ScriptAnalysis:
    return ScriptAnalysis(
        direction=ScriptDirection.LTR,
        primary_script=ScriptFamily.LATIN,
        ltr_ratio=1.0,
        rtl_ratio=0.0,
        arabic_char_count=0,
        latin_char_count=18,
        extended_latin_count=0,
        has_diacritics=False,
        sample_rtl_chars="",
        sample_ltr_chars="hello",
        detected_languages=["en"],
    )


def build_document() -> DocumentMetadata:
    return DocumentMetadata(
        filename="sample.pdf",
        file_path="/tmp/sample.pdf",
        file_size_bytes=2048,
        file_sha256="abc123" * 10 + "abcd",
        total_pages=2,
        pdf_title="Sample",
        pdf_author="Tester",
        pdf_creation_date=None,
        pdf_producer="PyMuPDF",
        total_chars=40,
        total_words=8,
        total_tokens_cl100k=24,
        total_processing_time_ms=250.0,
        avg_time_per_page_ms=125.0,
        dominant_direction="ltr",
        dominant_script="latin",
        pages_ltr=2,
        pages_rtl=0,
        pages_mixed=0,
        languages_detected=["en"],
        pages_pass=2,
        pages_warn=0,
        pages_fail=0,
        pages_empty=0,
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        pipeline_version="2.0.0",
        model_used="deepseek-ai/DeepSeek-OCR",
        pages=[build_page(1), build_page(2)],
    )


def test_write_all_creates_raw_clean_markdown_and_metadata(tmp_path):
    storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
    storage.ensure_run_dirs("run-test")
    document = build_document()
    document_id = document.file_sha256[:16]
    paths = storage.artifact_paths("run-test", document_id, document.filename)

    writer = OutputWriter()
    writer.write_all(
        paths=paths,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    assert paths.raw_txt.read_text(encoding="utf-8") == f"raw page one{PAGE_BREAK}raw page two"
    assert paths.clean_txt.read_text(encoding="utf-8") == f"clean page one{PAGE_BREAK}clean page two"
    assert paths.markdown.exists()
    assert paths.meta_json.exists()

    metadata = json.loads(paths.meta_json.read_text(encoding="utf-8"))
    assert metadata["file_sha256"] == document.file_sha256
    assert metadata["total_pages"] == 2
    assert document_id in paths.markdown.name
