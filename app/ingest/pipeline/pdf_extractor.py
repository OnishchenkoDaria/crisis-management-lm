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