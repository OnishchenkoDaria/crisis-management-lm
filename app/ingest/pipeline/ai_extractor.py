"""
ai_extractor.py
Runs the 4 extraction prompts against a single text chunk.
Returns structured JSON for each prompt type.
"""

import json
import time
import logging
from dataclasses import dataclass

import anthropic

log = logging.getLogger(__name__)

import os
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL")
MAX_TOK = os.getenv("MAX_TOK")

client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env


# ── System prompt shared across all extraction calls ─────────────────────────
SYSTEM = (
    "You are a dataset builder for a Decision Support System (DSS) that helps "
    "rookie Communications Specialists handle crisis situations. "
    "You extract structured knowledge from source material. "
    "Respond ONLY in valid JSON — no markdown fences, no commentary, no preamble."
)


def _prompt_scenarios(passage: str) -> str:
    return f"""From the following passage, extract all CRISIS SCENARIOS described.
    For each scenario output a JSON object with these fields:
    - scenario_id: short kebab-case slug (e.g. "chemical-spill-public-panic")
    - crisis_type: one of [reputational, safety, operational, political, media, natural_disaster, internal]
    - severity: one of [low, medium, high, critical]
    - context: 1-2 sentences describing the situation
    - key_stakeholders: list of affected parties (e.g. ["media", "public", "CEO", "employees"])
    - initial_trigger: what caused the crisis
    - phase: one of [pre_crisis, acute, containment, recovery, post_crisis]
    
    Respond ONLY as a JSON array. If no scenarios are present, return [].

PASSAGE:
{passage}"""


def _prompt_decision_nodes(passage: str, scenario_ids: list[str]) -> str:
    ids_hint = (
        f"\nKnown scenario IDs from this chapter: {json.dumps(scenario_ids)}\n"
        "Link each decision node to one of these IDs in the source_scenario_id field."
        if scenario_ids else ""
    )
    return f"""From the passage below, extract all DECISION POINTS a Communications Specialist must navigate.
    For each decision point output a JSON object:{ids_hint}
    - decision_id: short kebab-case slug
    - source_scenario_id: matching scenario_id from the passage (or null)
    - situation: what is happening RIGHT NOW at this decision point
    - options: array of objects with fields: id (opt-a/opt-b/...), action, consequence, is_recommended (bool)
    - recommended_action_id: the id of the best option (e.g. "opt-a")
    - common_rookie_mistake: describe the wrong choice rookies typically make
    - consequence_if_wrong: what happens if the wrong choice is made
    - rationale: why the recommended action is correct
    
    Respond ONLY as a JSON array. If no decision points are found, return [].

    PASSAGE:
    {passage}"""


def _prompt_tactics(passage: str) -> str:
    return f"""From the following text, extract all named TACTICS, RULES, or PRINCIPLES for crisis communication.
    For each one output a JSON object:
    - name: the tactic or rule name (e.g. "Golden Hour Rule")
    - slug: kebab-case version (e.g. "golden-hour-rule")
    - description: what it means in plain terms (2-3 sentences)
    - when_to_apply: the triggering condition (1-2 sentences)
    - example: a concrete application example (from the text or synthesized if absent)
    - anti_pattern: the wrong version of this tactic — what NOT to do
    - crisis_types: list of crisis types this applies to, subset of [reputational, safety, operational, political, media, natural_disaster, internal]
    
    Respond ONLY as a JSON array. If no tactics are found, return [].

    PASSAGE:
    {passage}"""


def _prompt_qa_pairs(passage: str, scenario_ids: list[str]) -> str:
    ids_hint = (
        f"\nKnown scenario IDs from this chapter: {json.dumps(scenario_ids)}\n"
        if scenario_ids else ""
    )
    return f"""You are building training data for a DSS that guides rookie Communications Specialists.

    From the passage below, generate 10-15 realistic Q&A pairs that a rookie specialist might ask
    the system during a crisis.{ids_hint}
    Questions must be:
    - Urgent and specific, not academic
    - Phrased as a person under pressure would ask them
    - Varied: mix tactical (what do I do right now) and strategic (how should I frame this)
    
    For each pair output a JSON object:
    - question: the question as the specialist would ask it
    - answer: expert-level answer grounded strictly in the passage
    - difficulty: one of [basic, intermediate, expert]
    - scenario_tags: list of relevant tags (crisis type, phase, stakeholder, etc.)
    - source_scenario_id: matching scenario_id if applicable, else null
    - common_mistake: what a rookie would incorrectly say or do instead
    
    Respond ONLY as a JSON array.
    
    PASSAGE:
    {passage}"""


# Single API call with retry
def _call(user_prompt: str, retries: int = 3) -> list | dict:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model      = MODEL,
                max_tokens = int(MAX_TOK),
                system     = SYSTEM,
                messages   = [{"role": "user", "content": user_prompt}],
            )
            raw = msg.content[0].text.strip()
            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error (attempt {attempt+1}): {e}")
            if attempt == retries - 1:
                log.error("All retries exhausted for JSON parsing.")
                return []
        except anthropic.RateLimitError:
            wait = 20 * (attempt + 1)
            log.warning(f"Rate limit hit — waiting {wait}s …")
            time.sleep(wait)
        except anthropic.APIError as e:
            log.error(f"API error: {e}")
            if attempt == retries - 1:
                return []
            time.sleep(5)
    return []


import re  # needed for fence stripping above


# Main extraction function for one chunk
@dataclass
class ChunkExtractionResult:
    chunk_id:       str
    source_slug:    str
    chapter_title:  str
    chapter_index:  int
    chunk_index:    int
    scenarios:      list
    decision_nodes: list
    tactics:        list
    qa_pairs:       list


def extract_from_chunk(chunk) -> ChunkExtractionResult:
    """
    Runs all 4 prompts against one TextChunk.
    Prompts 1 and 3 run first (parallel-safe but kept sequential for rate limits).
    Prompts 2 and 4 use scenario IDs from Prompt 1.
    """
    passage = chunk.text
    log.info(f"  → Prompt 1 (scenarios)   [{chunk.chunk_id}]")
    scenarios = _call(_prompt_scenarios(passage))
    scenario_ids = [s.get("scenario_id", "") for s in scenarios if isinstance(s, dict)]

    # Small pause to respect rate limits
    time.sleep(1)

    log.info(f"  → Prompt 3 (tactics)     [{chunk.chunk_id}]")
    tactics = _call(_prompt_tactics(passage))
    time.sleep(1)

    log.info(f"  → Prompt 2 (decisions)   [{chunk.chunk_id}]")
    decision_nodes = _call(_prompt_decision_nodes(passage, scenario_ids))
    time.sleep(1)

    log.info(f"  → Prompt 4 (qa_pairs)    [{chunk.chunk_id}]")
    qa_pairs = _call(_prompt_qa_pairs(passage, scenario_ids))
    time.sleep(1)

    # Stamp every record with provenance
    for record_list in (scenarios, decision_nodes, tactics, qa_pairs):
        for rec in record_list:
            if isinstance(rec, dict):
                rec["_source_chunk_id"]   = chunk.chunk_id
                rec["_source_slug"]       = chunk.source_slug
                rec["_chapter_title"]     = chunk.chapter_title
                rec["_chapter_index"]     = chunk.chapter_index

    return ChunkExtractionResult(
        chunk_id       = chunk.chunk_id,
        source_slug    = chunk.source_slug,
        chapter_title  = chunk.chapter_title,
        chapter_index  = chunk.chapter_index,
        chunk_index    = chunk.chunk_index,
        scenarios      = scenarios      if isinstance(scenarios,      list) else [],
        decision_nodes = decision_nodes if isinstance(decision_nodes, list) else [],
        tactics        = tactics        if isinstance(tactics,        list) else [],
        qa_pairs       = qa_pairs       if isinstance(qa_pairs,       list) else [],
    )