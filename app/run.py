import logging
import sys

from app.ingest.pipeline.pdf_extractor import extract_chunks, save_chunk_manifest
from app.ingest.pipeline.ai_extractor import extract_from_chunk
from app.ingest.pipeline.storage import (
    save_book_metadata, save_chunk_result, is_chunk_done,
    merge_book_to_processed, build_training_jsonl, get_stats,
    DATA_DIR,
)
from app.ingest.pipeline.storage import get_book_dir
from pathlib import Path

# CLI entry point — processes all PDFs in data/raw/ through the full pipeline.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def process_pdf(pdf_path: Path) -> None:
    log.info(f"\n{'=' * 60}")
    log.info(f"Processing: {pdf_path.name}")
    log.info(f"{'=' * 60}")


    log.info("Step 1/4  Extracting text and splitting into chunks …")
    try:
        chunks = extract_chunks(pdf_path)
    except ValueError as e:
        log.error(str(e))
        return

    source_slug = chunks[0].source_slug
    log.info(f"  Found {len(chunks)} chunks across "
             f"{max(c.chapter_index for c in chunks) + 1} chapters")


    log.info("Step 2/4  Saving chunk manifest …")
    save_chunk_manifest(chunks, get_book_dir(source_slug))
    save_book_metadata(source_slug, {
        "title": pdf_path.stem,
        "source_slug": source_slug,
        "file_name": pdf_path.name,
        "total_chunks": len(chunks),
        "chapters": list({c.chapter_title for c in chunks}),
    })


    log.info("Step 3/4  Running AI extraction …")
    done = sum(1 for c in chunks if is_chunk_done(source_slug, c.chunk_id))
    todo = len(chunks) - done
    log.info(f"  {done} chunks already done, {todo} remaining")

    for i, chunk in enumerate(chunks):
        if is_chunk_done(source_slug, chunk.chunk_id):
            log.info(f"  [{i + 1}/{len(chunks)}] SKIP (cached)  {chunk.chunk_id}")
            continue
        log.info(f"  [{i + 1}/{len(chunks)}] Processing  {chunk.chunk_id} "
                 f"({chunk.token_count} tokens, chapter: {chunk.chapter_title[:50]})")
        try:
            result = extract_from_chunk(chunk)
            save_chunk_result(result)
        except Exception as e:
            log.error(f"  ERROR on {chunk.chunk_id}: {e}")
            continue  # don't abort the whole book on one bad chunk

    log.info("Step 4/4  Merging into processed/ …")
    counts = merge_book_to_processed(source_slug)
    log.info(f"  Done: {counts}")