import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ocr_pipeline.config import settings
from ocr_pipeline.services.dataset_exporter import PROJECT_METADATA
from ocr_pipeline.services.output_writer import PAGE_BREAK


@dataclass(frozen=True)
class TextBundleExportResult:
    export_dir: Path
    bundle: Path
    documents_count: int
    pages_count: int


class TextBundleExporter:
    """Builds plain-text exports for corpus and NLP work."""

    def __init__(self, export_dir: Path):
        self.export_dir = export_dir

    @staticmethod
    def _read_text(path_str: str | None) -> str:
        if not path_str:
            return ""
        path = Path(path_str)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def _split_pages(text: str, total_pages: int) -> list[str]:
        pages = text.split(PAGE_BREAK) if text else [""]
        if len(pages) < total_pages:
            pages.extend([""] * (total_pages - len(pages)))
        return pages[:total_pages]

    @staticmethod
    def _json_list(raw) -> list[str]:
        if isinstance(raw, list):
            return [str(item) for item in raw]
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return [part.strip() for part in str(raw).split(",") if part.strip()]
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _language_list(value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        return [part.strip() for part in str(value).split(",") if part.strip()]

    @staticmethod
    def _text_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _file_stem(filename: str, document_id: str) -> str:
        stem = Path(filename or document_id).stem or document_id
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
        return f"{safe or 'document'}__{document_id[:8]}"

    def export_run(
        self,
        *,
        run: dict,
        documents: list[dict],
        pages_by_document: dict[str, list[dict]],
        catalog_by_document: dict[str, dict],
        document_ids: set[str] | None = None,
    ) -> TextBundleExportResult:
        tmp_parent = self.export_dir.parent
        tmp_parent.mkdir(parents=True, exist_ok=True)
        tmp_path = Path(
            tempfile.mkdtemp(prefix=f"{self.export_dir.name}.", dir=tmp_parent)
        )
        clean_dir = tmp_path / "clean"
        raw_dir = tmp_path / "raw"
        clean_dir.mkdir()
        raw_dir.mkdir()

        page_rows: list[dict] = []
        document_rows: list[dict] = []

        for doc in documents:
            document_id = doc["document_id"]
            if doc.get("status") != "completed":
                continue
            if document_ids is not None and document_id not in document_ids:
                continue

            total_pages = int(
                doc.get("total_pages")
                or len(pages_by_document.get(document_id, []))
                or 0
            )
            raw_text = self._read_text(doc.get("artifact_raw_txt"))
            clean_text = self._read_text(doc.get("artifact_clean_txt"))
            if not raw_text and not clean_text:
                continue

            stem = self._file_stem(doc.get("document_filename") or "", document_id)
            raw_rel = f"raw/{stem}.txt"
            clean_rel = f"clean/{stem}.txt"
            (tmp_path / raw_rel).write_text(raw_text, encoding="utf-8")
            (tmp_path / clean_rel).write_text(clean_text, encoding="utf-8")

            raw_pages = self._split_pages(raw_text, total_pages)
            clean_pages = self._split_pages(clean_text, total_pages)
            page_meta = {
                row["page_num"]: row for row in pages_by_document.get(document_id, [])
            }
            catalog = catalog_by_document.get(document_id, {})
            language = self._language_list(catalog.get("language"))

            for page_num in range(1, total_pages + 1):
                meta = page_meta.get(page_num, {})
                page_raw = raw_pages[page_num - 1]
                page_clean = clean_pages[page_num - 1]
                page_rows.append(
                    {
                        "id": f"{document_id}_page_{page_num:04d}",
                        "run_id": run["id"],
                        "document_id": document_id,
                        "document_name": doc.get("document_filename"),
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
                        "language": language
                        or self._json_list(meta.get("detected_languages")),
                        "script": catalog.get("script")
                        or meta.get("primary_script"),
                        "page": page_num,
                        "raw_text": page_raw,
                        "clean_text": page_clean,
                        "raw_text_sha256": self._text_sha256(page_raw),
                        "clean_text_sha256": self._text_sha256(page_clean),
                        "ocr_status": meta.get("status"),
                        "validation_issues": self._json_list(
                            meta.get("validation_issues")
                        ),
                        "extraction_mode": meta.get("extraction_mode"),
                        "extraction_attempt": meta.get("extraction_attempt"),
                        "source_file": doc.get("document_filename"),
                        "source_pdf_sha256": doc.get("file_sha256"),
                        "ocr_model": run.get("model_used") or settings.model_name,
                        "pipeline_version": run.get("pipeline_version")
                        or settings.pipeline_version,
                    }
                )

            document_rows.append(
                {
                    "run_id": run["id"],
                    "document_id": document_id,
                    "document_name": doc.get("document_filename"),
                    "group_path": catalog.get("group_path"),
                    "title": catalog.get("display_title")
                    or catalog.get("pdf_title"),
                    "author": catalog.get("author") or catalog.get("pdf_author"),
                    "work": catalog.get("work"),
                    "book": catalog.get("book"),
                    "document_date_label": catalog.get("document_date_label"),
                    "document_date_precision": catalog.get("document_date_precision"),
                    "language": language,
                    "script": catalog.get("script"),
                    "page_count": total_pages,
                    "raw_file": raw_rel,
                    "clean_file": clean_rel,
                    "raw_text_sha256": self._text_sha256(raw_text),
                    "clean_text_sha256": self._text_sha256(clean_text),
                    "source_pdf_sha256": doc.get("file_sha256"),
                    "ocr_model": run.get("model_used") or settings.model_name,
                    "pipeline_version": run.get("pipeline_version")
                    or settings.pipeline_version,
                }
            )

        self._write_jsonl(tmp_path / "pages.jsonl", page_rows)
        self._write_jsonl(tmp_path / "documents.jsonl", document_rows)
        self._write_manifest(tmp_path, run, len(document_rows), len(page_rows))

        if self.export_dir.exists():
            shutil.rmtree(self.export_dir)
        tmp_path.replace(self.export_dir)

        bundle = self.export_dir.with_suffix(".zip")
        if bundle.exists():
            bundle.unlink()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.export_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(self.export_dir))

        return TextBundleExportResult(
            export_dir=self.export_dir,
            bundle=bundle,
            documents_count=len(document_rows),
            pages_count=len(page_rows),
        )

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    @staticmethod
    def _write_manifest(
        export_dir: Path, run: dict, documents_count: int, pages_count: int
    ) -> None:
        payload = {
            "export_type": "text_bundle",
            "run_id": run["id"],
            "created_by": PROJECT_METADATA,
            "documents_count": documents_count,
            "pages_count": pages_count,
            "schema_version": 1,
            "artifacts": {
                "clean_text_dir": "clean/",
                "raw_text_dir": "raw/",
                "pages_jsonl": "pages.jsonl",
                "documents_jsonl": "documents.jsonl",
            },
            "ocr_model": run.get("model_used") or settings.model_name,
            "pipeline_version": run.get("pipeline_version")
            or settings.pipeline_version,
        }
        (export_dir / "manifest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
