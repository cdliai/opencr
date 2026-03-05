import fitz  # PyMuPDF
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageProfile:
    page_num: int
    has_embedded_text: bool
    embedded_text_length: int
    has_images: bool
    image_count: int
    width: float
    height: float
    is_landscape: bool
    estimated_complexity: str  # "simple" | "moderate" | "complex"
    recommended_dpi: int
    recommended_mode: str  # "markdown" | "free_ocr" | "figure"


class PageAnalyzer:
    """
    Analyzes PDF pages BEFORE rendering to determine optimal extraction strategy.
    Uses PyMuPDF for fast metadata extraction without full rendering.
    """

    def analyze_document(self, pdf_path: Path) -> list[PageProfile]:
        doc = fitz.open(str(pdf_path))
        profiles = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            profiles.append(self._analyze_page(page, page_num + 1))

        doc.close()
        return profiles

    def _analyze_page(self, page, page_num: int) -> PageProfile:
        text = page.get_text().strip()
        has_text = len(text) > 50
        images = page.get_images()
        has_images = len(images) > 0
        rect = page.rect
        width = rect.width
        height = rect.height
        is_landscape = width > height

        blocks = page.get_text("dict")["blocks"]
        num_blocks = len(blocks)
        has_tables = any(
            b.get("type", 0) == 0 and len(b.get("lines", [])) > 5
            for b in blocks
        )

        if has_tables or num_blocks > 20:
            complexity = "complex"
        elif num_blocks > 5 or has_images:
            complexity = "moderate"
        else:
            complexity = "simple"

        if not has_text and has_images:
            dpi = 300
            mode = "markdown"
        elif has_images and not has_text:
            dpi = 300
            mode = "figure"
        elif complexity == "complex":
            dpi = 200
            mode = "markdown"
        else:
            dpi = 200
            mode = "markdown"

        return PageProfile(
            page_num=page_num,
            has_embedded_text=has_text,
            embedded_text_length=len(text),
            has_images=has_images,
            image_count=len(images),
            width=width,
            height=height,
            is_landscape=is_landscape,
            estimated_complexity=complexity,
            recommended_dpi=dpi,
            recommended_mode=mode,
        )
