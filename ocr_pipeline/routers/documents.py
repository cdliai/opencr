from fastapi import APIRouter, HTTPException, Path as PathParam, Query

from ocr_pipeline.models.schemas import (
    BulkDocumentUpdate,
    DocumentSummary,
    DocumentUpdate,
    RunSummary,
)
from ocr_pipeline.routers.runs import _run_summary
from ocr_pipeline.services.db import get_db


router = APIRouter()

ID = PathParam(..., pattern=r"^[A-Za-z0-9_\-]{1,64}$")


def _document_summary(row: dict) -> DocumentSummary:
    data = dict(row)
    data["display_title"] = (
        data.get("display_title") or data.get("pdf_title") or data["filename"]
    )
    data["metadata_complete"] = bool(data.get("metadata_complete"))
    return DocumentSummary(**data)


@router.get("/api/documents", response_model=list[DocumentSummary])
async def list_documents(limit: int = Query(500, ge=1, le=1000)):
    return [_document_summary(d) for d in await get_db().list_documents(limit=limit)]


@router.patch("/api/documents/bulk", response_model=list[DocumentSummary])
async def update_documents_bulk(payload: BulkDocumentUpdate):
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="document_ids must not be empty")
    db = get_db()
    try:
        await db.update_documents_metadata(
            payload.document_ids,
            group_path=payload.group_path,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Document not found: {exc.args[0]}"
        )
    documents = await db.list_documents(limit=1000)
    by_id = {doc["id"]: doc for doc in documents}
    return [
        _document_summary(by_id[document_id]) for document_id in payload.document_ids
    ]


@router.get("/api/documents/{document_id}", response_model=DocumentSummary)
async def get_document(document_id: str = ID):
    doc = await get_db().get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    listed = [
        d for d in await get_db().list_documents(limit=1000) if d["id"] == document_id
    ]
    return _document_summary(listed[0] if listed else doc)


@router.patch("/api/documents/{document_id}", response_model=DocumentSummary)
async def update_document(payload: DocumentUpdate, document_id: str = ID):
    try:
        await get_db().update_document_metadata(
            document_id,
            **payload.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found")
    return await get_document(document_id)


@router.get("/api/documents/{document_id}/runs", response_model=list[RunSummary])
async def list_document_runs(document_id: str = ID):
    if not await get_db().get_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return [_run_summary(r) for r in await get_db().list_document_runs(document_id)]
