"""
storage.py
Handles all file I/O for the DSS pipeline.

Folder layout:
  data/
    raw/                          ← drop your PDFs here
    extracted/
      {book_slug}/
        metadata.json             ← book-level info
        chunk_manifest.json       ← all chunks with token counts
        chunks/
          {chunk_id}/
            scenarios.json
            decision_nodes.json
            tactics.json
            qa_pairs.json
    processed/                    ← merged across all books
      scenarios.jsonl
      decision_nodes.jsonl
      tactics.jsonl
      qa_pairs.jsonl
      rag_chunks.jsonl            ← ready for vector embedding
"""

import json
import logging
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def get_book_dir(source_slug: str) -> Path:
    p = DATA_DIR / "extracted" / source_slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_book_metadata(source_slug: str, metadata: dict) -> None:
    path = get_book_dir(source_slug) / "metadata.json"
    metadata["_created_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    log.info(f"  ✓ metadata saved → {path}")


def save_chunk_result(result) -> None:
    """Save one ChunkExtractionResult to its own subfolder."""
    chunk_dir = get_book_dir(result.source_slug) / "chunks" / result.chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [
        ("scenarios.json",      result.scenarios),
        ("decision_nodes.json", result.decision_nodes),
        ("tactics.json",        result.tactics),
        ("qa_pairs.json",       result.qa_pairs),
    ]:
        (chunk_dir / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )

    log.info(
        f"  ✓ chunk saved [{result.chunk_id}]: "
        f"{len(result.scenarios)} scenarios, "
        f"{len(result.decision_nodes)} decisions, "
        f"{len(result.tactics)} tactics, "
        f"{len(result.qa_pairs)} qa_pairs"
    )


def is_chunk_done(source_slug: str, chunk_id: str) -> bool:
    """Check if a chunk was already processed (resume support)."""
    chunk_dir = get_book_dir(source_slug) / "chunks" / chunk_id
    return all(
        (chunk_dir / f).exists()
        for f in ("scenarios.json", "decision_nodes.json", "tactics.json", "qa_pairs.json")
    )


def merge_book_to_processed(source_slug: str) -> dict:
    """
    After all chunks of a book are done, merge everything into
    data/processed/*.jsonl  (appending — safe to run multiple books).
    Returns counts.
    """
    book_dir  = get_book_dir(source_slug)
    proc_dir  = DATA_DIR / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    counts = dict(scenarios=0, decision_nodes=0, tactics=0, qa_pairs=0, rag_chunks=0)

    chunk_dirs = sorted((book_dir / "chunks").glob("*"))
    if not chunk_dirs:
        log.warning(f"No chunk dirs found for {source_slug}")
        return counts

    files = {
        "scenarios":      proc_dir / "scenarios.jsonl",
        "decision_nodes": proc_dir / "decision_nodes.jsonl",
        "tactics":        proc_dir / "tactics.jsonl",
        "qa_pairs":       proc_dir / "qa_pairs.jsonl",
        "rag_chunks":     proc_dir / "rag_chunks.jsonl",
    }

    handles = {k: open(v, "a", encoding="utf-8") for k, v in files.items()}

    try:
        manifest_path = book_dir / "chunk_manifest.json"
        manifest = {}
        if manifest_path.exists():
            for c in json.loads(manifest_path.read_text()):
                manifest[c["chunk_id"]] = c

        for chunk_dir in chunk_dirs:
            chunk_id = chunk_dir.name

            for key in ("scenarios", "decision_nodes", "tactics", "qa_pairs"):
                fpath = chunk_dir / f"{key}.json"
                if not fpath.exists():
                    continue
                records = json.loads(fpath.read_text())
                for rec in records:
                    handles[key].write(json.dumps(rec, ensure_ascii=False) + "\n")
                    counts[key] += 1

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

    log.info(f"  ✓ merged {source_slug} → processed/: {counts}")
    return counts


def build_training_jsonl(output_path: Path | None = None) -> Path:
    """
    Reads processed/qa_pairs.jsonl and builds a fine-tuning ready JSONL
    in OpenAI / Anthropic messages format.
    """
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
            qa = json.loads(line)
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
    """Return counts across all processed files."""
    proc_dir = DATA_DIR / "processed"
    stats = {}
    for name in ("scenarios", "decision_nodes", "tactics", "qa_pairs",
                 "rag_chunks", "training_samples"):
        path = proc_dir / f"{name}.jsonl"
        if path.exists():
            stats[name] = sum(1 for _ in open(path, encoding="utf-8"))
        else:
            stats[name] = 0
    return stats