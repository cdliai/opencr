from pydantic import BaseModel, Field
from typing import Optional


class ExtractRequest(BaseModel):
    """Single PDF extraction request."""
    file_path: str = Field(description="Path to the PDF file")
    output_dir: Optional[str] = Field(None, description="Output directory override")


class ExtractResponse(BaseModel):
    """Single PDF extraction response."""
    filename: str
    total_pages: int
    pages_pass: int
    pages_warn: int
    pages_fail: int
    pages_empty: int
    total_processing_time_ms: float
    output_md: str
    output_meta: str


class JobRequest(BaseModel):
    """Batch extraction job request."""
    file_paths: list[str] = Field(description="List of PDF file paths to process")
    output_dir: Optional[str] = Field(None, description="Output directory override")
    strip_refs: bool = Field(False, description="Strip model reference blocks (bounding boxes) from output")


class JobStatusResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    progress: float  # 0.0 to 1.0
    documents_completed: int
    documents_total: int
    current_document: Optional[str] = None
    current_page: Optional[int] = None
    current_total_pages: Optional[int] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str  # "ready" | "waiting" | "degraded"
    pipeline_version: str
    model_server_url: str
    model_name: str
    model_status: str  # "ready" | "waiting (reason)"
    input_dir: str = ""
    output_dir: str = ""


class FileInfo(BaseModel):
    """Input file info."""
    name: str
    size: int
    modified: float
    path: str


class OutputFileInfo(BaseModel):
    """Output file pair info."""
    stem: str
    md_size: int
    meta_exists: bool
    modified: float
