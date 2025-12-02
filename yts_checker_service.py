# yts_checker_service.py
import re
import logging
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yts-checker")

# Config: add more site bases here if you want to check additional mirrors
SITE_BASES = [
    "https://www.yts-official.cc/movies",
    # "https://yts.mx/movies",  # add if needed
]

# HTTP settings
REQUEST_TIMEOUT = 8.0
MAX_WORKERS = 8  # for parallel page checks and link validations

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
    "webrip": "WEB",
    "bluray": "BLURAY",
    "brrip": "BLURAY",
    "hdrip": "HDRIP",
    "cam": "CAM",
}

CODEC_TOKENS = {"x265": "x265", "h.265": "x265", "hevc": "x265", "x264": "x264", "h.264": "x264"}

# regex helpers
TORRENT_REGEX = re.compile(r"\.torrent\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z0-9\-\.]{2,}", re.IGNORECASE)  # tokens in anchor text/title


def slugify_title_for_yts(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    t = t.strip("-")
    return t


def build_candidate_urls(title: str, year: str) -> List[str]:
    slug = slugify_title_for_yts(title)
    urls = [f"{base}/{slug}-{year}" for base in SITE_BASES]
    return urls


def normalize_tokens(tokens: List[str]) -> Dict[str, Any]:
    """
    Given a list of textual tokens (from anchor text/title), return normalized fields.
    """
    quality = None
    source = None
    codec = None
    extras = []

    for t in tokens:
        low = t.lower()
        if not quality:
            for k, v in QUALITY_MAP.items():
                if k in low:
                    quality = v
                    break
        if not source:
            for k, v in SOURCE_TOKENS.items():
                if k in low:
                    source = v
                    break
        if not codec:
            for k, v in CODEC_TOKENS.items():
                if k in low:
                    codec = v
                    break
        # collect candidate extras like '1080p.WEB' parts
        extras.append(t)

    return {
        "quality": quality or "unknown",
        "source": source or "unknown",
        "codec": codec or "unknown",
        "raw_tokens": extras,
    }


def resolve_absolute_url(page_url: str, href: str) -> str:
    return urljoin(page_url, href)


def lightweight_validate_url(url: str) -> Dict[str, Any]:
    """
    Do a small validation request to the torrent URL (allow redirects).
    Returns metadata like final_url, status_code, content_type, content_length.
    """
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
        final_url = r.url
        status = r.status_code
        ctype = r.headers.get("Content-Type", "")
        clen = r.headers.get("Content-Length")
        # close stream
        try:
            r.close()
        except Exception:
            pass
        return {"ok": status == 200, "status": status, "final_url": final_url, "content_type": ctype, "content_length": clen}
    except requests.RequestException as exc:
        logger.debug("validate_url error for %s : %s", url, exc)
        return {"ok": False, "error": str(exc)}


def extract_torrents_from_html(page_url: str, html: str) -> List[Dict[str, Any]]:
    """
    Parse the HTML and return a list of found torrent link dictionaries with metadata.
    """
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    found = []

    for a in anchors:
        href = a["href"]
        if not TORRENT_REGEX.search(href):
            continue  # skip non-torrent links

        title_attr = a.get("title", "")
        anchor_text = (a.get_text(" ", strip=True) or "").strip()

        # tokens gathered from title and anchor text
        token_source = " ".join([title_attr, anchor_text])
        tokens = TOKEN_RE.findall(token_source)

        meta = normalize_tokens(tokens)
        abs_url = resolve_absolute_url(page_url, href)

        found.append({
            "torrent_href": href,
            "torrent_url": abs_url,
            "anchor_text": anchor_text,
            "anchor_title": title_attr,
            "tokens": tokens,
            "quality": meta["quality"],
            "source": meta["source"],
            "codec": meta["codec"],
        })

    return found


def check_single_movie(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    For a single item {imdbID, title, year}, check all candidate site pages,
    parse torrent anchors, validate links in parallel, and return structured result.
    """
    imdbid = item.get("imdbID") or item.get("id") or ""
    title = item.get("title", "") or item.get("Title", "")
    year = str(item.get("year", "") or item.get("Year", ""))

    out = {"imdbID": imdbid, "title": title, "year": year, "checked_urls": [], "torrents": []}

    candidate_pages = build_candidate_urls(title, year)
    page_htmls = {}

    # fetch candidate pages (sequentially or parallel)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(candidate_pages))) as ex:
        future_to_url = {ex.submit(fetch_page, url): url for url in candidate_pages}
        for fut in as_completed(future_to_url):
            url = future_to_url[fut]
            try:
                success, status, text = fut.result()
                out["checked_urls"].append({"url": url, "status": status})
                if success:
                    page_htmls[url] = text
            except Exception as exc:
                out["checked_urls"].append({"url": url, "status": "error", "error": str(exc)})

    # for each fetched page, extract torrent anchors
    link_candidates = []
    for page_url, html in page_htmls.items():
        extracted = extract_torrents_from_html(page_url, html)
        for e in extracted:
            e["source_page"] = page_url
            link_candidates.append(e)

    # validate each torrent link (parallel)
    validations = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_to_link = {ex.submit(lightweight_validate_url, link["torrent_url"]): link for link in link_candidates}
        for fut in as_completed(future_to_link):
            link = future_to_link[fut]
            res = fut.result()
            # attach validation result
            link_out = dict(link)  # shallow copy
            link_out.update({"validation": res})
            out["torrents"].append(link_out)

    # dedupe by final_url or torrent_url path
    seen = set()
    deduped = []
    for t in out["torrents"]:
        key = (t.get("validation", {}).get("final_url") or t["torrent_url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    out["torrents"] = deduped
    return out


def fetch_page(url: str):
    """
    Fetch a page, return tuple (success:bool, status:int or str, text:str)
    """
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        status = r.status_code
        if status == 200:
            return True, status, r.text
        return False, status, ""
    except requests.RequestException as exc:
        logger.debug("fetch_page error for %s : %s", url, exc)
        return False, "error", ""


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/check", methods=["POST"])
def check_endpoint():
    """
    POST payload:
    { "items": [ {"imdbID": ".", "title": ".", "year": "."}, . ] }

    Response:
    { "results": { "<imdbID>": { . movie result . }, . } }
    """
    try:
        payload = request.get_json(force=True)
    except Exception as exc:
        return jsonify({"error": "invalid json", "details": str(exc)}), 400

    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "payload must contain 'items' list"}), 400

    results = {}
    # process movies in parallel (but limit total workers)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(items)))) as ex:
        future_to_item = {ex.submit(check_single_movie, it): it for it in items}
        for fut in as_completed(future_to_item):
            it = future_to_item[fut]
            try:
                res = fut.result()
                key = res.get("imdbID") or res.get("title")
                results[key] = res
            except Exception as exc:
                key = (it.get("imdbID") or it.get("title"))
                results[key] = {"error": str(exc)}

    return jsonify({"results": results}), 200


if __name__ == "__main__":
    # run simple Flask server (dev). In production use a WSGI server (gunicorn/uvicorn).
    app.run(host="0.0.0.0", port=8000)
