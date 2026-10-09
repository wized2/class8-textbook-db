/**
 * class-8-get — serves Class 8 PCTB textbook page text from GitHub JSON.
 * Routes:
 *   GET /                 info
 *   GET /v1/books         list books
 *   GET /v1/books/:id     book metadata + page count
 *   GET /v1/books/:id/pages/:n   page text (n = printed book page number)
 */
const GH_BASE = "https://raw.githubusercontent.com/wized2/class8-textbook-db/main";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...cors },
  });
}

async function gh(path) {
  const r = await fetch(`${GH_BASE}${path}`, {
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!r.ok) return null;
  return r.json();
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (path === "/" || path === "/v1") {
      return json({
        name: "class-8-get",
        description: "Class 8 PCTB textbook page text API",
        routes: [
          "GET /v1/books",
          "GET /v1/books/:bookId",
          "GET /v1/books/:bookId/pages/:page",
        ],
        source: "https://github.com/wized2/class8-textbook-db",
      });
    }

    if (path === "/v1/books") {
      const idx = await gh("/index.json");
      if (!idx) return json({ error: "index unavailable" }, 502);
      return json(idx);
    }

    let m = path.match(/^\/v1\/books\/([a-z0-9_]+)$/i);
    if (m) {
      const bookId = m[1];
      const data = await gh(`/books/${bookId}/data.json`);
      if (!data) return json({ error: "book not found", bookId }, 404);
      return json({
        bookId: data.bookId || bookId,
        title: data.title,
        class: data.class,
        source: data.source,
        pageCount: data.pageCount || Object.keys(data.pages || {}).length,
      });
    }

    m = path.match(/^\/v1\/books\/([a-z0-9_]+)\/pages\/(\d+)$/i);
    if (m) {
      const bookId = m[1];
      const page = String(parseInt(m[2], 10));
      const data = await gh(`/books/${bookId}/data.json`);
      if (!data) return json({ error: "book not found", bookId }, 404);
      const entry = (data.pages || {})[page];
      if (!entry) return json({ error: "page not found", bookId, page: Number(page) }, 404);
      return json({
        book: bookId,
        page: Number(page),
        text: entry.text || "",
        title: data.title || null,
      });
    }

    return json({ error: "not found" }, 404);
  },
};
