#!/usr/bin/env python3
"""High-quality CI OCR for one PCTB textbook PDF → books/<id>/data.json

Page keys are **printed book page numbers** (footer), not PDF indices.
Each entry includes pdfPage for debugging.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def download_drive(file_id: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=180).read()
    if data[:4] != b"%PDF":
        text = data.decode("utf-8", "replace")
        m = re.search(r"confirm=([0-9A-Za-z_]+)", text)
        if not m:
            m2 = re.search(r"/uc\?export=download[^\"']+confirm=([0-9A-Za-z_]+)", text)
            if m2:
                m = m2
        if m:
            url2 = f"https://drive.google.com/uc?export=download&confirm={m.group(1)}&id={file_id}"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req2, timeout=300).read()
    if data[:4] != b"%PDF":
        raise SystemExit(f"Download failed for {file_id}: not a PDF ({len(data)} bytes)")
    dest.write_bytes(data)
    print(f"downloaded {dest} ({len(data)} bytes)", flush=True)


def page_count(pdf: Path) -> int:
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True)
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise SystemExit("Could not read page count")


def _ocr_image(img: Path, langs: str) -> str:
    r = subprocess.run(
        ["tesseract", str(img), "stdout", "-l", langs, "--psm", "6"],
        capture_output=True,
        text=True,
    )
    return "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())


def detect_book_page(text: str, footer_text: str, pdf_page: int, offset: int | None) -> int | None:
    """Best-effort printed page number from footer / full text."""
    candidates: list[int] = []

    # Footer-first: short lines that are mostly digits
    for src in (footer_text, text):
        for ln in (src or "").splitlines()[-8:]:
            s = ln.strip()
            if re.fullmatch(r"\d{1,3}", s):
                n = int(s)
                if 1 <= n <= 400:
                    candidates.append(n)
            # e.g. "- 42 -" or "Page 42"
            m = re.search(r"(?:page\s*)?(\d{1,3})\s*$", s, re.I)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 400:
                    candidates.append(n)

    if candidates:
        if offset is not None:
            expected = pdf_page - offset
            # prefer candidate closest to expected
            candidates.sort(key=lambda n: (abs(n - expected), -n))
        return candidates[0]

    if offset is not None:
        n = pdf_page - offset
        if n >= 1:
            return n
    return None


def ocr_pdf_page(pdf: Path, pdf_page: int, langs: str, dpi: int) -> tuple[int, str, str]:
    """Returns (pdf_page, full_text, footer_text)."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        prefix = td_path / "p"
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(pdf_page),
                "-l",
                str(pdf_page),
                str(pdf),
                str(prefix),
            ],
            check=False,
            capture_output=True,
        )
        imgs = list(td_path.glob("p*.png"))
        if not imgs:
            return pdf_page, "", ""
        img = imgs[0]
        full = _ocr_image(img, langs)

        # Crop bottom ~12% for page number
        footer_txt = ""
        try:
            from subprocess import run as srun

            # identify size via file or convert
            r = srun(["identify", "-format", "%w %h", str(img)], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                w, h = map(int, r.stdout.strip().split())
            else:
                # fallback: use python pillow if available, else skip crop
                w = h = 0
            if h > 0:
                top = int(h * 0.88)
                crop = td_path / "footer.png"
                srun(
                    ["convert", str(img), "-crop", f"{w}x{h - top}+0+{top}", "+repage", str(crop)],
                    capture_output=True,
                )
                if crop.exists():
                    footer_txt = _ocr_image(crop, "eng")  # digits only need eng
        except Exception:
            footer_txt = ""

        return pdf_page, full, footer_txt


def estimate_offset(samples: list[tuple[int, int | None]]) -> int | None:
    """samples: list of (pdf_page, detected_book_page)."""
    deltas = []
    for pdf_p, book_p in samples:
        if book_p is not None and book_p >= 1:
            deltas.append(pdf_p - book_p)
    if not deltas:
        return None
    # median
    deltas.sort()
    return deltas[len(deltas) // 2]


def main() -> None:
    book_id, title, drive_id, langs = sys.argv[1:5]
    dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 150
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 4

    root = Path.cwd()
    pdf = root / "pdfs" / f"{book_id}.pdf"
    out = root / "books" / book_id / "data.json"

    download_drive(drive_id, pdf)
    n = page_count(pdf)
    print(f"{book_id}: {n} PDF pages, langs={langs}, dpi={dpi}, workers={workers}", flush=True)

    # Pass 1: OCR all PDF pages (by pdf index)
    raw: dict[int, tuple[str, str]] = {}  # pdf_page -> (text, footer)

    def work(p: int):
        return ocr_pdf_page(pdf, p, langs, dpi)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, p): p for p in range(1, n + 1)}
        for fut in as_completed(futs):
            pdf_p, text, footer = fut.result()
            raw[pdf_p] = (text, footer)
            done += 1
            if done % 20 == 0 or done == n:
                print(f"{book_id} OCR {done}/{n}", flush=True)

    # Pass 2: detect page numbers + offset
    preliminary: list[tuple[int, int | None]] = []
    for pdf_p in range(1, n + 1):
        text, footer = raw[pdf_p]
        bp = detect_book_page(text, footer, pdf_p, offset=None)
        preliminary.append((pdf_p, bp))

    offset = estimate_offset(preliminary)
    print(f"{book_id}: estimated PDF→book offset = {offset}", flush=True)

    pages: dict[str, dict] = {}
    for pdf_p in range(1, n + 1):
        text, footer = raw[pdf_p]
        book_p = detect_book_page(text, footer, pdf_p, offset=offset)
        if book_p is None:
            # front matter without numbers — skip indexing by book page
            # still keep under pdf-only key if needed
            continue
        key = str(book_p)
        # Prefer denser text if duplicate book page detected
        prev = pages.get(key)
        if prev and len(prev.get("text") or "") >= len(text or ""):
            continue
        pages[key] = {
            "page": book_p,
            "pdfPage": pdf_p,
            "text": text or "",
        }

    # If detection failed badly, fall back to offset mapping for all pages
    if len(pages) < max(5, n // 4) and offset is not None:
        print(f"{book_id}: weak detection ({len(pages)} pages) — using offset map", flush=True)
        pages = {}
        for pdf_p in range(1, n + 1):
            book_p = pdf_p - offset
            if book_p < 1:
                continue
            text, _ = raw[pdf_p]
            pages[str(book_p)] = {"page": book_p, "pdfPage": pdf_p, "text": text or ""}

    if not pages:
        print(f"{book_id}: no book pages detected — indexing by PDF page as last resort", flush=True)
        for pdf_p in range(1, n + 1):
            text, _ = raw[pdf_p]
            pages[str(pdf_p)] = {"page": pdf_p, "pdfPage": pdf_p, "text": text or ""}

    book_nums = sorted(int(k) for k in pages)
    data = {
        "bookId": book_id,
        "title": title,
        "class": 8,
        "source": "PCTB",
        "pageCount": len(pages),
        "pdfPageCount": n,
        "pageMin": book_nums[0] if book_nums else None,
        "pageMax": book_nums[-1] if book_nums else None,
        "pdfOffset": offset,
        "pageNumbering": "printed_book_page",
        "ocr": {"langs": langs, "dpi": dpi},
        "pages": pages,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for v in pages.values() if len(v.get("text") or "") >= 25)
    print(
        f"DONE {book_id}: book pages {data['pageMin']}-{data['pageMax']} "
        f"({ok} with text, offset={offset})",
        flush=True,
    )


if __name__ == "__main__":
    main()
