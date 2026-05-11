from pathlib import Path
from typing import get_args

from ocr_pipeline.config import Settings, settings
from ocr_pipeline.models.schemas import HealthResponse
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
