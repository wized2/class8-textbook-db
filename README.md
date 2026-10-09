# Class 8 Textbook Page Database + API

OCR page text from **PCTB Class 8** textbooks for tutor / study APIs.

## Live API

**Base:** https://class-8-get.endroid.workers.dev

| Route | Description |
|-------|-------------|
| `GET /` | API info |
| `GET /v1/books` | List books |
| `GET /v1/books/{bookId}` | Book metadata |
| `GET /v1/books/{bookId}/pages/{page}` | Page text |

### Examples

```bash
curl https://class-8-get.endroid.workers.dev/v1/books
curl https://class-8-get.endroid.workers.dev/v1/books/english8/pages/15
curl https://class-8-get.endroid.workers.dev/v1/books/math8/pages/42
```

### Tutor tool shape

```json
{ "tool": "textbook_page", "book": "english8", "page": 15 }
```

## Books (bookId)

| bookId | Subject |
|--------|---------|
| english8 | English |
| math8 | Mathematics |
| science8 | General Science |
| computer8 | Computer Science |
| history8 | History |
| geography8 | Geography |
| ethics8 | Ethics |
| islamiat8 | Islamiat |
| urdu8 | Urdu |
| arabic8 | Arabic |
| tarjama8 | Tarjama-tul-Quran |

Data lives in `books/{bookId}/data.json`. Worker reads from this GitHub repo (raw).

## OCR note

Scanned PDFs → Tesseract OCR. English-medium books are more reliable; Urdu/Arabic pages may be incomplete or noisy. Educational use only (PCTB free e-books).

## Worker

Source: `worker/worker.js` — Cloudflare Worker `class-8-get` on `*.endroid.workers.dev`.
