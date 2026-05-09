"""
storage.py
Handles all file I/O for the DSS pipeline.

Key fixes vs original:
  1. All read_text() / open() calls use encoding='utf-8' (Windows cp1251 crash fix)
  2. is_chunk_done() checks for _completed marker, not just file existence
     — chunks that failed (API 400/timeout) saved [] but no _completed marker
     — they are re-processed on restart instead of being permanently skipped
  3. save_chunk_result() only writes _completed when extraction had no API errors

Primary storage: PostgreSQL (via IngestDAO).
File storage (kept only for idempotency and restart):
  data/extracted/{slug}/metadata.json        — book info
  data/extracted/{slug}/chunk_manifest.json  — chunk text + positions
  data/extracted/{slug}/chunks/{id}/_completed — success marker
  data/processed/*.jsonl                     — JSONL export (secondary/backup)
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def get_book_dir(source_slug: str) -> Path:
    p = DATA_DIR / "extracted" / source_slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_manifest_entry(source_slug: str, chunk_id: str) -> dict:
    """Load manifest entry for one chunk (needed for RagChunk text + metadata)."""
    manifest_path = get_book_dir(source_slug) / "chunk_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
            if entry.get("chunk_id") == chunk_id:
                return entry
    except (json.JSONDecodeError, KeyError):
        pass
    return {}


async def _ensure_source_doc_async(source_slug: str) -> int | None:
    """Get or create SourceDocument in DB, return its id."""
    try:
        from app.ingest.dao.ingest_dao import SourceDocumentDAO
    except ImportError:
        log.warning("IngestDAO not importable — DB save skipped")
        return None

    meta_path = get_book_dir(source_slug) / "metadata.json"
    if not meta_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    doc = await SourceDocumentDAO.get_or_create(
        source_slug  = source_slug,
        title        = meta.get("title", source_slug),
        file_name    = meta.get("file_name", ""),
        language     = meta.get("language", "mixed"),
        doc_type     = meta.get("doc_type", "manual"),
        total_chunks = meta.get("total_chunks", 0),
        meta         = meta,
    )
    return doc.id if doc else None


def save_book_metadata(source_slug: str, metadata: dict) -> None:
    path = get_book_dir(source_slug) / "metadata.json"
    metadata["_created_at"] = datetime.now(timezone.utc).isoformat()
    # encoding='utf-8' — critical on Windows where default is cp1251
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"  ✓ metadata saved → {path}")


def save_chunk_result(result) -> None:
    """
    Persist one completed ChunkExtractionResult.

    Success  -> writes _completed marker + saves all records to PostgreSQL.
    Failure  -> removes stale _completed marker, nothing written to DB.

    JSON files (scenarios.json etc.) are NO LONGER written to disk.
    PostgreSQL is the primary storage for extracted records.
    The _completed marker and chunk_manifest.json are kept for idempotency.
    """
    chunk_dir = get_book_dir(result.source_slug) / "chunks" / result.chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    total      = (len(result.scenarios) + len(result.decision_nodes)
                  + len(result.tactics) + len(result.qa_pairs))
    had_errors = getattr(result, "had_api_errors", False)

    if had_errors:
        completed_path = chunk_dir / "_completed"
        if completed_path.exists():
            completed_path.unlink()
        log.info(
            "  WARNING: saved (API errors - will retry) [%s]: "
            "%d scenarios, %d decisions, %d tactics, %d qa_pairs%s",
            result.chunk_id,
            len(result.scenarios), len(result.decision_nodes),
            len(result.tactics), len(result.qa_pairs),
            "  [all empty]" if total == 0 else "  [total=%d]" % total,
        )
        return

    # Write _completed marker
    (chunk_dir / "_completed").write_text(
        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
    )

    # Save to PostgreSQL
    try:
        from app.ingest.dao.ingest_dao import IngestDAO

        manifest_entry = _load_manifest_entry(result.source_slug, result.chunk_id)
        source_doc_id  = asyncio.run(_ensure_source_doc_async(result.source_slug))

        if source_doc_id:
            db_counts = asyncio.run(
                IngestDAO.save_chunk_result(result, manifest_entry, source_doc_id)
            )
            log.info(
                "  completed [%s]: %d scenarios, %d decisions, %d tactics, "
                "%d qa_pairs [total=%d] -> DB: %s",
                result.chunk_id,
                len(result.scenarios), len(result.decision_nodes),
                len(result.tactics), len(result.qa_pairs),
                total, db_counts,
            )
        else:
            log.warning(
                "  completed [%s] but DB save skipped (metadata.json missing or DB unavailable)",
                result.chunk_id,
            )

    except Exception as e:
        log.error(
            "  completed [%s] but DB save FAILED: %s"
            " -- run `python -m app.run --promote-only` to retry.",
            result.chunk_id, e,
        )


def is_chunk_done(source_slug: str, chunk_id: str) -> bool:
    """
    A chunk is done if _completed marker exists.
    Fast file-based check — no DB query needed on every chunk at startup.
    JSON result files are no longer written, so we only check the marker.
    """
    chunk_dir = get_book_dir(source_slug) / "chunks" / chunk_id
    return (chunk_dir / "_completed").exists()


def merge_book_to_processed(source_slug: str) -> dict:
    """
    Merge completed chunk results into data/processed/*.jsonl
    Only processes chunks that have the _completed marker.
    Appending is safe — run for multiple books sequentially.
    """
    book_dir  = get_book_dir(source_slug)
    proc_dir  = DATA_DIR / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    counts = dict(scenarios=0, decision_nodes=0, tactics=0, qa_pairs=0, rag_chunks=0)

    chunks_root = book_dir / "chunks"
    if not chunks_root.exists():
        log.warning(f"No chunks directory found for {source_slug}")
        return counts

    chunk_dirs = sorted(d for d in chunks_root.glob("*") if d.is_dir())
    if not chunk_dirs:
        log.warning(f"No chunk dirs found for {source_slug}")
        return counts

    # load manifest for RAG chunk records
    manifest: dict = {}
    manifest_path = book_dir / "chunk_manifest.json"
    if manifest_path.exists():
        try:
            for c in json.loads(manifest_path.read_text(encoding="utf-8")):
                manifest[c["chunk_id"]] = c
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"Could not parse chunk_manifest.json: {e}")

    files = {
        "scenarios":      proc_dir / "scenarios.jsonl",
        "decision_nodes": proc_dir / "decision_nodes.jsonl",
        "tactics":        proc_dir / "tactics.jsonl",
        "qa_pairs":       proc_dir / "qa_pairs.jsonl",
        "rag_chunks":     proc_dir / "rag_chunks.jsonl",
    }

    handles = {k: open(v, "a", encoding="utf-8") for k, v in files.items()}

    skipped_incomplete = 0

    try:
        for chunk_dir in chunk_dirs:
            chunk_id = chunk_dir.name

            # skip chunks that didn't complete successfully
            if not (chunk_dir / "_completed").exists():
                skipped_incomplete += 1
                continue

            for key in ("scenarios", "decision_nodes", "tactics", "qa_pairs"):
                fpath = chunk_dir / f"{key}.json"
                if not fpath.exists():
                    continue
                try:
                    records = json.loads(fpath.read_text(encoding="utf-8"))
                    for rec in records:
                        handles[key].write(json.dumps(rec, ensure_ascii=False) + "\n")
                        counts[key] += 1
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    log.warning(f"  Skipping {fpath.name} in {chunk_id}: {e}")

            # Build RAG chunk record from chunk manifest
            if chunk_id in manifest:
                m = manifest[chunk_id]
                rag_rec = {
                    "chunk_id":          chunk_id,
                    "source_slug":       m["source_slug"],
                    "chapter_title":     m["chapter_title"],
                    "chapter_index":     m["chapter_index"],
                    "chunk_index":       m["chunk_index"],
                    "content":           m["text"],
                    "token_count":       m["token_count"],
                    "page_start":        m["page_start"],
                    "page_end":          m["page_end"],
                    "embedding":         None,   # populated later by embed step
                    "indexed_at":        None,
                }
                handles["rag_chunks"].write(json.dumps(rag_rec, ensure_ascii=False) + "\n")
                counts["rag_chunks"] += 1
    finally:
        for h in handles.values():
            h.close()

    if skipped_incomplete:
        log.info(
            f"  WARNING: Skipped {skipped_incomplete} incomplete chunks (will retry on next run)"
        )
    log.info(f"  ✓ merged {source_slug} → processed/: {counts}")
    return counts


def build_training_jsonl(output_path: Path | None = None) -> Path:
    """Build fine-tuning JSONL from processed qa_pairs."""
    qa_path = DATA_DIR / "processed" / "qa_pairs.jsonl"
    if not qa_path.exists():
        raise FileNotFoundError("Run merge step first — qa_pairs.jsonl not found.")

    output_path = output_path or DATA_DIR / "processed" / "training_samples.jsonl"

    SYSTEM_PROMPT = (
        "You are a Decision Support System for crisis communications. "
        "You are advising a rookie Communications Specialist who is under pressure right now. "
        "Be direct, tactical, and specific. "
        "Warn about the most common rookie mistake for this situation. "
        "Give a concrete first action as your #1 priority."
    )

    count = 0
    with (
        open(qa_path,    encoding="utf-8") as src,
        open(output_path, "w", encoding="utf-8") as dst,
    ):
        for line in src:
            try:
                qa = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not qa.get("question") or not qa.get("answer"):
                continue
            sample = {
                "messages": [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    {"role": "user",      "content": qa["question"]},
                    {"role": "assistant", "content": qa["answer"]},
                ]
            }
            dst.write(json.dumps(sample, ensure_ascii=False) + "\n")
            count += 1

    log.info(f"  ✓ training_samples.jsonl: {count} samples → {output_path}")
    return output_path


def get_stats() -> dict:
    """Return record counts from DB (falls back to JSONL files if DB unavailable)."""
    try:
        from app.ingest.dao.ingest_dao import (
            ScenarioDAO, DecisionNodeDAO, TacticDAO,
            QAPairDAO, RagChunkDAO, TrainingSampleDAO,
        )

        async def _counts():
            return {
                "scenarios":        len(await ScenarioDAO.find_all()),
                "decision_nodes":   len(await DecisionNodeDAO.find_all()),
                "tactics":          len(await TacticDAO.find_all()),
                "qa_pairs":         len(await QAPairDAO.find_all()),
                "rag_chunks":       len(await RagChunkDAO.find_all()),
                "training_samples": len(await TrainingSampleDAO.find_all()),
            }

        return asyncio.run(_counts())

    except Exception:
        # Fallback: count JSONL lines if DB is unavailable
        proc_dir = DATA_DIR / "processed"
        stats = {}
        for name in ("scenarios", "decision_nodes", "tactics", "qa_pairs",
                     "rag_chunks", "training_samples"):
            path = proc_dir / f"{name}.jsonl"
            stats[name] = sum(1 for _ in open(path, encoding="utf-8")) if path.exists() else 0
        return stats