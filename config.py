# config.py
import os
from dataclasses import dataclass
from typing import Optional

try:
    # optional: if you keep a .env file locally, python-dotenv will load it
    # (this is safe because .env should be in .gitignore)
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv not required; env vars still work
    pass


@dataclass
class Config:
    TELEGRAM_BOT_TOKEN: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
    OMDB_API_KEY: Optional[str] = os.environ.get("OMDB_API_KEY")
    YTS_CHECKER_URL: str = os.environ.get("YTS_CHECKER_URL", "http://127.0.0.1:8000")
    MAX_RESULTS: int = int(os.environ.get("MAX_RESULTS", "8"))

    def checker_endpoint(self) -> str:
        return self.YTS_CHECKER_URL.rstrip("/") + "/check"


cfg = Config()
