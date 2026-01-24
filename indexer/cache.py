import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

CACHE_VERSION = "v1"
CACHE_DIR = ".cache"


def generate_cache_key(content: str, model: str) -> str:
    """Creates a deterministic hash from content and model."""
    key_input = f"{CACHE_VERSION}:{model}:{content}"
    return hashlib.sha256(key_input.encode()).hexdigest()


def _get_cache_path(subdir: str, cache_key: str) -> str:
    """Returns the full path for a cache file."""
    return os.path.join(CACHE_DIR, subdir, f"{cache_key}.json")


def get_cached(subdir: str, cache_key: str) -> Any | None:
    """Retrieves cached data or returns None if not found."""
    cache_path = _get_cache_path(subdir, cache_key)

    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
            return cached.get("data")
    except (json.JSONDecodeError, IOError):
        return None


def set_cached(subdir: str, cache_key: str, data: Any, model: str) -> None:
    """Stores data to cache."""
    cache_path = _get_cache_path(subdir, cache_key)
    cache_dir = os.path.dirname(cache_path)

    os.makedirs(cache_dir, exist_ok=True)

    cache_entry = {
        "model": model,
        "cache_version": CACHE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_entry, f)


def get_cache_stats() -> dict[str, int]:
    """Returns count of cached items per category."""
    stats = {}

    if not os.path.exists(CACHE_DIR):
        return stats

    for subdir in os.listdir(CACHE_DIR):
        subdir_path = os.path.join(CACHE_DIR, subdir)
        if os.path.isdir(subdir_path):
            count = len([f for f in os.listdir(subdir_path) if f.endswith(".json")])
            stats[subdir] = count

    return stats
