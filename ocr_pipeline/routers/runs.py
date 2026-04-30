import asyncio
import json
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import (
    HFPublishRequest, HFPublishResponse, PageSummary, RunCreateRequest,
    RunCreateResponse, RunDetail, RunDocumentDetail, RunDocumentSummary,
    RunSummary, StagedDocumentInfo,
)
from ocr_pipeline.services.db import get_db
from ocr_pipeline.services.hf_publisher import publish_run_to_hf
from ocr_pipeline.services.pdf_renderer import PDFRenderer
from ocr_pipeline.services.run_orchestrator import get_orchestrator
from ocr_pipeline.services.startup import model_readiness


router = APIRouter()

# Identifiers from clients are restricted to safe characters at the route layer.
ID = PathParam(..., pattern=r"^[A-Za-z0-9_\-]{1,64}$")

ARTIFACT_FIELDS = {
    "raw_txt": ("artifact_raw_txt", "text/plain"),
    "txt": ("artifact_clean_txt", "text/plain"),
    "md": ("artifact_markdown", "text/markdown"),
    "meta": ("artifact_meta_json", "application/json"),
    "source": ("artifact_source_pdf", "application/pdf"),
}
TEXT_MODES = {
    "raw": "artifact_raw_txt", "raw_txt": "artifact_raw_txt",
    "txt": "artifact_clean_txt", "clean": "artifact_clean_txt",
    "md": "artifact_markdown", "markdown": "artifact_markdown",
}


def _parse_str_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def _run_summary(row: dict) -> RunSummary:
    return RunSummary(
        id=row["id"],
        name=row.get("name"),
        status=row["status"],
        stage=row.get("stage"),
        progress=row.get("progress") or 0.0,
        documents_total=row.get("documents_total") or 0,
        documents_completed=row.get("documents_completed") or 0,
        pages_total=row.get("pages_total") or 0,
        pages_completed=row.get("pages_completed") or 0,
        strip_refs=bool(row.get("strip_refs")),
        export_parquet=bool(row.get("export_parquet")),
        pipeline_version=row.get("pipeline_version"),
        model_used=row.get("model_used"),
        error=row.get("error"),
        dataset_bundle=row.get("dataset_bundle"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )


def _doc_summary(row: dict) -> RunDocumentSummary:
    return RunDocumentSummary(
        document_id=row["document_id"],
        filename=row.get("document_filename") or "",
        file_sha256=row.get("file_sha256") or "",
        file_size_bytes=row.get("file_size_bytes") or 0,
        status=row["status"],
        total_pages=row.get("total_pages"),
        pages_pass=row.get("pages_pass") or 0,
        pages_warn=row.get("pages_warn") or 0,
        pages_fail=row.get("pages_fail") or 0,
        pages_empty=row.get("pages_empty") or 0,
        total_processing_time_ms=row.get("total_processing_time_ms") or 0.0,
        total_tokens_cl100k=row.get("total_tokens_cl100k") or 0,
        dominant_script=row.get("dominant_script"),
        dominant_direction=row.get("dominant_direction"),
        languages_detected=_parse_str_list(row.get("languages_detected")),
        artifact_raw_txt=row.get("artifact_raw_txt"),
        artifact_clean_txt=row.get("artifact_clean_txt"),
        artifact_markdown=row.get("artifact_markdown"),
        artifact_meta_json=row.get("artifact_meta_json"),
        artifact_source_pdf=row.get("artifact_source_pdf"),
        source_run_id=row.get("source_run_id"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )


def _page_summary(row: dict) -> PageSummary:
    def _bool(v):
        return bool(v) if v is not None else None
    return PageSummary(
        page_num=row["page_num"],
        status=row["status"],
        validation_issues=_parse_str_list(row.get("validation_issues")),
        script_direction=row.get("script_direction"),
        primary_script=row.get("primary_script"),
        detected_languages=_parse_str_list(row.get("detected_languages")),
        token_count_cl100k=row.get("token_count_cl100k"),
        text_length_chars=row.get("text_length_chars"),
        text_length_words=row.get("text_length_words"),
        processing_time_ms=row.get("processing_time_ms"),
        extraction_mode=row.get("extraction_mode"),
        extraction_attempt=row.get("extraction_attempt"),
        dpi_used=row.get("dpi_used"),
        has_embedded_text=_bool(row.get("has_embedded_text")),
        is_image_only=_bool(row.get("is_image_only")),
    )


async def _require_run(run_id: str) -> dict:
    run = await get_db().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


async def _require_doc(run_id: str, document_id: str) -> dict:
    rd = await get_db().get_run_document(run_id, document_id)
    if not rd:
        raise HTTPException(status_code=404, detail="Document not found in run")
    return rd


def _existing_path(rd: dict, field: str) -> Path:
    path_str = rd.get(field)
    if not path_str:
        raise HTTPException(status_code=404, detail="Artifact not yet available")
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact missing on disk")
    return path


@router.post("/api/runs", response_model=RunCreateResponse)
async def create_run(request: RunCreateRequest):
    if not model_readiness.ready:
        raise HTTPException(status_code=503, detail=f"Model server not ready: {model_readiness.status}")
    if not request.file_paths:
        raise HTTPException(status_code=400, detail="file_paths must not be empty")

    orchestrator = get_orchestrator()
    try:
        result = await orchestrator.create_run(
            request.file_paths,
            name=request.name,
            strip_refs=request.strip_refs,
            export_parquet=request.export_parquet,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    orchestrator.start(result, strip_refs=request.strip_refs, export_parquet=request.export_parquet)

    return RunCreateResponse(
        run_id=result.run_id,
        status="queued",
        documents_total=len(result.documents),
        pages_total_estimate=result.pages_total_estimate,
        documents=[
            StagedDocumentInfo(
                document_id=d.document_id,
                filename=d.filename,
                file_sha256=d.file_sha256,
                deduped=d.deduped,
                estimated_pages=d.estimated_pages,
            )
            for d in result.documents
        ],
    )


@router.get("/api/runs", response_model=list[RunSummary])
async def list_runs(limit: int = Query(50, ge=1, le=500)):
    return [_run_summary(r) for r in await get_db().list_runs(limit=limit)]


@router.get("/api/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str = ID):
    run = await _require_run(run_id)
    documents = await get_db().list_run_documents(run_id)
    return RunDetail(**_run_summary(run).model_dump(),
                     documents=[_doc_summary(d) for d in documents])


@router.delete("/api/runs/{run_id}")
async def delete_run(run_id: str = ID):
    run = await _require_run(run_id)
    if run["status"] == "processing":
        raise HTTPException(status_code=409, detail="Cannot delete a run that is still processing")
    await get_db().delete_run(run_id)
    return {"deleted": run_id}


@router.get("/api/runs/{run_id}/documents/{document_id}", response_model=RunDocumentDetail)
async def get_run_document(run_id: str = ID, document_id: str = ID):
    rd = await _require_doc(run_id, document_id)
    pages = await get_db().list_pages(run_id, document_id)
    return RunDocumentDetail(**_doc_summary(rd).model_dump(),
                             pages=[_page_summary(p) for p in pages])


@router.get("/api/runs/{run_id}/documents/{document_id}/text")
async def get_run_document_text(run_id: str = ID, document_id: str = ID, mode: str = "txt"):
    field = TEXT_MODES.get(mode)
    if not field:
        raise HTTPException(status_code=400, detail="Unsupported mode")
    path = _existing_path(await _require_doc(run_id, document_id), field)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.get("/api/runs/{run_id}/documents/{document_id}/meta")
async def get_run_document_meta(run_id: str = ID, document_id: str = ID):
    path = _existing_path(await _require_doc(run_id, document_id), "artifact_meta_json")
    return FileResponse(path, media_type="application/json")


@router.get("/api/runs/{run_id}/documents/{document_id}/download/{artifact}")
async def download_artifact(artifact: str, run_id: str = ID, document_id: str = ID):
    if artifact not in ARTIFACT_FIELDS:
        raise HTTPException(status_code=400, detail="Unsupported artifact")
    field, media_type = ARTIFACT_FIELDS[artifact]
    path = _existing_path(await _require_doc(run_id, document_id), field)
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/api/runs/{run_id}/documents/{document_id}/pages/{page_num}/image")
async def render_page_image(
    page_num: int,
    run_id: str = ID,
    document_id: str = ID,
    dpi: int = Query(120, ge=50, le=400),
):
    rd = await _require_doc(run_id, document_id)
    pdf_path_str = rd.get("artifact_source_pdf") or rd.get("document_source_path")
    if not pdf_path_str or not Path(pdf_path_str).exists():
        raise HTTPException(status_code=404, detail="Source PDF not available")

    try:
        image = await asyncio.to_thread(
            PDFRenderer().render_page, Path(pdf_path_str), page_num, dpi
        )
    except IndexError:
        raise HTTPException(status_code=404, detail="Page not found in PDF")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/api/runs/{run_id}/dataset/download")
async def download_dataset_bundle(run_id: str = ID):
    run = await _require_run(run_id)
    bundle = run.get("dataset_bundle")
    if not bundle or not Path(bundle).exists():
        raise HTTPException(status_code=404, detail="Dataset bundle not available")
    return FileResponse(bundle, media_type="application/zip", filename=Path(bundle).name)


@router.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str = ID, after_event_id: int = 0):
    await _require_run(run_id)
    orchestrator = get_orchestrator()

    async def gen():
        async for event in orchestrator.subscribe(run_id, after_event_id=after_event_id):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/api/runs/{run_id}/publish/hf", response_model=HFPublishResponse)
async def publish_to_hf(request: HFPublishRequest, run_id: str = ID):
    db = get_db()
    run = await _require_run(run_id)
    if run["status"] != "completed":
        raise HTTPException(status_code=409, detail="Run is not yet completed")

    documents = await db.list_run_documents(run_id)
    try:
        result = await publish_run_to_hf(
            run=run,
            documents=documents,
            dataset_dir=settings.runs_dir / run_id / "dataset",
            repo_id=request.repo_id,
            private=request.private,
            token=request.token,
            commit_message=request.commit_message,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}")
    return HFPublishResponse(**result)
