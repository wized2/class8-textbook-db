#!/usr/bin/env python3
"""OCR entire PDF into books/<id>/data.json"""
import json, subprocess, sys, tempfile
from pathlib import Path

def page_count(pdf):
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0

def ocr_page(pdf, page, langs, dpi=90):
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
            capture_output=True,
        )
        imgs = list(Path(td).glob("p*.png"))
        if not imgs:
            return ""
        r = subprocess.run(
            ["tesseract", str(imgs[0]), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True, text=True,
        )
        return "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())

def main():
    pdf, out_json, langs, title, book_id = sys.argv[1:6]
    pdf, out_json = Path(pdf), Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    n = page_count(pdf)
    pages = {}
    # resume if partial
    if out_json.exists():
        try:
            pages = json.loads(out_json.read_text()).get("pages") or {}
        except Exception:
            pages = {}
    for p in range(1, n + 1):
        key = str(p)
        if key in pages and len(pages[key].get("text") or "") >= 20:
            continue
        text = ocr_page(pdf, p, langs)
        pages[key] = {"page": p, "text": text}
        if p % 5 == 0 or p == n:
            data = {
                "bookId": book_id,
                "title": title,
                "class": 8,
                "source": "PCTB",
                "pageCount": n,
                "pages": pages,
            }
            out_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"{book_id} {p}/{n}", flush=True)
    data = {
        "bookId": book_id,
        "title": title,
        "class": 8,
        "source": "PCTB",
        "pageCount": n,
        "pages": pages,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"DONE {book_id} {n}", flush=True)

if __name__ == "__main__":
    main()
