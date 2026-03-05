import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, HTTPException
from fastapi.responses import StreamingResponse

from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import JobRequest, JobStatusResponse
from ocr_pipeline.services.batch_processor import BatchProcessor
from ocr_pipeline.services.startup import model_readiness

router = APIRouter()

jobs: dict[str, dict] = {}


async def run_job(job_id: str, request: JobRequest):
    """Background task to process all documents in a job."""
    job = jobs[job_id]
    job["status"] = "processing"
    output_dir = Path(request.output_dir) if request.output_dir else settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    total_docs = len(request.file_paths)
    completed_docs = 0
    total_pages_all = 0
    total_pass = 0
    total_warn = 0
    total_fail = 0
    total_empty = 0
    total_time_ms = 0.0

    async def event_callback(event: dict):
        nonlocal completed_docs
        event["job_id"] = job_id

        if event.get("type") == "page_start":
            job["current_document"] = event.get("document")
            job["current_page"] = event.get("page")
            job["current_total_pages"] = event.get("total_pages")

        # Push to all listeners
        for queue in job.get("listeners", []):
            await queue.put(event)

    for file_path_str in request.file_paths:
        pdf_path = Path(file_path_str)
        if not pdf_path.exists():
            error_event = {
                "type": "document_error",
                "document": pdf_path.name,
                "error": f"File not found: {file_path_str}",
            }
            for queue in job.get("listeners", []):
                await queue.put(error_event)
            continue

        processor = BatchProcessor(event_callback=event_callback)
        doc_meta = await processor.process_document(pdf_path, output_dir)

        completed_docs += 1
        total_pages_all += doc_meta.total_pages
        total_pass += doc_meta.pages_pass
        total_warn += doc_meta.pages_warn
        total_fail += doc_meta.pages_fail
        total_empty += doc_meta.pages_empty
        total_time_ms += doc_meta.total_processing_time_ms

        job["progress"] = completed_docs / total_docs
        job["documents_completed"] = completed_docs

    job["status"] = "completed"
    job["progress"] = 1.0

    complete_event = {
        "type": "job_complete",
        "total_documents": total_docs,
        "total_pages": total_pages_all,
        "total_time_ms": round(total_time_ms, 1),
        "summary": {
            "pass": total_pass,
            "warn": total_warn,
            "fail": total_fail,
            "empty": total_empty,
        },
    }
    for queue in job.get("listeners", []):
        await queue.put(complete_event)


@router.post("/api/jobs")
async def create_job(request: JobRequest):
    """Create a batch extraction job."""
    if not model_readiness.ready:
        raise HTTPException(
            status_code=503,
            detail=f"Model server not ready: {model_readiness.status}",
        )

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "progress": 0.0,
        "documents_total": len(request.file_paths),
        "documents_completed": 0,
        "current_document": None,
        "current_page": None,
        "current_total_pages": None,
        "listeners": [],
    }

    # Start processing in background
    asyncio.create_task(run_job(job_id, request))

    return {"job_id": job_id, "status": "queued"}


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get job status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        documents_completed=job["documents_completed"],
        documents_total=job["documents_total"],
        current_document=job.get("current_document"),
        current_page=job.get("current_page"),
        current_total_pages=job.get("current_total_pages"),
    )


@router.get("/api/jobs/{job_id}/stream")
async def stream_progress(job_id: str):
    """SSE endpoint — works with EventSource in browsers."""

    async def event_generator():
        if job_id not in jobs:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        queue: asyncio.Queue = asyncio.Queue()
        jobs[job_id]["listeners"].append(queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "job_complete":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            jobs[job_id]["listeners"].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.websocket("/ws/jobs/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint — lower latency, bidirectional."""
    await websocket.accept()

    if job_id not in jobs:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return

    queue: asyncio.Queue = asyncio.Queue()
    jobs[job_id]["listeners"].append(queue)

    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=60)
            await websocket.send_json(event)
            if event.get("type") == "job_complete":
                break
    except Exception:
        pass
    finally:
        if queue in jobs.get(job_id, {}).get("listeners", []):
            jobs[job_id]["listeners"].remove(queue)
        await websocket.close()
