#!/usr/bin/env python3
"""OCR a range of PDF pages into per-page JSON files."""
import json, subprocess, sys, tempfile
from pathlib import Path

def ocr_page(pdf: Path, page: int, langs: str, out: Path, dpi: int = 100):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 20:
        return "skip"
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), str(pdf), str(prefix)],
            check=False, capture_output=True,
        )
        imgs = list(Path(td).glob("p*.png"))
        if not imgs:
            out.write_text(json.dumps({"page": page, "text": ""}, ensure_ascii=False), encoding="utf-8")
            return "empty"
        r = subprocess.run(
            ["tesseract", str(imgs[0]), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True, text=True,
        )
        text = "\n".join(ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip())
        out.write_text(json.dumps({"page": page, "text": text}, ensure_ascii=False), encoding="utf-8")
        return "ok"

if __name__ == "__main__":
    pdf, outdir, langs, start, end = sys.argv[1:6]
    start, end = int(start), int(end)
    for p in range(start, end + 1):
        dest = Path(outdir) / f"{p:03d}.json"
        st = ocr_page(Path(pdf), p, langs, dest)
        print(f"{p}:{st}", flush=True)
