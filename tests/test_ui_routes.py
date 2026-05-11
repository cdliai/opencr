from fastapi.testclient import TestClient
from pathlib import Path

import ocr_pipeline.main as main_module
from ocr_pipeline.config import settings
from ocr_pipeline.services.startup import model_readiness


def test_upload_and_list_input(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    runs_dir = output_dir / "runs"
    db_path = output_dir / "opencr.sqlite"
    input_dir.mkdir()
    output_dir.mkdir()

    async def fake_wait_for_model_server():
        model_readiness.ready = True
        model_readiness.error = None
        return True

    monkeypatch.setattr(settings, "input_dir", input_dir)
    monkeypatch.setattr(settings, "output_dir", output_dir)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(main_module, "wait_for_model_server", fake_wait_for_model_server)
    model_readiness.ready = True
    model_readiness.error = None

    with TestClient(main_module.app) as client:
        files = {"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["filename"] == "sample.pdf"
        assert payload["size"] > 0

        listing = client.get("/api/files/input")
        assert listing.status_code == 200
        items = listing.json()
        assert any(item["name"] == "sample.pdf" for item in items)


def test_runs_list_empty_when_no_runs(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    async def fake_wait_for_model_server():
        model_readiness.ready = True
        return True

    monkeypatch.setattr(settings, "input_dir", tmp_path / "input")
    monkeypatch.setattr(settings, "output_dir", output_dir)
    monkeypatch.setattr(settings, "runs_dir", output_dir / "runs")
    monkeypatch.setattr(settings, "db_path", output_dir / "opencr.sqlite")
    monkeypatch.setattr(main_module, "wait_for_model_server", fake_wait_for_model_server)
    model_readiness.ready = True

    with TestClient(main_module.app) as client:
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        assert resp.json() == []


def test_run_detail_uses_minimal_terminal_progress():
    repo_root = Path(__file__).parents[1]
    html = (repo_root / "ocr_pipeline/static/index.html").read_text(encoding="utf-8")
    app_js = (repo_root / "ocr_pipeline/static/js/app.js").read_text(encoding="utf-8")

    assert 'class="run-terminal"' in html
    assert 'x-text="runDocumentProgressLabel()"' in html
    assert 'class="run-spinner"' in html
    assert 'class="summary-card"' not in html
    assert 'class="heatmap"' not in html
    assert "currentRunDocument()" in app_js
    assert "runDocumentProgressLabel()" in app_js
