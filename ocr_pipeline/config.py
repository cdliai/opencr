from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


def _default_input_dir() -> Path:
    """Use /data/input inside Docker, ./input on a developer machine."""
    if Path("/data").is_dir():
        return Path("/data/input")
    return Path.cwd() / "input"


def _default_output_dir() -> Path:
    if Path("/data").is_dir():
        return Path("/data/output")
    return Path.cwd() / "output"


class Settings(BaseSettings):
    # Model backend selection
    # - "vllm" / "remote": call any OpenAI-compatible /v1/chat/completions server
    # - "local" / "transformers": load DeepSeek-OCR in-process via transformers (Mac/CPU)
    model_backend: Literal["vllm", "remote", "local", "transformers"] = "vllm"
    model_server_url: str = "http://ocr-model:39671"
    model_name: str = "deepseek-ai/DeepSeek-OCR"
    model_api_key: str = "EMPTY"
    model_timeout: float = 120.0

    # Local backend (Apple Silicon / CPU)
    local_device: Literal["auto", "mps", "cuda", "cpu"] = "auto"
    local_dtype: Literal["auto", "float16", "bfloat16", "float32"] = "auto"
    local_model_cache: Path = Path.home() / ".cache" / "huggingface"

    # Startup readiness (used by the remote backend)
    model_ready_timeout: int = 300
    model_ready_interval: int = 5

    # NGram processor defaults (vLLM-only feature; ignored by local backend)
    ngram_size: int = 30
    window_size: int = 90
    whitelist_token_ids: list[int] = [128821, 128822]  # <td>, </td>

    # Extraction defaults
    default_dpi: int = 200
    arabic_dpi: int = 300
    max_tokens: int = 4096
    temperature: float = 0.0

    # Retry settings
    max_retries: int = 2

    # Paths — default to ./input, ./output on a dev machine; /data/* in Docker
    input_dir: Path = _default_input_dir()
    output_dir: Path = _default_output_dir()
    runs_dir: Path = _default_output_dir() / "runs"
    db_path: Path = _default_output_dir() / "opencr.sqlite"

    # Server
    host: str = "0.0.0.0"
    port: int = 39672

    # Pipeline
    pipeline_version: str = "2.0.0"
    batch_concurrency: int = 8

    # HuggingFace OAuth (optional — gates the publish UI when configured)
    hf_oauth_client_id: str = ""
    hf_oauth_client_secret: str = ""
    hf_oauth_redirect_uri: str = "http://localhost:39672/api/auth/callback"
    hf_oauth_scopes: str = "openid profile email write-repos"

    # Session signing
    app_session_secret: str = ""
    app_session_cookie: str = "opencr_session"

    model_config = {"env_prefix": "", "case_sensitive": False, "extra": "ignore"}

    @property
    def is_local_backend(self) -> bool:
        return self.model_backend in ("local", "transformers")


settings = Settings()
