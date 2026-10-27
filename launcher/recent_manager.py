"""
recent_manager.py - Manages recent projects (.beat) and media history (.mp4) for Beatbar Launcher.

Aggregates recent files from user interaction history and local library folders,
providing quick-access lists sorted by last modified time.
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from launcher.version_manager import ROOT_DIR


def format_file_size(num_bytes: int) -> str:
    """Formats file size into human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}" if unit != 'B' else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def format_relative_time(timestamp: float) -> str:
    """Formats timestamp into clean readable string."""
    try:
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("Today, %H:%M")
        elif (now.date() - dt.date()).days == 1:
            return dt.strftime("Yesterday, %H:%M")
        elif (now.date() - dt.date()).days < 7:
            return dt.strftime("%a, %H:%M")
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def get_recent_media_history(
    config_history: Optional[List[str]] = None,
    max_items: int = 5
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns the most recent .beat projects and .mp4 videos.
    Combines persistent user history with scanned local files in ROOT_DIR/videos.
    """
    videos_dir = os.path.join(ROOT_DIR, "videos")
    discovered_beats = []
    discovered_videos = []
    seen_paths = set()

    # 1. Process explicit user history first
    if config_history:
        for p in config_history:
            if not p or p in seen_paths:
                continue
            norm = os.path.abspath(p)
            if not os.path.isfile(norm):
                continue
            seen_paths.add(norm)
            lower = norm.lower()
            mtime = os.path.getmtime(norm)
            size = os.path.getsize(norm)
            info = {
                "path": norm,
                "name": os.path.basename(norm),
                "mtime": mtime,
                "time_str": format_relative_time(mtime),
                "size_str": format_file_size(size)
            }
            if lower.endswith(".beat"):
                discovered_beats.append(info)
            elif lower.endswith((".mp4", ".mkv", ".webm", ".avi")):
                discovered_videos.append(info)

    # 2. Scan videos directory for any recently edited/added media
    if os.path.isdir(videos_dir):
        try:
            for root, dirs, files in os.walk(videos_dir):
                # Avoid hidden / cache folders
                if any(skip in root for skip in ["__pycache__", "cache", ".git", "thumbnails"]):
                    continue
                for f in files:
                    lower = f.lower()
                    if lower.endswith(".beat") or lower.endswith((".mp4", ".mkv", ".webm")):
                        full_p = os.path.abspath(os.path.join(root, f))
                        if full_p in seen_paths:
                            continue
                        seen_paths.add(full_p)
                        try:
                            mtime = os.path.getmtime(full_p)
                            size = os.path.getsize(full_p)
                            info = {
                                "path": full_p,
                                "name": f,
                                "mtime": mtime,
                                "time_str": format_relative_time(mtime),
                                "size_str": format_file_size(size)
                            }
                            if lower.endswith(".beat"):
                                discovered_beats.append(info)
                            else:
                                discovered_videos.append(info)
                        except OSError:
                            pass
        except Exception:
            pass

    # Sort each list by last modified time (newest first)
    discovered_beats.sort(key=lambda x: x["mtime"], reverse=True)
    discovered_videos.sort(key=lambda x: x["mtime"], reverse=True)

    return {
        "beats": discovered_beats[:max_items],
        "videos": discovered_videos[:max_items]
    }


def add_to_recent_history(config_history: List[str], new_path: str, max_stored: int = 25) -> List[str]:
    """Adds a file path to the recent history list, moving it to top and deduplicating."""
    if not new_path or not os.path.isfile(new_path):
        return config_history

    norm = os.path.abspath(new_path)
    res = [p for p in config_history if os.path.abspath(p) != norm]
    res.insert(0, norm)
    return res[:max_stored]
