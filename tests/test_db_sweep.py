import asyncio

from ocr_pipeline.services.db import Database


def test_fail_orphan_runs_marks_processing_and_queued(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            for run_id in ("run-a", "run-b", "run-c"):
                await db.create_run(
                    run_id,
                    name=None,
                    documents_total=1,
                    pages_total_estimate=1,
                    strip_refs=False,
                    export_parquet=False,
                    pipeline_version="2.0.0",
                    model_used="m",
                )
            await db.update_run("run-a", status="processing", stage="ocr")
            # run-b stays queued
            await db.update_run(
                "run-c", status="completed", stage="completed", progress=1.0
            )

            affected = await db.fail_orphan_runs()
            assert affected == 2

            assert (await db.get_run("run-a"))["status"] == "failed"
            assert (await db.get_run("run-b"))["status"] == "failed"
            assert (await db.get_run("run-c"))["status"] == "completed"
            a = await db.get_run("run-a")
            assert a["error"] and a["completed_at"]
        finally:
            await db.close()

    asyncio.run(_scenario())


def test_fail_orphan_runs_marks_incomplete_documents_failed(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            await db.create_run(
                "run-a",
                name=None,
                documents_total=3,
                pages_total_estimate=3,
                strip_refs=False,
                export_parquet=False,
                pipeline_version="2.0.0",
                model_used="m",
            )
            for doc_id, status in (
                ("doc-done", "completed"),
                ("doc-active", "processing"),
                ("doc-waiting", "pending"),
            ):
                await db.upsert_document(
                    doc_id,
                    filename=f"{doc_id}.pdf",
                    source_path=f"/tmp/{doc_id}.pdf",
                    file_sha256=doc_id,
                    file_size_bytes=1,
                )
                await db.link_run_document("run-a", doc_id, status=status)
            await db.update_run("run-a", status="processing", stage="ocr")

            await db.fail_orphan_runs()

            docs = {
                doc["document_id"]: doc for doc in await db.list_run_documents("run-a")
            }
            assert docs["doc-done"]["status"] == "completed"
            assert docs["doc-active"]["status"] == "failed"
            assert docs["doc-waiting"]["status"] == "failed"
        finally:
            await db.close()

    asyncio.run(_scenario())


def test_failed_runs_normalize_incomplete_documents(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            await db.create_run(
                "run-a",
                name=None,
                documents_total=2,
                pages_total_estimate=2,
                strip_refs=False,
                export_parquet=False,
                pipeline_version="2.0.0",
                model_used="m",
            )
            for doc_id, status in (
                ("doc-active", "processing"),
                ("doc-waiting", "pending"),
            ):
                await db.upsert_document(
                    doc_id,
                    filename=f"{doc_id}.pdf",
                    source_path=f"/tmp/{doc_id}.pdf",
                    file_sha256=doc_id,
                    file_size_bytes=1,
                )
                await db.link_run_document("run-a", doc_id, status=status)
            await db.update_run("run-a", status="failed", stage="failed")

            affected = await db.fail_documents_for_failed_runs()

            assert affected == 2
            assert {doc["status"] for doc in await db.list_run_documents("run-a")} == {
                "failed"
            }
        finally:
            await db.close()

    asyncio.run(_scenario())
