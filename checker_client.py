# checker_client.py
import logging
import requests
from typing import Optional, Dict
from config import cfg

logger = logging.getLogger("checker_client")


def post_to_checker(payload: Dict, endpoint: Optional[str] = None, timeout: int = 20) -> Optional[Dict]:
    """
    Post the payload to the checker service and return parsed JSON or None.
    Payload format expected: {"items": [{"imdbID": "...", "title": "...", "year": "..."} ...]}
    """
    url = endpoint or cfg.checker_endpoint()
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("post_to_checker failed")
        return None
