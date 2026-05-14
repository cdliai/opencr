import asyncio
import hashlib

from ocr_pipeline.services.db import Database
from ocr_pipeline.services.run_orchestrator import RunOrchestrator
from ocr_pipeline.services.run_storage import RunStorage


def test_document_metadata_can_be_updated_and_listed(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            await db.upsert_document(
                "doc-1",
                filename="source.pdf",
                source_path="/tmp/source.pdf",
                file_sha256="abc",
                file_size_bytes=123,
                total_pages=4,
            )

            updated = await db.update_document_metadata(
                "doc-1",
                group_path="Ottoman/Seyahatname",
                author="Evliyâ Çelebi",
                work="Seyahatnâme",
                book="1",
                document_date_label="1900s",
                document_date_precision="century",
                language="ota-Latn,tr",
                script="latin_extended",
                license="cc-by-4.0",
            )

            assert updated["author"] == "Evliyâ Çelebi"
            assert updated["group_path"] == "Ottoman/Seyahatname"
            assert updated["document_date_label"] == "1900s"
            assert updated["document_date_precision"] == "century"

            docs = await db.list_documents()
            assert docs[0]["id"] == "doc-1"
            assert docs[0]["display_title"] == "source.pdf"
            assert docs[0]["metadata_complete"] == 1
        finally:
            await db.close()

    asyncio.run(_scenario())


def test_bulk_document_metadata_validates_before_writing(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            await db.upsert_document(
                "doc-1",
                filename="source.pdf",
                source_path="/tmp/source.pdf",
                file_sha256="abc",
                file_size_bytes=123,
            )

            try:
                await db.update_documents_metadata(
                    ["doc-1", "missing"],
                    group_path="Should/Not/Write",
                )
            except KeyError:
                pass
            else:
                raise AssertionError("expected missing document to fail")

            doc = await db.get_document("doc-1")
            assert doc["group_path"] is None
        finally:
            await db.close()

    asyncio.run(_scenario())


def test_run_staging_preserves_catalog_filename_for_canonical_pdf(tmp_path):
    async def _scenario():
        db = Database(tmp_path / "opencr.sqlite")
        await db.connect()
        try:
            storage = RunStorage(output_root=tmp_path, runs_root=tmp_path / "runs")
            content = b"%PDF-1.4\n"
            sha = hashlib.sha256(content).hexdigest()
            document_id = sha[:16]
            canonical = storage.source_pdf_path(document_id)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(content)

            await db.upsert_document(
                document_id,
                filename="YUNANISTAN-LA-BARIS-ANDLASMASI.pdf",
                source_path=str(canonical),
                file_sha256=sha,
                file_size_bytes=len(content),
            )

            staged = await RunOrchestrator(db, storage)._stage_document(canonical)
            doc = await db.get_document(document_id)

            assert staged.filename == "YUNANISTAN-LA-BARIS-ANDLASMASI.pdf"
            assert doc["filename"] == "YUNANISTAN-LA-BARIS-ANDLASMASI.pdf"
        finally:
            await db.close()

    asyncio.run(_scenario())
