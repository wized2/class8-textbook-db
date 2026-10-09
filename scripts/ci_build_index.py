#!/usr/bin/env python3
import json
from pathlib import Path

root = Path.cwd()
books = []
for d in sorted((root / "books").iterdir()):
    f = d / "data.json"
    if not f.exists():
        continue
    data = json.loads(f.read_text(encoding="utf-8"))
    pages = data.get("pages") or {}
    ok = sum(1 for v in pages.values() if len(v.get("text") or "") >= 25)
    books.append(
        {
            "bookId": data.get("bookId") or d.name,
            "title": data.get("title") or d.name,
            "class": 8,
            "source": "PCTB",
            "pageCount": data.get("pageCount") or len(pages),
            "ocrPages": ok,
        }
    )
(root / "index.json").write_text(
    json.dumps({"books": books}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"index: {len(books)} books")
for b in books:
    print(f"  {b['bookId']}: {b['ocrPages']}/{b['pageCount']}")
