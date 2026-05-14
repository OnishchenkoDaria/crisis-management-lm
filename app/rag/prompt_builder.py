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
    """
    Returns (system_prompt, user_message) ready for LLM call.
    """
    parts: list[str] = []

    # Crisis context header
    if ctx.detected_crisis_type:
        parts.append(
            f"DETECTED CRISIS TYPE: {ctx.detected_crisis_type}"
            + (f" | PHASE: {ctx.detected_phase}" if ctx.detected_phase else "")
        )

    # Retrieved document chunks — primary grounding
    if ctx.chunks:
        parts.append("\n── RELEVANT SOURCE PASSAGES ──")
        for i, chunk in enumerate(ctx.chunks, 1):
            text = chunk.text[:CHUNK_MAX_CHARS]
            if len(chunk.text) > CHUNK_MAX_CHARS:
                text += "…"
            parts.append(
                f"[{i}] {chunk.source_title} / {chunk.source_chapter} "
                f"(similarity={chunk.similarity:.2f})\n{text}"
            )
    else:
        parts.append("\n── NOTE: No relevant document passages found. ──")
        parts.append("Confidence should be LOW in your response.")

    # Matching scenarios
    if ctx.scenarios:
        parts.append("\n── MATCHING CRISIS SCENARIOS ──")
        for s in ctx.scenarios:
            parts.append(
                f"Scenario: {s['title']}\n"
                f"  Type: {s['crisis_type']} | Severity: {s['severity']} | Phase: {s['phase']}\n"
                f"  Context: {s['context']}\n"
                f"  Stakeholders: {', '.join(s.get('stakeholders', []))}"
            )

    # Applicable tactics
    if ctx.tactics:
        parts.append("\n── APPLICABLE TACTICS ──")
        for t in ctx.tactics:
            text = (t.get("description") or "")[:TACTIC_MAX_CHARS]
            parts.append(
                f"• {t['name']}: {text}\n"
                f"  When to apply: {t.get('when_to_apply', '')}\n"
                f"  Anti-pattern: {t.get('anti_pattern', '')}"
            )

    # Decision nodes
    if ctx.decision_nodes:
        parts.append("\n── DECISION POINTS ──")
        for d in ctx.decision_nodes:
            parts.append(
                f"Situation: {d.get('situation', '')}\n"
                f"  Recommended: {d.get('recommended_action', '')}\n"
                f"  Common mistake: {d.get('common_mistake', '')}\n"
                f"  Consequence if wrong: {d.get('consequence_if_wrong', '')}"
            )

    # QA few-shot examples
    if ctx.qa_pairs:
        parts.append("\n── REFERENCE Q&A ──")
        for qa in ctx.qa_pairs:
            parts.append(f"Q: {qa['question']}\nA: {qa['answer']}")

    # User query
    user_message = "\n".join(parts) + f"\n\n── USER QUERY ──\n{ctx.query}"

    return SYSTEM_PROMPT, user_message