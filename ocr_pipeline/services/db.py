import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import aiosqlite

logger = logging.getLogger("ocr_pipeline.db")


DOCUMENT_METADATA_FIELDS = {
    "display_title",
    "group_path",
    "author",
    "work",
    "book",
    "document_date_label",
    "document_date_precision",
    "language",
    "script",
    "license",
    "source_citation",
    "notes",
    "tags_json",
}

DOCUMENT_METADATA_COLUMNS = {
    "display_title": "TEXT",
    "group_path": "TEXT",
    "author": "TEXT",
    "work": "TEXT",
    "book": "TEXT",
    "document_date_label": "TEXT",
    "document_date_precision": "TEXT",
    "language": "TEXT",
    "script": "TEXT",
    "license": "TEXT",
    "source_citation": "TEXT",
    "notes": "TEXT",
    "tags_json": "TEXT",
    "catalog_updated_at": "TEXT",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0,
    documents_total INTEGER NOT NULL DEFAULT 0,
    documents_completed INTEGER NOT NULL DEFAULT 0,
    pages_total INTEGER NOT NULL DEFAULT 0,
    pages_completed INTEGER NOT NULL DEFAULT 0,
    strip_refs INTEGER NOT NULL DEFAULT 0,
    export_parquet INTEGER NOT NULL DEFAULT 0,
    pipeline_version TEXT,
    model_used TEXT,
    error TEXT,
    dataset_bundle TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    source_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    file_size_bytes INTEGER NOT NULL,
    total_pages INTEGER,
    pdf_title TEXT,
    pdf_author TEXT,
    pdf_creation_date TEXT,
    pdf_producer TEXT,
    display_title TEXT,
    group_path TEXT,
    author TEXT,
    work TEXT,
    book TEXT,
    document_date_label TEXT,
    document_date_precision TEXT,
    language TEXT,
    script TEXT,
    license TEXT,
    source_citation TEXT,
    notes TEXT,
    tags_json TEXT,
    catalog_updated_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_documents (
    run_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,
    total_pages INTEGER,
    pages_pass INTEGER NOT NULL DEFAULT 0,
    pages_warn INTEGER NOT NULL DEFAULT 0,
    pages_fail INTEGER NOT NULL DEFAULT 0,
    pages_empty INTEGER NOT NULL DEFAULT 0,
    total_processing_time_ms REAL NOT NULL DEFAULT 0,
    total_tokens_cl100k INTEGER NOT NULL DEFAULT 0,
    dominant_script TEXT,
    dominant_direction TEXT,
    languages_detected TEXT,
    artifact_raw_txt TEXT,
    artifact_clean_txt TEXT,
    artifact_markdown TEXT,
    artifact_meta_json TEXT,
    artifact_source_pdf TEXT,
    source_run_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (run_id, document_id),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pages (
    run_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    page_num INTEGER NOT NULL,
    status TEXT NOT NULL,
    validation_issues TEXT,
    script_direction TEXT,
    primary_script TEXT,
    detected_languages TEXT,
    token_count_cl100k INTEGER,
    text_length_chars INTEGER,
    text_length_words INTEGER,
    processing_time_ms REAL,
    extraction_mode TEXT,
    extraction_attempt INTEGER,
    dpi_used INTEGER,
    has_embedded_text INTEGER,
    is_image_only INTEGER,
    PRIMARY KEY (run_id, document_id, page_num),
    FOREIGN KEY (run_id, document_id)
        REFERENCES run_documents(run_id, document_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_run_documents_run_id ON run_documents(run_id);
CREATE INDEX IF NOT EXISTS idx_pages_run_doc ON pages(run_id, document_id, page_num);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: aiosqlite.Row | None) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


class Database:
    """Async SQLite registry for runs, documents, pages, and events."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()
        logger.info("Database ready at %s", self.db_path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected; call connect() first.")
        return self._conn

    async def _migrate(self) -> None:
        """Apply additive migrations for existing local SQLite catalogs."""
        async with self.conn.execute("PRAGMA table_info(documents)") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for name, column_type in DOCUMENT_METADATA_COLUMNS.items():
            if name not in existing:
                await self.conn.execute(
                    f"ALTER TABLE documents ADD COLUMN {name} {column_type}"
                )

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[aiosqlite.Cursor]:
        async with self.conn.cursor() as cur:
            yield cur

    # ---------- runs ----------

    async def create_run(
        self,
        run_id: str,
        *,
        name: str | None,
        documents_total: int,
        pages_total_estimate: int,
        strip_refs: bool,
        export_parquet: bool,
        pipeline_version: str,
        model_used: str,
    ) -> dict[str, Any]:
        now = _now()
        await self.conn.execute(
            """
            INSERT INTO runs (
                id, name, status, stage, progress,
                documents_total, documents_completed,
                pages_total, pages_completed,
                strip_refs, export_parquet,
                pipeline_version, model_used,
                created_at
            ) VALUES (?, ?, 'queued', 'queued', 0, ?, 0, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                name,
                documents_total,
                pages_total_estimate,
                int(strip_refs),
                int(export_parquet),
                pipeline_version,
                model_used,
                now,
            ),
        )
        await self.conn.commit()
        return await self.get_run(run_id)  # type: ignore[return-value]

    async def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        values.append(run_id)
        await self.conn.execute(f"UPDATE runs SET {cols} WHERE id = ?", values)
        await self.conn.commit()

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row)

    async def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    async def delete_run(self, run_id: str) -> None:
        await self.conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        await self.conn.commit()

    async def fail_orphan_runs(self) -> int:
        """Mark any run still in `processing`/`queued` as failed. Called once
        on startup so a crashed process does not leave runs visibly live."""
        async with self.conn.execute(
            "SELECT id FROM runs WHERE status IN ('queued', 'processing')"
        ) as cur:
            run_ids = [row["id"] for row in await cur.fetchall()]
        for run_id in run_ids:
            await self.fail_incomplete_run_documents(run_id)
        cur = await self.conn.execute(
            """
            UPDATE runs
               SET status = 'failed',
                   stage = 'failed',
                   error = COALESCE(error, 'Process exited before run finished'),
                   completed_at = COALESCE(completed_at, ?)
             WHERE status IN ('queued', 'processing')
            """,
            (_now(),),
        )
        await self.conn.commit()
        affected = cur.rowcount or 0
        await cur.close()
        return affected

    async def fail_incomplete_run_documents(self, run_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE run_documents
               SET status = 'failed',
                   completed_at = COALESCE(completed_at, ?)
             WHERE run_id = ?
               AND status != 'completed'
            """,
            (_now(), run_id),
        )
        await self.conn.commit()

    async def fail_documents_for_failed_runs(self) -> int:
        cur = await self.conn.execute(
            """
            UPDATE run_documents
               SET status = 'failed',
                   completed_at = COALESCE(completed_at, ?)
             WHERE status != 'completed'
               AND run_id IN (SELECT id FROM runs WHERE status = 'failed')
            """,
            (_now(),),
        )
        await self.conn.commit()
        affected = cur.rowcount or 0
        await cur.close()
        return affected

    # ---------- documents (content-addressed) ----------

    async def upsert_document(
        self,
        document_id: str,
        *,
        filename: str,
        source_path: str,
        file_sha256: str,
        file_size_bytes: int,
        total_pages: int | None = None,
        pdf_title: str | None = None,
        pdf_author: str | None = None,
        pdf_creation_date: str | None = None,
        pdf_producer: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        await self.conn.execute(
            """
            INSERT INTO documents (
                id, filename, source_path, file_sha256, file_size_bytes,
                total_pages, pdf_title, pdf_author, pdf_creation_date, pdf_producer,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                filename = excluded.filename,
                source_path = excluded.source_path,
                file_size_bytes = excluded.file_size_bytes,
                last_seen_at = excluded.last_seen_at,
                total_pages = COALESCE(excluded.total_pages, documents.total_pages),
                pdf_title = COALESCE(excluded.pdf_title, documents.pdf_title),
                pdf_author = COALESCE(excluded.pdf_author, documents.pdf_author),
                pdf_creation_date = COALESCE(excluded.pdf_creation_date, documents.pdf_creation_date),
                pdf_producer = COALESCE(excluded.pdf_producer, documents.pdf_producer)
            """,
            (
                document_id,
                filename,
                source_path,
                file_sha256,
                file_size_bytes,
                total_pages,
                pdf_title,
                pdf_author,
                pdf_creation_date,
                pdf_producer,
                now,
                now,
            ),
        )
        await self.conn.commit()
        return await self.get_document(document_id)  # type: ignore[return-value]

    async def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ) as cur:
            return _row_to_dict(await cur.fetchone())

    async def list_documents(self, limit: int = 500) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT d.id, d.filename, d.source_path, d.file_sha256, d.file_size_bytes,
                   d.total_pages, d.pdf_title, d.pdf_author, d.pdf_creation_date, d.pdf_producer,
                   d.group_path, d.author, d.work, d.book, d.document_date_label, d.document_date_precision,
                   d.language, d.script, d.license, d.source_citation, d.notes, d.tags_json,
                   d.catalog_updated_at, d.first_seen_at, d.last_seen_at,
                   COALESCE(NULLIF(d.display_title, ''), NULLIF(d.pdf_title, ''), d.filename)
                       AS display_title,
                   CASE
                     WHEN COALESCE(d.author, '') != ''
                      AND COALESCE(d.work, '') != ''
                      AND COALESCE(d.document_date_label, '') != ''
                      AND COALESCE(d.document_date_precision, '') != ''
                      AND COALESCE(d.language, '') != ''
                      AND COALESCE(d.script, '') != ''
                      AND COALESCE(d.license, '') != ''
                     THEN 1 ELSE 0
                   END AS metadata_complete,
                   (
                     SELECT r.id
                     FROM run_documents rd
                     JOIN runs r ON r.id = rd.run_id
                     WHERE rd.document_id = d.id
                     ORDER BY r.created_at DESC
                     LIMIT 1
                   ) AS latest_run_id,
                   (
                     SELECT r.status
                     FROM run_documents rd
                     JOIN runs r ON r.id = rd.run_id
                     WHERE rd.document_id = d.id
                     ORDER BY r.created_at DESC
                     LIMIT 1
                   ) AS latest_run_status
            FROM documents d
            ORDER BY d.last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    async def update_document_metadata(
        self, document_id: str, **fields: Any
    ) -> dict[str, Any]:
        clean = {k: v for k, v in fields.items() if k in DOCUMENT_METADATA_FIELDS}
        if clean:
            clean["catalog_updated_at"] = _now()
            cols = ", ".join(f"{k} = ?" for k in clean)
            values = [*clean.values(), document_id]
            cur = await self.conn.execute(
                f"UPDATE documents SET {cols} WHERE id = ?",
                values,
            )
            await self.conn.commit()
            affected = cur.rowcount or 0
            await cur.close()
            if not affected:
                raise KeyError(document_id)

        doc = await self.get_document(document_id)
        if not doc:
            raise KeyError(document_id)
        return doc

    async def update_documents_metadata(
        self, document_ids: list[str], **fields: Any
    ) -> list[dict[str, Any]]:
        if not document_ids:
            return []
        clean = {k: v for k, v in fields.items() if k in DOCUMENT_METADATA_FIELDS}
        placeholders = ", ".join("?" for _ in document_ids)
        async with self.conn.execute(
            f"SELECT id FROM documents WHERE id IN ({placeholders})",
            document_ids,
        ) as cur:
            existing = {row["id"] for row in await cur.fetchall()}
        missing = [
            document_id for document_id in document_ids if document_id not in existing
        ]
        if missing:
            raise KeyError(missing[0])
        if clean:
            clean["catalog_updated_at"] = _now()
            cols = ", ".join(f"{k} = ?" for k in clean)
            values = [*clean.values()]
            for document_id in document_ids:
                await self.conn.execute(
                    f"UPDATE documents SET {cols} WHERE id = ?",
                    [*values, document_id],
                )
            await self.conn.commit()
        docs = []
        for document_id in document_ids:
            doc = await self.get_document(document_id)
            if doc:
                docs.append(doc)
        return docs

    async def list_document_runs(self, document_id: str) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT r.*, rd.status AS document_status, rd.pages_pass, rd.pages_warn, rd.pages_fail
            FROM run_documents rd
            JOIN runs r ON r.id = rd.run_id
            WHERE rd.document_id = ?
            ORDER BY r.created_at DESC
            """,
            (document_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    async def get_document_by_sha(self, file_sha256: str) -> Optional[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM documents WHERE file_sha256 = ?", (file_sha256,)
        ) as cur:
            return _row_to_dict(await cur.fetchone())

    # ---------- run_documents ----------

    async def link_run_document(
        self,
        run_id: str,
        document_id: str,
        *,
        status: str = "pending",
        source_run_id: str | None = None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO run_documents (run_id, document_id, status, source_run_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, document_id) DO UPDATE SET
                status = excluded.status,
                source_run_id = excluded.source_run_id
            """,
            (run_id, document_id, status, source_run_id),
        )
        await self.conn.commit()

    async def update_run_document(
        self, run_id: str, document_id: str, **fields: Any
    ) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        values.extend([run_id, document_id])
        await self.conn.execute(
            f"UPDATE run_documents SET {cols} WHERE run_id = ? AND document_id = ?",
            values,
        )
        await self.conn.commit()

    async def list_run_documents(self, run_id: str) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT rd.*, d.filename AS document_filename, d.file_sha256, d.file_size_bytes,
                   d.source_path AS document_source_path
            FROM run_documents rd
            JOIN documents d ON d.id = rd.document_id
            WHERE rd.run_id = ?
            ORDER BY rd.started_at IS NULL, rd.started_at
            """,
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    async def get_run_document(
        self, run_id: str, document_id: str
    ) -> Optional[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT rd.*, d.filename AS document_filename, d.file_sha256, d.file_size_bytes,
                   d.source_path AS document_source_path
            FROM run_documents rd
            JOIN documents d ON d.id = rd.document_id
            WHERE rd.run_id = ? AND rd.document_id = ?
            """,
            (run_id, document_id),
        ) as cur:
            return _row_to_dict(await cur.fetchone())

    # ---------- pages ----------

    async def upsert_page(
        self,
        run_id: str,
        document_id: str,
        page_num: int,
        **fields: Any,
    ) -> None:
        defaults = {
            "status": "pending",
            "validation_issues": None,
            "script_direction": None,
            "primary_script": None,
            "detected_languages": None,
            "token_count_cl100k": None,
            "text_length_chars": None,
            "text_length_words": None,
            "processing_time_ms": None,
            "extraction_mode": None,
            "extraction_attempt": None,
            "dpi_used": None,
            "has_embedded_text": None,
            "is_image_only": None,
        }
        defaults.update(fields)
        for list_key in ("validation_issues", "detected_languages"):
            v = defaults.get(list_key)
            if isinstance(v, list):
                defaults[list_key] = json.dumps(v, ensure_ascii=False)
        for bool_key in ("has_embedded_text", "is_image_only"):
            v = defaults.get(bool_key)
            if isinstance(v, bool):
                defaults[bool_key] = int(v)
        cols = list(defaults.keys())
        placeholders = ", ".join(["?"] * (3 + len(cols)))
        update_clauses = ", ".join(f"{c} = excluded.{c}" for c in cols)
        await self.conn.execute(
            f"""
            INSERT INTO pages (run_id, document_id, page_num, {", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(run_id, document_id, page_num) DO UPDATE SET {update_clauses}
            """,
            [run_id, document_id, page_num, *defaults.values()],
        )
        await self.conn.commit()

    async def list_pages(self, run_id: str, document_id: str) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT * FROM pages
            WHERE run_id = ? AND document_id = ?
            ORDER BY page_num
            """,
            (run_id, document_id),
        ) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    # ---------- events ----------

    async def append_event(
        self, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> int:
        now = _now()
        cur = await self.conn.execute(
            "INSERT INTO run_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (
                run_id,
                event_type,
                json.dumps(payload, ensure_ascii=False, default=str),
                now,
            ),
        )
        await self.conn.commit()
        last_id = cur.lastrowid or 0
        await cur.close()
        return last_id

    async def list_events(
        self, run_id: str, after_id: int = 0, limit: int = 1000
    ) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT id, event_type, payload, created_at
            FROM run_events
            WHERE run_id = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (run_id, after_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]


_db: Database | None = None


def init_database(db_path: Path) -> Database:
    global _db
    _db = Database(db_path)
    return _db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized; call init_database() first.")
    return _db
