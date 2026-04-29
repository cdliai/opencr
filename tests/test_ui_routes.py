from fastapi.testclient import TestClient

import ocr_pipeline.main as main_module
from ocr_pipeline.config import settings
from ocr_pipeline.services.startup import model_readiness


def test_ui_routes_expose_document_and_dataset_artifacts(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    datasets_dir = output_dir / "datasets"
    input_dir.mkdir()
    datasets_dir.mkdir(parents=True)

    (input_dir / "sample.pdf").write_bytes(b"%PDF-1.4\n")
    (output_dir / "sample.raw.txt").write_text("raw text", encoding="utf-8")
    (output_dir / "sample.txt").write_text("clean text", encoding="utf-8")
    (output_dir / "sample.md").write_text("# markdown", encoding="utf-8")
    (output_dir / "sample.meta.json").write_text('{"ok": true}', encoding="utf-8")
    (datasets_dir / "job-123.zip").write_bytes(b"zip-data")

    async def fake_wait_for_model_server():
        model_readiness.ready = True
        model_readiness.error = None
        return True

    monkeypatch.setattr(settings, "input_dir", input_dir)
    monkeypatch.setattr(settings, "output_dir", output_dir)
    monkeypatch.setattr(main_module, "wait_for_model_server", fake_wait_for_model_server)
    model_readiness.ready = True
    model_readiness.error = None

    with TestClient(main_module.app) as client:
        outputs = client.get("/api/files/output")
        assert outputs.status_code == 200
        payload = outputs.json()
        assert payload[0]["raw_txt_exists"] is True
        assert payload[0]["txt_exists"] is True
        assert payload[0]["md_exists"] is True
        assert payload[0]["meta_exists"] is True

        raw = client.get("/api/files/output/sample.raw.txt")
        assert raw.status_code == 200
        assert raw.text == "raw text"

        datasets = client.get("/api/files/datasets")
        assert datasets.status_code == 200
        assert datasets.json()[0]["name"] == "job-123.zip"

        download = client.get("/api/files/datasets/job-123.zip/download")
        assert download.status_code == 200
        assert download.content == b"zip-data"
