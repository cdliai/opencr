"""In-process OCR engine using HuggingFace `transformers`.

Used by the `local` model backend so OpenCR runs on Apple Silicon, CPU-only
boxes, and any environment without a GPU model server. Trades throughput for
zero-deployment-friction: a single Python process boots the web UI and serves
inference.

Caveats:
- DeepSeek-OCR is ~3B params + a vision tower; on M-series Macs expect
  5–30 s/page, on CPU much slower. Production batch jobs should use vLLM.
- The model loads lazily on the first extraction request so server startup
  stays fast.
- `transformers` and `torch` are intentionally optional — they only get
  imported when this module is instantiated. Install them via
  `requirements-local.txt`.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from PIL import Image

from ocr_pipeline.config import settings

logger = logging.getLogger("ocr_pipeline.local_engine")

# Maps the same `mode` strings the remote backend uses to the prompt strings
# DeepSeek-OCR's reference inference helper expects.
LOCAL_PROMPTS = {
    "markdown": "<image>\n<|grounding|>Convert the document to markdown.",
    "free_ocr": "<image>\nFree OCR.",
    "figure": "<image>\nParse the figure.",
}


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "MODEL_BACKEND=local requires `torch`. Install with: "
            "pip install -r requirements-local.txt"
        ) from exc
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(requested: str, device: str):
    import torch

    if requested == "float16":
        return torch.float16
    if requested == "bfloat16":
        return torch.bfloat16
    if requested == "float32":
        return torch.float32
    # auto — bf16 on CUDA, fp16 on MPS, fp32 on CPU (mps doesn't love bf16, cpu hates fp16)
    if device == "cuda":
        return torch.bfloat16
    if device == "mps":
        return torch.float16
    return torch.float32


class LocalOCREngine:
    """In-process DeepSeek-OCR inference via `transformers`.

    Only one instance is loaded per process; concurrent requests serialize on
    the same model object via an asyncio lock since GPU/MPS memory makes
    parallel calls impractical at this size.
    """

    _instance: "LocalOCREngine | None" = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_name: str | None = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self.model_name = model_name or settings.model_name
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: str | None = None
        self._dtype: Any = None
        self._lock = asyncio.Lock()
        self._load_error: BaseException | None = None
        self._initialized = True

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        if self._load_error is not None:
            raise RuntimeError("Local OCR engine failed to load") from self._load_error
        async with self._lock:
            if self._model is not None:
                return
            if self._load_error is not None:
                raise RuntimeError(
                    "Local OCR engine failed to load"
                ) from self._load_error
            try:
                await asyncio.to_thread(self._load_blocking)
            except Exception as exc:
                self._load_error = exc
                logger.error("Local OCR engine failed to load: %s", exc)
                raise

    def _load_blocking(self) -> None:
        missing = [
            package
            for package in ("torch", "transformers", "easydict")
            if find_spec(package) is None
        ]
        if missing:
            raise RuntimeError(
                "MODEL_BACKEND=local missing package(s): "
                f"{', '.join(missing)}. Install with: "
                "pip install -r ocr_pipeline/requirements.txt -r requirements-local.txt"
            )
        from transformers import AutoModel, AutoTokenizer

        device = _resolve_device(settings.local_device)
        dtype = _resolve_dtype(settings.local_dtype, device)
        logger.info(
            "Loading %s on %s (%s). First boot downloads ~6 GB.",
            self.model_name,
            device,
            dtype,
        )

        # eager attention works everywhere; flash-attn-2 is CUDA-only and would
        # break MPS/CPU loads.
        attn_impl = "flash_attention_2" if device == "cuda" else "eager"

        tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            cache_dir=str(settings.local_model_cache),
        )
        model = AutoModel.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            use_safetensors=True,
            attn_implementation=attn_impl,
            cache_dir=str(settings.local_model_cache),
        )
        model = model.eval().to(dtype)
        if device != "cpu":
            model = model.to(device)

        self._tokenizer = tokenizer
        self._model = model
        self._device = device
        self._dtype = dtype
        logger.info("Local OCR engine ready on %s", device)

    async def extract_page(
        self,
        image: Image.Image,
        mode: str = "markdown",
        ngram_size: int | None = None,  # noqa: ARG002 (vLLM-only knob)
        window_size: int | None = None,  # noqa: ARG002
    ) -> str:
        await self._ensure_loaded()
        prompt = LOCAL_PROMPTS.get(mode, LOCAL_PROMPTS["markdown"])

        async with self._lock:
            return await asyncio.to_thread(self._infer_blocking, image, prompt)

    def _infer_blocking(self, image: Image.Image, prompt: str) -> str:
        # DeepSeek-OCR's `model.infer` (registered via trust_remote_code) expects a
        # path on disk for the image and writes its result alongside it. We feed it
        # a temp dir so nothing leaks into the output volume.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            image_path = tmp / "page.png"
            image.save(image_path, format="PNG")

            try:
                result = self._model.infer(
                    self._tokenizer,
                    prompt=prompt,
                    image_file=str(image_path),
                    output_path=str(tmp),
                    base_size=1024,
                    image_size=640,
                    crop_mode=True,
                    save_results=False,
                    test_compress=False,
                )
            except TypeError:
                # Older variants of the remote-code helper had a slightly
                # different signature; fall back to the minimal kwargs.
                result = self._model.infer(
                    self._tokenizer,
                    prompt=prompt,
                    image_file=str(image_path),
                    output_path=str(tmp),
                )

            if isinstance(result, str):
                return result
            # Some forks return a dict / list; prefer a 'text' key, else stringify.
            if isinstance(result, dict) and "text" in result:
                return str(result["text"])
            return str(result) if result is not None else ""
