import asyncio

from ocr_pipeline.services.local_ocr_engine import LocalOCREngine


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
