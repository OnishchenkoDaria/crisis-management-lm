from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

MODEL = os.getenv("MODEL", "claude-3-5-sonnet-latest")
MAX_TOK = int(os.getenv("MAX_TOK", "4096"))

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

SYSTEM = (
    "You are a dataset builder for a Decision Support System (DSS) that helps "
    "rookie Communications Specialists handle crisis situations. "
    "You extract structured knowledge from source material. "
    "Respond ONLY in valid JSON — no markdown fences, no commentary, no preamble."
)


def _lang_note(language: str | None) -> str:
    if language in {"uk", "mixed"}:
        return (
            "\nLANGUAGE NOTE: The passage may be in Ukrainian or mixed Ukrainian/English. "
            "Extract knowledge regardless of source language. "
            "ALL output field values MUST be written in English.\n"
        )
    return ""


def _prompt_scenarios(passage: str, language: str | None = None) -> str:
    return f"""From the following passage, extract all CRISIS SCENARIOS described.{_lang_note(language)}
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


def _prompt_decision_nodes(passage: str, scenario_ids: list[str], language: str | None = None) -> str:
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


def _prompt_tactics(passage: str, language: str | None = None) -> str:
    return f"""From the following text, extract all named TACTICS, RULES, or PRINCIPLES for crisis communication.{_lang_note(language)}
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


def _prompt_qa_pairs(passage: str, scenario_ids: list[str], language: str | None = None) -> str:
    ids_hint = (
        f"\nKnown scenario IDs from this chapter: {json.dumps(scenario_ids)}\n"
        if scenario_ids else ""
    )
    return f"""You are building training data for a DSS that guides rookie Communications Specialists.{_lang_note(language)}
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


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _call(user_prompt: str, retries: int = 3) -> list[Any] | dict[str, Any]:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOK,
                system=SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = _strip_json_fences(msg.content[0].text)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("JSON parse error (attempt %s/%s): %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                return []
            time.sleep(2)
        except anthropic.RateLimitError:
            wait = 20 * (attempt + 1)
            log.warning("Rate limit hit — waiting %ss", wait)
            time.sleep(wait)
        except anthropic.APIError as e:
            log.error("Anthropic API error: %s", e)
            if attempt == retries - 1:
                return []
            time.sleep(5)
    return []


# Main extraction function for one chunk
@dataclass
class ChunkExtractionResult:
    chunk_id: str
    source_slug: str
    chapter_title: str
    chapter_index: int
    chunk_index: int
    language: str
    doc_type: str
    scenarios: list
    decision_nodes: list
    tactics: list
    qa_pairs: list


def extract_from_chunk(chunk) -> ChunkExtractionResult:
    passage = chunk.text
    language = getattr(chunk, "language", None)

    log.info("  → Prompt 1 (scenarios)   [%s]", chunk.chunk_id)
    scenarios = _call(_prompt_scenarios(passage, language))
    scenarios = scenarios if isinstance(scenarios, list) else []
    scenario_ids = [s.get("scenario_id", "") for s in scenarios if isinstance(s, dict)]
    time.sleep(1)

    log.info("  → Prompt 3 (tactics)     [%s]", chunk.chunk_id)
    tactics = _call(_prompt_tactics(passage, language))
    tactics = tactics if isinstance(tactics, list) else []
    time.sleep(1)

    log.info("  → Prompt 2 (decisions)   [%s]", chunk.chunk_id)
    decision_nodes = _call(_prompt_decision_nodes(passage, scenario_ids, language))
    decision_nodes = decision_nodes if isinstance(decision_nodes, list) else []
    time.sleep(1)

    log.info("  → Prompt 4 (qa_pairs)    [%s]", chunk.chunk_id)
    qa_pairs = _call(_prompt_qa_pairs(passage, scenario_ids, language))
    qa_pairs = qa_pairs if isinstance(qa_pairs, list) else []
    time.sleep(1)

    for record_list in (scenarios, decision_nodes, tactics, qa_pairs):
        for rec in record_list:
            if isinstance(rec, dict):
                rec["_source_chunk_id"] = chunk.chunk_id
                rec["_source_slug"] = chunk.source_slug
                rec["_chapter_title"] = chunk.chapter_title
                rec["_chapter_index"] = chunk.chapter_index
                rec["_chunk_index"] = chunk.chunk_index
                rec["_language"] = getattr(chunk, "language", "mixed")
                rec["_doc_type"] = getattr(chunk, "doc_type", "manual")

    return ChunkExtractionResult(
        chunk_id=chunk.chunk_id,
        source_slug=chunk.source_slug,
        chapter_title=chunk.chapter_title,
        chapter_index=chunk.chapter_index,
        chunk_index=chunk.chunk_index,
        language=getattr(chunk, "language", "mixed"),
        doc_type=getattr(chunk, "doc_type", "manual"),
        scenarios=scenarios,
        decision_nodes=decision_nodes,
        tactics=tactics,
        qa_pairs=qa_pairs,
    )