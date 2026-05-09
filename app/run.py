import logging
import sys

from app.ingest.pipeline.pdf_extractor import extract_chunks, save_chunk_manifest
from app.ingest.pipeline.ai_extractor import extract_from_chunk
from app.ingest.pipeline.storage import (
    save_book_metadata, save_chunk_result, is_chunk_done,
    merge_book_to_processed, build_training_jsonl, get_stats,
    promote_all_to_db, DATA_DIR,
)
from app.ingest.pipeline.storage import get_book_dir
from pathlib import Path
import argparse

'''
CLI entry point — processes all PDFs in data/raw/ through the full pipeline.

Usage:
  python run.py                         # process all new PDFs
  python run.py --pdf data/raw/book.pdf # process one specific PDF
  python run.py --merge-only            # just re-merge already-extracted books
  python run.py --build-training        # build fine-tuning JSONL from qa_pairs
  python run.py --stats                 # print current dataset stats
  python run.py --promote-only          # push all completed chunks to PostgreSQL
'''

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

    log.info("Step 4/4  Finalising book in DB ...")
    try:
        import asyncio
        from app.ingest.dao import IngestDAO
        n = asyncio.run(IngestDAO.finalize_book())
        log.info("  Done: %d TrainingSamples created", n)
    except Exception as e:
        log.warning("  finalize_book skipped: %s", e)


def main():
    parser = argparse.ArgumentParser(description="DSS Dataset Pipeline")
    parser.add_argument("--pdf", help="Path to a single PDF to process")
    parser.add_argument("--merge-only", action="store_true",
                        help="Re-merge already-extracted data (no AI calls)")
    parser.add_argument("--build-training", action="store_true",
                        help="Build fine-tuning JSONL from qa_pairs.jsonl")
    parser.add_argument("--stats", action="store_true",
                        help="Print current dataset statistics")
    parser.add_argument("--promote-only", action="store_true",
                        help="Push all completed chunks to PostgreSQL (no AI calls)")
    args = parser.parse_args()

    if args.promote_only:
        print("\nPromoting all completed chunks to PostgreSQL ...")
        counts = promote_all_to_db()
        print("\n-- Promotion complete --")
        for k, v in counts.items():
            print(f"  {k:<20} {v:>6} records inserted")
        print()
        return

    if args.stats:
        stats = get_stats()
        print("\n── Dataset statistics ──────────────────")
        for k, v in stats.items():
            print(f"  {k:<20} {v:>6} records")
        print()
        return

    if args.build_training:
        path = build_training_jsonl()
        print(f"\n✓ Training JSONL saved to: {path}")
        return

    if args.merge_only:
        raw_dir = DATA_DIR / "extracted"
        for book_dir in raw_dir.iterdir():
            if book_dir.is_dir():
                log.info(f"Merging: {book_dir.name}")
                merge_book_to_processed(book_dir.name)
        return

    # Normal mode: process PDFs
    if args.pdf:
        pdfs = [Path(args.pdf)]
    else:
        pdfs = sorted((DATA_DIR / "raw").glob("*.pdf"))
        if not pdfs:
            print(f"\nNo PDFs found in {DATA_DIR / 'raw'}/")
            print("Drop your PDF books there and re-run.\n")
            return

    print(f"\nFound {len(pdfs)} PDF(s) to process.\n")
    for pdf in pdfs:
        process_pdf(pdf)

    # Build training JSONL automatically after all books processed
    log.info("\nBuilding training_samples.jsonl …")
    try:
        build_training_jsonl()
    except FileNotFoundError:
        pass

    print("\n── Final dataset statistics ──────────────")
    stats = get_stats()
    for k, v in stats.items():
        print(f"  {k:<20} {v:>6} records")
    print()


if __name__ == "__main__":
    main()