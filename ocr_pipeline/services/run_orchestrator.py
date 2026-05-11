import asyncio
import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import fitz

from ocr_pipeline.config import settings
from ocr_pipeline.services.batch_processor import BatchProcessor
from ocr_pipeline.services.dataset_exporter import DatasetExporter, DocumentExport
from ocr_pipeline.services.db import Database
from ocr_pipeline.services.observability import observability
from ocr_pipeline.services.run_storage import RunStorage


logger = logging.getLogger("ocr_pipeline.orchestrator")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StagedDocument:
    document_id: str
    file_sha256: str
    filename: str
    source_path: Path
    deduped: bool
    estimated_pages: int


@dataclass
class CreateRunResult:
    run_id: str
    documents: list[StagedDocument]
    pages_total_estimate: int


class RunOrchestrator:
    """Owns run lifecycle: staging, execution, event broadcasting, DB state."""

    def __init__(self, db: Database, storage: RunStorage):
        self.db = db
        self.storage = storage
        self._listeners: dict[str, set[asyncio.Queue]] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---------- staging ----------

    @staticmethod
    def _hash_file_sync(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _count_pages(pdf_path: Path) -> int:
        with fitz.open(str(pdf_path)) as doc:
            return len(doc)

    async def _stage_document(self, file_path: Path) -> StagedDocument:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        sha = await asyncio.to_thread(self._hash_file_sync, file_path)
        document_id = sha[:16]
        canonical = self.storage.source_pdf_path(document_id)
        existing = await self.db.get_document_by_sha(sha)

        if not canonical.exists():
            self.storage.sources_dir().mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.copyfile, file_path, canonical)

        size = (await asyncio.to_thread(canonical.stat)).st_size
        try:
            page_count = await asyncio.to_thread(self._count_pages, canonical)
        except Exception:
            page_count = 0

        await self.db.upsert_document(
            document_id,
            filename=file_path.name,
            source_path=str(canonical),
            file_sha256=sha,
            file_size_bytes=size,
            total_pages=page_count or None,
        )

        return StagedDocument(
            document_id=document_id,
            file_sha256=sha,
            filename=file_path.name,
            source_path=canonical,
            deduped=existing is not None,
            estimated_pages=page_count,
        )

    async def create_run(
        self,
        file_paths: list[str],
        *,
        name: str | None = None,
        strip_refs: bool = False,
        export_parquet: bool = True,
    ) -> CreateRunResult:
        if not file_paths:
            raise ValueError("file_paths must not be empty")

        run_id = uuid.uuid4().hex[:12]
        self.storage.ensure_run_dirs(run_id)

        staged = [await self._stage_document(Path(fp)) for fp in file_paths]
        pages_total = sum(s.estimated_pages for s in staged)

        await self.db.create_run(
            run_id,
            name=name,
            documents_total=len(staged),
            pages_total_estimate=pages_total,
            strip_refs=strip_refs,
            export_parquet=export_parquet,
            pipeline_version=settings.pipeline_version,
            model_used=settings.model_name,
        )
        for s in staged:
            await self.db.link_run_document(run_id, s.document_id, status="pending")

        observability.job_created()
        return CreateRunResult(
            run_id=run_id, documents=staged, pages_total_estimate=pages_total
        )

    # ---------- execution ----------

    def start(
        self, result: CreateRunResult, *, strip_refs: bool, export_parquet: bool
    ) -> asyncio.Task:
        task = asyncio.create_task(
            self._run(result, strip_refs=strip_refs, export_parquet=export_parquet)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run(
        self,
        result: CreateRunResult,
        *,
        strip_refs: bool,
        export_parquet: bool,
    ) -> None:
        run_id = result.run_id
        started_at = _now()
        await self.db.update_run(
            run_id, status="processing", stage="ocr", started_at=started_at
        )
        await self._emit(run_id, "run_started", {"started_at": started_at})

        pages_total = result.pages_total_estimate
        pages_completed = 0
        documents_meta: list = []

        async def page_event(event: dict) -> None:
            nonlocal pages_completed
            etype = event.get("type")
            if etype == "page_complete":
                pages_completed += 1
                progress = (pages_completed / pages_total) if pages_total else 0
                await self.db.update_run(
                    run_id,
                    pages_completed=pages_completed,
                    progress=min(0.99, progress),
                )
                observability.page_completed(
                    processing_time_ms=event.get("processing_time_ms", 0.0),
                    token_count=event.get("token_count", 0),
                    validation_status=event.get("validation_status", "pass"),
                )
            elif etype == "page_retry":
                observability.page_retry()
            await self._emit(run_id, etype, event)

        try:
            for staged in result.documents:
                paths = self.storage.artifact_paths(
                    run_id, staged.document_id, staged.filename
                )
                processor = BatchProcessor(
                    self.db, event_callback=page_event, strip_refs=strip_refs
                )
                doc_meta = await processor.process_document(
                    staged.source_path,
                    run_id=run_id,
                    document_id=staged.document_id,
                    file_sha256=staged.file_sha256,
                    artifact_paths=paths,
                )
                documents_meta.append((staged.document_id, paths, doc_meta))
                observability.document_completed()
                await self.db.update_run(
                    run_id, documents_completed=len(documents_meta)
                )

            dataset_bundle = await self._maybe_export(
                run_id, documents_meta, export_parquet
            )

            completed_at = _now()
            await self.db.update_run(
                run_id,
                status="completed",
                stage="completed",
                progress=1.0,
                pages_completed=pages_total,
                dataset_bundle=dataset_bundle,
                completed_at=completed_at,
            )
            observability.job_completed()
            await self._emit(
                run_id,
                "run_complete",
                {
                    "completed_at": completed_at,
                    "documents_total": len(result.documents),
                    "documents_completed": len(documents_meta),
                    "pages_total": pages_total,
                    "dataset_bundle": dataset_bundle,
                    **self._aggregate_totals(documents_meta),
                },
            )
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            await self.db.update_run(
                run_id,
                status="failed",
                stage="failed",
                error=str(exc),
                completed_at=_now(),
            )
            observability.job_failed()
            await self._emit(run_id, "run_failed", {"error": str(exc)})

    async def _maybe_export(
        self, run_id: str, documents_meta: list, export_parquet: bool
    ) -> str | None:
        if not (export_parquet and documents_meta):
            return None
        await self.db.update_run(run_id, stage="exporting")
        await self._emit(run_id, "dataset_export_started", {})
        exports = []
        for did, paths, meta in documents_meta:
            exports.append(
                DocumentExport(
                    metadata=meta,
                    document_id=did,
                    artifact_paths=paths,
                    catalog_metadata=await self.db.get_document(did) or {},
                )
            )
        result = await asyncio.to_thread(
            DatasetExporter(self.storage.dataset_dir(run_id)).export_run,
            run_id,
            exports,
        )
        return str(result.bundle)

    @staticmethod
    def _aggregate_totals(documents_meta) -> dict:
        return {
            "pages_pass": sum(m.pages_pass for _, _, m in documents_meta),
            "pages_warn": sum(m.pages_warn for _, _, m in documents_meta),
            "pages_fail": sum(m.pages_fail for _, _, m in documents_meta),
            "pages_empty": sum(m.pages_empty for _, _, m in documents_meta),
            "total_time_ms": round(
                sum(m.total_processing_time_ms for _, _, m in documents_meta), 1
            ),
        }

    # ---------- events ----------

    async def _emit(self, run_id: str, event_type: str, payload: dict) -> None:
        full = {"type": event_type, "run_id": run_id, **payload}
        full["event_id"] = await self.db.append_event(run_id, event_type, full)
        run = await self.db.get_run(run_id)
        if run:
            full.setdefault("status", run["status"])
            full.setdefault("stage", run["stage"])
            full.setdefault("progress_percent", round((run["progress"] or 0) * 100, 1))

        for queue in list(self._listeners.get(run_id, ())):
            try:
                queue.put_nowait(full)
            except asyncio.QueueFull:
                logger.warning("Listener queue full for run %s; dropping event", run_id)

    async def subscribe(
        self, run_id: str, after_event_id: int = 0
    ) -> AsyncIterator[dict]:
        for ev in await self.db.list_events(run_id, after_id=after_event_id):
            yield {**ev["payload"], "event_id": ev["id"]}

        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._listeners.setdefault(run_id, set()).add(queue)

        run = await self.db.get_run(run_id)
        terminal = run and run["status"] in ("completed", "failed")

        try:
            while True:
                if terminal and queue.empty():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"type": "keepalive", "run_id": run_id}
                    continue
                yield event
                if event.get("type") in ("run_complete", "run_failed"):
                    return
        finally:
            self._listeners[run_id].discard(queue)
            if not self._listeners[run_id]:
                self._listeners.pop(run_id, None)


_orchestrator: RunOrchestrator | None = None


def init_orchestrator(db: Database, storage: RunStorage) -> RunOrchestrator:
    global _orchestrator
    _orchestrator = RunOrchestrator(db, storage)
    return _orchestrator


def get_orchestrator() -> RunOrchestrator:
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator
