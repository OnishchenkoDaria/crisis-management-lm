from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000,
                              example="Journalists have arrived but we have no confirmed data yet.")
    crisis_type: str | None = Field(None,
                              example="media",
                              description="Optional — auto-detected if omitted")
    phase: str | None = Field(None,
                              example="acute",
                              description="pre_crisis | acute | containment | recovery | post_crisis")
    language: str | None = Field(None, example="uk",
                              description="Filter chunks by language (uk | en | mixed)")
    chunk_limit: int = Field(5, ge=1, le=20)


class TacticRef(BaseModel):
    name: str
    description: str


class SourceRef(BaseModel):
    title:      str
    chapter:    str
    similarity: float


class RagQueryResponse(BaseModel):
    direct_answer:      str
    crisis_type:        str | None
    recommended_actions: list[str]
    suggested_message:  str
    risks:              list[str]
    relevant_tactics:   list[TacticRef]
    sources:            list[SourceRef]
    confidence:         Literal["high", "medium", "low"]
    next_steps:         list[str]


class EmbeddingStatusResponse(BaseModel):
    total:    int
    embedded: int
    pending:  int
    coverage: float = Field(description="embedded / total")