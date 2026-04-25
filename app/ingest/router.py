import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, BackgroundTasks
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi.params import File
from app.ingest.schemas import JobStatus,

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


@router.post("/upload", response_model=JobStatus, status_code=202)
async def upload_pdf(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
):
    """Upload a PDF book and queue it for AI extraction."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    from pipeline.storage import DATA_DIR
    raw_dir = DATA_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    pdf_path = raw_dir / file.filename
    content = await file.read()
    pdf_path.write_bytes(content)

    job_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    _jobs[job_id] = {
        "job_id": job_id,
        "file_name": file.filename,
        "source_slug": None,
        "status": "queued",
        "progress": "Queued",
        "total_chunks": 0,
        "done_chunks": 0,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "counts": None,
    }

    # Run pipeline in thread pool so it doesn't block FastAPI event loop
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_pipeline, job_id, pdf_path)

    return JobStatus(**_jobs[job_id])