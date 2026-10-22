"""
ratings_manager.py - Shared 1-5 Star User Ratings Store for Beatbar Suite.

Persists user ratings across Desktop Viewer, Web Viewer, and .beat archives.
Stored in cache/user_ratings.json and optionally embedded into .beat manifest.json.
"""

import os
import json
import time
from typing import Dict, Any, Optional

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
RATINGS_FILE = os.path.join(CACHE_DIR, "user_ratings.json")


def _get_key(filename_or_path: str) -> str:
    """Normalizes file path or name to base filename for consistent lookup."""
    if not filename_or_path:
        return ""
    return os.path.basename(filename_or_path).strip().lower()


def get_all_ratings() -> Dict[str, Dict[str, Any]]:
    """Returns all ratings as a dict keyed by normalized filename."""
    if not os.path.exists(RATINGS_FILE):
        return {}
    try:
        with open(RATINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_rating(filename_or_path: str) -> int:
    """Returns star rating (1-5) for a video or beat file, or 0 if unrated."""
    key = _get_key(filename_or_path)
    if not key:
        return 0
    all_ratings = get_all_ratings()
    entry = all_ratings.get(key)
    if entry:
        if isinstance(entry, dict):
            return int(entry.get("rating", 0))
        elif isinstance(entry, (int, float)):
            return int(entry)
    return 0


def set_rating(filename_or_path: str, rating: int, sync_beat_archive: bool = True) -> int:
    """
    Saves a 1-5 star rating for the given file.
    Optionally syncs rating into .beat archive manifest.json if applicable.
    Returns the clamped rating (1-5, or 0 to clear).
    """
    key = _get_key(filename_or_path)
    if not key:
        return 0

    rating = max(0, min(5, int(rating)))
    os.makedirs(CACHE_DIR, exist_ok=True)

    all_ratings = get_all_ratings()
    if rating == 0:
        if key in all_ratings:
            del all_ratings[key]
    else:
        all_ratings[key] = {
            "rating": rating,
            "filename": os.path.basename(filename_or_path),
            "updated_at": time.time()
        }

    try:
        with open(RATINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_ratings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[RatingsManager] Failed to write {RATINGS_FILE}: {e}")

    # Optionally sync into .beat file manifest if it exists
    if sync_beat_archive and filename_or_path and os.path.isfile(filename_or_path):
        if filename_or_path.lower().endswith(".beat"):
            _sync_rating_to_beat(filename_or_path, rating)

    return rating


def _sync_rating_to_beat(beat_path: str, rating: int):
    """Ratings have been deprecated from .beat archives per project specification."""
    return
