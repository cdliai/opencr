from ocr_pipeline.config import settings
from ocr_pipeline.services.batch_processor import BatchProcessor


def test_gpu_backend_keeps_configured_page_concurrency(monkeypatch):
    monkeypatch.setattr(settings, "model_backend", "vllm")
    monkeypatch.setattr(settings, "batch_concurrency", 8)

    processor = BatchProcessor(db=object())

    assert processor.page_concurrency == 8


def test_explicit_page_concurrency_overrides_gpu_default(monkeypatch):
    monkeypatch.setattr(settings, "model_backend", "vllm")
    monkeypatch.setattr(settings, "batch_concurrency", 8)

    processor = BatchProcessor(db=object(), page_concurrency=2)

    assert processor.page_concurrency == 2
