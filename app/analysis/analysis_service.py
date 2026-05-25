from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.analysis.schemas import (
    SituationInput, RefinementRequest,
    AnalysisResponse, RoadmapResponse,
    CrisisType, UrgencyLevel, CrisisPhase,
    RoadmapPhase, ActionItem, MonitoringItem, EscalationRule,
    TacticRef, SourceRef, ActionPriority, ActionStatus,
)
from app.analysis.prompt_templates import build_analysis_prompt, build_roadmap_prompt
from app.rag.retrieval_service import retrieve_context
from app.rag.rag_service import _call_llm
from app.database import async_session_maker
from app.analysis.input_guard import classify_input
from app.rag.book_registry import resolve_citation

log = logging.getLogger(__name__)

MINIMUM_SIMILARITY = 0.60
MAX_AUTO_CLARIFICATIONS = 2

async def create_analysis(
    workspace_id: int,
    situation: SituationInput,
) -> AnalysisResponse:
    guard = await classify_input(situation.situation_description)

    if guard.get("injection_detected"):
        log.warning("Prompt injection attempt: workspace=%d", workspace_id)
        raise ValueError("Input rejected: contains disallowed patterns.")

    if not guard.get("valid"):
        raise ValueError(
            f"Input does not describe a recognisable crisis situation. "
            f"{guard.get('reason', 'Please describe a real organisational crisis.')}"
        )

    analysis_id = str(uuid.uuid4())

    # Workspace context
    workspace_ctx = await _load_workspace_context(workspace_id)
    # RAG retrieval
    ctx = await retrieve_context(situation.situation_description, chunk_limit=6)

    system_prompt, user_message = build_analysis_prompt(situation, ctx, workspace_ctx)
    raw = await _call_llm(system_prompt, user_message)
    response = _parse_analysis_response(raw, analysis_id, workspace_id, ctx)

    await _store_analysis(analysis_id, workspace_id, situation, response, ctx)

    return response


async def refine_analysis(
    analysis_id: str,
    workspace_id: int,
    refinement: RefinementRequest,
) -> AnalysisResponse:
    # Load existing analysis state
    stored = await _load_analysis(analysis_id)
    current_count = stored.get("clarification_count", 0)
    new_count = current_count + 1

    if not stored or stored["workspace_id"] != workspace_id:
        raise ValueError(f"Analysis {analysis_id} not found")

    # Rebuild situation with overrides applied
    original = SituationInput(**stored["situation_input"])
    for field, value in refinement.fields_to_update.items():
        if hasattr(original, field):
            setattr(original, field, value)

    # Rebuild context with refinement comment appended
    augmented_description = original.situation_description
    if refinement.user_comment:
        augmented_description += f"\n\nAdditional context from user: {refinement.user_comment}"
    if refinement.additional_context:
        augmented_description += f"\n\nFurther constraints: {refinement.additional_context}"

    ctx = await retrieve_context(augmented_description, chunk_limit=6)
    workspace_ctx = await _load_workspace_context(workspace_id)

    system_prompt, user_message = build_analysis_prompt(
        original, ctx, workspace_ctx, refinement=refinement
    )
    raw = await _call_llm(system_prompt, user_message)
    new_count = stored.get("clarification_count", 0) + 1
    response = _parse_analysis_response(
        raw, analysis_id, workspace_id, ctx,
        clarification_count=new_count
    )
    response.status = "refined"

    await _update_analysis(analysis_id, refinement, response, clarification_count=new_count)
    return response


async def generate_roadmap(analysis_id: str, workspace_id: int) -> RoadmapResponse:
    stored = await _load_analysis(analysis_id)
    if not stored:
        raise ValueError(f"Analysis {analysis_id} not found")
    if not stored.get("can_generate_roadmap"):
        raise ValueError("Analysis not ready for roadmap generation. Add missing information first.")

    roadmap_id = str(uuid.uuid4())
    ctx = await retrieve_context(
        stored["situation_input"]["situation_description"],
        crisis_type=stored["detected_crisis_type"],
        chunk_limit=8,
    )

    system_prompt, user_message = build_roadmap_prompt(stored, ctx)
    raw = await _call_llm(system_prompt, user_message)
    roadmap = _parse_roadmap_response(raw, roadmap_id, analysis_id, workspace_id, ctx)

    await _store_roadmap(roadmap_id, analysis_id, workspace_id, roadmap)
    return roadmap


def _parse_analysis_response(
    raw: str, analysis_id: str, workspace_id: int, ctx, clarification_count: int = 0,
) -> AnalysisResponse:
    #Parse LLM JSON into AnalysisResponse with graceful fallback
    import re
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON for analysis — using fallback")
        data = {}

    missing = data.get("missing_information", [])
    confidence = data.get("confidence", "low")

    readiness = _compute_readiness(confidence, len(missing), clarification_count)
    can_generate = readiness >= 55

    response = AnalysisResponse(
        analysis_id=analysis_id,
        workspace_id=workspace_id,
        status="draft",
        crisis_summary=data.get("crisis_summary", ""),
        detected_crisis_type=_safe_enum(CrisisType, data.get("detected_crisis_type"), CrisisType.reputational),
        urgency_level=_safe_enum(UrgencyLevel, data.get("urgency_level"), UrgencyLevel.high),
        phase=_safe_enum(CrisisPhase, data.get("phase"), CrisisPhase.acute),
        confidence=confidence,
        key_risks=data.get("key_risks", []),
        stakeholders=data.get("stakeholders", []),
        recommended_strategy=data.get("recommended_strategy", ""),
        relevant_tactics=[
            TacticRef(**t) for t in data.get("relevant_tactics", [])
            if isinstance(t, dict)
        ],
        suggested_initial_message=data.get("suggested_initial_message", ""),
        missing_information=missing,
        next_questions=data.get("next_questions", []),
        retrieved_sources=[
            SourceRef(
                title=resolve_citation(c.source_title, c.source_chapter),
                chapter=c.source_chapter,
                similarity=c.similarity,
            )
            for c in ctx.chunks
        ],
        can_generate_roadmap=can_generate,
        readiness_score=readiness,
    )

    # Override after max clarifications — never block the user past this point
    if clarification_count >= MAX_AUTO_CLARIFICATIONS:
        response.can_generate_roadmap = True
        response.missing_information = []
        response.readiness_score = max(response.readiness_score, 75)

    return response


def _parse_roadmap_response(
    raw: str, roadmap_id: str, analysis_id: str, workspace_id: int, ctx
) -> RoadmapResponse:
    import re
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    phases = []
    for ph in data.get("phases", []):
        items = [
            ActionItem(
                id = item.get("id", str(uuid.uuid4())),
                phase = ph.get("id", ""),
                title = item.get("title", ""),
                description = item.get("description", ""),
                priority = _safe_enum(ActionPriority, item.get("priority"), ActionPriority.high),
                owner_role = item.get("owner_role", "Communications Lead"),
                channel = item.get("channel"),
                due_hint = item.get("due_hint", ""),
                rationale = item.get("rationale", ""),
                risk_if_skipped = item.get("risk_if_skipped", ""),
                source_refs = item.get("source_refs", []),
            )
            for item in ph.get("action_items", [])
            if isinstance(item, dict)
        ]
        phases.append(RoadmapPhase(
            id = ph.get("id", ""),
            label = ph.get("label", ""),
            description = ph.get("description", ""),
            action_items = items,
        ))

    return RoadmapResponse(
        roadmap_id = roadmap_id,
        analysis_id = analysis_id,
        workspace_id = workspace_id,
        crisis_type = _safe_enum(CrisisType, data.get("crisis_type"), CrisisType.reputational),
        executive_summary = data.get("executive_summary", ""),
        phases = phases,
        communication_messages = data.get("communication_messages", []),
        monitoring_plan = [MonitoringItem(**m) for m in data.get("monitoring_plan", []) if isinstance(m, dict)],
        escalation_rules = [EscalationRule(**e) for e in data.get("escalation_rules", []) if isinstance(e, dict)],
        risks = data.get("risks", []),
        sources = [SourceRef(title=c.source_title, chapter=c.source_chapter, similarity=c.similarity) for c in ctx.chunks],
        confidence = data.get("confidence", "medium"),
        next_steps = data.get("next_steps", []),
    )



async def _load_workspace_context(workspace_id: int) -> dict:
    #Load brand profile, tone, constraints from workspace
    try:
        from app.workspaces.dao import WorkspaceDAO
        ws = await WorkspaceDAO.find_one_or_none_by_id(workspace_id)
        return ws.to_dict() if ws else {}
    except Exception:
        return {}


async def _store_analysis(analysis_id, workspace_id, situation, response, ctx):
    from app.database import async_session_maker
    from app.analysis.models import Analysis
    async with async_session_maker() as session:
        session.add(Analysis(
            id = analysis_id,
            workspace_id = workspace_id,
            situation_input = situation.model_dump(),
            detected_type = response.detected_crisis_type.value,
            urgency = response.urgency_level.value,
            confidence = response.confidence,
            response_json = response.model_dump(),
            can_generate_roadmap = response.can_generate_roadmap,
            retrieved_chunk_ids = [c.chunk_id for c in ctx.chunks],
        ))
        await session.commit()


async def _load_analysis(analysis_id: str) -> dict | None:
    from app.analysis.models import Analysis
    from sqlalchemy import select
    async with async_session_maker() as session:
        row = (await session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )).scalar_one_or_none()
        if not row:
            return None
        return {
            **row.response_json,
            "workspace_id":       row.workspace_id,
            "situation_input":    row.situation_input,
            "detected_crisis_type": row.detected_type,
            "can_generate_roadmap": row.can_generate_roadmap,
        }


async def _update_analysis(analysis_id: str,
    refinement: RefinementRequest,
    response: AnalysisResponse,
    clarification_count: int = 0,
) -> None:
    from app.analysis.models import Analysis
    from sqlalchemy import update
    async with async_session_maker() as session:
        await session.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                response_json = response.model_dump(),
                confidence = response.confidence,
                refinement_json = refinement.model_dump(),
                can_generate_roadmap = response.can_generate_roadmap,
                clarification_count = clarification_count,
            )
        )
        await session.commit()

def _compute_readiness(
    confidence: str,
    missing_count: int,
    clarification_count: int
) -> int:
    base = {"high": 85, "medium": 65, "low": 35}.get(confidence, 35)
    # Each clarification adds points, diminishing returns
    clarification_bonus = min(clarification_count * 12, 30)
    # Missing info reduces score
    missing_penalty = min(missing_count * 5, 25)
    return min(100, max(0, base + clarification_bonus - missing_penalty))


async def _store_roadmap(roadmap_id, analysis_id, workspace_id, roadmap):
    from app.roadmaps.models import Roadmap
    async with async_session_maker() as session:
        session.add(Roadmap(
            id = roadmap_id,
            analysis_id = analysis_id,
            workspace_id = workspace_id,
            crisis_type = roadmap.crisis_type.value,
            roadmap_json = roadmap.model_dump(),
            confidence = roadmap.confidence,
        ))
        await session.commit()


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default