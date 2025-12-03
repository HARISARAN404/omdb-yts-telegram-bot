# utils.py
from typing import Optional, Any


def pretty_bytes(val: Optional[Any]) -> str:
    """Turn bytes (int or numeric string) into human-readable string."""
    if val is None:
        return "unknown"
    try:
        if isinstance(val, str):
            v = int(val.replace(",", "").strip())
        else:
            v = int(val)
    except Exception:
        return "unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(v)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx >= 2:
        return f"{size:.1f} {units[idx]}"
    else:
        return f"{int(size)} {units[idx]}"
