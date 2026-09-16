"""Async OMDb API client."""

import logging
from typing import Any

import httpx

from config import cfg

logger = logging.getLogger("omdb_client")
OMDB_URL = "https://www.omdbapi.com/"


async def _get(client: httpx.AsyncClient, params: dict[str, str], timeout: float) -> dict[str, Any] | None:
    key = cfg.OMDB_API_KEY
    if not key:
        logger.error("OMDB API key not set")
        return None
    try:
        r = await client.get(OMDB_URL, params={"apikey": key, **params}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("OMDb request failed (%s)", params)
        return None


async def omdb_search(client: httpx.AsyncClient, query: str, timeout: float = 8) -> dict[str, Any] | None:
    """Search OMDb by title. Returns parsed JSON or None on error."""
    return await _get(client, {"s": query}, timeout)


async def omdb_get_by_id(client: httpx.AsyncClient, imdbid: str, timeout: float = 8) -> dict[str, Any] | None:
    """Fetch a single title by IMDb ID. Returns parsed JSON or None on error."""
    return await _get(client, {"i": imdbid, "plot": "short"}, timeout)
