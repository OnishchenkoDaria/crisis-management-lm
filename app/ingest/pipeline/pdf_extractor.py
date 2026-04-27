from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from email.header import decode_header
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

load_dotenv()

TOKEN_RATIO = float(os.getenv("TOKEN_RATIO", "1.4"))
MAX_CHUNK_TOKENS = int(os.getenv("MAX_CHUNK_TOKENS", "4500"))
OVERLAP_TOKENS = int(os.getenv("OVERLAP_TOKENS", "250"))
MAX_PAGES_FOR_COLUMN_DETECTION = int(os.getenv("MAX_PAGES_FOR_COLUMN_DETECTION", "300"))

_CYRILLIC_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia",
    "ы": "y", "э": "e", "ё": "io", "ъ": "",
}

_EN_SECTION = re.compile(
    r"^(chapter\s+\d+[\s:—–-]?.+|part\s+[ivxlcdm\d]+[\s:—–-]?.+|"
    r"section\s+\d+[\s:—–-]?.+|abstract|introduction|background|methods?|"
    r"methodology|results?|discussion|conclusions?|references|bibliography)$",
    re.IGNORECASE,
)

_UK_SECTION = re.compile(
    r"^(анотація|абстракт|вступ|постановка проблеми|аналіз останніх досліджень( і публікацій)?|"
    r"мета( дослідження| статті)?|завдання( дослідження)?|виклад основного матеріалу( дослідження)?|"
    r"методологія|методи( дослідження)?|результати( дослідження)?|обговорення|дискусія|"
    r"висновки( та перспективи подальших досліджень)?|список використаних джерел|"
    r"список літератури|література|джерела|references)$",
    re.IGNORECASE,
)

_NOISE = re.compile(
    r"(" 
    r"^\s*удк\s+|^\s*doi\s*:|^\s*orcid\s*:|^\s*issn\s+|"
    r"www\.|https?://|e-mail|email|"
    r"збірник наукових праць|науковий вісник|вісник .* університету|"
    r"гуманітарний вісник|актуальні проблеми|"
    r"^\s*том\s+\d+|^\s*№\s*\d+|^\s*вип\.\s*\d+|^\s*с\.\s*\d+\s*$|"
    r"^\s*\d+\s*$"
    r")",
    re.IGNORECASE,
)


@dataclass
class TextChunk:
    chunk_id: str
    source_slug: str
    chapter_title: str
    chapter_index: int
    chunk_index: int
    text: str
    token_count: int
    page_start: int
    page_end: int
    language: str  # 'en' | 'uk' | 'mixed'
    doc_type: str  # 'article' | 'book' | 'manual'


def _decode_mime_filename(name: str) -> str:
    """Decode MIME-encoded attachment names like =?UTF-8?B?...?=."""
    try:
        decoded_parts = decode_header(name)
        result = ""
        for value, charset in decoded_parts:
            if isinstance(value, bytes):
                result += value.decode(charset or "utf-8", errors="ignore")
            else:
                result += value
        if result.strip():
            return result
    except Exception:
        pass

    match = re.search(r"UTF-8[_?]B[_?]([A-Za-z0-9+/=_-]+)", name, flags=re.IGNORECASE)
    if match:
        raw = match.group(1).replace("_", "=")
        try:
            return base64.b64decode(raw).decode("utf-8", errors="ignore")
        except Exception:
            return name
    return name


def _safe_slug(value: str, max_len: int = 80) -> str:
    """Create stable ASCII slug that preserves Cyrillic meaning via transliteration."""
    original = value
    value = _decode_mime_filename(value).lower()
    chars: list[str] = []
    for ch in value:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            chars.append(ch)
        elif ch in _CYRILLIC_TRANSLIT:
            chars.append(_CYRILLIC_TRANSLIT[ch])
        else:
            chars.append("-")
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")[:max_len].strip("-")
    if not slug:
        slug = hashlib.md5(original.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return slug


def _count_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * TOKEN_RATIO))


def _clean_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or _NOISE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _is_section_heading(line: str) -> bool:
    line = re.sub(r"\s+", " ", line).strip().strip(".:;—–-")
    if len(line) < 4 or len(line) > 120:
        return False
    return bool(_EN_SECTION.match(line) or _UK_SECTION.match(line))


def _extract_page_text(page, *, force_single_col: bool = False) -> str:
    """Extract page text, using left+right column order only when page is likely two-column."""
    full_text = page.extract_text() or ""
    if force_single_col or not full_text.strip():
        return _clean_text(full_text)

    width = float(page.width)
    height = float(page.height)
    split_x = width * 0.52

    left = page.crop((0, 0, split_x, height)).extract_text() or ""
    right = page.crop((split_x, 0, width, height)).extract_text() or ""

    full_words = max(1, len(full_text.split()))
    left_words = len(left.split())
    right_words = len(right.split())

    if left_words >= full_words * 0.25 and right_words >= full_words * 0.25:
        return _clean_text(left + "\n" + right)
    return _clean_text(full_text)


def _detect_language(text: str) -> str:
    cyr = len(re.findall(r"[А-Яа-яЄєІіЇїҐґ]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    total = cyr + lat
    if total == 0:
        return "mixed"
    cyr_ratio = cyr / total
    if cyr_ratio >= 0.7:
        return "uk"
    if cyr_ratio <= 0.2:
        return "en"
    return "mixed"


def _guess_doc_type(page_count: int, all_text: str) -> str:
    first_pages = all_text[:6000].lower()
    has_abstract = any(marker in first_pages for marker in ("abstract", "анотація", "абстракт"))
    if page_count <= 20 and has_abstract:
        return "article"
    if page_count <= 50:
        return "manual"
    return "book"


def _split_into_token_chunks(
    text: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    count = 0.0  # float so TOKEN_RATIO accumulates correctly

    for word in words:
        wt = TOKEN_RATIO         # each word ≈ TOKEN_RATIO tokens (float accumulator)
        if count + wt > max_tokens and current:
            chunks.append(" ".join(current))
            carry: list[str] = []
            carry_count = 0.0
            for w in reversed(current):
                wc = TOKEN_RATIO
                if carry_count + wc > overlap:
                    break
                carry.insert(0, w)
                carry_count += wc
            current = carry + [word]
            count = carry_count + wt
        else:
            current.append(word)
            count += wt

    if current:
        chunks.append(" ".join(current))
    return chunks


def extract_chunks(pdf_path: str | Path) -> list[TextChunk]:
    pdf_path = Path(pdf_path)
    source_slug = _safe_slug(pdf_path.stem)

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        force_single_col = page_count > MAX_PAGES_FOR_COLUMN_DETECTION
        for i, page in enumerate(pdf.pages, start=1):
            raw = _extract_page_text(page, force_single_col=force_single_col)
            if raw.strip():
                pages.append((i, raw))

    if not pages:
        raise ValueError(
            f"No extractable text found in {pdf_path.name}. The PDF may be scanned — run OCR first."
        )

    all_text = "\n".join(text for _, text in pages)
    language = _detect_language(all_text)
    doc_type = _guess_doc_type(pages[-1][0], all_text)

    chapters: list[dict] = []
    current: dict | None = None

    for page_num, page_text in pages:
        for line in page_text.splitlines():
            if _is_section_heading(line):
                if current:
                    current["page_end"] = page_num
                    chapters.append(current)
                current = {
                    "title": re.sub(r"\s+", " ", line).strip(),
                    "page_start": page_num,
                    "page_end": page_num,
                    "lines": [],
                }
            if current:
                current["lines"].append(line)

    if current:
        current["page_end"] = pages[-1][0]
        chapters.append(current)

    if not chapters:
        chapters = [{
            "title": pdf_path.stem,
            "page_start": pages[0][0],
            "page_end": pages[-1][0],
            "lines": all_text.splitlines(),
        }]

    all_chunks: list[TextChunk] = []
    for ch_idx, chapter in enumerate(chapters):
        body = "\n".join(chapter["lines"]).strip()
        if not body:
            continue
        sub_texts = [body] if _count_tokens(body) <= MAX_CHUNK_TOKENS else _split_into_token_chunks(body)

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
                language=language,
                doc_type=doc_type,
            ))

    return all_chunks


def save_chunk_manifest(chunks: list[TextChunk], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = [asdict(c) for c in chunks]
    (out_dir / "chunk_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✓ Saved manifest: {len(chunks)} chunks → {out_dir}/chunk_manifest.json")