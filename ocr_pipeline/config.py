from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Model server
    model_server_url: str = "http://ocr-model:39671"
    model_name: str = "deepseek-ai/DeepSeek-OCR"
    model_timeout: float = 120.0

    # Startup readiness
    model_ready_timeout: int = 300  # Max seconds to wait for model server on startup
    model_ready_interval: int = 5   # Seconds between readiness checks

    # NGram processor defaults
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

    # Paths
    input_dir: Path = Path("/data/input")
    output_dir: Path = Path("/data/output")
    runs_dir: Path = Path("/data/output/runs")
    db_path: Path = Path("/data/output/opencr.sqlite")

    # Server
    host: str = "0.0.0.0"
    port: int = 39672

    # Pipeline
    pipeline_version: str = "2.0.0"
    batch_concurrency: int = 8

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
