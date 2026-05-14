"""
Unified embedding client — outputs 768-dim vectors (Vector(768) schema).

Supported backends (EMBEDDING_BACKEND in .env):
  gemini     – gemini-embedding-001 or text-embedding-004 (FREE, recommended)
               Uses same GEMINI_API_KEY already set for PDF extraction.
  lmstudio   – all-mpnet-base-v2 loaded in LM Studio (768 dims, offline)
  openrouter – fallback, nomic-embed-text-v1.5 (may have issues)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BACKEND = os.getenv("EMBEDDING_BACKEND", "gemini").lower()
DIM = int(os.getenv("EMBEDDING_DIM", "768"))
MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5:free")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://dss-crisis",
                     "X-Title": "Crisis DSS"},
            json={"model": model, "input": texts},
            # removed "dimensions": 1536 for now
        )
        # Log the actual error body before raise_for_status
        if resp.status_code != 200:
            log.error("OpenRouter error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()

    if not api_key or api_key == "lm-studio":
        raise EnvironmentError(
            "OPENAI_API_KEY not set or still set to lm-studio.\n"
            "Get a key at https://platform.openai.com/api-keys\n"
            "Add to .env: OPENAI_API_KEY=sk-..."
        )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": MODEL, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()

    items = sorted(data["data"], key=lambda x: x["index"])
    vectors = [item["embedding"] for item in items]
    _validate_dim(vectors[0])
    return vectors


# OpenRouter (nomic-embed-text-v1.5 with dimensions=1536, free)
async def _embed_openrouter(texts: list[str]) -> list[list[float]]:
    """
    nomic-embed-text-v1.5 supports matryoshka embeddings —
    pass dimensions=1536 to match the existing schema.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model   = os.getenv("OPENROUTER_EMBED_MODEL",
                        "nomic-ai/nomic-embed-text-v1.5:free")

    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY not set.\n"
            "Get one at https://openrouter.ai"
        )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://dss-crisis",
                     "X-Title": "Crisis DSS"},
            json={
                "model": model,
                "input": texts,
                "dimensions": 1536,   # matryoshka — truncate to 1536
            },
        )
        resp.raise_for_status()
        data = resp.json()

    items = sorted(data["data"], key=lambda x: x["index"])
    vectors = [item["embedding"] for item in items]
    _validate_dim(vectors[0])
    return vectors



async def _embed_lmstudio(texts: list[str]) -> list[list[float]]:
    base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1").rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "lm-studio")
    model = os.getenv("LM_STUDIO_EMBED_MODEL", "all-mpnet-base-v2")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model, "input": texts},  # ← lowercase model, not MODEL
        )
        resp.raise_for_status()
        data = resp.json()

    items = sorted(data["data"], key=lambda x: x["index"])
    vectors = [item["embedding"] for item in items]
    _validate_dim(vectors[0])
    return vectors


async def _embed_gemini(texts: list[str]) -> list[list[float]]:
    """
    Google Gemini text-embedding-004 — free, 768 dims.
    Uses the same GEMINI_API_KEY already configured for PDF extraction.
    """
    from google import genai as _genai
    from google.genai import types as _gt

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set.")

    # Strip "models/" prefix if present — SDK adds it automatically
    model = MODEL.removeprefix("models/")

    gc     = _genai.Client(api_key=api_key)
    result = gc.models.embed_content(    # sync call — async method unreliable in v1
        model=model,
        contents=texts,
        config=_gt.EmbedContentConfig(output_dimensionality=DIM),
    )

    vectors = [list(e.values) for e in result.embeddings]
    _validate_dim(vectors[0])
    return vectors


def _validate_dim(vector: list[float]) -> None:
    actual = len(vector)
    if actual != DIM:
        raise ValueError(
            f"Embedding dimension mismatch: expected {DIM} "
            f"(EMBEDDING_DIM={DIM} in .env) but got {actual}.\n"
            f"Fix options:\n"
            f"  1. Switch to OpenAI text-embedding-3-small "
            f"(EMBEDDING_BACKEND=openai) — always outputs 1536\n"
            f"  2. Set EMBEDDING_DIM={actual} and run migration 003"
        )


_EXHAUSTED: set[str] = set()

# Priority order — first available non-exhausted backend is used
_BACKEND_CHAIN = [b.strip() for b in
    os.getenv("EMBEDDING_BACKEND_CHAIN", "gemini,lmstudio").split(",")]

async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, batched to avoid request size limits."""
    if not texts:
        return []

    available = [b for b in _BACKEND_CHAIN if b not in _EXHAUSTED]
    if not available:
        raise RuntimeError(
            f"All embedding backends exhausted: {_EXHAUSTED}. "
            "Restart the process to reset or add more backends."
        )

    results: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vectors = await _call_with_fallback(batch)
        results.extend(vectors)
        log.debug("Embedded batch %d–%d", i, i + len(batch))

    return results

async def _call_with_fallback(texts: list[str]) -> list[list[float]]:
    for backend in [b for b in _BACKEND_CHAIN if b not in _EXHAUSTED]:
        try:
            if backend == "gemini":
                return await _embed_gemini(texts)
            elif backend == "lmstudio":
                return await _embed_lmstudio(texts)
            elif backend == "openrouter":
                return await _embed_openrouter(texts)
            elif backend == "openai":
                return await _embed_openai(texts)
        except Exception as e:
            err = str(e).lower()
            is_quota = any(x in err for x in
                ("resource_exhausted", "quota", "429", "rate", "too many", "daily"))
            if is_quota:
                log.warning("[embed:%s] quota exhausted — switching to next backend", backend)
                _EXHAUSTED.add(backend)
                continue
            # Non-quota error — log and re-raise
            log.error("[embed:%s] error: %s", backend, e)
            raise

    raise RuntimeError("All embedding backends failed or exhausted.")


async def embed_one(text: str) -> list[float]:
    """Embed a single string - convenience wrapper for query embedding."""
    results = await embed_texts([text])
    return results[0]
