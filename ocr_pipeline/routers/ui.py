"""Static-friendly endpoints for input file management. Output/dataset listing
moved to /api/runs."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import FileInfo


router = APIRouter()


@router.post("/api/upload")
async def upload_pdf(file: UploadFile):
    """Accept a multipart PDF upload and save to input directory."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    safe_name = Path(file.filename).name
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    settings.input_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.input_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)

    return {"filename": safe_name, "size": len(content), "path": str(dest)}


@router.get("/api/files/input", response_model=list[FileInfo])
async def list_input_files():
    """List PDF files in the input directory."""
    input_dir = settings.input_dir
    if not input_dir.exists():
        return []

    files = []
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.suffix.lower() == ".pdf":
            stat = p.stat()
            files.append(FileInfo(
                name=p.name,
                size=stat.st_size,
                modified=stat.st_mtime,
                path=str(p),
            ))
    return files
