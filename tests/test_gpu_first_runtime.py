import asyncio
from pathlib import Path
from typing import get_args

import httpx

from ocr_pipeline.config import Settings, settings
from ocr_pipeline.models.schemas import HealthResponse
from ocr_pipeline.services import startup
from ocr_pipeline.services.startup import ModelReadiness


def test_default_runtime_is_gpu_first_deepseek_ocr2():
    assert settings.model_name == "deepseek-ai/DeepSeek-OCR-2"
    assert set(get_args(Settings.model_fields["model_backend"].annotation)) == {
        "vllm",
        "remote",
    }
    assert not hasattr(settings, "local_device")


def test_health_schema_does_not_expose_local_model_cache_state():
    assert "local_model_cached" not in HealthResponse.model_fields
    assert "local_model_cache_dir" not in HealthResponse.model_fields


def test_model_readiness_tracks_only_remote_server_state():
    readiness = ModelReadiness()

    assert not hasattr(readiness, "local_model_cached")
    assert not hasattr(readiness, "local_model_cache_dir")


def test_local_backend_dependency_file_is_removed():
    repo_root = Path(__file__).parents[1]

    assert not (repo_root / "requirements-local.txt").exists()


def test_model_readiness_treats_read_error_as_waiting(monkeypatch):
    class DroppingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            raise httpx.ReadError("connection dropped")

    monkeypatch.setattr(startup.httpx, "AsyncClient", DroppingAsyncClient)
    monkeypatch.setattr(startup.settings, "model_ready_timeout", 0.001)
    monkeypatch.setattr(startup.settings, "model_ready_interval", 0.001)
    monkeypatch.setattr(startup, "model_readiness", ModelReadiness())

    assert asyncio.run(startup.wait_for_model_server()) is False
    assert startup.model_readiness.error == "connection failed (ReadError)"
