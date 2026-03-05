import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ocr_pipeline.config import settings
from ocr_pipeline.routers import health, extract, jobs
from ocr_pipeline.services.startup import wait_for_model_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ocr_pipeline")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Pipeline v%s starting...", settings.pipeline_version)
    logger.info("Model server: %s", settings.model_server_url)
    logger.info("Model: %s", settings.model_name)

    ready = await wait_for_model_server()
    if not ready:
        logger.warning(
            "Model server not ready — pipeline will start but extraction "
            "requests will fail until the model is available."
        )
    else:
        logger.info("Pipeline ready to accept requests.")

    yield

    # --- Shutdown ---
    logger.info("Pipeline shutting down.")


app = FastAPI(
    title="DeepSeek-OCR Pipeline",
    description="PDF text extraction using DeepSeek-OCR via vLLM",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(extract.router)
app.include_router(jobs.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ocr_pipeline.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
