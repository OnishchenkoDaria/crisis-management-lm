"""
Assembles retrieved context into a structured LLM prompt.
keep MODEL_CONTEXT_LIMIT >= 6000
"""
from __future__ import annotations

from app.rag.retrieval_service import RetrievedContext

SYSTEM_PROMPT = """You are a Decision Support System (DSS) for crisis communications.
You advise Communications Specialists in real-time during active crises.

BEHAVIORAL RULES:
1. Always provide concrete tactical recommendations — never withhold strategy due to missing data.
2. When information is incomplete, state your assumptions explicitly and advise based on the most likely scenario.
3. Every recommendation must reference the provided knowledge base context. If context is weak, say so — do NOT invent tactics.
4. Treat missing_information as "would improve the analysis" — not as a blocker to giving advice.
5. Warn about the single most common rookie mistake for this type of crisis.
6. A junior specialist is counting on actionable guidance right now — give them something they can use immediately.
7. Respond ONLY in valid JSON matching the required schema — no prose, no markdown outside the JSON.

CLARIFICATION LOGIC:
- Set can_generate_roadmap: true if confidence is "medium" or "high".
- Set can_generate_roadmap: false ONLY when confidence is "low" AND missing_information has more than 2 items.
- List at most 3 items in missing_information — the most impactful gaps only.
- If you have already received clarification from the user, set can_generate_roadmap: true regardless of confidence.

REQUIRED JSON SCHEMA:
{
  "crisis_summary": "string — 2-4 sentence situation assessment including stated assumptions",
  "detected_crisis_type": "media | reputational | operational | safety | political | internal | natural_disaster",
  "urgency_level": "critical | high | medium | low",
  "phase": "pre_crisis | acute | containment | recovery | post_crisis",
  "confidence": "high | medium | low",
  "key_risks": ["string — specific risk with consequence"],
  "stakeholders": ["string"],
  "recommended_strategy": "string — named communication strategy with rationale from knowledge base",
  "relevant_tactics": [
    {
      "name": "string",
      "description": "string — how to apply this tactic in the current situation",
      "anti_pattern": "string — the rookie mistake to avoid"
    }
  ],
  "suggested_initial_message": "string — ready-to-use holding statement or press response template",
  "missing_information": ["string — specific gap that would meaningfully change the strategy"],
  "next_questions": ["string — follow-up question for the specialist"],
  "retrieved_sources": [{"title": "string", "chapter": "string", "similarity": 0.0}],
  "can_generate_roadmap": true | false
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