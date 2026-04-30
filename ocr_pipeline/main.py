import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ocr_pipeline.config import settings
from ocr_pipeline.routers import health, extract, jobs, metrics, runs, ui
from ocr_pipeline.services.db import init_database
from ocr_pipeline.services.run_orchestrator import init_orchestrator
from ocr_pipeline.services.run_storage import RunStorage
from ocr_pipeline.services.startup import wait_for_model_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ocr_pipeline")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OpenCR v%s starting (cdli.ai)", settings.pipeline_version)
    logger.info("Model server: %s | Model: %s", settings.model_server_url, settings.model_name)

    db = init_database(settings.db_path)
    await db.connect()
    orphans = await db.fail_orphan_runs()
    if orphans:
        logger.warning("Marked %d orphan run(s) as failed (process restart).", orphans)

    storage = RunStorage(output_root=settings.output_dir, runs_root=settings.runs_dir)
    init_orchestrator(db, storage)

    if await wait_for_model_server():
        logger.info("Pipeline ready to accept requests.")
    else:
        logger.warning("Model server not ready — extraction requests will 503 until it is available.")

    yield

    await db.close()
    logger.info("Pipeline shutting down.")


app = FastAPI(
    title="OpenCR — OCR Operator Console",
    description=(
        "Open-source OCR pipeline that turns PDFs into HuggingFace-ready datasets. "
        "Built by [cdli.ai](https://cdli.ai)."
    ),
    version=settings.pipeline_version,
    contact={"name": "cdli.ai", "url": "https://cdli.ai"},
    license_info={"name": "© cdli.ai — All rights reserved."},
    lifespan=lifespan,
)

for r in (health, extract, jobs, runs, metrics, ui):
    app.include_router(r.router)

_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(str(_static_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ocr_pipeline.main:app", host=settings.host, port=settings.port, reload=False)
