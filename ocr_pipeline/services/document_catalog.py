import asyncio
import hashlib
from pathlib import Path

import fitz

from ocr_pipeline.services.db import Database


def _hash_file_sync(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_pages_sync(path: Path) -> int:
    with fitz.open(str(path)) as doc:
        return len(doc)


async def catalog_pdf(db: Database, path: Path, *, filename: str | None = None) -> dict:
    sha = await asyncio.to_thread(_hash_file_sync, path)
    try:
        page_count = await asyncio.to_thread(_count_pages_sync, path)
    except Exception:
        page_count = 0
    return await db.upsert_document(
        sha[:16],
        filename=filename or path.name,
        source_path=str(path),
        file_sha256=sha,
        file_size_bytes=(await asyncio.to_thread(path.stat)).st_size,
        total_pages=page_count or None,
    )
