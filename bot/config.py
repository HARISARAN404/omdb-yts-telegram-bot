"""Bot configuration, read from environment variables (and a local .env if present)."""

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; plain env vars still work
    pass


@dataclass(frozen=True)
class Config:
    TELEGRAM_BOT_TOKEN: str | None = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN"))
    OMDB_API_KEY: str | None = field(default_factory=lambda: os.environ.get("OMDB_API_KEY"))
    YTS_CHECKER_URL: str = field(default_factory=lambda: os.environ.get("YTS_CHECKER_URL", "http://127.0.0.1:8000"))
    MAX_RESULTS: int = field(default_factory=lambda: int(os.environ.get("MAX_RESULTS", "8")))

    def checker_endpoint(self) -> str:
        return self.YTS_CHECKER_URL.rstrip("/") + "/check"


cfg = Config()
