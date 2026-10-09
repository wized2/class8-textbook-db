#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = {
    "english8": {"title": "English Class 8 (PCTB SNC)", "class": 8, "subject": "English", "source": "PCTB"},
    "tarjama8": {"title": "Tarjama-tul-Quran Class 8 (PCTB)", "class": 8, "subject": "Tarjama-tul-Quran", "source": "PCTB"},
}

index = {"books": []}
for bid, meta in BOOKS.items():
    pdir = ROOT / "books" / bid / "pages"
    pages = {}
    if pdir.exists():
        for f in sorted(pdir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                pages[str(d.get("page", int(f.stem)))] = d.get("text", "")
            except Exception:
                pass
    page_nums = sorted(int(k) for k in pages)
    manifest = {
        **meta,
        "bookId": bid,
        "pageCount": len(pages),
        "pageMin": page_nums[0] if page_nums else None,
        "pageMax": page_nums[-1] if page_nums else None,
        "note": "OCR text from official PCTB scan; may contain recognition errors.",
    }
    bdir = ROOT / "books" / bid
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    full = {"bookId": bid, **meta, "pages": {k: {"page": int(k), "text": v} for k, v in pages.items()}}
    (bdir / "full.json").write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    index["books"].append(manifest)
    print(bid, "pages", len(pages))

(ROOT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote index.json")
