from __future__ import annotations

import argparse
import json
import sys
import logging
from dataclasses import asdict
from pathlib import Path

import pdfplumber

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR
for _ in range(4):
    if (PROJECT_ROOT / "app").exists():
        break
    PROJECT_ROOT = PROJECT_ROOT.parent

INGEST_DIR      = PROJECT_ROOT / "app" / "ingest"
DEFAULT_PDF_DIR = INGEST_DIR / "data" / "raw"
DEFAULT_OUT_DIR = INGEST_DIR / "data" / "test_output"
EXTRACTOR_PATH  = INGEST_DIR / "pipeline" / "pdf_extractor.py"


# Run with: python test_extraction.py
# Override: python test_extraction.py --files "other.pdf"
DEFAULT_TEST_FILES = [
    "komunikaciyi-u-roboti-derzhavnyh-organiv-vlady-ta-organiv-misczevogo-samovryaduvannya.-suchasni-praktyk",
    "Materialy_konf_Transformatsiya_obliku_2025_442-444.pdf",
    "Materialy_konf_Transformatsiya_obliku_2025_442-444-2.pdf",
    "maxim,+26.pdf",
    "npnbuimviv_2018_49_7.pdf",
    "ostapenko_politychna.pdf",
    "Piir_2023_30_6.pdf",
    "stapttp_2017_76_20.pdf",
    "Strategia_krizovoi_komunikacii_u_sistemi_vlada-gro.pdf",
    "uazt_2014_3_14.pdf",
    "VKNU-ES-2024-N3(330)+116-122.pdf",
    "Vpliv_komunikacij_na_efektivnist_publicnogo_upravl.pdf",
    "ZBIRNIK_Konferencia_Ekonomicni_perspektivi_pidpriemnictva_31.05.2024_.pdf",
    "Zubareva_150123_20.pdf",
    "Дисертація Раупов Р.Б-2.pdf",
    "Збірка_семінар_права-людини_2023.pdf",
    "Костирко_Кризові комунікації.pdf",
    "макет_Навчальний посібник СЕМИСТУПЕНЕВА МОДЕЛЬ КРИЗОВИХ КОМУНІКАЦІЙ_edit.pdf",
    "макет_Навчальний посібник СЕМИСТУПЕНЕВА МОДЕЛЬ КРИЗОВИХ КОМУНІКАЦІЙ_edit-2.pdf",
    "Маранчак М. М. Антикризові комунікації.pdf",
]



def _import_extractor() -> object:
    import importlib.util
    candidates = [
        EXTRACTOR_PATH,
        SCRIPT_DIR / "pdf_extractor.py",
        SCRIPT_DIR.parent / "pdf_extractor.py",
    ]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location("pdf_extractor", path)
            mod  = importlib.util.module_from_spec(spec)
            sys.modules["pdf_extractor"] = mod
            spec.loader.exec_module(mod)
            log.info("Module: %s", path.relative_to(PROJECT_ROOT))
            return mod
    log.error("pdf_extractor.py not found. Checked:\n  %s",
              "\n  ".join(str(p) for p in candidates))
    sys.exit(1)



def analyze_columns(pdf_path: Path, extractor) -> dict:
    MAX_CROSS = extractor.COLUMN_MAX_CROSS_RATIO
    MIN_SIDE  = extractor.COLUMN_MIN_SIDE_RATIO
    MAX_PAGES = extractor.MAX_PAGES_FOR_COLUMN_DETECTION

    pages_report = []
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        large_doc  = page_count > MAX_PAGES

        for i, page in enumerate(pdf.pages, start=1):
            words = page.extract_words() or []
            full  = page.extract_text() or ""
            if not full.strip() or not words:
                pages_report.append({"page": i, "status": "empty"})
                continue

            w      = float(page.width)
            center = w / 2
            total  = len(words)
            cross  = sum(1 for wd in words
                         if float(wd["x0"]) < center < float(wd["x1"]))
            left   = sum(1 for wd in words
                         if (float(wd["x0"]) + float(wd["x1"])) / 2 < center)
            cr = cross / total
            lr = left  / total
            rr = 1 - lr
            is_two = (cr <= MAX_CROSS and lr >= MIN_SIDE and rr >= MIN_SIDE)

            pages_report.append({
                "page":        i,
                "words":       total,
                "cross_ratio": round(cr, 4),
                "left_pct":    round(lr * 100, 1),
                "right_pct":   round(rr * 100, 1),
                "two_col":     is_two,
                "large_doc":   large_doc,
            })

    valid        = [p for p in pages_report if p.get("status") != "empty"]
    two_count    = sum(1 for p in valid if p.get("two_col"))
    doc_decision = "two_col" if two_count > len(valid) / 2 else "single"

    return {
        "file":             pdf_path.name,
        "pages":            page_count,
        "large_doc":        large_doc,
        "doc_decision":     doc_decision,
        "two_col_pages":    two_count,
        "single_col_pages": len(valid) - two_count,
        "per_page":         pages_report,
    }



def extract_to_json(pdf_path: Path, out_dir: Path, extractor) -> dict:
    log.info("  Extracting chunks...")
    try:
        chunks = extractor.extract_chunks(pdf_path)
    except Exception as e:
        log.error("  ERROR: %s", e)
        return {"file": pdf_path.name, "error": str(e)}

    slug     = chunks[0].source_slug if chunks else pdf_path.stem
    slug_dir = out_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    out_path = slug_dir / "chunks.json"
    out_path.write_text(
        json.dumps([asdict(c) for c in chunks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    preview_path = slug_dir / "chunks_preview.txt"
    with preview_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(f"{'='*60}\n")
            f.write(f"chunk_id  : {c.chunk_id}\n")
            f.write(f"chapter   : {c.chapter_title}\n")
            f.write(f"pages     : {c.page_start}–{c.page_end}\n")
            f.write(f"tokens    : {c.token_count}\n")
            f.write(f"text:\n{c.text[:400]}\n")
            if len(c.text) > 400:
                f.write(f"... [+{len(c.text)-400} chars]\n")
            f.write("\n")

    log.info("  DONE: %d chunks → %s", len(chunks),
             slug_dir.relative_to(PROJECT_ROOT))
    return {"file": pdf_path.name, "slug": slug, "chunks": len(chunks)}



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test pdf_extractor — no DB writes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python test_extraction.py                          # default test set\n"
            "  python test_extraction.py --columns-only           # column check only\n"
            "  python test_extraction.py --files 'my.pdf'        # single file\n"
            "  python test_extraction.py --files 'a.pdf' 'b.pdf' # multiple files\n"
        ),
    )
    parser.add_argument("--files", nargs="+", metavar="FILENAME",
                        help="File names inside data/raw/ (overrides default set)")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR,
                        help="PDF source folder")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="Results folder")
    parser.add_argument("--columns-only", action="store_true",
                        help="Column detection only, skip chunk extraction")
    parser.add_argument("--all", action="store_true",
                        help="Process ALL pdfs in --pdf-dir (ignore default set)")
    args = parser.parse_args()

    extractor = _import_extractor()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve file list
    if args.files:
        # explicit list passed on command line
        names = args.files
    elif args.all:
        # every PDF in the folder
        names = [p.name for p in sorted(args.pdf_dir.glob("*.pdf"))]
    else:
        # hardcoded default set
        names = DEFAULT_TEST_FILES
        log.info("Using default test set (%d files)", len(names))

    pdf_files = []
    for name in names:
        # tolerate missing .pdf extension
        p = args.pdf_dir / (name if name.endswith(".pdf") else name + ".pdf")
        if p.exists():
            pdf_files.append(p)
        else:
            log.warning("Not found (skipped): %s", p.name)

    if not pdf_files:
        log.warning("No PDF files found in %s", args.pdf_dir)
        sys.exit(0)

    log.info("Files to process: %d", len(pdf_files))
    report = {"column_analysis": [], "extraction": []}

    for pdf_path in pdf_files:
        log.info("\n── %s ──", pdf_path.name)

        col = analyze_columns(pdf_path, extractor)
        report["column_analysis"].append(col)
        log.info(
            "  Columns: %-10s  (2col: %d  1col: %d  pages: %d%s)",
            col["doc_decision"],
            col["two_col_pages"],
            col["single_col_pages"],
            col["pages"],
            "  [LARGE — sampled]" if col["large_doc"] else "",
        )

        # per-page details for small or large (sampled) docs
        if col["pages"] <= 20 or col["large_doc"]:
            for p in col["per_page"]:
                if p.get("status") == "empty":
                    continue
                marker = "2col" if p["two_col"] else "1col"
                log.info("    p%-3d  %-4s  cross=%.3f  L=%.0f%%  R=%.0f%%",
                         p["page"], marker,
                         p["cross_ratio"], p["left_pct"], p["right_pct"])

        if not args.columns_only:
            ext = extract_to_json(pdf_path, args.out_dir, extractor)
            report["extraction"].append(ext)

    # Save report
    report_path = args.out_dir / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Summary table
    print("\n" + "="*68)
    print(f"{'File':<40} {'Decision':<10} {'2col':<6} {'1col':<6} {'pages'}")
    print("-"*68)
    for r in report["column_analysis"]:
        flag = " [large]" if r["large_doc"] else ""
        print(
            f"{r['file'][:39]:<40} "
            f"{r['doc_decision']:<10} "
            f"{r['two_col_pages']:<6} "
            f"{r['single_col_pages']:<6} "
            f"{r['pages']}{flag}"
        )
    print("="*68)
    print(f"\nResults : {args.out_dir.relative_to(PROJECT_ROOT)}")
    print(f"Report  : {report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()