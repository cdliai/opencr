#!/usr/bin/env python3
"""CLI for headless batch PDF processing."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_pipeline.config import settings
from ocr_pipeline.services.batch_processor import BatchProcessor


async def progress_callback(event: dict):
    """Print progress events to stdout."""
    event_type = event.get("type", "")

    if event_type == "page_start":
        doc = event["document"]
        page = event["page"]
        total = event["total_pages"]
        print(
            f"  [{page}/{total}] Processing {doc} page {page} ({event['mode']}, {event['dpi']} DPI)..."
        )

    elif event_type == "page_complete":
        doc = event["document"]
        page = event["page"]
        total = event["total_pages"]
        status = event["validation_status"]
        direction = event["script_direction"]
        time_ms = event["processing_time_ms"]
        tokens = event["token_count"]
        print(
            f"  [{page}/{total}] Done: {status} | {direction} | "
            f"{tokens} tokens | {time_ms:.0f}ms"
        )

    elif event_type == "page_retry":
        page = event["page"]
        attempt = event["attempt"]
        reason = event["reason"]
        strategy = event["new_strategy"]
        print(f"  [!] Page {page} retry #{attempt}: {reason} -> {strategy}")

    elif event_type == "document_complete":
        doc = event["document"]
        pages = event["total_pages"]
        time_ms = event["total_time_ms"]
        p = event["pages_pass"]
        w = event["pages_warn"]
        f = event["pages_fail"]
        print(
            f"\n  {doc}: {pages} pages | pass={p} warn={w} fail={f} | {time_ms:.0f}ms"
        )
        print(f"  Output: {event['output_path']}")


async def main():
    parser = argparse.ArgumentParser(
        description="DeepSeek-OCR batch PDF extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="PDF file(s) or directory containing PDFs",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=f"Output directory (default: {settings.output_dir})",
    )
    parser.add_argument(
        "--model-url",
        default=None,
        help=f"Model server URL (default: {settings.model_server_url})",
    )
    args = parser.parse_args()

    if args.model_url:
        settings.model_server_url = args.model_url

    output_dir = Path(args.output) if args.output else settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files: list[Path] = []
    for input_path_str in args.input:
        input_path = Path(input_path_str)
        if input_path.is_dir():
            pdf_files.extend(sorted(input_path.glob("*.pdf")))
        elif input_path.is_file() and input_path.suffix.lower() == ".pdf":
            pdf_files.append(input_path)
        else:
            print(f"Warning: skipping {input_path} (not a PDF or directory)")

    if not pdf_files:
        print("No PDF files found.")
        sys.exit(1)

    print(f"Processing {len(pdf_files)} PDF(s) -> {output_dir}\n")

    processor = BatchProcessor(event_callback=progress_callback)
    t0 = time.perf_counter()

    for pdf_path in pdf_files:
        print(f"--- {pdf_path.name} ---")
        await processor.process_document(pdf_path, output_dir)

    elapsed = time.perf_counter() - t0
    print(f"\nAll done. {len(pdf_files)} document(s) in {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
