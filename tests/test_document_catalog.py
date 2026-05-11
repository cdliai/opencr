import asyncio

from ocr_pipeline.services.db import Database


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
            assert updated["document_date_label"] == "1900s"
            assert updated["document_date_precision"] == "century"

            docs = await db.list_documents()
            assert docs[0]["id"] == "doc-1"
            assert docs[0]["display_title"] == "source.pdf"
            assert docs[0]["metadata_complete"] == 1
        finally:
            await db.close()

    asyncio.run(_scenario())
