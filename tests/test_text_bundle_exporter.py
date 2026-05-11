import json
import zipfile

from ocr_pipeline.services.output_writer import OutputWriter
from ocr_pipeline.services.run_storage import RunStorage
from ocr_pipeline.services.text_bundle_exporter import TextBundleExporter
from tests.test_output_writer import build_document, build_script


def _rows(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_text_bundle_export_writes_raw_clean_text_and_jsonl(tmp_path):
    storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
    storage.ensure_run_dirs("run-text")
    document = build_document()
    document_id = document.file_sha256[:16]
    paths = storage.artifact_paths("run-text", document_id, document.filename)

    OutputWriter().write_all(
        paths=paths,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    result = TextBundleExporter(storage.dataset_dir("run-text") / "text_bundle").export_run(
        run={"id": "run-text", "model_used": "model", "pipeline_version": "2.0.0"},
        documents=[
            {
                "document_id": document_id,
                "document_filename": document.filename,
                "status": "completed",
                "total_pages": 2,
                "file_sha256": document.file_sha256,
                "artifact_raw_txt": str(paths.raw_txt),
                "artifact_clean_txt": str(paths.clean_txt),
            }
        ],
        pages_by_document={
            document_id: [
                {"page_num": 1, "status": "pass", "extraction_mode": "markdown"},
                {"page_num": 2, "status": "warn", "extraction_mode": "free_ocr"},
            ]
        },
        catalog_by_document={
            document_id: {
                "group_path": "Ottoman/Sample",
                "author": "Tester",
                "language": "ota-Latn,tr",
            }
        },
    )

    assert result.documents_count == 1
    assert result.pages_count == 2
    assert result.bundle.exists()

    clean_files = list((result.export_dir / "clean").glob("*.txt"))
    raw_files = list((result.export_dir / "raw").glob("*.txt"))
    assert clean_files[0].read_text(encoding="utf-8") == paths.clean_txt.read_text(
        encoding="utf-8"
    )
    assert raw_files[0].read_text(encoding="utf-8") == paths.raw_txt.read_text(
        encoding="utf-8"
    )

    page_rows = _rows(result.export_dir / "pages.jsonl")
    assert [row["clean_text"] for row in page_rows] == [
        "clean page one",
        "clean page two",
    ]
    assert page_rows[0]["raw_text"] == "raw page one"
    assert page_rows[0]["group_path"] == "Ottoman/Sample"
    assert page_rows[0]["language"] == ["ota-Latn", "tr"]
    assert page_rows[1]["extraction_mode"] == "free_ocr"

    document_rows = _rows(result.export_dir / "documents.jsonl")
    assert document_rows[0]["clean_file"].startswith("clean/")
    assert document_rows[0]["raw_file"].startswith("raw/")

    manifest = json.loads((result.export_dir / "manifest.json").read_text("utf-8"))
    assert manifest["export_type"] == "text_bundle"
    assert manifest["created_by"]["organization"] == "cdli.ai"

    with zipfile.ZipFile(result.bundle) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "pages.jsonl" in names
    assert "documents.jsonl" in names
    assert any(name.startswith("clean/") and name.endswith(".txt") for name in names)
    assert any(name.startswith("raw/") and name.endswith(".txt") for name in names)


def test_text_bundle_export_can_filter_selected_documents(tmp_path):
    storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
    storage.ensure_run_dirs("run-selected-text")
    document = build_document()
    paths = storage.artifact_paths("run-selected-text", "doc-a", document.filename)
    OutputWriter().write_all(
        paths=paths,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    result = TextBundleExporter(
        storage.dataset_dir("run-selected-text") / "text_bundle"
    ).export_run(
        run={
            "id": "run-selected-text",
            "model_used": "model",
            "pipeline_version": "2.0.0",
        },
        documents=[
            {
                "document_id": "doc-a",
                "document_filename": "a.pdf",
                "status": "completed",
                "total_pages": 2,
                "file_sha256": "doc-a-sha",
                "artifact_raw_txt": str(paths.raw_txt),
                "artifact_clean_txt": str(paths.clean_txt),
            },
            {
                "document_id": "doc-b",
                "document_filename": "b.pdf",
                "status": "completed",
                "total_pages": 2,
                "file_sha256": "doc-b-sha",
                "artifact_raw_txt": str(paths.raw_txt),
                "artifact_clean_txt": str(paths.clean_txt),
            },
        ],
        pages_by_document={
            "doc-a": [{"page_num": 1}, {"page_num": 2}],
            "doc-b": [{"page_num": 1}, {"page_num": 2}],
        },
        catalog_by_document={"doc-a": {}, "doc-b": {}},
        document_ids={"doc-a"},
    )

    rows = _rows(result.export_dir / "pages.jsonl")
    assert result.documents_count == 1
    assert result.pages_count == 2
    assert {row["document_id"] for row in rows} == {"doc-a"}
