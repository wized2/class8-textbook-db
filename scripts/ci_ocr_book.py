#!/usr/bin/env python3
"""High-quality CI OCR for one PCTB textbook PDF → books/<id>/data.json"""
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
            # cookie confirm fallback
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


def ocr_page(pdf: Path, page: int, langs: str, dpi: int) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(page),
                "-l",
                str(page),
                str(pdf),
                str(prefix),
            ],
            check=False,
            capture_output=True,
        )
        imgs = list(Path(td).glob("p*.png"))
        if not imgs:
            return page, ""
        r = subprocess.run(
            ["tesseract", str(imgs[0]), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True,
            text=True,
        )
        text = "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())
        return page, text


def main() -> None:
    # args: bookId title driveId langs [dpi] [workers]
    book_id, title, drive_id, langs = sys.argv[1:5]
    dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 150
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 4

    root = Path.cwd()
    pdf = root / "pdfs" / f"{book_id}.pdf"
    out = root / "books" / book_id / "data.json"

    download_drive(drive_id, pdf)
    n = page_count(pdf)
    print(f"{book_id}: {n} pages, langs={langs}, dpi={dpi}, workers={workers}", flush=True)

    pages: dict[str, dict] = {}
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            pages = prev.get("pages") or {}
        except Exception:
            pages = {}

    todo = [
        p
        for p in range(1, n + 1)
        if len((pages.get(str(p)) or {}).get("text") or "") < 25
    ]
    print(f"todo={len(todo)} (resume-aware)", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ocr_page, pdf, p, langs, dpi): p for p in todo}
        for fut in as_completed(futs):
            p, text = fut.result()
            pages[str(p)] = {"page": p, "text": text}
            done += 1
            if done % 20 == 0 or done == len(todo):
                data = {
                    "bookId": book_id,
                    "title": title,
                    "class": 8,
                    "source": "PCTB",
                    "pageCount": n,
                    "ocr": {"langs": langs, "dpi": dpi},
                    "pages": pages,
                }
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"{book_id} {done}/{len(todo)}", flush=True)

    data = {
        "bookId": book_id,
        "title": title,
        "class": 8,
        "source": "PCTB",
        "pageCount": n,
        "ocr": {"langs": langs, "dpi": dpi},
        "pages": pages,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for v in pages.values() if len(v.get("text") or "") >= 25)
    print(f"DONE {book_id}: {ok}/{n} pages with text", flush=True)


if __name__ == "__main__":
    main()
