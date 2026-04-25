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