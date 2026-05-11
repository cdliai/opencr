import asyncio

from ocr_pipeline.services.startup import ModelReadiness, configure_local_readiness


def test_local_readiness_reports_cached_model(monkeypatch, tmp_path):
    readiness = ModelReadiness()

    monkeypatch.setattr(
        "ocr_pipeline.services.startup.try_to_load_from_cache",
        lambda _repo_id, filename, **_kwargs: str(tmp_path / filename),
    )

    asyncio.run(configure_local_readiness(readiness))

    assert readiness.ready is True
    assert readiness.local_model_cached is True
    assert "cached" in readiness.status


def test_local_readiness_reports_download_needed(monkeypatch):
    readiness = ModelReadiness()

    monkeypatch.setattr(
        "ocr_pipeline.services.startup.try_to_load_from_cache",
        lambda *_args, **_kwargs: None,
    )

    asyncio.run(configure_local_readiness(readiness))

    assert readiness.ready is True
    assert readiness.local_model_cached is False
    assert "will download on first extraction" in readiness.status
