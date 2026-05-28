from __future__ import annotations

from app.analysis.schemas import SituationInput, RefinementRequest
from app.rag.book_registry import resolve_citation

ANALYSIS_SYSTEM = """You are an expert Crisis Communications Decision Support System (DSS).
You advise Communications Specialists in real-time during active crises.

BEHAVIORAL RULES:
1. Always provide concrete tactical recommendations — never withhold strategy due to missing data.
2. When information is incomplete, state your assumptions explicitly and advise based on the most likely scenario.
3. Base ALL recommendations strictly on the provided context documents and structured knowledge.
4. If context is weak or absent for a specific point — say so in missing_information.
5. Treat missing_information as "would improve the analysis" — not as a blocker to giving advice.
6. Do NOT invent facts, case precedents, or statistics not present in the retrieved context.
7. List at most 3 items in missing_information — only the gaps that would meaningfully change the strategy.
8. Tone: direct, tactical, professional. No academic padding.
9. Return ONLY valid JSON matching the schema below. No markdown, no preamble.

CLARIFICATION LOGIC:
- Set can_generate_roadmap: true if confidence is "medium" or "high".
- Set can_generate_roadmap: false ONLY when confidence is "low" AND missing_information has more than 2 critical items.
- If user has already provided clarifications, set can_generate_roadmap: true regardless.

REQUIRED JSON SCHEMA:
{
  "crisis_summary": "string — 2-3 sentences describing the situation and any stated assumptions",
  "detected_crisis_type": "media|reputational|operational|safety|political|internal|natural_disaster",
  "urgency_level": "critical|high|medium|low",
  "phase": "pre_crisis|acute|containment|recovery|post_crisis",
  "confidence": "high|medium|low",
  "key_risks": ["string — specific risk with stated consequence"],
  "stakeholders": ["string"],
  "recommended_strategy": "string — core strategic direction in 3-4 sentences, with rationale",
  "relevant_tactics": [
    {
      "name": "string",
      "description": "string — how to apply this tactic to THIS specific situation",
      "anti_pattern": "string — the specific mistake to avoid here, or null"
    }
  ],
  "suggested_initial_message": "string — ready-to-use holding statement in the OUTPUT LANGUAGE specified below",
  "missing_information": ["string — specific gap that would meaningfully change the strategy"],
  "next_questions": ["string — focused clarifying question"],
  "can_generate_roadmap": true
}"""


ROADMAP_SYSTEM = """You are generating a detailed Crisis Communications Action Roadmap.
Base it strictly on the confirmed analysis and retrieved source documents.

RULES:
1. Every action item must reference a source from the retrieved knowledge where applicable.
2. Timing must be realistic — do not cluster everything in T0.
3. Owner roles must be specific (e.g. "Head of Communications", not "team member").
4. Return ONLY valid JSON. No markdown, no preamble.

Return ONLY valid JSON matching this schema:
{
  "executive_summary": "string",
  "crisis_type": "media|reputational|operational|safety|political|internal|natural_disaster",
  "confidence": "high|medium|low",
  "phases": [
    {
      "id": "t0_30min",
      "label": "T0 – 30 minutes",
      "description": "string",
      "action_items": [
        {
          "id": "a1",
          "title": "string",
          "description": "string",
          "priority": "immediate|high|medium|low",
          "owner_role": "string",
          "channel": "string|null",
          "due_hint": "string",
          "rationale": "string",
          "risk_if_skipped": "string",
          "source_refs": ["string"]
        }
      ]
    }
  ],
  "communication_messages": [{"channel":"string","message":"string","timing":"string","tone":"string"}],
  "monitoring_plan": [{"metric":"string","frequency":"string","owner":"string","threshold":"string"}],
  "escalation_rules": [{"trigger":"string","action":"string","owner_role":"string"}],
  "risks": ["string"],
  "next_steps": ["string"]
}

Roadmap phases MUST be exactly:
  1. t0_30min    → T0 – 30 minutes     (immediate containment)
  2. t30_2h      → 30 min – 2 hours    (situation management)
  3. t2_24h      → 2 – 24 hours        (stabilisation)
  4. t1_7days    → 1 – 7 days          (recovery)
  5. monitoring  → Ongoing monitoring  (follow-up)"""


def build_analysis_prompt(
    situation: SituationInput,
    ctx,
    workspace_ctx: dict,
    refinement: RefinementRequest | None = None,
) -> tuple[str, str]:

    # Determine output language from workspace
    lang_code  = workspace_ctx.get("language", "ua") if workspace_ctx else "ua"
    lang_label = "Ukrainian" if lang_code == "ua" else "English"

    system = ANALYSIS_SYSTEM + f"""

    OUTPUT LANGUAGE RULE:
    - Analyse the situation in whatever language the user provided it.
    - Write crisis_summary, recommended_strategy, relevant_tactics, key_risks,
      and next_questions in {lang_label}.
    - Write suggested_initial_message ONLY in {lang_label} — this is the text
      the organisation will publish and must match their audience's language.
    - Never mix languages within a single field."""

    parts = []

    # Workspace context
    if workspace_ctx:
        parts.append("── WORKSPACE CONTEXT ──")
        for k, v in workspace_ctx.items():
            if v and k not in ("id", "created_at", "updated_at"):
                parts.append(f"{k}: {v}")

    # Situation form
    parts.append("\n── CRISIS SITUATION ──")
    parts.append(f"Description: {situation.situation_description}")
    if situation.crisis_type:
        parts.append(f"Declared crisis type: {situation.crisis_type.value}")
    if situation.urgency_level:
        parts.append(f"Declared urgency: {situation.urgency_level.value}")
    if situation.affected_stakeholders:
        parts.append(f"Stakeholders: {', '.join(situation.affected_stakeholders)}")
    if situation.communication_channels:
        parts.append(f"Channels: {', '.join(situation.communication_channels)}")
    if situation.current_public_reaction:
        parts.append(f"Public reaction: {situation.current_public_reaction}")
    if situation.already_published:
        parts.append(f"Already published: {situation.already_published}")
    if situation.internal_constraints:
        parts.append(f"Constraints: {situation.internal_constraints}")
    if situation.desired_tone:
        parts.append(f"Desired tone: {situation.desired_tone}")
    if situation.legal_risks:
        parts.append(f"Legal risks: {', '.join(situation.legal_risks)}")

    # Refinement
    if refinement:
        parts.append("\n── USER CLARIFICATION ──")
        if refinement.user_comment:
            parts.append(f"User provided: {refinement.user_comment}")
        if refinement.additional_context:
            parts.append(f"Additional context: {refinement.additional_context}")
        if refinement.changed_constraints:
            parts.append(f"Changed constraints: {', '.join(refinement.changed_constraints)}")

    # RAG context
    if ctx.chunks:
        parts.append("\n── RELEVANT SOURCE PASSAGES ──")
        for i, c in enumerate(ctx.chunks, 1):
            citation = resolve_citation(c.source_title, c.source_chapter)
            parts.append(f"[{i}] {citation} (relevance: {c.similarity:.0%})")
            parts.append(c.text[:500] + ("…" if len(c.text) > 500 else ""))

    if ctx.scenarios:
        parts.append("\n── MATCHING CRISIS SCENARIOS ──")
        for s in ctx.scenarios:
            parts.append(f"- {s['title']}: {s['crisis_type']}, {s['severity']}, {s['phase']}")
            parts.append(f"  {s['context']}")

    if ctx.tactics:
        parts.append("\n── APPLICABLE TACTICS ──")
        for t in ctx.tactics:
            parts.append(f"• {t['name']}: {t.get('description','')[:200]}")
            if t.get("anti_pattern"):
                parts.append(f"  Anti-pattern: {t['anti_pattern']}")

    if ctx.decision_nodes:
        parts.append("\n── DECISION POINTS ──")
        for d in ctx.decision_nodes:
            parts.append(f"Situation: {d.get('situation','')}")
            parts.append(f"  Recommended: {d.get('recommended_action','')}")
            parts.append(f"  Common mistake: {d.get('common_mistake','')}")

    return system, "\n".join(parts)


def build_roadmap_prompt(
    stored_analysis: dict,
    ctx,
    workspace_ctx: dict | None = None,
) -> tuple[str, str]:
    lang_code  = (workspace_ctx or {}).get("language", "ua")
    lang_label = "Ukrainian" if lang_code == "ua" else "English"

    system = ROADMAP_SYSTEM + f"\n\nOUTPUT LANGUAGE: Generate all text fields in {lang_label}."

    parts = ["── CONFIRMED ANALYSIS ──"]
    resp = stored_analysis.get("response_json", stored_analysis)

    parts.append(f"Crisis type:     {resp.get('detected_crisis_type','')}")
    parts.append(f"Urgency:         {resp.get('urgency_level','')}")
    parts.append(f"Phase:           {resp.get('phase','')}")
    parts.append(f"Summary:         {resp.get('crisis_summary','')}")
    parts.append(f"Strategy:        {resp.get('recommended_strategy','')}")

    if resp.get("key_risks"):
        parts.append(f"Key risks: {'; '.join(resp['key_risks'])}")
    if resp.get("stakeholders"):
        parts.append(f"Stakeholders: {', '.join(resp['stakeholders'])}")

    situation = stored_analysis.get("situation_input", {})
    if situation.get("internal_constraints"):
        parts.append(f"Constraints: {situation['internal_constraints']}")
    if situation.get("desired_tone"):
        parts.append(f"Tone: {situation['desired_tone']}")

    if ctx.chunks:
        parts.append("\n── RETRIEVED KNOWLEDGE ──")
        for i, c in enumerate(ctx.chunks, 1):
            citation = resolve_citation(c.source_title, c.source_chapter)
            parts.append(f"[{i}] {citation}")
            parts.append(c.text[:400] + ("…" if len(c.text) > 400 else ""))

    if ctx.tactics:
        parts.append("\n── TACTICS ──")
        for t in ctx.tactics:
            parts.append(f"• {t['name']}: {t.get('description','')[:150]}")

    return system, "\n".join(parts)