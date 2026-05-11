import asyncio

import pytest
from PIL import Image

from ocr_pipeline.services.local_ocr_engine import (
    LocalOCREngine,
    _resolve_attn_implementation,
)


def test_local_engine_caches_load_failure(monkeypatch):
    async def _scenario():
        LocalOCREngine._instance = None
        engine = LocalOCREngine()
        calls = 0

        def fail_load():
            nonlocal calls
            calls += 1
            raise RuntimeError("missing dependency")

        monkeypatch.setattr(engine, "_load_blocking", fail_load)

        for _ in range(2):
            try:
                await engine._ensure_loaded()
            except RuntimeError:
                pass
            else:
                raise AssertionError("expected load failure")

        assert calls == 1

    asyncio.run(_scenario())


def test_local_attn_auto_uses_eager_when_flash_attn_missing(monkeypatch):
    monkeypatch.setattr(
        "ocr_pipeline.services.local_ocr_engine.find_spec", lambda _name: None
    )

    assert _resolve_attn_implementation("auto", "cuda") == "eager"


def test_local_attn_auto_uses_flash_when_available_on_cuda(monkeypatch):
    monkeypatch.setattr(
        "ocr_pipeline.services.local_ocr_engine.find_spec", lambda _name: object()
    )

    assert _resolve_attn_implementation("auto", "cuda") == "flash_attention_2"


def test_local_attn_forced_flash_requires_flash_attn(monkeypatch):
    monkeypatch.setattr(
        "ocr_pipeline.services.local_ocr_engine.find_spec", lambda _name: None
    )

    with pytest.raises(RuntimeError, match="requires `flash_attn`"):
        _resolve_attn_implementation("flash_attention_2", "cuda")


def test_local_infer_uses_eval_mode_so_text_is_returned(monkeypatch):
    LocalOCREngine._instance = None
    engine = LocalOCREngine()
    engine._tokenizer = object()

    calls = {}

    class FakeModel:
        def infer(self, tokenizer, **kwargs):
            calls.update(kwargs)
            return "recognized text"

    engine._model = FakeModel()

    result = engine._infer_blocking(Image.new("RGB", (8, 8)), "<image>\nFree OCR.")

    assert result == "recognized text"
    assert calls["eval_mode"] is True
    assert calls["save_results"] is False


def test_local_infer_suppresses_remote_model_stdout(capsys):
    LocalOCREngine._instance = None
    engine = LocalOCREngine()
    engine._tokenizer = object()

    class FakeModel:
        def infer(self, tokenizer, **kwargs):
            print("remote model debug noise")
            return "recognized text"

    engine._model = FakeModel()

    result = engine._infer_blocking(Image.new("RGB", (8, 8)), "<image>\nFree OCR.")

    assert result == "recognized text"
    assert "remote model debug noise" not in capsys.readouterr().out
