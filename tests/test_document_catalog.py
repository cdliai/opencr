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
