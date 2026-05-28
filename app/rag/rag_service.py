"""
Main orchestrator for the RAG query pipeline.
Flow:
  1. retrieve_context()  — embed query + fetch all relevant DB records
  2. build_prompt()      — assemble context into LLM prompt
  3. call_llm()          — send to Mistral / Gemini / OpenRouter
  4. parse_response()    — parse structured JSON response
  5. Return RagQueryResponse
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv

from app.rag.retrieval_service import RetrievedContext, retrieve_context
from app.rag.prompt_builder import build_prompt
from app.rag.schemas import RagQueryRequest, RagQueryResponse, TacticRef, SourceRef

load_dotenv()
log = logging.getLogger(__name__)

# Use the same LLM backend already configured for PDF extraction
LLM_BACKEND  = os.getenv("LLM_BACKEND", "mistral").lower()
LLM_MAX_TOKENS = int(os.getenv("RAG_MAX_TOKENS", "2048"))
ROADMAP_MAX_TOKENS = int(os.getenv("ROADMAP_MAX_TOKENS", "8192"))

MAX_LLM_RETRIES = 3
RETRY_STATUSES  = {429, 500, 502, 503, 504}


async def handle_query(req: RagQueryRequest) -> RagQueryResponse:
    """End-to-end RAG query pipeline."""

    # Retrieve context from DB
    ctx = await retrieve_context(
        req.query,
        crisis_type=req.crisis_type,
        phase=req.phase,
        language=req.language,
        chunk_limit=req.chunk_limit,
    )

    # Build prompt
    system_prompt, user_message = build_prompt(ctx)

    # Call LLM
    raw_response = await _call_llm(system_prompt, user_message)

    # Parse response
    return _parse_response(raw_response, ctx)



async def _call_llm(system_prompt: str, user_message: str, max_tokens: int = LLM_MAX_TOKENS) -> str:
    for attempt in range(MAX_LLM_RETRIES):
        try:
            return await _call_llm_once(system_prompt, user_message, max_tokens)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in RETRY_STATUSES:
                wait = 2 ** attempt   # 1s, 2s, 4s
                log.warning(
                    "LLM returned %d (attempt %d/%d) — retrying in %ds",
                    e.response.status_code, attempt + 1, MAX_LLM_RETRIES, wait,
                )
                if attempt < MAX_LLM_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
            raise
    raise RuntimeError("LLM call failed after all retries")


async def _call_llm_once(system_prompt: str, user_message: str, max_tokens: int = LLM_MAX_TOKENS) -> str:
    if LLM_BACKEND == "mistral":
        return await _call_mistral(system_prompt, user_message, max_tokens)
    elif LLM_BACKEND == "gemini":
        return await _call_gemini(system_prompt, user_message)
    elif LLM_BACKEND in ("openrouter", "groq", "openai", "lmstudio"):
        return await _call_openai_compat(system_prompt, user_message)
    else:
        raise ValueError(f"Unknown LLM_BACKEND='{LLM_BACKEND}'")


async def _call_mistral(system_prompt: str, user_message: str, max_tokens: int = LLM_MAX_TOKENS) -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    model   = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    timeout = 120 if max_tokens > 4096 else 60

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _call_gemini(system_prompt: str, user_message: str) -> str:
    from google import genai as _genai
    from google.genai import types as _gt

    api_key = os.getenv("GEMINI_API_KEY", "")
    model   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    gc   = _genai.Client(api_key=api_key)
    resp = await gc.aio.models.generate_content(
        model=model,
        contents=user_message,
        config=_gt.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            max_output_tokens=LLM_MAX_TOKENS,
            response_mime_type="application/json",
        ),
    )
    return resp.text or "{}"


async def _call_openai_compat(system_prompt: str, user_message: str) -> str:
    base_url = {
        "openrouter": "https://openrouter.ai/api/v1",
        "groq":       "https://api.groq.com/openai/v1",
        "lmstudio":   os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1"),
        "openai":     "https://api.openai.com/v1",
    }[LLM_BACKEND]

    key_env = {
        "openrouter": "OPENROUTER_API_KEY",
        "groq":       "GROQ_API_KEY",
        "lmstudio":   "OPENAI_API_KEY",
        "openai":     "OPENAI_API_KEY",
    }[LLM_BACKEND]

    api_key = os.getenv(key_env, "lm-studio")
    model   = os.getenv("MODEL", "mistral-small-latest")

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": LLM_MAX_TOKENS,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]



def _parse_response(raw: str, ctx: RetrievedContext) -> RagQueryResponse:
    """
    Parse LLM JSON response into RagQueryResponse.
    """
    # Strip markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        import re
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("LLM returned non-JSON response: %s", e)
        return _fallback_response(raw, ctx)

    # Build sources from retrieved chunks
    sources = [
        SourceRef(
            title      = c.source_title,
            chapter    = c.source_chapter,
            similarity = c.similarity,
        )
        for c in ctx.chunks
    ]

    tactics = [
        TacticRef(
            name        = t.get("name", ""),
            description = t.get("description", ""),
        )
        for t in data.get("relevant_tactics", [])
    ]

    return RagQueryResponse(
        direct_answer       = data.get("direct_answer", ""),
        crisis_type         = data.get("crisis_type") or ctx.detected_crisis_type,
        recommended_actions = data.get("recommended_actions", []),
        suggested_message   = data.get("suggested_message", ""),
        risks               = data.get("risks", []),
        relevant_tactics    = tactics,
        sources             = sources,
        confidence          = data.get("confidence", "low"),
        next_steps          = data.get("next_steps", []),
    )


def _fallback_response(raw: str, ctx: RetrievedContext) -> RagQueryResponse:
    """Used when LLM response can't be parsed as JSON."""
    return RagQueryResponse(
        direct_answer       = raw[:500] if raw else "Unable to generate response.",
        crisis_type         = ctx.detected_crisis_type,
        recommended_actions = [],
        suggested_message   = "",
        risks               = ["LLM response was not structured JSON — verify manually."],
        relevant_tactics    = [],
        sources             = [
            SourceRef(title=c.source_title, chapter=c.source_chapter,
                      similarity=c.similarity)
            for c in ctx.chunks
        ],
        confidence          = "low",
        next_steps          = ["Review source documents manually."],
    )