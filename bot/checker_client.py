"""Async client for the YTS checker service."""

import logging
from typing import Any

import httpx

from config import cfg

logger = logging.getLogger("checker_client")


async def post_to_checker(
    client: httpx.AsyncClient, payload: dict[str, Any], timeout: float = 20
) -> dict[str, Any] | None:
    """
    Post the payload to the checker service and return parsed JSON or None.
    Payload format expected: {"items": [{"imdbID": "...", "title": "...", "year": "..."} ...]}
    """
    try:
        r = await client.post(cfg.checker_endpoint(), json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("post_to_checker failed")
        return None
