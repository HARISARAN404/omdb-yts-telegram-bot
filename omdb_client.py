# omdb_client.py
import requests
import logging
from typing import Optional, Dict
from urllib.parse import urljoin
from config import cfg

logger = logging.getLogger("omdb_client")
OMDB_URL = "http://www.omdbapi.com/"


def omdb_search(query: str, api_key: Optional[str] = None, timeout: int = 8) -> Optional[Dict]:
    """
    Synchronous search to OMDb. Returns parsed JSON or None on error.
    """
    key = api_key or cfg.OMDB_API_KEY
    if not key:
        logger.error("OMDB API key not set")
        return None
    params = {"apikey": key, "s": query}
    try:
        r = requests.get(OMDB_URL, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("omdb_search failed")
        return None


def omdb_get_by_id(imdbid: str, api_key: Optional[str] = None, timeout: int = 8) -> Optional[Dict]:
    key = api_key or cfg.OMDB_API_KEY
    if not key:
        logger.error("OMDB API key not set")
        return None
    params = {"apikey": key, "i": imdbid, "plot": "short"}
    try:
        r = requests.get(OMDB_URL, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("omdb_get_by_id failed")
        return None
