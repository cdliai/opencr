from pathlib import Path

from fastapi import APIRouter, HTTPException

from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import ExtractRequest, ExtractResponse
from ocr_pipeline.services.batch_processor import BatchProcessor
from ocr_pipeline.services.startup import model_readiness

router = APIRouter()


@router.post("/api/extract", response_model=ExtractResponse)
async def extract_pdf(request: ExtractRequest):
    """Extract text from a single PDF."""
    if not model_readiness.ready:
        raise HTTPException(
            status_code=503,
            detail=f"Model server not ready: {model_readiness.status}",
        )

    pdf_path = Path(request.file_path)

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    if not pdf_path.suffix.lower() == ".pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    output_dir = Path(request.output_dir) if request.output_dir else settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    processor = BatchProcessor()
    doc_meta = await processor.process_document(pdf_path, output_dir)

    stem = pdf_path.stem
    return ExtractResponse(
        filename=doc_meta.filename,
        total_pages=doc_meta.total_pages,
        pages_pass=doc_meta.pages_pass,
        pages_warn=doc_meta.pages_warn,
        pages_fail=doc_meta.pages_fail,
        pages_empty=doc_meta.pages_empty,
        total_processing_time_ms=doc_meta.total_processing_time_ms,
        output_md=str(output_dir / f"{stem}.md"),
        output_meta=str(output_dir / f"{stem}.meta.json"),
    )
