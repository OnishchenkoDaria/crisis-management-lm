"""
ai_extractor.py
One API call per chunk — extracts all 4 data types simultaneously.

Before: 4 calls/chunk × 46 chunks = 184 API calls per book
After:  1 call/chunk × 46 chunks =  46 API calls per book  (4× less quota)

Supported backends (LLM_BACKEND in .env):
  gemini            – Google Gemini (free, 1500 req/day)  ← recommended
  groq              – Groq (free, 30 req/min)
  anthropic         – Anthropic Claude (paid)
  openai            – OpenAI (paid)
  lmstudio          – LM Studio local
  openai_compatible – Any OpenAI-compatible endpoint
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic as _antropic
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BACKEND = os.getenv("LLM_BACKEND", "gemini").lower().strip()
MODEL   = os.getenv("MODEL", {
    "gemini":            "gemini-2.0-flash",
    "groq":              "llama-3.3-70b-versatile",
    "anthropic":         "claude-3-5-sonnet-latest",
    "openai":            "gpt-4o-mini",
    "lmstudio":          "local-model",
    "openai_compatible": "local-model",
}.get(BACKEND, "gemini-2.0-flash"))

MAX_TOK = int(os.getenv("MAX_TOK", "8192"))

# Inter-call delay (only matters for rate-limited backends)
# With 1 call/chunk these limits are rarely hit
_DELAY = {
    "gemini": 4,    # 15 RPM free → 4s safe
    "groq":   10,   # 30 RPM free → 10s safe (vs 62s with 4 calls)
}.get(BACKEND, 0)

def _build_client():
    if BACKEND == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "GEMINI_API_KEY not set.\n"
                "Get free key: https://aistudio.google.com/apikey\n"
                "Add to .env:  GEMINI_API_KEY=AIza..."
            )
        class _G:
            api_key = key
        return _G()

    if BACKEND == "anthropic":
        try:
            import anthropic as _a
        except ImportError:
            raise ImportError("pip install anthropic")
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set.")
        return _a.Anthropic(api_key=key)

    if BACKEND in ("groq", "openai", "lmstudio", "openai_compatible"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai")

        if BACKEND == "groq":
            key = os.getenv("GROQ_API_KEY", "")
            if not key:
                raise EnvironmentError(
                    "GROQ_API_KEY not set.\n"
                    "Get free key: https://console.groq.com → API Keys\n"
                    "Add to .env:  GROQ_API_KEY=gsk_..."
                )
            return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)

        base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
        api_key  = os.getenv("OPENAI_API_KEY", "lm-studio")
        return OpenAI(base_url=base_url, api_key=api_key)

    raise ValueError(f"Unknown LLM_BACKEND='{BACKEND}'. "
                     "Choose: gemini, groq, anthropic, openai, lmstudio, openai_compatible")


client = _build_client()
log.info("LLM backend: %s | model: %s | delay: %ss", BACKEND, MODEL, _DELAY)

SYSTEM = (
    "You are a dataset builder for a Decision Support System (DSS) that helps "
    "rookie Communications Specialists handle crisis situations. "
    "You extract structured knowledge from source material. "
    "Respond ONLY in valid JSON — no markdown fences, no commentary, no preamble."
)


def _lang_note(language: str | None) -> str:
    if language in {"uk", "mixed"}:
        return (
            "\nLANGUAGE NOTE: The passage is in Ukrainian or mixed Ukrainian/English. "
            "Extract all knowledge regardless of source language. "
            "ALL output field values MUST be written in English.\n"
        )
    return ""


def _prompt_combined(passage: str, language: str | None = None) -> str:
        """
        One prompt that extracts all 4 data types in a single API call.
        Returns a JSON object with keys: scenarios, decision_nodes, tactics, qa_pairs.
        """
        return f"""You are building a crisis communications DSS dataset.
    From the passage below, extract ALL of the following in ONE response.{_lang_note(language)}
    
    Return a single JSON object with exactly these 4 keys:
    
    "scenarios": array of objects, each with:
      - scenario_id (kebab-case slug)
      - crisis_type (one of: reputational, safety, operational, political, media, natural_disaster, internal)
      - severity (one of: low, medium, high, critical)
      - context (1-2 sentences)
      - key_stakeholders (list of strings)
      - initial_trigger (string)
      - phase (one of: pre_crisis, acute, containment, recovery, post_crisis)
    
    "decision_nodes": array of objects, each with:
      - decision_id (kebab-case slug)
      - source_scenario_id (matching scenario_id above, or null)
      - situation (what is happening RIGHT NOW)
      - options (array: id like "opt-a", action, consequence, is_recommended bool)
      - recommended_action_id (e.g. "opt-a")
      - common_rookie_mistake (string)
      - consequence_if_wrong (string)
      - rationale (why the recommended action is correct)
    
    "tactics": array of objects, each with:
      - name (e.g. "Golden Hour Rule")
      - slug (kebab-case)
      - description (2-3 sentences)
      - when_to_apply (1-2 sentences)
      - example (concrete application)
      - anti_pattern (what NOT to do)
      - crisis_types (subset of the 7 types above)
    
    "qa_pairs": array of 5-8 objects, each with:
      - question (urgent, specific, as a specialist under pressure would ask)
      - answer (expert-level, grounded in the passage)
      - difficulty (one of: basic, intermediate, expert)
      - scenario_tags (list of relevant tags)
      - source_scenario_id (matching scenario_id, or null)
      - common_mistake (what a rookie would say instead)
    
    If a section has no relevant content, return an empty array [] for that key.
    Return ONLY the JSON object. No explanation, no markdown.
    
    PASSAGE:
    {passage}"""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$",          "", raw)
    return raw.strip()


def _call(prompt: str, retries: int = 3) -> tuple[dict, bool]:
    """Returns (parsed_dict, had_error)."""
    for attempt in range(retries):
        try:
            if BACKEND == "gemini":
                from google import genai as _genai
                from google.genai import types as _gt
                gc = _genai.Client(api_key=client.api_key)
                resp = gc.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=_gt.GenerateContentConfig(
                        system_instruction=SYSTEM,
                        temperature=0.1,
                        max_output_tokens=MAX_TOK,
                        response_mime_type="application/json",
                    ),
                )
                raw = _strip_fences(resp.text or "{}")

            elif BACKEND == "anthropic":
                msg = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOK,
                    system=SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = _strip_fences(msg.content[0].text)

            else:  # groq / openai / lmstudio / openai_compatible
                resp = client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOK,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                )
                raw = _strip_fences(resp.choices[0].message.content or "{}")

            result = json.loads(raw)
            # Accept both object and bare array (guard against model wrapping in array)
            if isinstance(result, list):
                log.warning("Model returned a bare array — wrapping. Check prompt compliance.")
                result = {"scenarios": result, "decision_nodes": [], "tactics": [], "qa_pairs": []}
            return result, False

        except json.JSONDecodeError as e:
            log.warning("JSON parse error (attempt %s/%s): %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                return {}, True
            time.sleep(3)

        except Exception as e:
            err = str(e)

            if "404" in err:
                log.error(
                    "404 Not Found — wrong model name.\n"
                    "  Current MODEL=%s\n"
                    "  Try: MODEL=gemini-2.0-flash  or  MODEL=gemini-1.5-flash", MODEL
                )
                return {}, True

            is_quota = any(x in err.lower() for x in
                           ("resource_exhausted", "quota", "daily", "per_day"))
            is_rate  = "429" in err or "rate" in err.lower()

            if is_quota:
                log.error(
                    "DAILY QUOTA EXHAUSTED (%s).\n"
                    "  Quota resets at midnight Pacific Time.\n"
                    "  Options:\n"
                    "    1. Wait until tomorrow — all completed chunks are cached\n"
                    "    2. Try MODEL=gemini-1.5-flash (separate quota bucket)\n"
                    "    3. Create a second Google account for a fresh key", BACKEND
                )
                return {}, True  # don't retry — quota won't recover in 60s

            if is_rate:
                wait = 60 if BACKEND == "gemini" else 20 * (attempt + 1)
                log.warning("Rate limit — waiting %ss", wait)
                time.sleep(wait)
                continue

            if any(x in err.lower() for x in ("auth", "api_key", "401")):
                log.error("Auth failed for %s: %s", BACKEND, e)
                return {}, True

            log.error("API error (attempt %s/%s): %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                return {}, True
            time.sleep(5)

    return {}, True


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
    scenarios: list = field(default_factory=list)
    decision_nodes: list = field(default_factory=list)
    tactics: list = field(default_factory=list)
    qa_pairs: list = field(default_factory=list)
    had_api_errors: bool = False


def _tag(records: list, chunk) -> list:
    for rec in records:
        if isinstance(rec, dict):
            rec["_source_chunk_id"] = chunk.chunk_id
            rec["_source_slug"]     = chunk.source_slug
            rec["_chapter_title"]   = chunk.chapter_title
            rec["_chapter_index"]   = chunk.chapter_index
            rec["_chunk_index"]     = chunk.chunk_index
            rec["_language"]        = getattr(chunk, "language", "mixed")
            rec["_doc_type"]        = getattr(chunk, "doc_type", "manual")
    return records


def extract_from_chunk(chunk) -> ChunkExtractionResult:
    """
    Single API call per chunk - extracts scenarios, decision_nodes,
    tactics and qa_pairs simultaneously.
    """
    language = getattr(chunk, "language", None)

    log.info("  → Combined extraction [%s] lang=%s (%s tokens)",
             chunk.chunk_id, language, chunk.token_count)

    result, had_error = _call(_prompt_combined(chunk.text, language))

    if had_error or not result:
        log.warning("  WARNING [%s] API error — will retry on next run", chunk.chunk_id)
        return ChunkExtractionResult(
            chunk_id=chunk.chunk_id, source_slug=chunk.source_slug,
            chapter_title=chunk.chapter_title, chapter_index=chunk.chapter_index,
            chunk_index=chunk.chunk_index,
            language=language or "mixed", doc_type=getattr(chunk, "doc_type", "manual"),
            had_api_errors=True,
        )

    scenarios      = _tag(result.get("scenarios",      []) or [], chunk)
    decision_nodes = _tag(result.get("decision_nodes", []) or [], chunk)
    tactics        = _tag(result.get("tactics",        []) or [], chunk)
    qa_pairs       = _tag(result.get("qa_pairs",       []) or [], chunk)

    total = len(scenarios) + len(decision_nodes) + len(tactics) + len(qa_pairs)
    log.info("  ✓ [%s] %d scenarios, %d decisions, %d tactics, %d qa_pairs",
             chunk.chunk_id, len(scenarios), len(decision_nodes),
             len(tactics), len(qa_pairs))

    if _DELAY:
        time.sleep(_DELAY)

    return ChunkExtractionResult(
        chunk_id=chunk.chunk_id, source_slug=chunk.source_slug,
        chapter_title=chunk.chapter_title, chapter_index=chunk.chapter_index,
        chunk_index=chunk.chunk_index,
        language=language or "mixed", doc_type=getattr(chunk, "doc_type", "manual"),
        scenarios=scenarios, decision_nodes=decision_nodes,
        tactics=tactics, qa_pairs=qa_pairs,
        had_api_errors=False,
    )