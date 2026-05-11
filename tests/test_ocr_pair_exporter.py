import json
import zipfile

from PIL import Image

from ocr_pipeline.services.ocr_pair_exporter import OCRPairExporter
from ocr_pipeline.services.output_writer import OutputWriter
from ocr_pipeline.services.run_storage import RunStorage
from tests.test_output_writer import build_document, build_script


class FakeRenderer:
    def render_page(self, _pdf_path, page_num, _dpi):
        return Image.new("RGB", (16, 16), color=(page_num * 40, 20, 20))


def test_ocr_pair_export_writes_images_jsonl_and_manifest(tmp_path):
    storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
    storage.ensure_run_dirs("run-1234")

    document = build_document()
    document_id = document.file_sha256[:16]
    paths = storage.artifact_paths("run-1234", document_id, document.filename)
    paths.source_pdf.write_bytes(b"%PDF-1.4\n")

    OutputWriter().write_all(
        paths=paths,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    exporter = OCRPairExporter(
        storage.dataset_dir("run-1234") / "ocr_pairs", renderer=FakeRenderer()
    )
    result = exporter.export_run(
        run={
            "id": "run-1234",
            "model_used": "deepseek-ai/DeepSeek-OCR",
            "pipeline_version": "2.0.0",
        },
        documents=[
            {
                "document_id": document_id,
                "document_filename": document.filename,
                "status": "completed",
                "total_pages": 2,
                "file_sha256": document.file_sha256,
                "artifact_source_pdf": str(paths.source_pdf),
                "artifact_raw_txt": str(paths.raw_txt),
                "artifact_clean_txt": str(paths.clean_txt),
            }
        ],
        pages_by_document={
            document_id: [
                {
                    "page_num": 1,
                    "status": "pass",
                    "detected_languages": json.dumps(["ota-Latn"]),
                    "validation_issues": "[]",
                    "primary_script": "latin_extended",
                    "extraction_mode": "markdown",
                    "extraction_attempt": 1,
                    "dpi_used": 160,
                },
                {
                    "page_num": 2,
                    "status": "pass",
                    "detected_languages": json.dumps(["ota-Latn"]),
                    "validation_issues": "[]",
                    "primary_script": "latin_extended",
                    "extraction_mode": "free_ocr",
                    "extraction_attempt": 2,
                    "dpi_used": 160,
                },
            ]
        },
        catalog_by_document={
            document_id: {
                "group_path": "Ottoman/Seyahatname",
                "author": "Evliyâ Çelebi",
                "work": "Seyahatnâme",
                "language": "ota-Latn,tr",
                "script": "latin_extended",
            }
        },
    )

    assert result.pages_count == 2
    assert result.bundle.exists()

    rows = []
    for split in ("train", "validation", "test"):
        rows.extend(
            json.loads(line)
            for line in (result.export_dir / f"{split}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    assert [row["text"] for row in rows] == ["clean page one", "clean page two"]
    assert rows[0]["image"].startswith("images/")
    assert rows[0]["group_path"] == "Ottoman/Seyahatname"
    assert rows[1]["extraction_mode"] == "free_ocr"

    manifest = json.loads(
        (result.export_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["export_type"] == "ocr_pairs"
    assert manifest["created_by"]["organization"] == "cdli.ai"

    with zipfile.ZipFile(result.bundle) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "train.jsonl" in names
    assert any(name.startswith("images/") and name.endswith(".png") for name in names)
