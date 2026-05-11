import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ocr_pipeline.config import settings
from ocr_pipeline.services.dataset_exporter import PROJECT_METADATA
from ocr_pipeline.services.output_writer import PAGE_BREAK
from ocr_pipeline.services.pdf_renderer import PDFRenderer


@dataclass(frozen=True)
class OCRPairExportResult:
    export_dir: Path
    bundle: Path
    pages_count: int


class OCRPairExporter:
    """Builds image/text pairs for OCR model fine-tuning."""

    def __init__(self, export_dir: Path, renderer: PDFRenderer | None = None):
        self.export_dir = export_dir
        self.renderer = renderer or PDFRenderer()

    @staticmethod
    def _split_pages(text: str, total_pages: int) -> list[str]:
        pages = text.split(PAGE_BREAK) if text else [""]
        if len(pages) < total_pages:
            pages.extend([""] * (total_pages - len(pages)))
        return pages[:total_pages]

    @staticmethod
    def _split_name(stable_key: str) -> str:
        bucket = (
            int(hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:8], 16) % 100
        )
        if bucket < 90:
            return "train"
        if bucket < 95:
            return "validation"
        return "test"

    @staticmethod
    def _json_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return [part.strip() for part in raw.split(",") if part.strip()]
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _language_list(value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def export_run(
        self,
        *,
        run: dict,
        documents: list[dict],
        pages_by_document: dict[str, list[dict]],
        catalog_by_document: dict[str, dict],
        dpi: int = 160,
        text_mode: str = "clean",
    ) -> OCRPairExportResult:
        if text_mode not in {"clean", "raw"}:
            raise ValueError("text_mode must be clean or raw")

        if self.export_dir.exists():
            shutil.rmtree(self.export_dir)
        images_dir = self.export_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        split_rows: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}
        pages_count = 0

        for doc in documents:
            if doc.get("status") != "completed":
                continue
            document_id = doc["document_id"]
            catalog = catalog_by_document.get(document_id, {})
            pdf_path_str = doc.get("artifact_source_pdf") or doc.get(
                "document_source_path"
            )
            if not pdf_path_str:
                continue
            pdf_path = Path(pdf_path_str)
            if not pdf_path.exists():
                continue

            total_pages = int(
                doc.get("total_pages")
                or len(pages_by_document.get(document_id, []))
                or 0
            )
            raw_pages = self._split_pages(
                self._read_text(doc.get("artifact_raw_txt")), total_pages
            )
            clean_pages = self._split_pages(
                self._read_text(doc.get("artifact_clean_txt")), total_pages
            )
            page_rows = {
                row["page_num"]: row for row in pages_by_document.get(document_id, [])
            }

            for page_num in range(1, total_pages + 1):
                page_id = f"{document_id}_page_{page_num:04d}"
                image_rel = f"images/{page_id}.png"
                image = self.renderer.render_page(pdf_path, page_num, dpi)
                image.save(images_dir / f"{page_id}.png", format="PNG")

                page_meta = page_rows.get(page_num, {})
                raw_text = raw_pages[page_num - 1]
                clean_text = clean_pages[page_num - 1]
                text = clean_text if text_mode == "clean" else raw_text
                split = self._split_name(page_id)

                split_rows[split].append(
                    {
                        "id": page_id,
                        "image": image_rel,
                        "text": text,
                        "raw_text": raw_text,
                        "clean_text": clean_text,
                        "text_mode": text_mode,
                        "document_id": document_id,
                        "document_name": doc.get("document_filename"),
                        "page": page_num,
                        "group_path": catalog.get("group_path"),
                        "title": catalog.get("display_title")
                        or catalog.get("pdf_title"),
                        "author": catalog.get("author") or catalog.get("pdf_author"),
                        "work": catalog.get("work"),
                        "book": catalog.get("book"),
                        "document_date_label": catalog.get("document_date_label"),
                        "document_date_precision": catalog.get(
                            "document_date_precision"
                        ),
                        "language": self._language_list(catalog.get("language"))
                        or self._json_list(page_meta.get("detected_languages")),
                        "script": catalog.get("script")
                        or page_meta.get("primary_script"),
                        "ocr_status": page_meta.get("status"),
                        "validation_issues": self._json_list(
                            page_meta.get("validation_issues")
                        ),
                        "extraction_mode": page_meta.get("extraction_mode"),
                        "extraction_attempt": page_meta.get("extraction_attempt"),
                        "dpi_used": page_meta.get("dpi_used"),
                        "source_file": doc.get("document_filename"),
                        "source_pdf_sha256": doc.get("file_sha256"),
                        "ocr_model": run.get("model_used"),
                        "pipeline_version": run.get("pipeline_version"),
                    }
                )
                pages_count += 1

        self._write_jsonl(split_rows)
        self._write_manifest(run, pages_count, dpi, text_mode)
        bundle = self.export_dir.with_suffix(".zip")
        if bundle.exists():
            bundle.unlink()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.export_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(self.export_dir))
        return OCRPairExportResult(self.export_dir, bundle, pages_count)

    @staticmethod
    def _read_text(path_str: str | None) -> str:
        if not path_str:
            return ""
        path = Path(path_str)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _write_jsonl(self, split_rows: dict[str, list[dict]]) -> None:
        for split, rows in split_rows.items():
            path = self.export_dir / f"{split}.jsonl"
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

    def _write_manifest(
        self, run: dict, pages_count: int, dpi: int, text_mode: str
    ) -> None:
        payload = {
            "export_type": "ocr_pairs",
            "run_id": run["id"],
            "created_by": PROJECT_METADATA,
            "pages_count": pages_count,
            "image_format": "png",
            "dpi": dpi,
            "text_mode": text_mode,
            "schema_version": 1,
            "ocr_model": run.get("model_used") or settings.model_name,
            "pipeline_version": run.get("pipeline_version")
            or settings.pipeline_version,
            "splits": ["train", "validation", "test"],
        }
        (self.export_dir / "manifest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
