"""OCR engine abstraction.

OpenCR is GPU-first: `RemoteOCREngine` calls an OpenAI-compatible
`/v1/chat/completions` endpoint, with vLLM serving DeepSeek-OCR-2 as the
default production target. `MODEL_BACKEND=remote` can point the same client at
another compatible GPU service.
"""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Protocol

from openai import AsyncOpenAI
from PIL import Image

from ocr_pipeline.config import settings

PROMPTS = {
    "markdown": "<|grounding|>Convert the document to markdown.",
    "free_ocr": "Free OCR.",
    "figure": "Parse the figure.",
}


class _OCREngineProtocol(Protocol):
    async def extract_page(
        self,
        image: Image.Image,
        mode: str = "markdown",
        ngram_size: int | None = None,
        window_size: int | None = None,
    ) -> str: ...


def _image_to_base64(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class RemoteOCREngine:
    """Talks to any OpenAI-compatible vision endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
    ):
        self.model_name = model_name or settings.model_name
        self.client = AsyncOpenAI(
            api_key=api_key or settings.model_api_key or "EMPTY",
            base_url=f"{base_url or settings.model_server_url}/v1",
            timeout=settings.model_timeout,
        )

    @staticmethod
    def image_to_base64(image: Image.Image) -> str:
        return _image_to_base64(image)

    async def extract_page(
        self,
        image: Image.Image,
        mode: str = "markdown",
        ngram_size: int | None = None,
        window_size: int | None = None,
    ) -> str:
        prompt_text = PROMPTS.get(mode, PROMPTS["markdown"])
        image_b64 = _image_to_base64(image)

        # vLLM-specific knobs go in extra_body. Generic OpenAI servers will
        # ignore unknown extra_body keys.
        extra_body = {
            "skip_special_tokens": False,
            "vllm_xargs": {
                "ngram_size": ngram_size or settings.ngram_size,
                "window_size": window_size or settings.window_size,
                "whitelist_token_ids": settings.whitelist_token_ids,
            },
        }

        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            extra_body=extra_body,
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("No content returned from model")
        return content


def OCREngine(*args, **kwargs) -> _OCREngineProtocol:
    """Factory kept for existing callers."""
    return RemoteOCREngine(*args, **kwargs)
