import base64
from io import BytesIO
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image


class PDFRenderer:
    """Renders PDF pages to PIL Images using pdf2image (poppler)."""

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        dpi: int = 200,
    ) -> Image.Image:
        """Render a single page (1-indexed) at the given DPI."""
        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            first_page=page_num,
            last_page=page_num,
        )
        return images[0]

    def render_all_pages(
        self,
        pdf_path: Path,
        dpi: int = 200,
    ) -> list[Image.Image]:
        """Render all pages at the given DPI."""
        return convert_from_path(str(pdf_path), dpi=dpi)

    @staticmethod
    def image_to_base64(image: Image.Image) -> str:
        buf = BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
