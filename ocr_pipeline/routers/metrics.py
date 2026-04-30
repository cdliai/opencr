from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ocr_pipeline.services.observability import observability


router = APIRouter()


@router.get("/api/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(observability.render_prometheus())


@router.get("/api/metrics/summary")
async def metrics_summary():
    snapshot = observability.snapshot()
    return {
        "jobs_created_total": snapshot.jobs_created_total,
        "jobs_completed_total": snapshot.jobs_completed_total,
        "jobs_failed_total": snapshot.jobs_failed_total,
        "active_jobs": snapshot.active_jobs,
        "documents_processed_total": snapshot.documents_processed_total,
        "pages_processed_total": snapshot.pages_processed_total,
        "page_retries_total": snapshot.page_retries_total,
        "pages_warn_total": snapshot.pages_warn_total,
        "pages_fail_total": snapshot.pages_fail_total,
        "pages_empty_total": snapshot.pages_empty_total,
        "tokens_total": snapshot.tokens_total,
        "average_tokens_per_second": round(snapshot.average_tokens_per_second, 2),
        "average_page_latency_ms": round(snapshot.average_page_latency_ms, 2),
    }
