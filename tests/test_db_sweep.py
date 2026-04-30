import asyncio

from ocr_pipeline.services.db import Database


def test_fail_orphan_runs_marks_processing_and_queued(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            for run_id in ("run-a", "run-b", "run-c"):
                await db.create_run(
                    run_id, name=None, documents_total=1, pages_total_estimate=1,
                    strip_refs=False, export_parquet=False,
                    pipeline_version="2.0.0", model_used="m",
                )
            await db.update_run("run-a", status="processing", stage="ocr")
            # run-b stays queued
            await db.update_run("run-c", status="completed", stage="completed", progress=1.0)

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
