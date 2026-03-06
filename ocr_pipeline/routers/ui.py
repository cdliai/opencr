from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from ocr_pipeline.config import settings
from ocr_pipeline.models.schemas import FileInfo, OutputFileInfo

router = APIRouter()


def _safe_stem(stem: str) -> str:
    """Reject path traversal attempts."""
    if "/" in stem or "\\" in stem or ".." in stem or stem != Path(stem).name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return stem


@router.post("/api/upload")
async def upload_pdf(file: UploadFile):
    """Accept a multipart PDF upload and save to input directory."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    safe_name = Path(file.filename).name
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    dest = settings.input_dir / safe_name
    settings.input_dir.mkdir(parents=True, exist_ok=True)

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


@router.get("/api/files/output", response_model=list[OutputFileInfo])
async def list_output_files():
    """List extraction results (paired .md + .meta.json)."""
    output_dir = settings.output_dir
    if not output_dir.exists():
        return []

    md_files = {p.stem: p for p in output_dir.iterdir() if p.suffix == ".md"}
    results = []
    for stem, md_path in sorted(md_files.items()):
        meta_path = output_dir / f"{stem}.meta.json"
        md_stat = md_path.stat()
        results.append(OutputFileInfo(
            stem=stem,
            md_size=md_stat.st_size,
            meta_exists=meta_path.exists(),
            modified=md_stat.st_mtime,
        ))
    return results


@router.get("/api/files/output/{stem}.md")
async def get_output_md(stem: str):
    """Serve markdown content for a given stem."""
    stem = _safe_stem(stem)
    md_path = settings.output_dir / f"{stem}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return PlainTextResponse(md_path.read_text(encoding="utf-8"))


@router.get("/api/files/output/{stem}.meta.json")
async def get_output_meta(stem: str):
    """Serve metadata JSON for a given stem."""
    stem = _safe_stem(stem)
    meta_path = settings.output_dir / f"{stem}.meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(meta_path, media_type="application/json")


@router.get("/api/files/output/{stem}/download")
async def download_output_md(stem: str):
    """Download .md file with attachment header."""
    stem = _safe_stem(stem)
    md_path = settings.output_dir / f"{stem}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        md_path,
        media_type="text/markdown",
        filename=f"{stem}.md",
    )
