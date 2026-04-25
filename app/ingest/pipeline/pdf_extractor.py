import re
import re
import json
from pathlib import Path
from dataclasses import dataclass, asdict

import pdfplumber
from slugify import slugify

import os
from dotenv import load_dotenv

load_dotenv()

# for eng sources -- adapt
CHAPTER_PATTERNS = [
    re.compile(r"^(chapter\s+\d+[\s:—–-]?.+)", re.IGNORECASE),
    re.compile(r"^(\d+\.\s+[A-Z].{5,60})"),          # "1. Managing the Media"
    re.compile(r"^(PART\s+[IVXLC\d]+[\s:—–-]?.+)", re.IGNORECASE),
    re.compile(r"^(Section\s+\d+[\s:—–-]?.+)",       re.IGNORECASE),
]

TOKEN_RATIO = os.getenv("TOKEN_RATIO")
MAX_CHUNK_TOKENS=os.getenv("MAX_CHUNK_TOKENS")
OVERLAP_TOKENS=os.getenv("OVERLAP_TOKENS")


@dataclass
class TextChunk:
    chunk_id: str
    source_slug: str  # book slug
    chapter_title: str
    chapter_index: int
    chunk_index: int  # position within the chapter
    text: str
    token_count: int
    page_start: int
    page_end: int


def _count_tokens(text: str) -> int:
    return int(len(text.split()) * TOKEN_RATIO)


def _is_chapter_heading(line: str) -> bool:
    line = line.strip()
    if len(line) < 4 or len(line) > 120:
        return False
    return any(p.match(line) for p in CHAPTER_PATTERNS)


def _split_into_token_chunks(
        text: str,
        max_tokens: int = MAX_CHUNK_TOKENS,
        overlap: int = OVERLAP_TOKENS,
) -> list[str]:
    """Split a long text into overlapping token-safe chunks."""
    words = text.split()
    chunks, current, count = [], [], 0

    for word in words:
        wt = int(len((word + " ").split()) * TOKEN_RATIO)
        if count + wt > max_tokens and current:
            chunks.append(" ".join(current))
            # keep last `overlap` tokens as carry-over
            carry, carry_count = [], 0
            for w in reversed(current):
                wc = int(len((w + " ").split()) * TOKEN_RATIO)
                if carry_count + wc > overlap:
                    break
                carry.insert(0, w)
                carry_count += wc
            current, count = carry + [word], carry_count + wt
        else:
            current.append(word)
            count += wt

    if current:
        chunks.append(" ".join(current))

    return chunks


def extract_chunks(pdf_path: str | Path) -> list[TextChunk]:
    """
    Main entry point.
    Returns a flat list of TextChunk objects ordered by chapter → chunk.
    """
    pdf_path = Path(pdf_path)
    source_slug = slugify(pdf_path.stem)

    # Extract raw text page-by-page
    pages: list[tuple[int, str]] = []  # (page_number, text)
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text() or ""
            if raw.strip():
                pages.append((i, raw))

    if not pages:
        raise ValueError(f"No extractable text found in {pdf_path.name}. "
                         "The PDF may be scanned — run OCR first.")

    #Detect chapter boundaries
    # Each chapter = {"title": str, "page_start": int, "lines": [str]}
    chapters: list[dict] = []
    current: dict | None = None

    for page_num, page_text in pages:
        for line in page_text.splitlines():
            if _is_chapter_heading(line):
                if current:
                    current["page_end"] = page_num
                    chapters.append(current)
                current = {
                    "title": line.strip(),
                    "page_start": page_num,
                    "page_end": page_num,
                    "lines": [],
                }
            if current:
                current["lines"].append(line)

    # flush last chapter
    if current:
        current["page_end"] = pages[-1][0]
        chapters.append(current)

    # Fallback: if no chapter headings detected, treat whole book as one section
    if not chapters:
        all_text = "\n".join(t for _, t in pages)
        chapters = [{
            "title": pdf_path.stem,
            "page_start": pages[0][0],
            "page_end": pages[-1][0],
            "lines": all_text.splitlines(),
        }]

    #Split chapters into token-safe chunks
    all_chunks: list[TextChunk] = []

    for ch_idx, chapter in enumerate(chapters):
        body = "\n".join(chapter["lines"]).strip()
        if _count_tokens(body) <= MAX_CHUNK_TOKENS:
            sub_texts = [body]
        else:
            sub_texts = _split_into_token_chunks(body)

        for ck_idx, sub_text in enumerate(sub_texts):
            chunk_id = f"{source_slug}__ch{ch_idx:03d}__ck{ck_idx:03d}"
            all_chunks.append(TextChunk(
                chunk_id=chunk_id,
                source_slug=source_slug,
                chapter_title=chapter["title"],
                chapter_index=ch_idx,
                chunk_index=ck_idx,
                text=sub_text,
                token_count=_count_tokens(sub_text),
                page_start=chapter["page_start"],
                page_end=chapter["page_end"],
            ))

    return all_chunks


def save_chunk_manifest(chunks: list[TextChunk], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = [asdict(c) for c in chunks]
    (out_dir / "chunk_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    print(f"  ✓ Saved manifest: {len(chunks)} chunks → {out_dir}/chunk_manifest.json")