#!/usr/bin/env python3
"""CI OCR: PDF → books/<id>/data.json keyed by printed book page numbers."""
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


def ocr_pdf_page(pdf: Path, pdf_page: int, langs: str, dpi: int) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(pdf_page), "-l", str(pdf_page),
             str(pdf), str(prefix)],
            capture_output=True,
        )
        imgs = list(Path(td).glob("p*.png"))
        if not imgs:
            return pdf_page, ""
        r = subprocess.run(
            ["tesseract", str(imgs[0]), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True, text=True,
        )
        text = "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())
        return pdf_page, text


def detect_num(text: str) -> int | None:
    # Prefer short trailing digit lines (footer page numbers)
    for ln in reversed((text or "").splitlines()[-12:]):
        s = ln.strip()
        if re.fullmatch(r"\d{1,3}", s):
            n = int(s)
            if 1 <= n <= 400:
                return n
        m = re.search(r"(?:^|\s)(\d{1,3})\s*$", s)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 400:
                return n
    return None


def median(xs: list[int]) -> int:
    xs = sorted(xs)
    return xs[len(xs) // 2]


def main() -> None:
    book_id, title, drive_id, langs = sys.argv[1:5]
    dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 110
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 6

    root = Path.cwd()
    pdf = root / "pdfs" / f"{book_id}.pdf"
    out = root / "books" / book_id / "data.json"

    download_drive(drive_id, pdf)
    n = page_count(pdf)
    print(f"{book_id}: {n} PDF pages langs={langs} dpi={dpi} workers={workers}", flush=True)

    raw: dict[int, str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ocr_pdf_page, pdf, p, langs, dpi): p for p in range(1, n + 1)}
        for fut in as_completed(futs):
            p, text = fut.result()
            raw[p] = text
            done += 1
            if done % 25 == 0 or done == n:
                print(f"{book_id} OCR {done}/{n}", flush=True)

    # Estimate offset from detected footer numbers
    deltas = []
    for pdf_p, text in raw.items():
        bp = detect_num(text)
        if bp is not None:
            deltas.append(pdf_p - bp)
    offset = median(deltas) if deltas else 0
    print(f"{book_id}: offset={offset} samples={len(deltas)}", flush=True)

    pages: dict[str, dict] = {}
    for pdf_p in range(1, n + 1):
        text = raw.get(pdf_p) or ""
        book_p = detect_num(text)
        if book_p is None:
            book_p = pdf_p - offset
        if book_p < 1:
            continue
        key = str(book_p)
        prev = pages.get(key)
        if prev and len(prev.get("text") or "") >= len(text):
            continue
        pages[key] = {"page": book_p, "pdfPage": pdf_p, "text": text}

    nums = sorted(int(k) for k in pages)
    data = {
        "bookId": book_id,
        "title": title,
        "class": 8,
        "source": "PCTB",
        "pageCount": len(pages),
        "pdfPageCount": n,
        "pageMin": nums[0] if nums else None,
        "pageMax": nums[-1] if nums else None,
        "pdfOffset": offset,
        "pageNumbering": "printed_book_page",
        "ocr": {"langs": langs, "dpi": dpi},
        "pages": pages,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for v in pages.values() if len(v.get("text") or "") >= 25)
    print(f"DONE {book_id}: book {data['pageMin']}-{data['pageMax']} ok={ok} offset={offset}", flush=True)


if __name__ == "__main__":
    main()
