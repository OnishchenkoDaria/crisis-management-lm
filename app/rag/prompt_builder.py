"""
Assembles retrieved context into a structured LLM prompt.
keep MODEL_CONTEXT_LIMIT >= 6000
"""
from __future__ import annotations

from app.rag.retrieval_service import RetrievedContext

SYSTEM_PROMPT = """You are a Decision Support System (DSS) for crisis communications.
You advise Communications Specialists in real-time during active crises.

RULES:
1. Be direct and tactical. No generic advice.
2. Every recommendation must come from the provided context.
3. If the context is weak, say so explicitly — do NOT invent tactics.
4. Warn about the single most common rookie mistake for this situation.
5. Respond ONLY in valid JSON matching the required schema — no prose, no markdown.

REQUIRED JSON SCHEMA:
{
  "direct_answer": "string — immediate tactical advice in 2-3 sentences",
  "crisis_type": "string — detected crisis type or null",
  "recommended_actions": ["string", ...],
  "suggested_message": "string — a holding statement or press response template",
  "risks": ["string", ...],
  "relevant_tactics": [{"name": "string", "description": "string"}, ...],
  "sources": [{"title": "string", "chapter": "string", "similarity": 0.0}],
  "confidence": "high | medium | low",
  "next_steps": ["string", ...]
}"""

CHUNK_MAX_CHARS = 600    # trim long chunks to stay within context budget
TACTIC_MAX_CHARS = 300


def build_prompt(ctx: RetrievedContext) -> tuple[str, str]:
    system_prompt = """You are a senior crisis communications strategist with 20+ years of experience.
    You advise organizations using evidence-based methodology grounded in academic crisis communication research.
    
    CRITICAL RULES:
    1. Every recommendation must cite the specific source it comes from using [Source: title, chapter]
    2. Reference Situational Crisis Communication Theory (SCCT), Image Repair Theory, or other frameworks by name when applying them
    3. Never give generic advice — ground every tactical suggestion in the retrieved knowledge
    4. If retrieved sources are insufficient for a recommendation, say so explicitly
    5. Urgency and crisis type must be justified with observable evidence from the situation described
    6. Respond ONLY in valid JSON matching the required schema
    
    REASONING APPROACH:
    - First identify what crisis communication theory applies and WHY
    - Then derive tactics from that theory, citing the specific book/chapter
    - Then assess risks based on documented case precedents from the knowledge base
    - Flag missing information that would change the strategy"""

    # Build context block with explicit source labels
    context_parts = []

    for i, chunk in enumerate(ctx.chunks, 1):
        context_parts.append(
            f"[SOURCE {i}: {chunk.source_title} — {chunk.source_chapter}]\n{chunk.text}"
        )

    for scenario in ctx.scenarios:
        context_parts.append(
            f"[PRECEDENT CASE: {scenario.title}]\n{scenario.description}"
        )

    for tactic in ctx.tactics:
        context_parts.append(
            f"[TACTIC: {tactic.name}]\n{tactic.description}\n"
            f"Anti-pattern to avoid: {tactic.anti_pattern}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    user_message = f"""KNOWLEDGE BASE:
    {context_block}
    
    SITUATION TO ANALYSE:
    {ctx.query}
    
    Provide a structured crisis communication analysis in JSON.
    For every recommended_action and tactic, include which source it comes from.
    Justify your confidence level with specific reasoning."""

    return system_prompt, user_message