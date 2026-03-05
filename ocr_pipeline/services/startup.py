import asyncio
import logging
import time

import httpx

from ocr_pipeline.config import settings

logger = logging.getLogger("ocr_pipeline.startup")


class ModelReadiness:
    """Tracks whether the model server is ready to serve inference."""

    def __init__(self):
        self.ready = False
        self.model_name: str | None = None
        self.error: str | None = None
        self.checked_at: float = 0

    @property
    def status(self) -> str:
        if self.ready:
            return "ready"
        if self.error:
            return f"waiting ({self.error})"
        return "waiting"


model_readiness = ModelReadiness()


async def wait_for_model_server() -> bool:
    """
    Block until the model server is healthy and can list its model.
    Called once at pipeline startup. Returns True if ready, False if timed out.
    """
    base = settings.model_server_url
    timeout = settings.model_ready_timeout
    interval = settings.model_ready_interval
    deadline = time.monotonic() + timeout

    logger.info(
        "Waiting for model server at %s (timeout %ds)...", base, timeout
    )

    async with httpx.AsyncClient(timeout=10) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{base}/health")
                if resp.status_code != 200:
                    model_readiness.error = f"health returned {resp.status_code}"
                    logger.info("Model server not healthy yet (%s)", model_readiness.error)
                    await asyncio.sleep(interval)
                    continue
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                model_readiness.error = f"connection failed ({type(exc).__name__})"
                logger.info("Model server not reachable yet (%s)", model_readiness.error)
                await asyncio.sleep(interval)
                continue

            try:
                resp = await client.get(f"{base}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    if models:
                        model_readiness.ready = True
                        model_readiness.model_name = models[0]
                        model_readiness.error = None
                        model_readiness.checked_at = time.time()
                        logger.info(
                            "Model server ready. Available models: %s",
                            ", ".join(models),
                        )
                        return True
                    else:
                        model_readiness.error = "healthy but no models loaded yet"
                        logger.info("Model server healthy but still loading model...")
                else:
                    model_readiness.error = f"/v1/models returned {resp.status_code}"
            except Exception as exc:
                model_readiness.error = str(exc)

            await asyncio.sleep(interval)

    logger.error(
        "Model server did not become ready within %ds. Last error: %s",
        timeout,
        model_readiness.error,
    )
    return False
