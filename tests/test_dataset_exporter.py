import json

import pyarrow.parquet as pq

from ocr_pipeline.services.dataset_exporter import DatasetExporter, DocumentExport
from ocr_pipeline.services.output_writer import OutputWriter
from ocr_pipeline.services.run_storage import RunStorage
from tests.test_output_writer import build_document, build_script


def test_export_run_writes_parquet_manifest_and_bundle(tmp_path):
    storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
    storage.ensure_run_dirs("run-1234")

    document = build_document()
    document_id = document.file_sha256[:16]
    paths = storage.artifact_paths("run-1234", document_id, document.filename)

    OutputWriter().write_all(
        paths=paths,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    exporter = DatasetExporter(storage.dataset_dir("run-1234"))
    export = DocumentExport(
        metadata=document,
        document_id=document_id,
        artifact_paths=paths,
        catalog_metadata={
            "author": "Evliyâ Çelebi",
            "work": "Seyahatnâme",
            "book": "1",
            "document_date_label": "1900s",
            "document_date_precision": "century",
            "language": "ota-Latn,tr",
            "script": "latin_extended",
            "license": "cc-by-4.0",
        },
    )
    result = exporter.export_run("run-1234", [export])

    assert result.pages_parquet.exists()
    assert result.documents_parquet.exists()
    assert result.manifest.exists()
    assert result.bundle.exists()

    pages_table = pq.read_table(result.pages_parquet)
    documents_table = pq.read_table(result.documents_parquet)
    assert pages_table.num_rows == 2
    assert documents_table.num_rows == 1
    assert "raw_text" in pages_table.column_names
    assert "clean_text" in pages_table.column_names
    assert "author" in pages_table.column_names
    assert pages_table.column("work").to_pylist() == ["Seyahatnâme", "Seyahatnâme"]
    assert pages_table.column("document_date_precision").to_pylist() == ["century", "century"]
    assert "split" in documents_table.column_names
    assert documents_table.column("author").to_pylist() == ["Evliyâ Çelebi"]

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-1234"
    assert manifest["documents_count"] == 1
    assert manifest["pages_count"] == 2
    assert manifest["schema_version"] == 2
