#!/usr/bin/env python3
"""CI: PDF → books/<id>/data.json (printed page numbers).

Fast path: extract embedded text with pdftotext (one process).
Slow path: OCR only pages with little/no text (batch pdftoppm + tesseract).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

MIN_TEXT = 40  # chars — below this, treat as needs OCR


def download_drive(file_id: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10_000 and dest.read_bytes()[:4] == b"%PDF":
        print(f"reuse {dest} ({dest.stat().st_size} bytes)", flush=True)
        return

    def fetch(url: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.read()

    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    data = fetch(url)
    if data[:4] != b"%PDF":
        text = data.decode("utf-8", "replace")
        # large-file confirm token
        m = re.search(r"confirm=([0-9A-Za-z_-]+)", text)
        m2 = re.search(r"/uc\?export=download&amp;id=" + re.escape(file_id) + r"&amp;confirm=([0-9A-Za-z_-]+)", text)
        token = (m.group(1) if m else None) or (m2.group(1) if m2 else None)
        if not token:
            m3 = re.search(r"name=\"confirm\"\s+value=\"([^\"]+)\"", text)
            token = m3.group(1) if m3 else "t"
        url2 = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
        data = fetch(url2)
    if data[:4] != b"%PDF":
        # last try: googleusercontent direct pattern sometimes works after cookie-less confirm=t
        url3 = f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
        data = fetch(url3)
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


def extract_text_layer(pdf: Path, n_pages: int) -> dict[int, str]:
    """One pdftotext call; split on form-feed into 1-based pages."""
    r = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"pdftotext failed: {r.stderr[:200]}", flush=True)
        return {p: "" for p in range(1, n_pages + 1)}

    chunks = r.stdout.split("\f")
    # pdftotext often ends with trailing empty chunk
    while chunks and not chunks[-1].strip():
        chunks.pop()
    out: dict[int, str] = {}
    for i in range(1, n_pages + 1):
        raw = chunks[i - 1] if i - 1 < len(chunks) else ""
        text = "\n".join(ln.rstrip() for ln in raw.splitlines()).strip()
        out[i] = text
    ok = sum(1 for t in out.values() if len(t) >= MIN_TEXT)
    print(f"text-layer: {ok}/{n_pages} pages usable (>= {MIN_TEXT} chars)", flush=True)
    return out


def detect_num(text: str) -> int | None:
    for ln in reversed((text or "").splitlines()[-14:]):
        s = ln.strip()
        if re.fullmatch(r"\d{1,3}", s):
            v = int(s)
            if 1 <= v <= 400:
                return v
    # also check last short tokens
    tail = " ".join((text or "").split()[-8:])
    m = re.search(r"\b(\d{1,3})\b\s*$", tail)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 400:
            return v
    return None


def median(xs: list[int]) -> int:
    if not xs:
        return 0
    xs = sorted(xs)
    return xs[len(xs) // 2]


def _ocr_one(args: tuple) -> tuple[int, str]:
    img_path, langs = args
    r = subprocess.run(
        ["tesseract", img_path, "stdout", "-l", langs, "--psm", "6", "-c", "preserve_interword_spaces=1"],
        capture_output=True,
        text=True,
    )
    text = "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())
    # page number from filename p-00012.png
    m = re.search(r"(\d+)\.png$", img_path)
    page = int(m.group(1)) if m else 0
    return page, text


def ocr_pages(pdf: Path, page_nums: list[int], langs: str, dpi: int, workers: int) -> dict[int, str]:
    if not page_nums:
        return {}
    results: dict[int, str] = {}
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Batch render in chunks to limit disk
        chunk = 40
        for i in range(0, len(page_nums), chunk):
            batch = page_nums[i : i + chunk]
            lo, hi = batch[0], batch[-1]
            # Render contiguous range if dense, else page-by-page ranges
            if hi - lo + 1 <= len(batch) + 5:
                prefix = td_path / f"b{lo}"
                subprocess.run(
                    ["pdftoppm", "-png", "-r", str(dpi), "-f", str(lo), "-l", str(hi), str(pdf), str(prefix)],
                    capture_output=True,
                    check=False,
                )
            else:
                for p in batch:
                    prefix = td_path / f"p{p}"
                    subprocess.run(
                        ["pdftoppm", "-png", "-r", str(dpi), "-f", str(p), "-l", str(p), str(pdf), str(prefix)],
                        capture_output=True,
                        check=False,
                    )

            imgs: list[tuple[int, Path]] = []
            for p in batch:
                # pdftoppm names: prefix-12.png or prefix-012.png
                found = list(td_path.glob(f"*{p:d}.png")) + list(td_path.glob(f"*{p:02d}.png")) + list(td_path.glob(f"*{p:03d}.png"))
                # also match any ending
                if not found:
                    found = [x for x in td_path.glob("*.png") if re.search(rf"[-\.]0*{p}\.png$", x.name)]
                if found:
                    imgs.append((p, found[0]))

            # Rename to stable names for worker
            jobs = []
            for p, img in imgs:
                stable = td_path / f"ocr-{p:05d}.png"
                if img.resolve() != stable.resolve():
                    stable.write_bytes(img.read_bytes())
                jobs.append((str(stable), langs))

            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_ocr_one, j): j for j in jobs}
                for fut in as_completed(futs):
                    try:
                        p, text = fut.result()
                        results[p] = text
                    except Exception as e:
                        print(f"ocr worker error: {e}", flush=True)

            done = len(results)
            print(f"OCR progress {done}/{len(page_nums)}", flush=True)

            # cleanup pngs to save space
            for png in td_path.glob("*.png"):
                try:
                    png.unlink()
                except OSError:
                    pass

    return results


def main() -> None:
    book_id, title, drive_id, langs = sys.argv[1:5]
    dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 100
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 4

    root = Path.cwd()
    pdf = root / "pdfs" / f"{book_id}.pdf"
    out = root / "books" / book_id / "data.json"

    download_drive(drive_id, pdf)
    n = page_count(pdf)
    print(f"{book_id}: {n} PDF pages langs={langs} dpi={dpi} workers={workers}", flush=True)

    # 1) Fast text layer
    raw = extract_text_layer(pdf, n)

    # 2) OCR only weak pages
    need_ocr = [p for p in range(1, n + 1) if len(raw.get(p) or "") < MIN_TEXT]
    print(f"{book_id}: need OCR on {len(need_ocr)}/{n} pages", flush=True)

    if need_ocr:
        ocr_lang = langs.replace("+", "+")  # tesseract uses +
        ocred = ocr_pages(pdf, need_ocr, ocr_lang, dpi, workers)
        for p, text in ocred.items():
            if len(text) > len(raw.get(p) or ""):
                raw[p] = text

    # 3) Printed page mapping
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
    method = "text+ocr" if need_ocr else "text"
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
        "ocr": {"langs": langs, "dpi": dpi, "method": method, "ocrPages": len(need_ocr)},
        "pages": pages,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for v in pages.values() if len(v.get("text") or "") >= 25)
    print(
        f"DONE {book_id}: book {data['pageMin']}-{data['pageMax']} "
        f"ok={ok}/{len(pages)} method={method} ocrPages={len(need_ocr)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
