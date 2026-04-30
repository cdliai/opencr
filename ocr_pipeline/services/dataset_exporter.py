import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ocr_pipeline.models.metadata import DocumentMetadata
from ocr_pipeline.services.output_writer import PAGE_BREAK
from ocr_pipeline.services.run_storage import ArtifactPaths


@dataclass
class DatasetExportResult:
    export_id: str
    export_dir: Path
    pages_parquet: Path
    documents_parquet: Path
    manifest: Path
    bundle: Path
    documents_count: int
    pages_count: int


@dataclass
class DocumentExport:
    metadata: DocumentMetadata
    document_id: str
    artifact_paths: ArtifactPaths


class DatasetExporter:
    """Exports OCR outputs into a Parquet bundle for training and analysis."""

    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir

    @staticmethod
    def _split_pages(text: str, total_pages: int) -> list[str]:
        pages = text.split(PAGE_BREAK) if text else [""]
        if len(pages) < total_pages:
            pages.extend([""] * (total_pages - len(pages)))
        return pages[:total_pages]

    @staticmethod
    def _split_name(stable_key: str) -> str:
        bucket = int(hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:8], 16) % 100
        if bucket < 90:
            return "train"
        if bucket < 95:
            return "validation"
        return "test"

    def export_run(
        self,
        run_id: str,
        documents: list[DocumentExport],
    ) -> DatasetExportResult:
        export_id = f"run-{run_id}"
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        page_rows: list[dict] = []
        document_rows: list[dict] = []

        for entry in documents:
            doc_meta = entry.metadata
            paths = entry.artifact_paths
            raw_text = paths.raw_txt.read_text(encoding="utf-8") if paths.raw_txt.exists() else ""
            clean_text = paths.clean_txt.read_text(encoding="utf-8") if paths.clean_txt.exists() else ""
            markdown_text = paths.markdown.read_text(encoding="utf-8") if paths.markdown.exists() else ""
            raw_pages = self._split_pages(raw_text, doc_meta.total_pages)
            clean_pages = self._split_pages(clean_text, doc_meta.total_pages)
            split = self._split_name(doc_meta.file_sha256)

            for page_meta, page_raw_text, page_clean_text in zip(
                doc_meta.pages, raw_pages, clean_pages
            ):
                page_rows.append(
                    {
                        "dataset_export_id": export_id,
                        "run_id": run_id,
                        "document_id": entry.document_id,
                        "document_name": doc_meta.filename,
                        "page_number": page_meta.page_num,
                        "source_pdf_sha256": doc_meta.file_sha256,
                        "raw_text": page_raw_text,
                        "clean_text": page_clean_text,
                        "validation_status": page_meta.validation_status,
                        "validation_issues": page_meta.validation_issues,
                        "script_direction": page_meta.script_direction,
                        "primary_script": page_meta.primary_script,
                        "detected_languages": page_meta.detected_languages,
                        "token_count_cl100k": page_meta.token_count_cl100k,
                        "text_length_chars": page_meta.text_length_chars,
                        "text_length_words": page_meta.text_length_words,
                        "dpi_used": page_meta.dpi_used,
                        "has_embedded_text": page_meta.has_embedded_text,
                        "is_image_only": page_meta.is_image_only,
                        "pipeline_version": doc_meta.pipeline_version,
                        "model_used": doc_meta.model_used,
                        "split": split,
                    }
                )

            document_rows.append(
                {
                    "dataset_export_id": export_id,
                    "run_id": run_id,
                    "document_id": entry.document_id,
                    "document_name": doc_meta.filename,
                    "source_pdf_sha256": doc_meta.file_sha256,
                    "page_count": doc_meta.total_pages,
                    "raw_text": raw_text,
                    "clean_text": clean_text,
                    "markdown": markdown_text,
                    "pages_pass": doc_meta.pages_pass,
                    "pages_warn": doc_meta.pages_warn,
                    "pages_fail": doc_meta.pages_fail,
                    "pages_empty": doc_meta.pages_empty,
                    "dominant_script": doc_meta.dominant_script,
                    "dominant_direction": doc_meta.dominant_direction,
                    "languages_detected": doc_meta.languages_detected,
                    "total_tokens_cl100k": doc_meta.total_tokens_cl100k,
                    "pipeline_version": doc_meta.pipeline_version,
                    "model_used": doc_meta.model_used,
                    "split": split,
                }
            )

        pages_parquet = self.dataset_dir / "pages.parquet"
        documents_parquet = self.dataset_dir / "documents.parquet"
        manifest = self.dataset_dir / "manifest.json"
        bundle = self.dataset_dir / "bundle.zip"

        pq.write_table(pa.Table.from_pylist(page_rows), pages_parquet)
        pq.write_table(pa.Table.from_pylist(document_rows), documents_parquet)

        manifest_payload = {
            "export_id": export_id,
            "run_id": run_id,
            "documents_count": len(document_rows),
            "pages_count": len(page_rows),
            "artifacts": {
                "pages_parquet": pages_parquet.name,
                "documents_parquet": documents_parquet.name,
            },
            "schema_version": 2,
            "split_strategy": {
                "method": "sha256_bucket",
                "ratios": {"train": 0.90, "validation": 0.05, "test": 0.05},
            },
            "columns": {
                "pages": list(page_rows[0].keys()) if page_rows else [],
                "documents": list(document_rows[0].keys()) if document_rows else [],
            },
            "documents": [asdict(entry.metadata) for entry in documents],
        }
        manifest.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(pages_parquet, arcname=pages_parquet.name)
            archive.write(documents_parquet, arcname=documents_parquet.name)
            archive.write(manifest, arcname=manifest.name)

        return DatasetExportResult(
            export_id=export_id,
            export_dir=self.dataset_dir,
            pages_parquet=pages_parquet,
            documents_parquet=documents_parquet,
            manifest=manifest,
            bundle=bundle,
            documents_count=len(document_rows),
            pages_count=len(page_rows),
        )
