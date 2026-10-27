"""
web/video_scanner.py - Video folder scanner and thumbnail generator for Web Viewer.

Scans specified directory (e.g. C:\\HDD\\code\\gemini antigrav\\beatmake\\videos),
generates thumbnails using ffmpeg, extracts media duration/resolution,
and associates matching beat files.
"""

import os
import re
import json
import hashlib
import sys
import subprocess
import threading
import uuid
from typing import List, Dict, Any, Optional

from web.beat_parser import find_matching_beat_file, parse_beat_file, VIDEO_EXTS


import zipfile
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
THUMBNAIL_DIR = os.path.join(WEB_DIR, "thumbnails")
PREVIEWS_DIR = os.path.join(WEB_DIR, "previews")
EXTRACTED_DIR = os.path.join(CACHE_DIR, "extracted_videos")
METADATA_CACHE_FILE = os.path.join(CACHE_DIR, "video_metadata.json")

os.makedirs(PREVIEWS_DIR, exist_ok=True)

# Per-file locks to prevent simultaneous duplicate FFmpeg preview encoding
_preview_locks: Dict[str, threading.Lock] = {}
_preview_locks_mutex = threading.Lock()


def _get_preview_lock(path: str) -> threading.Lock:
    with _preview_locks_mutex:
        if path not in _preview_locks:
            _preview_locks[path] = threading.Lock()
        return _preview_locks[path]


def get_embedded_video_info(beat_path: str) -> Optional[Dict[str, Any]]:
    """
    Checks if a .beat archive contains an embedded video.
    Returns dict with 'entry_name', 'file_size', 'ext' if found, else None.
    """
    if not os.path.isfile(beat_path):
        return None
    try:
        with zipfile.ZipFile(beat_path, "r") as zf:
            namelist = zf.namelist()
            # 1. Look for 'video.*'
            for name in namelist:
                base, ext = os.path.splitext(os.path.basename(name))
                if base.lower() == "video" and ext.lower() in VIDEO_EXTS:
                    info = zf.getinfo(name)
                    return {"entry_name": name, "file_size": info.file_size, "ext": ext.lower()}
            # 2. Look for any video file in archive
            for name in namelist:
                ext = os.path.splitext(name)[1].lower()
                if ext in VIDEO_EXTS:
                    info = zf.getinfo(name)
                    return {"entry_name": name, "file_size": info.file_size, "ext": ext}
    except Exception:
        pass
    return None


def extract_embedded_video(beat_path: str, entry_name: str, expected_size: int) -> Optional[str]:
    """
    Extracts embedded video from .beat archive into cache/extracted_videos/<beat_filename>/<entry_basename>.
    Returns absolute path to extracted video file.
    """
    try:
        beat_filename = os.path.basename(beat_path)
        out_dir = os.path.join(EXTRACTED_DIR, beat_filename)
        os.makedirs(out_dir, exist_ok=True)

        entry_base = os.path.basename(entry_name)
        out_path = os.path.join(out_dir, entry_base)

        # Check if already extracted and size matches
        if os.path.isfile(out_path) and os.path.getsize(out_path) == expected_size:
            return out_path

        with zipfile.ZipFile(beat_path, "r") as zf:
            with zf.open(entry_name) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)

        return out_path
    except Exception as e:
        print(f"Error extracting video from {beat_path}: {e}")
        return None


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _clean_title(filename: str) -> str:
    name, _ = os.path.splitext(filename)
    # Remove resolution tags
    clean = re.sub(r'[-_](?:720p|1080p|480p|4k|360p|2160p)', '', clean_name := name, flags=re.IGNORECASE)
    clean = clean.replace("-", " ").replace("_", " ")
    clean = " ".join(clean.split())
    # Capitalize words
    return clean.title()


class VideoScanner:
    """
    Scans a folder of videos, extracts metadata, produces thumbnails,
    and pairs each video with beatmaps.
    """
    def __init__(self, folder_path: str):
        self.folder_path = os.path.abspath(folder_path)
        os.makedirs(THUMBNAIL_DIR, exist_ok=True)
        os.makedirs(PREVIEWS_DIR, exist_ok=True)
        os.makedirs(EXTRACTED_DIR, exist_ok=True)
        self.metadata_cache = self._load_metadata_cache()

    def _load_metadata_cache(self) -> Dict[str, Any]:
        if os.path.exists(METADATA_CACHE_FILE):
            try:
                with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_metadata_cache(self):
        try:
            with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.metadata_cache, f, indent=2)
        except Exception:
            pass

    def get_extracted_video_path(self, beat_path: str) -> Optional[str]:
        """Returns path to extracted video file for a .beat archive containing an embedded video."""
        info = get_embedded_video_info(beat_path)
        if not info:
            return None
        return extract_embedded_video(beat_path, info["entry_name"], info["file_size"])

    def scan(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Scans self.folder_path for video files and .beat bundles and returns detailed list.
        """
        if not os.path.isdir(self.folder_path):
            return []

        if force_refresh:
            try:
                self.clean_unused_cache()
            except Exception:
                pass

        results = []
        files = sorted(os.listdir(self.folder_path))
        changed = False

        regular_videos = []
        regular_bases = set()
        beat_files = []

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTS:
                regular_videos.append(f)
                regular_bases.add(os.path.splitext(f)[0].lower())
            elif ext == ".beat":
                beat_files.append(f)

        # 1. Process regular videos
        for f in regular_videos:
            full_path = os.path.join(self.folder_path, f)
            if not os.path.isfile(full_path):
                continue

            mtime = os.path.getmtime(full_path)
            size = os.path.getsize(full_path)
            cache_key = f"{f}_{mtime}_{size}"

            meta = self.metadata_cache.get(cache_key)
            if force_refresh or not meta:
                meta = self._probe_video(full_path, f)
                self.metadata_cache[cache_key] = meta
                changed = True

            meta["is_bundle"] = False
            meta["filepath"] = full_path

            # Ensure thumbnail exists
            thumb_path = self.ensure_thumbnail(full_path, f, meta.get("duration", 0))
            meta["has_thumbnail"] = os.path.exists(thumb_path)
            meta["thumbnail_path"] = thumb_path
            meta["thumbnail_url"] = f"/api/thumbnail/{f}"
            meta["preview_url"] = f"/api/preview/{f}"

            # Check matching beats dynamically
            prev_beat_info = meta.get("beat_info") or {}
            prev_beat_path = prev_beat_info.get("beat_path")
            prev_had_beats = prev_beat_info.get("has_beats", False)

            matched_beat = find_matching_beat_file(full_path)

            if matched_beat:
                try:
                    beat_data = parse_beat_file(matched_beat)
                    new_beat_info = {
                        "has_beats": True,
                        "beat_filename": os.path.basename(matched_beat),
                        "beat_path": matched_beat,
                        "format": beat_data["format"],
                        "beat_count": beat_data["total_beats"],
                        "zone_count": beat_data["total_zones"],
                        "bpm": beat_data["settings"].get("bpm", 120.0),
                        "lead_time": beat_data["settings"].get("lead_time", 1.5),
                        "level": beat_data.get("level", 1),
                        "difficulty": beat_data.get("difficulty", "Normal"),
                        "difficulty_stats": beat_data.get("difficulty_stats", {}),
                        "title": beat_data.get("title", meta["title"])
                    }
                    if not prev_had_beats or prev_beat_path != matched_beat:
                        changed = True
                    meta["beat_info"] = new_beat_info
                except Exception as e:
                    new_beat_info = {
                        "has_beats": False,
                        "error": str(e),
                        "beat_filename": os.path.basename(matched_beat),
                        "beat_path": matched_beat
                    }
                    if prev_had_beats:
                        changed = True
                    meta["beat_info"] = new_beat_info
            else:
                if prev_had_beats:
                    changed = True
                meta["beat_info"] = {
                    "has_beats": False,
                    "beat_filename": None,
                    "beat_path": None,
                    "beat_count": 0,
                    "zone_count": 0
                }

            meta["mtime"] = round(mtime, 1)
            results.append(meta)

        # 2. Process .beat files with embedded videos
        for f in beat_files:
            base = os.path.splitext(f)[0].lower()
            if base in regular_bases:
                # Video file with same base exists, already listed
                continue

            full_path = os.path.join(self.folder_path, f)
            if not os.path.isfile(full_path):
                continue

            embed_info = get_embedded_video_info(full_path)
            if not embed_info:
                # Not a video bundle
                continue

            extracted_path = extract_embedded_video(full_path, embed_info["entry_name"], embed_info["file_size"])
            if not extracted_path or not os.path.isfile(extracted_path):
                continue

            mtime = os.path.getmtime(full_path)
            size = os.path.getsize(full_path)
            cache_key = f"{f}_{mtime}_{size}"

            meta = self.metadata_cache.get(cache_key)
            if force_refresh or not meta or not meta.get("duration"):
                meta = self._probe_video(extracted_path, f)
                meta["id"] = f
                meta["filename"] = f
                meta["file_size"] = size
                meta["file_size_formatted"] = _format_size(size)
                self.metadata_cache[cache_key] = meta
                changed = True

            meta["id"] = f
            meta["filename"] = f
            meta["filepath"] = full_path
            meta["is_bundle"] = True
            meta["video_url"] = f"/api/video/{f}"
            meta["thumbnail_url"] = f"/api/thumbnail/{f}"
            meta["preview_url"] = f"/api/preview/{f}"
            meta["extracted_video_path"] = extracted_path

            # Ensure thumbnail exists
            thumb_path = self.ensure_thumbnail(extracted_path, f, meta.get("duration", 0))
            meta["has_thumbnail"] = os.path.exists(thumb_path)
            meta["thumbnail_path"] = thumb_path

            # Parse beats from the .beat archive
            try:
                beat_data = parse_beat_file(full_path)
                if beat_data.get("title"):
                    meta["title"] = beat_data["title"]
                meta["beat_info"] = {
                    "has_beats": True,
                    "beat_filename": f,
                    "beat_path": full_path,
                    "format": "beat",
                    "beat_count": beat_data["total_beats"],
                    "zone_count": beat_data["total_zones"],
                    "bpm": beat_data["settings"].get("bpm", 120.0),
                    "lead_time": beat_data["settings"].get("lead_time", 1.5),
                    "level": beat_data.get("level", 1),
                    "difficulty": beat_data.get("difficulty", "Normal"),
                    "difficulty_stats": beat_data.get("difficulty_stats", {}),
                    "title": beat_data.get("title", meta["title"])
                }
            except Exception as e:
                meta["beat_info"] = {
                    "has_beats": False,
                    "error": str(e),
                    "beat_filename": f,
                    "beat_path": full_path,
                    "beat_count": 0,
                    "zone_count": 0
                }

            meta["mtime"] = round(mtime, 1)
            results.append(meta)

        if changed:
            self._save_metadata_cache()

        return results

    def _probe_video(self, full_path: str, filename: str) -> Dict[str, Any]:
        """Uses ffprobe to extract duration, width, and height."""
        size = os.path.getsize(full_path)
        duration = 0.0
        width = 1280
        height = 720

        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration:format=duration",
                "-of", "json",
                full_path
            ]
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=creationflags)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                streams = data.get("streams", [])
                if streams:
                    s = streams[0]
                    width = int(s.get("width", 1280))
                    height = int(s.get("height", 720))
                    if "duration" in s and s["duration"]:
                        duration = float(s["duration"])

                if duration <= 0.0:
                    fmt = data.get("format", {})
                    if "duration" in fmt and fmt["duration"]:
                        duration = float(fmt["duration"])
        except Exception:
            pass

        return {
            "id": filename,
            "filename": filename,
            "title": _clean_title(filename),
            "file_size": size,
            "file_size_formatted": _format_size(size),
            "duration": round(duration, 2),
            "duration_formatted": self._format_duration(duration),
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}",
            "video_url": f"/api/video/{filename}"
        }

    def _format_duration(self, seconds: float) -> str:
        s = int(round(seconds))
        m = s // 60
        s = s % 60
        h = m // 60
        m = m % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def ensure_thumbnail(self, full_path: str, filename: str, duration: float) -> str:
        """Generates thumbnail frame if missing."""
        name_no_ext, _ = os.path.splitext(filename)
        img_exts = [".jpg", ".jpeg", ".png", ".webp"]

        # 1. Check in THUMBNAIL_DIR
        for ext in img_exts:
            cand = os.path.join(THUMBNAIL_DIR, f"{name_no_ext}{ext}")
            if os.path.exists(cand) and os.path.getsize(cand) > 0:
                return cand

        # 2. Check in video directory or video directory/thumbnails
        parent_dir = os.path.dirname(full_path)
        for cand_dir in [os.path.join(parent_dir, "thumbnails"), parent_dir]:
            if os.path.isdir(cand_dir):
                for ext in img_exts:
                    cand = os.path.join(cand_dir, f"{name_no_ext}{ext}")
                    if os.path.exists(cand) and os.path.getsize(cand) > 0:
                        return cand

        thumb_path = os.path.join(THUMBNAIL_DIR, f"{name_no_ext}.jpg")

        # If full_path is a .beat file, resolve to extracted video
        actual_video_path = full_path
        if full_path.lower().endswith(".beat"):
            extracted = self.get_extracted_video_path(full_path)
            if extracted and os.path.isfile(extracted):
                actual_video_path = extracted
            else:
                return thumb_path

        # Seek position: 10% in or 10 seconds in
        seek_sec = 10.0
        if duration > 0:
            seek_sec = min(15.0, max(1.0, duration * 0.15))

        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(seek_sec),
                "-i", actual_video_path,
                "-vframes", "1",
                "-vf", "scale=640:-1",
                "-q:v", "3",
                thumb_path
            ]
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
            subprocess.run(cmd, capture_output=True, timeout=15, creationflags=creationflags)
        except Exception:
            pass

        # Fallback if seek failed (try 0.5s)
        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", "0.5",
                    "-i", actual_video_path,
                    "-vframes", "1",
                    "-vf", "scale=640:-1",
                    "-q:v", "3",
                    thumb_path
                ]
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
                subprocess.run(cmd, capture_output=True, timeout=10, creationflags=creationflags)
            except Exception:
                pass

        return thumb_path

    def ensure_preview_clip(self, full_path: str, filename: str, duration: float = 0.0) -> Optional[str]:
        """
        Generates a lightweight 5-second 480p preview clip for fast looping in Web Library.
        This completely eliminates HTTP socket starvation and browser decoder stalls.
        Protected with per-file mutex lock and atomic temp file rename to prevent competing processes.
        """
        name_no_ext, _ = os.path.splitext(filename)
        clip_path = os.path.join(PREVIEWS_DIR, f"{name_no_ext}.mp4")

        # 1. Fast-path check: Reuse existing valid preview clip
        if os.path.isfile(clip_path) and os.path.getsize(clip_path) > 10240:
            return clip_path

        lock = _get_preview_lock(clip_path)
        with lock:
            # Re-check once lock is acquired in case another thread just completed it
            if os.path.isfile(clip_path) and os.path.getsize(clip_path) > 10240:
                return clip_path

            # 2. Resolve source video path
            actual_video_path = full_path
            if full_path.lower().endswith(".beat"):
                extracted = self.get_extracted_video_path(full_path)
                if extracted and os.path.isfile(extracted):
                    actual_video_path = extracted
                else:
                    return None

            if not os.path.isfile(actual_video_path):
                return None

            # 3. Determine start timestamp (15% in or 10s)
            start_sec = 10.0
            if duration > 10.0:
                start_sec = min(30.0, max(2.0, duration * 0.15))

            temp_clip_path = os.path.join(PREVIEWS_DIR, f"{name_no_ext}.tmp_{uuid.uuid4().hex[:8]}.mp4")

            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_sec),
                    "-t", "5",
                    "-i", actual_video_path,
                    "-vf", "scale=480:-2",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "28",
                    "-an",
                    "-movflags", "+faststart",
                    temp_clip_path
                ]
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
                res = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=creationflags)
                if res.returncode == 0 and os.path.isfile(temp_clip_path) and os.path.getsize(temp_clip_path) > 10240:
                    os.replace(temp_clip_path, clip_path)
                    return clip_path
            except Exception:
                pass
            finally:
                if os.path.isfile(temp_clip_path):
                    try:
                        os.remove(temp_clip_path)
                    except Exception:
                        pass

            # Fallback start at 0s
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", "0",
                    "-t", "5",
                    "-i", actual_video_path,
                    "-vf", "scale=480:-2",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "28",
                    "-an",
                    "-movflags", "+faststart",
                    temp_clip_path
                ]
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
                subprocess.run(cmd, capture_output=True, timeout=20, creationflags=creationflags)
                if os.path.isfile(temp_clip_path) and os.path.getsize(temp_clip_path) > 10240:
                    os.replace(temp_clip_path, clip_path)
                    return clip_path
            except Exception:
                pass
            finally:
                if os.path.isfile(temp_clip_path):
                    try:
                        os.remove(temp_clip_path)
                    except Exception:
                        pass

            return None

    def ensure_preview_clip_for_filename(self, filename: str) -> Optional[str]:
        """Finds source file by filename (or base name) and ensures preview clip exists."""
        name_no_ext, _ = os.path.splitext(filename)
        clip_path = os.path.join(PREVIEWS_DIR, f"{name_no_ext}.mp4")
        if os.path.isfile(clip_path) and os.path.getsize(clip_path) > 10240:
            return clip_path

        full_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(full_path):
            cand_beat = os.path.join(self.folder_path, f"{name_no_ext}.beat")
            if os.path.isfile(cand_beat):
                full_path = cand_beat
            else:
                return None

        return self.ensure_preview_clip(full_path, filename, 0.0)

    def _get_active_media_sets(self):
        """Returns set of active video base names and active beat archive filenames."""
        active_bases = set()
        active_beat_files = set()
        if os.path.isdir(self.folder_path):
            for f in os.listdir(self.folder_path):
                ext = os.path.splitext(f)[1].lower()
                if ext in VIDEO_EXTS:
                    active_bases.add(os.path.splitext(f)[0].lower())
                elif ext == ".beat":
                    active_bases.add(os.path.splitext(f)[0].lower())
                    active_beat_files.add(f.lower())
        return active_bases, active_beat_files

    def get_cache_stats(self) -> Dict[str, Any]:
        """Calculates storage sizes and item counts across previews, thumbnails, and extracted videos."""
        # 1. Previews
        previews_count = 0
        previews_size = 0
        if os.path.isdir(PREVIEWS_DIR):
            for fname in os.listdir(PREVIEWS_DIR):
                fpath = os.path.join(PREVIEWS_DIR, fname)
                if os.path.isfile(fpath):
                    previews_count += 1
                    previews_size += os.path.getsize(fpath)

        # 2. Thumbnails
        thumbnails_count = 0
        thumbnails_size = 0
        if os.path.isdir(THUMBNAIL_DIR):
            for fname in os.listdir(THUMBNAIL_DIR):
                fpath = os.path.join(THUMBNAIL_DIR, fname)
                if os.path.isfile(fpath):
                    thumbnails_count += 1
                    thumbnails_size += os.path.getsize(fpath)

        # 3. Extracted Videos
        extracted_count = 0
        extracted_size = 0
        if os.path.isdir(EXTRACTED_DIR):
            for root, _, files in os.walk(EXTRACTED_DIR):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if os.path.isfile(fpath):
                        extracted_count += 1
                        extracted_size += os.path.getsize(fpath)

        # 4. Determine unused/orphaned stats
        active_bases, active_beat_files = self._get_active_media_sets()
        unused_previews = 0
        unused_size = 0
        if os.path.isdir(PREVIEWS_DIR):
            for fname in os.listdir(PREVIEWS_DIR):
                base = os.path.splitext(fname)[0].lower()
                if base not in active_bases:
                    unused_previews += 1
                    unused_size += os.path.getsize(os.path.join(PREVIEWS_DIR, fname))

        unused_thumbnails = 0
        if os.path.isdir(THUMBNAIL_DIR):
            for fname in os.listdir(THUMBNAIL_DIR):
                base = os.path.splitext(fname)[0].lower()
                if base not in active_bases:
                    unused_thumbnails += 1
                    unused_size += os.path.getsize(os.path.join(THUMBNAIL_DIR, fname))

        unused_extracted = 0
        if os.path.isdir(EXTRACTED_DIR):
            for entry in os.listdir(EXTRACTED_DIR):
                if entry.lower() not in active_beat_files:
                    entry_path = os.path.join(EXTRACTED_DIR, entry)
                    if os.path.isdir(entry_path):
                        unused_extracted += 1
                        for root, _, files in os.walk(entry_path):
                            for fname in files:
                                unused_size += os.path.getsize(os.path.join(root, fname))

        total_size = previews_size + thumbnails_size + extracted_size
        unused_count = unused_previews + unused_thumbnails + unused_extracted

        return {
            "previews_count": previews_count,
            "previews_size": previews_size,
            "previews_size_formatted": _format_size(previews_size),
            "thumbnails_count": thumbnails_count,
            "thumbnails_size": thumbnails_size,
            "thumbnails_size_formatted": _format_size(thumbnails_size),
            "extracted_count": extracted_count,
            "extracted_size": extracted_size,
            "extracted_size_formatted": _format_size(extracted_size),
            "total_size": total_size,
            "total_size_formatted": _format_size(total_size),
            "unused_count": unused_count,
            "unused_size": unused_size,
            "unused_size_formatted": _format_size(unused_size)
        }

    def clean_unused_cache(self) -> Dict[str, Any]:
        """
        Scans cache directories and removes previews, thumbnails, extracted videos,
        and metadata entries that no longer correspond to any video or .beat file on disk.
        """
        active_bases, active_beat_files = self._get_active_media_sets()
        deleted_previews = 0
        deleted_thumbnails = 0
        deleted_extracted = 0
        freed_bytes = 0

        # 1. Clean orphaned preview clips
        if os.path.isdir(PREVIEWS_DIR):
            for fname in os.listdir(PREVIEWS_DIR):
                base = os.path.splitext(fname)[0].lower()
                if base not in active_bases:
                    fpath = os.path.join(PREVIEWS_DIR, fname)
                    try:
                        freed_bytes += os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_previews += 1
                    except Exception:
                        pass

        # 2. Clean orphaned thumbnails
        if os.path.isdir(THUMBNAIL_DIR):
            for fname in os.listdir(THUMBNAIL_DIR):
                base = os.path.splitext(fname)[0].lower()
                if base not in active_bases:
                    fpath = os.path.join(THUMBNAIL_DIR, fname)
                    try:
                        freed_bytes += os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_thumbnails += 1
                    except Exception:
                        pass

        # 3. Clean orphaned extracted video folders
        if os.path.isdir(EXTRACTED_DIR):
            for entry in os.listdir(EXTRACTED_DIR):
                if entry.lower() not in active_beat_files:
                    entry_path = os.path.join(EXTRACTED_DIR, entry)
                    if os.path.isdir(entry_path):
                        try:
                            for root, _, files in os.walk(entry_path):
                                for fname in files:
                                    freed_bytes += os.path.getsize(os.path.join(root, fname))
                            shutil.rmtree(entry_path, ignore_errors=True)
                            deleted_extracted += 1
                        except Exception:
                            pass

        # 4. Clean stale metadata cache keys
        cleaned_meta_keys = 0
        valid_files = set()
        if os.path.isdir(self.folder_path):
            valid_files = set(os.listdir(self.folder_path))

        keys_to_remove = []
        for key in list(self.metadata_cache.keys()):
            parts = key.rsplit("_", 2)
            fname = parts[0] if parts else key
            if fname not in valid_files:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.metadata_cache.pop(key, None)
            cleaned_meta_keys += 1

        if cleaned_meta_keys > 0:
            self._save_metadata_cache()

        return {
            "success": True,
            "deleted_previews": deleted_previews,
            "deleted_thumbnails": deleted_thumbnails,
            "deleted_extracted": deleted_extracted,
            "deleted_metadata_entries": cleaned_meta_keys,
            "freed_bytes": freed_bytes,
            "freed_bytes_formatted": _format_size(freed_bytes)
        }

    def clear_all_previews(self) -> Dict[str, Any]:
        """Purges all generated preview clips so they can be regenerated fresh on demand."""
        deleted_count = 0
        freed_bytes = 0
        if os.path.isdir(PREVIEWS_DIR):
            for fname in os.listdir(PREVIEWS_DIR):
                fpath = os.path.join(PREVIEWS_DIR, fname)
                try:
                    freed_bytes += os.path.getsize(fpath)
                    os.remove(fpath)
                    deleted_count += 1
                except Exception:
                    pass

        return {
            "success": True,
            "deleted_count": deleted_count,
            "freed_bytes": freed_bytes,
            "freed_bytes_formatted": _format_size(freed_bytes)
        }
