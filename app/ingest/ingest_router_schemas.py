from typing import Literal
from pydantic import BaseModel


class JobStatus(BaseModel):
    job_id: str
    file_name: str
    source_slug: str | None
    status: Literal["queued", "extracting", "ai_processing", "merging", "done", "error"]
    progress: str
    total_chunks: int
    done_chunks: int
    error: str | None
    created_at: str
    updated_at: str
    counts: dict | None


class StatsResponse(BaseModel):
    scenarios: int
    decision_nodes: int
    tactics: int
    qa_pairs: int
    rag_chunks: int
    training_samples: int