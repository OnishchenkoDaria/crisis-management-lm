from datetime import datetime, timezone

from fastapi import APIRouter
import logging
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ingest",
    tags=["Books and materials ingestion"],
)

# in-memory job store (replace with DB later)
# structure: { job_id: JobRecord }
_jobs: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)  # limit parallel AI calls


def _run_pipeline(job_id: str, pdf_path: Path) -> None:
    """Runs in a thread — updates _jobs[job_id] throughout."""
    from pipeline.pdf_extractor import extract_chunks, save_chunk_manifest
    from pipeline.ai_extractor import extract_from_chunk
    from pipeline.storage import (
        save_book_metadata, save_chunk_result, is_chunk_done,
        merge_book_to_processed, get_book_dir,
    )

    def update(status: str, progress: str, **kw):
        _jobs[job_id].update({
            "status": status, "progress": progress,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **kw,
        })

    try:
        # Step 1: Extract
        update("extracting", "Extracting text and splitting into chunks …")
        chunks = extract_chunks(pdf_path)
        source_slug = chunks[0].source_slug

        _jobs[job_id]["source_slug"] = source_slug
        _jobs[job_id]["total_chunks"] = len(chunks)

        save_chunk_manifest(chunks, get_book_dir(source_slug))
        save_book_metadata(source_slug, {
            "title": pdf_path.stem,
            "source_slug": source_slug,
            "file_name": pdf_path.name,
            "total_chunks": len(chunks),
            "chapters": list({c.chapter_title for c in chunks}),
        })

        # Step 2: AI extraction
        update("ai_processing", "Running AI extraction …")
        for i, chunk in enumerate(chunks):
            if is_chunk_done(source_slug, chunk.chunk_id):
                _jobs[job_id]["done_chunks"] = i + 1
                continue
            _jobs[job_id]["progress"] = f"Chunk {i + 1}/{len(chunks)}: {chunk.chapter_title[:40]}"
            _jobs[job_id]["done_chunks"] = i
            result = extract_from_chunk(chunk)
            save_chunk_result(result)
            _jobs[job_id]["done_chunks"] = i + 1

        # Step 3: Merge
        update("merging", "Merging into processed dataset …")
        counts = merge_book_to_processed(source_slug)

        update("done", "Complete", counts=counts)
        log.info(f"Job {job_id} completed: {counts}")

    except Exception as e:
        log.exception(f"Job {job_id} failed: {e}")
        _jobs[job_id].update({
            "status": "error",
            "error": str(e),
            "progress": "Failed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })