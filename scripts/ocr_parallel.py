#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def page_count(pdf):
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0

def ocr_one(pdf, page, langs, dpi=85):
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
            capture_output=True,
        )
        imgs = list(Path(td).glob("p*.png"))
        if not imgs:
            return page, ""
        r = subprocess.run(
            ["tesseract", str(imgs[0]), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True, text=True,
        )
        text = "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())
        return page, text

def main():
    pdf, out_json, langs, title, book_id, workers = sys.argv[1:7]
    workers = int(workers)
    pdf, out_json = Path(pdf), Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    n = page_count(pdf)
    pages = {}
    if out_json.exists():
        try:
            pages = json.loads(out_json.read_text()).get("pages") or {}
        except Exception:
            pages = {}
    todo = [p for p in range(1, n+1) if len((pages.get(str(p)) or {}).get("text") or "") < 15]
    print(f"{book_id}: total={n} todo={len(todo)} workers={workers}", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ocr_one, pdf, p, langs): p for p in todo}
        for fut in as_completed(futs):
            p, text = fut.result()
            pages[str(p)] = {"page": p, "text": text}
            done += 1
            if done % 10 == 0 or done == len(todo):
                data = {"bookId": book_id, "title": title, "class": 8, "source": "PCTB",
                        "pageCount": n, "pages": pages}
                out_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"{book_id} progress {done}/{len(todo)}", flush=True)
    data = {"bookId": book_id, "title": title, "class": 8, "source": "PCTB",
            "pageCount": n, "pages": pages}
    out_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"DONE {book_id}", flush=True)

if __name__ == "__main__":
    main()
