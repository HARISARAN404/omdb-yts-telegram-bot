"""YTS checker microservice: given OMDb results, find and validate .torrent links on YTS mirror pages."""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yts-checker")

# Add more site bases here if you want to check additional mirrors (or set YTS_SITE_BASES, comma-separated)
SITE_BASES = [
    base.strip()
    for base in os.environ.get("YTS_SITE_BASES", "https://www.yts-official.cc/movies").split(",")
    if base.strip()
]

# HTTP settings
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "8"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "8"))  # for parallel page checks and link validations
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) omdb-yts-checker/2.0"

# quality token mapping (normalize many tokens into canonical quality/source fields)
QUALITY_MAP = {
    "1080p": "1080p",
    "720p": "720p",
    "2160p": "2160p",
    "4k": "2160p",
    "uhd": "2160p",
    "2k": "2k",
    "1440p": "2k",
}

SOURCE_TOKENS = {
    "web": "WEB",
    "webrip": "WEB",
    "web-dl": "WEB",
    "bluray": "BLURAY",
    "brrip": "BLURAY",
    "hdrip": "HDRIP",
    "cam": "CAM",
}

CODEC_TOKENS = {"x265": "x265", "h.265": "x265", "hevc": "x265", "x264": "x264", "h.264": "x264"}

# regex helpers
TORRENT_REGEX = re.compile(r"\.torrent\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z0-9\-\.]{2,}")  # tokens in anchor text/title

# Shared, pooled HTTP session and I/O thread pool (reused across requests instead of per call).
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT
session.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS * 2))
session.mount("http://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS * 2))
io_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS * 2, thread_name_prefix="io")


def slugify_title_for_yts(title: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())
    return re.sub(r"-{2,}", "-", t).strip("-")


def build_candidate_urls(title: str, year: str) -> list[str]:
    slug = slugify_title_for_yts(title)
    return [f"{base}/{slug}-{year}" for base in SITE_BASES]


def _first_match(low: str, mapping: dict[str, str]) -> str | None:
    return next((v for k, v in mapping.items() if k in low), None)


def normalize_tokens(tokens: list[str]) -> dict[str, Any]:
    """Given a list of textual tokens (from anchor text/title), return normalized fields."""
    quality = source = codec = None
    for t in tokens:
        low = t.lower()
        quality = quality or _first_match(low, QUALITY_MAP)
        source = source or _first_match(low, SOURCE_TOKENS)
        codec = codec or _first_match(low, CODEC_TOKENS)

    return {
        "quality": quality or "unknown",
        "source": source or "unknown",
        "codec": codec or "unknown",
        "raw_tokens": list(tokens),
    }


def lightweight_validate_url(url: str) -> dict[str, Any]:
    """
    Do a small validation request to the torrent URL (allow redirects, body not downloaded).
    Returns metadata like final_url, status, content_type, content_length.
    """
    try:
        with session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True) as r:
            return {
                "ok": r.status_code == 200,
                "status": r.status_code,
                "final_url": r.url,
                "content_type": r.headers.get("Content-Type", ""),
                "content_length": r.headers.get("Content-Length"),
            }
    except requests.RequestException as exc:
        logger.debug("validate_url error for %s : %s", url, exc)
        return {"ok": False, "error": str(exc)}


def fetch_page(url: str) -> tuple[bool, int | str, str]:
    """Fetch a page, return tuple (success, status code or "error", text)."""
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return (True, r.status_code, r.text) if r.status_code == 200 else (False, r.status_code, "")
    except requests.RequestException as exc:
        logger.debug("fetch_page error for %s : %s", url, exc)
        return False, "error", ""


def extract_torrents_from_html(page_url: str, html: str) -> list[dict[str, Any]]:
    """Parse the HTML and return a list of found torrent link dictionaries with metadata."""
    soup = BeautifulSoup(html, "html.parser")
    found = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not TORRENT_REGEX.search(href):
            continue

        title_attr = a.get("title", "")
        anchor_text = a.get_text(" ", strip=True)
        tokens = TOKEN_RE.findall(f"{title_attr} {anchor_text}")
        meta = normalize_tokens(tokens)

        found.append(
            {
                "torrent_href": href,
                "torrent_url": urljoin(page_url, href),
                "anchor_text": anchor_text,
                "anchor_title": title_attr,
                "tokens": tokens,
                "quality": meta["quality"],
                "source": meta["source"],
                "codec": meta["codec"],
            }
        )

    return found


def check_single_movie(item: dict[str, Any]) -> dict[str, Any]:
    """
    For a single item {imdbID, title, year}, check all candidate site pages,
    parse torrent anchors, validate links in parallel, and return structured result.
    """
    imdbid = item.get("imdbID") or item.get("id") or ""
    title = item.get("title") or item.get("Title") or ""
    year = str(item.get("year") or item.get("Year") or "")

    out: dict[str, Any] = {"imdbID": imdbid, "title": title, "year": year, "checked_urls": [], "torrents": []}

    candidate_pages = build_candidate_urls(title, year)
    link_candidates = []
    for url, (success, status, html) in zip(candidate_pages, io_pool.map(fetch_page, candidate_pages), strict=True):
        out["checked_urls"].append({"url": url, "status": status})
        if success:
            for e in extract_torrents_from_html(url, html):
                e["source_page"] = url
                link_candidates.append(e)

    validations = io_pool.map(lightweight_validate_url, [link["torrent_url"] for link in link_candidates])

    # dedupe by final_url or torrent_url
    seen = set()
    for link, validation in zip(link_candidates, validations, strict=True):
        key = validation.get("final_url") or link["torrent_url"]
        if key in seen:
            continue
        seen.add(key)
        out["torrents"].append({**link, "validation": validation})

    return out


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.post("/check")
def check_endpoint():
    """
    POST payload:
    { "items": [ {"imdbID": ".", "title": ".", "year": "."}, . ] }

    Response:
    { "results": { "<imdbID>": { . movie result . }, . } }
    """
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid json"}), 400

    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "payload must contain 'items' list"}), 400

    results = {}
    # Movies run on their own pool; their page fetches/validations run on the shared io_pool.
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(items)))) as ex:
        futures = [(it, ex.submit(check_single_movie, it)) for it in items]
        for it, fut in futures:
            try:
                res = fut.result()
                results[res.get("imdbID") or res.get("title")] = res
            except Exception as exc:
                logger.exception("check failed for %s", it)
                results[it.get("imdbID") or it.get("title")] = {"error": str(exc)}

    return jsonify({"results": results}), 200


if __name__ == "__main__":
    # Dev server only. In production the Dockerfile runs gunicorn.
    app.run(host="0.0.0.0", port=8000)
