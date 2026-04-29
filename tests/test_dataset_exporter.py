import json

import pyarrow.parquet as pq

from ocr_pipeline.services.dataset_exporter import DatasetExporter
from ocr_pipeline.services.output_writer import OutputWriter
from tests.test_output_writer import build_document, build_script


def test_export_job_writes_parquet_manifest_and_bundle(tmp_path):
    writer = OutputWriter()
    document = build_document()
    writer.write_all(
        output_dir=tmp_path,
        filename=document.filename,
        raw_pages_text=["raw page one", "raw page two"],
        clean_pages_text=["clean page one", "clean page two"],
        pages_metadata=document.pages,
        pages_script=[build_script(), build_script()],
        doc_metadata=document,
    )

    exporter = DatasetExporter(tmp_path)
    result = exporter.export_job("job1234", [document])

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
    assert "split" in documents_table.column_names

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["job_id"] == "job1234"
    assert manifest["documents_count"] == 1
    assert manifest["pages_count"] == 2
