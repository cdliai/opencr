from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class PageMetadata:
    page_num: int

    # Extraction info
    processing_time_ms: float
    extraction_mode: str                # "markdown" | "free_ocr" | "figure"
    extraction_attempt: int             # 1 = first try, 2+ = retry
    dpi_used: int                       # DPI stands for the resolution at which OCR was performed (may differ from original PDF if resampled)

    # Content metrics
    text_length_chars: int
    text_length_words: int
    text_length_lines: int

    # Token counts (for LLM context budgeting)
    token_count_cl100k: int  # tiktoken cl100k_base (GPT-4 / Claude)
    token_count_approx: int  # word_count * 1.3 rough estimate

    # Script analysis
    script_direction: str  # "ltr"::left-to-right | "rtl"::right-to-left | "mixed"
    primary_script: str  # "latin" | "arabic" | "latin_extended"
    detected_languages: list[str]
    ltr_ratio: float
    rtl_ratio: float
    arabic_char_count: int
    latin_char_count: int
    has_diacritics: bool

    # Validation
    validation_status: str  # "pass" | "warn" | "fail" | "empty"
    validation_issues: list[str]
    repetition_ratio: float

    # Source page info
    has_embedded_text: bool
    is_image_only: bool
    page_width: float
    page_height: float
    image_count: int
    estimated_complexity: str
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    # File info
    filename: str
    file_path: str
    file_size_bytes: int
    file_sha256: str

    # PDF info
    total_pages: int
    pdf_title: Optional[str]
    pdf_author: Optional[str]
    pdf_creation_date: Optional[str]
    pdf_producer: Optional[str]

    # Aggregate metrics
    total_chars: int
    total_words: int
    total_tokens_cl100k: int
    total_processing_time_ms: float
    avg_time_per_page_ms: float

    # Script summary
    dominant_direction: str
    dominant_script: str
    pages_ltr: int
    pages_rtl: int
    pages_mixed: int
    languages_detected: list[str]

    # Quality summary
    pages_pass: int
    pages_warn: int
    pages_fail: int
    pages_empty: int

    # Timestamps
    started_at: str
    completed_at: str
    pipeline_version: str
    model_used: str

    # Per-page metadata
    pages: list[PageMetadata] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
