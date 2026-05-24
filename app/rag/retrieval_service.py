"""
Fetches all relevant context from PostgreSQL for a given query.
Combines:
  - ragchunks (vector search)
  - scenarios (filtered by crisis_type + phase)
  - tactics   (filtered by crisis_type)
  - decisionnodes (linked to matched scenarios)
  - qapairs   (filtered by scenario tags)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB

from app.database import async_session_maker
from app.ingest.models.scenario_model import Scenario
from app.ingest.models.tactics import Tactic
from app.ingest.models.decision_node_model import DecisionNode
from app.ingest.models.qa_model import QAPair
from app.rag.rag_chunk_dao import RagChunkDAO, SimilarChunk
from app.rag.embedding_provider import embed_one

log = logging.getLogger(__name__)


@dataclass
class RetrievedContext:
    """All context assembled for one user query."""
    query:          str
    query_vector:   list[float]

    chunks:         list[SimilarChunk] = field(default_factory=list)
    scenarios:      list[dict]         = field(default_factory=list)
    tactics:        list[dict]         = field(default_factory=list)
    decision_nodes: list[dict]         = field(default_factory=list)
    qa_pairs:       list[dict]         = field(default_factory=list)

    detected_crisis_type: str | None = None
    detected_phase:       str | None = None


async def retrieve_context(
    query: str,
    *,
    crisis_type: str | None = None,
    phase:       str | None = None,
    language:    str | None = None,
    chunk_limit: int = 10,
    tactic_limit: int = 4,
    qa_limit:    int = 3,
) -> RetrievedContext:
    """
    Main retrieval function called by RagService.
    Embeds the query once and fans out to all relevant tables.
    """
    log.info("Retrieving context for query: %.80s…", query)
    query_vector = await embed_one(query)

    ctx = RetrievedContext(
        query=query,
        query_vector=query_vector,
        detected_crisis_type=crisis_type,
        detected_phase=phase,
    )

    ctx.chunks = await RagChunkDAO.find_similar(
        query_vector,
        limit=chunk_limit,
        language=language,
    )
    log.info("  Retrieved %d chunks", len(ctx.chunks))

    if not crisis_type and ctx.chunks:
        # Heuristic: check if scenarios table has matching type
        detected = await _detect_crisis_type(query)
        ctx.detected_crisis_type = detected
        crisis_type = detected

    # Fetch scenarios matching crisis_type + phase
    ctx.scenarios = await _fetch_scenarios(crisis_type, phase, limit=3)

    # Fetch tactics matching crisis_type
    ctx.tactics = await _fetch_tactics(crisis_type, limit=tactic_limit)

    # Fetch decision nodes linked to matched scenarios
    scenario_ids = [s.get("external_id") for s in ctx.scenarios if s.get("external_id")]
    ctx.decision_nodes = await _fetch_decision_nodes(scenario_ids, limit=3)

    # Fetch QA pairs as few-shot examples
    ctx.qa_pairs = await _fetch_qa_pairs(crisis_type, limit=qa_limit)

    log.info(
        "  Context: %d chunks, %d scenarios, %d tactics, "
        "%d decisions, %d qa_pairs",
        len(ctx.chunks), len(ctx.scenarios), len(ctx.tactics),
        len(ctx.decision_nodes), len(ctx.qa_pairs),
    )
    return ctx



async def _detect_crisis_type(query: str) -> str | None:
    """
    Simple keyword-based crisis type detection.
    """
    q = query.lower()
    mapping = {
        "media":         ["journalist", "press", "media", "reporter", "camera", "interview"],
        "safety":        ["accident", "injury", "evacuation", "hazard", "emergency", "fire"],
        "reputational":  ["scandal", "reputation", "trust", "credibility", "accusation"],
        "operational":   ["outage", "system", "delay", "failure", "disruption", "supply"],
        "political":     ["protest", "government", "regulation", "policy", "sanction"],
        "internal":      ["employee", "staff", "hr", "internal", "layoff", "strike"],
        "natural_disaster": ["flood", "earthquake", "storm", "hurricane", "disaster"],
    }
    for crisis_type, keywords in mapping.items():
        if any(kw in q for kw in keywords):
            return crisis_type
    return None


async def _fetch_scenarios(
    crisis_type: str | None,
    phase: str | None,
    limit: int = 3,
) -> list[dict]:
    async with async_session_maker() as session:
        q = select(Scenario)
        if crisis_type:
            q = q.where(Scenario.crisis_type == crisis_type)
        if phase:
            q = q.where(Scenario.phase == phase)
        q = q.order_by(Scenario.id).limit(limit)
        rows = (await session.execute(q)).scalars().all()

    return [
        {
            "external_id":  r.external_id,
            "title":        r.title,
            "crisis_type":  r.crisis_type,
            "severity":     r.severity,
            "phase":        r.phase,
            "context":      r.context,
            "stakeholders": r.stakeholders,
        }
        for r in rows
    ]


async def _fetch_tactics(crisis_type: str | None, limit: int = 4) -> list[dict]:
    async with async_session_maker() as session:
        q = select(Tactic).limit(limit)
        if crisis_type:
            # crisis_types is JSONB in tactics model — no cast needed there
            q = q.where(Tactic.crisis_types.contains([crisis_type]))
        rows = (await session.execute(q)).scalars().all()

    return [
        {
            "name":          r.name,
            "description":   r.description,
            "when_to_apply": r.when_to_apply,
            "anti_pattern":  r.anti_pattern,
        }
        for r in rows
    ]


async def _fetch_decision_nodes(
    scenario_ids: list[str],
    limit: int = 3,
) -> list[dict]:
    if not scenario_ids:
        return []

    async with async_session_maker() as session:
        q = (
            select(DecisionNode)
            .where(DecisionNode.source_scenario_id.in_(scenario_ids))
            .limit(limit)
        )
        rows = (await session.execute(q)).scalars().all()

    return [
        {
            "decision_id":         r.decision_id,
            "situation":           r.situation,
            "options":             r.options,
            "recommended_action":  r.recommended_action_id,
            "common_mistake":      r.common_rookie_mistake,
            "consequence_if_wrong":r.consequence_if_wrong,
        }
        for r in rows
    ]

from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB

async def _fetch_qa_pairs(crisis_type: str | None, limit: int = 3) -> list[dict]:
    async with async_session_maker() as session:
        q = select(QAPair).where(QAPair.difficulty == "basic").limit(limit)
        if crisis_type:
            # Cast JSON -> JSONB for the @> contains operator
            q = q.where(cast(QAPair.scenario_tags, JSONB).contains([crisis_type]))
        rows = (await session.execute(q)).scalars().all()

    return [{"question": r.question, "answer": r.answer} for r in rows]