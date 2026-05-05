"""
ai_extractor.py  —  Multi-backend fallback extraction
======================================================
Tries backends in priority order. When one hits its daily quota or rate limit
it is marked exhausted and the next one is used automatically.
Processing never stops — it falls through to LM Studio if everything else fails.

Priority (configure in .env — set only the keys you have):
  1. gemini       – Google Gemini Flash       (1 500 req/day, fast)
  2. groq         – Groq Llama 70B            (14 400 req/day, very fast)
  3. openrouter   – OpenRouter free models    (varies, fast)
  4. mistral      – Mistral AI free tier      (varies, fast)
  5. github       – GitHub Models             (free with GitHub account)
  6. lmstudio     – LM Studio local           (unlimited, slow)

.env keys (add only the ones you have — missing keys skip that backend):
  GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY,
  GITHUB_TOKEN (GitHub -> Settings -> Developer -> PAT), OPENAI_BASE_URL, LM_STUDIO_MODEL
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

MAX_TOK = int(os.getenv("MAX_TOK", "8192"))

SYSTEM = (
    "You are a dataset builder for a Decision Support System (DSS) that helps "
    "rookie Communications Specialists handle crisis situations. "
    "You extract structured knowledge from source material. "
    "Respond ONLY in valid JSON — no markdown fences, no commentary, no preamble."
)


def _backends() -> list[dict]:
    """Returns ordered list of configured backend configs."""
    candidates = []

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        candidates.append({
            "name":  "gemini",
            "type":  "gemini",
            "key":   gemini_key,
            "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "delay": 4,
        })

    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        candidates.append({
            "name":     "groq",
            "type":     "openai",
            "key":      groq_key,
            "base_url": "https://api.groq.com/openai/v1",
            "model":    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "delay":    10,
        })

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        candidates.append({
            "name":     "openrouter",
            "type":     "openai",
            "key":      openrouter_key,
            "base_url": "https://openrouter.ai/api/v1",
            "model":    os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            "delay":    2,
            "extra_headers": {
                "HTTP-Referer": "https://github.com/dss-crisis",
                "X-Title":      "DSS Crisis Dataset Builder",
            },
        })

    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    if mistral_key:
        candidates.append({
            "name":     "mistral",
            "type":     "openai",
            "key":      mistral_key,
            "base_url": "https://api.mistral.ai/v1",
            "model":    os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
            "delay":    2,
        })

    github_token = os.getenv("GITHUB_TOKEN", "")
    if github_token:
        candidates.append({
            "name":     "github",
            "type":     "openai",
            "key":      github_token,
            "base_url": "https://models.inference.ai.azure.com",
            "model":    os.getenv("GITHUB_MODEL", "Meta-Llama-3.3-70B-Instruct"),
            "delay":    2,
        })

    lms_url = os.getenv("OPENAI_BASE_URL", "")
    if lms_url:
        candidates.append({
            "name":     "lmstudio",
            "type":     "openai",
            "key":      os.getenv("OPENAI_API_KEY", "lm-studio"),
            "base_url": lms_url,
            "model":    os.getenv("LM_STUDIO_MODEL", os.getenv("MODEL", "local-model")),
            "delay":    0,
        })

    if not candidates:
        raise EnvironmentError(
            "No LLM backends configured.\n"
            "Add at least one to your .env:\n"
            "  GEMINI_API_KEY      = AIza...  (free, https://aistudio.google.com/apikey)\n"
            "  GROQ_API_KEY        = gsk_...  (free, https://console.groq.com)\n"
            "  OPENROUTER_API_KEY  = sk-or-.. (free, https://openrouter.ai)\n"
            "  MISTRAL_API_KEY     = ...       (free, https://console.mistral.ai)\n"
            "  GITHUB_TOKEN        = ghp_...   (free, github.com Settings -> PAT)\n"
            "  OPENAI_BASE_URL     = http://localhost:1234/v1  (LM Studio)\n"
        )
    return candidates

_EXHAUSTED: set[str] = set()   # backends exhausted this session
_ALL_BACKENDS = _backends()

log.info("Fallback chain: %s",
         " -> ".join(b["name"] for b in _ALL_BACKENDS))

def _openai_client(backend: dict):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("poetry add openai")
    kwargs: dict = {"base_url": backend["base_url"], "api_key": backend["key"]}
    if "extra_headers" in backend:
        kwargs["default_headers"] = backend["extra_headers"]
    return OpenAI(**kwargs)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _call_backend(backend: dict, prompt: str) -> tuple[dict, str | None]:
    """Returns (result, error_type). error_type: None=ok, quota, rate, error."""
    name = backend["name"]
    raw  = "{}"

    try:
        if backend["type"] == "gemini":
            from google import genai as _genai
            from google.genai import types as _gt
            gc = _genai.Client(api_key=backend["key"])
            resp = gc.models.generate_content(
                model=backend["model"],
                contents=prompt,
                config=_gt.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    temperature=0.1,
                    max_output_tokens=MAX_TOK,
                    response_mime_type="application/json",
                ),
            )
            raw = _strip_fences(resp.text or "{}")
        else:
            client = _openai_client(backend)
            resp   = client.chat.completions.create(
                model=backend["model"],
                max_tokens=MAX_TOK,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
            )
            raw = _strip_fences(resp.choices[0].message.content or "{}")

        result = json.loads(raw)
        if isinstance(result, list):
            log.warning("[%s] returned bare array — wrapping", name)
            result = {"scenarios": result, "decision_nodes": [], "tactics": [], "qa_pairs": []}
        return result, None

    except json.JSONDecodeError as e:
        log.warning("[%s] JSON parse error: %s | raw: %.200s", name, e, raw)
        return {}, "error"

    except Exception as e:
        err = str(e)

        if "404" in err:
            log.error("[%s] 404 — wrong model name '%s'", name, backend["model"])
            return {}, "error"

        if any(x in err.lower() for x in (
            "resource_exhausted", "quota", "daily", "per_day",
            "exceeded your", "insufficient_quota", "limit reached"
        )):
            log.warning("[%s] Daily quota exhausted", name)
            return {}, "quota"

        if "429" in err or "rate_limit" in err.lower() or "too many" in err.lower():
            return {}, "rate"

        if any(x in err.lower() for x in ("auth", "api_key", "401", "invalid_api_key")):
            log.error("[%s] Auth failed — check key in .env", name)
            return {}, "quota"   # treat as exhausted — wrong key won't fix itself

        log.error("[%s] Error: %s", name, e)
        return {}, "error"

def _call(prompt: str) -> tuple[dict, bool]:
    """
    Tries each backend in order, skipping exhausted ones.
    Returns (result_dict, had_error).
    """
    available = [b for b in _ALL_BACKENDS if b["name"] not in _EXHAUSTED]

    if not available:
        log.error(
            "ALL backends exhausted: %s\n"
            "  -> Add more API keys to .env, start LM Studio, or wait for quota reset.",
            ", ".join(_EXHAUSTED)
        )
        return {}, True

    for backend in available:
        name = backend["name"]

        for attempt in range(3):
            result, err_type = _call_backend(backend, prompt)

            if err_type is None:
                if backend.get("delay"):
                    time.sleep(backend["delay"])
                return result, False

            if err_type == "quota":
                _EXHAUSTED.add(name)
                remaining = [b["name"] for b in _ALL_BACKENDS if b["name"] not in _EXHAUSTED]
                log.info("  Switching to next backend. Remaining: %s",
                         " -> ".join(remaining) if remaining else "NONE")
                break   # move to next backend

            if err_type == "rate":
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    log.warning("[%s] Rate limit — waiting %ss", name, wait)
                    time.sleep(wait)
                    continue
                else:
                    log.warning("[%s] Rate limit persists — skipping this backend for chunk", name)
                    break

            if err_type == "error":
                if attempt < 2:
                    time.sleep(5)
                    continue
                break

    return {}, True


def _lang_note(language: str | None) -> str:
    if language in {"uk", "mixed"}:
        return (
            "\nLANGUAGE NOTE: The passage is in Ukrainian or mixed Ukrainian/English. "
            "Extract all knowledge regardless of source language. "
            "ALL output field values MUST be written in English.\n"
        )
    return ""


def _prompt_combined(passage: str, language: str | None = None) -> str:
    lang = _lang_note(language)
    return (
        f"You are building a crisis communications DSS dataset.\n"
        f"From the passage below, extract ALL of the following in ONE response.{lang}\n"
        f"\n"
        f"Return a single JSON object with exactly these 4 keys:\n"
        f"\n"
        f'"scenarios": array of objects, each with:\n'
        f"  - scenario_id (kebab-case slug)\n"
        f"  - crisis_type (one of: reputational, safety, operational, political, media, natural_disaster, internal)\n"
        f"  - severity (one of: low, medium, high, critical)\n"
        f"  - context (1-2 sentences)\n"
        f"  - key_stakeholders (list of strings)\n"
        f"  - initial_trigger (string)\n"
        f"  - phase (one of: pre_crisis, acute, containment, recovery, post_crisis)\n"
        f"\n"
        f'"decision_nodes": array of objects, each with:\n'
        f"  - decision_id (kebab-case slug)\n"
        f"  - source_scenario_id (matching scenario_id above, or null)\n"
        f"  - situation (what is happening RIGHT NOW)\n"
        f"  - options (array: id like opt-a, action, consequence, is_recommended bool)\n"
        f"  - recommended_action_id (e.g. opt-a)\n"
        f"  - common_rookie_mistake (string)\n"
        f"  - consequence_if_wrong (string)\n"
        f"  - rationale (why the recommended action is correct)\n"
        f"\n"
        f'"tactics": array of objects, each with:\n'
        f"  - name (e.g. Golden Hour Rule)\n"
        f"  - slug (kebab-case)\n"
        f"  - description (2-3 sentences)\n"
        f"  - when_to_apply (1-2 sentences)\n"
        f"  - example (concrete application)\n"
        f"  - anti_pattern (what NOT to do)\n"
        f"  - crisis_types (subset of the 7 types above)\n"
        f"\n"
        f'"qa_pairs": array of 5-8 objects, each with:\n'
        f"  - question (urgent, specific, as a specialist under pressure would ask)\n"
        f"  - answer (expert-level, grounded in the passage)\n"
        f"  - difficulty (one of: basic, intermediate, expert)\n"
        f"  - scenario_tags (list of relevant tags)\n"
        f"  - source_scenario_id (matching scenario_id, or null)\n"
        f"  - common_mistake (what a rookie would say instead)\n"
        f"\n"
        f"If a section has no relevant content, return an empty array [] for that key.\n"
        f"Return ONLY the JSON object. No explanation, no markdown.\n"
        f"\n"
        f"PASSAGE:\n"
        f"{passage}"
    )


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
    language = getattr(chunk, "language", None)
    active   = [b["name"] for b in _ALL_BACKENDS if b["name"] not in _EXHAUSTED]

    log.info("  -> [%s] lang=%s tokens=%s | active backends: %s",
             chunk.chunk_id, language, chunk.token_count,
             " -> ".join(active) if active else "NONE")

    result, had_error = _call(_prompt_combined(chunk.text, language))

    if had_error or not result:
        log.warning("  [%s] failed — will retry on next run", chunk.chunk_id)
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

    log.info("  [%s] %d scenarios, %d decisions, %d tactics, %d qa_pairs",
             chunk.chunk_id, len(scenarios), len(decision_nodes),
             len(tactics), len(qa_pairs))

    return ChunkExtractionResult(
        chunk_id=chunk.chunk_id, source_slug=chunk.source_slug,
        chapter_title=chunk.chapter_title, chapter_index=chunk.chapter_index,
        chunk_index=chunk.chunk_index,
        language=language or "mixed", doc_type=getattr(chunk, "doc_type", "manual"),
        scenarios=scenarios, decision_nodes=decision_nodes,
        tactics=tactics, qa_pairs=qa_pairs,
        had_api_errors=False,
    )