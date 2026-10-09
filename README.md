# Class 8 Textbook Page Database + API

OCR page text from **PCTB Class 8** textbooks for tutor / study APIs.

## Live API

**https://class-8-get.endroid.workers.dev**

| Route | Description |
|-------|-------------|
| `GET /v1/books` | List books |
| `GET /v1/books/{bookId}` | Metadata |
| `GET /v1/books/{bookId}/pages/{page}` | Page text |

```bash
curl https://class-8-get.endroid.workers.dev/v1/books/english8/pages/15
```

## GitHub Actions OCR (recommended)

Workflow: **OCR Class 8 Textbooks** (`.github/workflows/ocr-textbooks.yml`)

1. Open **Actions** → **OCR Class 8 Textbooks** → **Run workflow**
2. Optional inputs:
   - `books` — e.g. `math8,science8` (empty = all)
   - `dpi` — default `150` (higher = better OCR, slower)
   - `workers` — parallel threads per book (default `4`)
3. Each book runs as its own job (matrix), uploads artifact, then one job merges + pushes `books/*/data.json` + `index.json`.

Catalog of Drive IDs: `books_catalog.json`.

```bash
# Local equivalent
python3 scripts/ci_ocr_book.py math8 Mathematics <driveId> eng 150 4
python3 scripts/ci_build_index.py
```

## bookIds

`english8` `math8` `science8` `computer8` `history8` `geography8` `ethics8` `islamiat8` `urdu8` `arabic8` `tarjama8`

Educational use — PCTB free e-books. OCR may contain errors on scanned Urdu/Arabic pages.

## Page numbers = printed book pages

API `pages/{n}` uses the **printed page number** in the physical textbook (footer), not the PDF file index.

Cover / title / TOC sheets without a printed number are skipped.
Each JSON entry also has `pdfPage` (1-based PDF index) for debugging.
