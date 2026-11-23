/* Serves the static landing page (../../landing) from memory.
   `bun build` inlines the four files, so the deployed server is one self-contained file. */
import page from "../../landing/index.html" with { type: "text" };
import styles from "../../landing/styles.css" with { type: "text" };
import script from "../../landing/main.js" with { type: "text" };
import persian from "../../landing/fa.js" with { type: "text" };

type Asset = { body: Uint8Array; gzip: Uint8Array; type: string; etag: string; cache: string };

const encoder = new TextEncoder();
const shortHash = (text: string) => Bun.hash(text).toString(36);
const sha256 = (text: string) => new Bun.CryptoHasher("sha256").update(text).digest("base64");

function asset(text: string, type: string, cache: string): Asset {
  const body = encoder.encode(text);
  return { body, gzip: Bun.gzipSync(body), type, etag: `"${shortHash(text)}"`, cache };
}

// Versioned asset URLs, so CSS and scripts can be cached for a year and still change on every deploy.
const LONG = "public, max-age=31536000, immutable";
const versions = { "styles.css": shortHash(styles), "main.js": shortHash(script), "fa.js": shortHash(persian) };
let html = page;
for (const [name, v] of Object.entries(versions)) {
  html = html.replace(new RegExp(`(href|src)="${name.replace(".", "\\.")}"`), `$1="${name}?v=${v}"`);
}

// The page's two inline scripts are allowed by hash; nothing else inline may run.
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => `'sha256-${sha256(m[1])}'`);
const CSP = [
  "default-src 'self'",
  `script-src 'self' ${inline.join(" ")}`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data:",
  "frame-src https://calendar.google.com",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

const SECURITY: Record<string, string> = {
  "Content-Security-Policy": CSP,
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
};

const HTML = "text/html; charset=utf-8";
const pageAsset = asset(html, HTML, "no-cache");
const ROUTES: Record<string, Asset> = {
  "/": pageAsset,
  "/index.html": pageAsset,
  "/styles.css": asset(styles, "text/css; charset=utf-8", LONG),
  "/main.js": asset(script, "text/javascript; charset=utf-8", LONG),
  "/fa.js": asset(persian, "text/javascript; charset=utf-8", LONG),
  "/robots.txt": asset("User-agent: *\nAllow: /\n", "text/plain; charset=utf-8", "public, max-age=3600"),
  "/healthz": asset("ok\n", "text/plain; charset=utf-8", "no-store"),
};
const NOT_FOUND = asset(
  '<!doctype html><meta charset="utf-8"><title>Not found — Soshyant Expert</title>' +
    '<body style="background:#030507;color:#dcfff3;font:16px system-ui;display:grid;place-items:center;min-height:90vh">' +
    '<p>404 · <a href="/" style="color:#19ffb0">Soshyant Expert</a></p>',
  HTML,
  "no-cache",
);

function send(req: Request, a: Asset, status = 200): Response {
  const headers = new Headers(SECURITY);
  headers.set("Content-Type", a.type);
  headers.set("Cache-Control", a.cache);
  headers.set("ETag", a.etag);
  headers.set("Vary", "Accept-Encoding");
  if (status === 200 && req.headers.get("If-None-Match") === a.etag) return new Response(null, { status: 304, headers });
  const gzip = /\bgzip\b/.test(req.headers.get("Accept-Encoding") ?? "");
  const body = gzip ? a.gzip : a.body;
  if (gzip) headers.set("Content-Encoding", "gzip");
  headers.set("Content-Length", String(body.byteLength));
  return new Response(req.method === "HEAD" ? null : body, { status, headers });
}

export function handle(req: Request): Response {
  if (req.method !== "GET" && req.method !== "HEAD") {
    return new Response("Method not allowed\n", { status: 405, headers: { ...SECURITY, Allow: "GET, HEAD" } });
  }
  const a = ROUTES[new URL(req.url).pathname];
  return a ? send(req, a) : send(req, NOT_FOUND, 404);
}
