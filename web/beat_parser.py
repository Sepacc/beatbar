"""
web/beat_parser.py - Parser for .beat archives and JSON beatmaps for Web Viewer.

Supports:
- .beat ZIP archive bundles (manifest.json, beatmap.json, video_name.txt, skins/)
- V2 Beatmap JSON files (with settings, zones, beats)
- V1 / Legacy Beatmap JSON files
- Automatic burst detection (5+ rapid beats) and zone tagging
- Intelligent auto-matching between video files and beat files
"""

import os
import glob
import json
import zipfile
from typing import Optional, Dict, List, Any, Tuple


VIDEO_EXTS = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.m4v']


def parse_beat_file(file_path: str) -> Dict[str, Any]:
    """
    Parses a .beat archive or JSON beatmap file into a standardized dictionary:
    {
        "title": str,
        "video_name": str,
        "format": "beat" | "json",
        "format_version": str,
        "settings": dict,
        "zones": list[dict],
        "beats": list[dict],
        "total_beats": int,
        "total_zones": int,
        "source_path": str
    }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Beatmap file not found: {file_path}")

    file_path = os.path.abspath(file_path)
    is_beat_zip = file_path.lower().endswith(".beat") or (zipfile.is_zipfile(file_path) and not file_path.lower().endswith(".json"))

    if is_beat_zip:
        return _parse_beat_archive(file_path)
    else:
        return _parse_beat_json(file_path)


def _parse_beat_archive(file_path: str) -> Dict[str, Any]:
    with zipfile.ZipFile(file_path, "r") as zf:
        namelist = zf.namelist()
        manifest = {}
        if "manifest.json" in namelist:
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8", errors="replace"))
            except Exception:
                manifest = {}

        beatmap = {}
        if "beatmap.json" in namelist:
            try:
                beatmap = json.loads(zf.read("beatmap.json").decode("utf-8", errors="replace"))
            except Exception as e:
                raise ValueError(f"Corrupt beatmap.json in .beat archive: {e}")
        else:
            raise ValueError("Missing beatmap.json inside .beat archive")

        video_name = ""
        if "video_name.txt" in namelist:
            try:
                video_name = zf.read("video_name.txt").decode("utf-8", errors="replace").strip()
            except Exception:
                video_name = ""
        if not video_name and manifest:
            video_name = manifest.get("video_name", "")
        if not video_name and beatmap:
            video_name = beatmap.get("video_file", beatmap.get("audio_file", ""))

        title = manifest.get("title", "") or beatmap.get("title", "") or os.path.splitext(os.path.basename(file_path))[0]
        settings = beatmap.get("settings", {}) or {}
        zones = _normalize_zones(beatmap.get("zones", []))
        raw_beats = beatmap.get("beats", [])
        beats = _normalize_beats(raw_beats)
        beats = tag_bursts_and_zones(beats, zones)

        level = beatmap.get("level", 1)
        difficulty = beatmap.get("difficulty", None)
        diff_stats = beatmap.get("difficulty_stats", None)
        if not diff_stats or not difficulty:
            try:
                from beat_generator import calculate_beat_difficulty
                diff_stats = calculate_beat_difficulty(beats)
                if not difficulty:
                    difficulty = diff_stats.get("difficulty", "Normal")
                if "level" in diff_stats and "level" not in beatmap:
                    level = diff_stats.get("level", 1)
            except Exception:
                diff_stats = {}
                if not difficulty:
                    difficulty = "Normal"

        levels = beatmap.get("levels", [])
        level_mode = beatmap.get("level_mode", "named_levels" if isinstance(level, str) and "-" in level else "ramp_within_level")
        max_t = beats[-1]["time"] + 2.0 if beats else 60.0
        try:
            from beat_generator import infer_or_standardize_levels
            levels = infer_or_standardize_levels(max_t, title=title or video_name, level=level, levels=levels)
        except Exception:
            if not levels:
                levels = [{"name": str(level) if "-" in str(level) else f"Level {level}", "start_time": 0.0, "end_time": max_t, "difficulty": difficulty}]

        return {
            "title": title,
            "video_name": video_name,
            "format": "beat",
            "format_version": manifest.get("format_version", "1.0"),
            "settings": _normalize_settings(settings),
            "zones": zones,
            "beats": beats,
            "total_beats": len(beats),
            "total_zones": len(zones),
            "level": level,
            "levels": levels,
            "level_mode": level_mode,
            "difficulty": difficulty,
            "difficulty_stats": diff_stats,
            "source_path": file_path
        }


def _parse_beat_json(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    if isinstance(data, list):
        # Raw list of beats
        beats = _normalize_beats(data)
        zones = []
        settings = {}
        title = os.path.splitext(os.path.basename(file_path))[0]
        video_name = ""
        level = 1
        levels = []
        level_mode = "ramp_within_level"
        difficulty = "Normal"
        diff_stats = None
    elif isinstance(data, dict):
        raw_beats = data.get("beats", [])
        beats = _normalize_beats(raw_beats)
        zones = _normalize_zones(data.get("zones", []))
        settings = data.get("settings", {}) or {}
        title = data.get("title", "") or os.path.splitext(os.path.basename(file_path))[0]
        video_name = data.get("video_file", data.get("audio_file", ""))
        level = data.get("level", 1)
        levels = data.get("levels", [])
        level_mode = data.get("level_mode", "named_levels" if isinstance(level, str) and "-" in level else "ramp_within_level")
        difficulty = data.get("difficulty", None)
        diff_stats = data.get("difficulty_stats", None)
    else:
        raise ValueError("Unrecognized JSON format for beatmap")

    beats = tag_bursts_and_zones(beats, zones)

    if not diff_stats or not difficulty:
        try:
            from beat_generator import calculate_beat_difficulty
            diff_stats = calculate_beat_difficulty(beats)
            if not difficulty:
                difficulty = diff_stats.get("difficulty", "Normal")
            if "level" in diff_stats and (not isinstance(data, dict) or "level" not in data):
                level = diff_stats.get("level", 1)
        except Exception:
            diff_stats = {}
            if not difficulty:
                difficulty = "Normal"

    max_t = beats[-1]["time"] + 2.0 if beats else 60.0
    try:
        from beat_generator import infer_or_standardize_levels
        levels = infer_or_standardize_levels(max_t, title=title or video_name, level=level, levels=levels)
    except Exception:
        if not levels:
            levels = [{"name": str(level) if "-" in str(level) else f"Level {level}", "start_time": 0.0, "end_time": max_t, "difficulty": difficulty}]

    return {
        "title": title,
        "video_name": video_name,
        "format": "json",
        "format_version": data.get("version", "2.0") if isinstance(data, dict) else "1.0",
        "settings": _normalize_settings(settings),
        "zones": zones,
        "beats": beats,
        "total_beats": len(beats),
        "total_zones": len(zones),
        "level": level,
        "levels": levels,
        "level_mode": level_mode,
        "difficulty": difficulty,
        "difficulty_stats": diff_stats,
        "source_path": file_path
    }


def _normalize_beats(raw_beats: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for item in raw_beats:
        if isinstance(item, (int, float)):
            normalized.append({
                "time": round(float(item), 4),
                "lane": 4,
                "type": "beat"
            })
        elif isinstance(item, dict):
            t = float(item.get("time", item.get("t", 0.0)))
            lane = int(item.get("lane", item.get("l", 4)))
            btype = str(item.get("type", "beat"))
            normalized.append({
                "time": round(t, 4),
                "lane": lane,
                "type": btype
            })
    normalized.sort(key=lambda b: b["time"])
    return normalized


def _normalize_zones(raw_zones: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for idx, z in enumerate(raw_zones):
        if not isinstance(z, dict):
            continue
        zid = str(z.get("id", f"zone_{idx}"))
        name = str(z.get("name", z.get("zone_type", f"Zone {idx + 1}")))
        st = float(z.get("start_time", z.get("start", 0.0)))
        et = float(z.get("end_time", z.get("end", 0.0)))
        ztype = str(z.get("type", z.get("zone_type", "normal"))).lower()
        color = z.get("color", None)
        normalized.append({
            "id": zid,
            "name": name,
            "start_time": round(st, 3),
            "end_time": round(et, 3),
            "type": ztype,
            "color": color
        })
    normalized.sort(key=lambda z: z["start_time"])
    return normalized


def _normalize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    default_settings = {
        "bpm": 120.0,
        "lead_time": 1.5,
        "speed": 1.0,
        "screen_shake": True,
        "screen_shake_strength": 0.045,
        "timeline_fill_mode": "left_to_right",
        "scroll_direction": "rtl",
        "intense_zones_direction": "ltr",
        "hit_animation": "shockwave"
    }
    merged = {**default_settings, **settings}
    return merged


def tag_bursts_and_zones(beats: List[Dict[str, Any]], zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tags beats with:
    - is_burst: True if in a rapid group of 5+ beats (gap <= 0.36s)
    - in_intense_zone: True if within 'climax', 'edging', or 'intense' zone
    - in_speedy_zone: True if within 'speeding_up', 'speedy', or 'fast' zone
    - Ensures no beats fall inside credits zones
    """
    # 0. Filter out beats falling in skippable credits zones
    credits_zones = [z for z in zones if z.get("type") == "credits"]
    if credits_zones:
        beats = [b for b in beats if not any(cz["start_time"] <= b["time"] <= cz["end_time"] for cz in credits_zones)]

    n = len(beats)
    for b in beats:
        b["is_burst"] = False
        b["in_intense_zone"] = False
        b["in_speedy_zone"] = False

    # 1. Burst detection
    i = 0
    while i < n:
        run_end = i
        while run_end + 1 < n and (beats[run_end + 1]["time"] - beats[run_end]["time"]) <= 0.36:
            run_end += 1
        run_len = run_end - i + 1
        if run_len >= 5:
            for k in range(i, run_end + 1):
                beats[k]["is_burst"] = True
        i = run_end + 1

    # 2. Zone tagging
    for b in beats:
        bt = b["time"]
        for z in zones:
            st = z["start_time"]
            et = z["end_time"]
            if st <= bt <= et:
                ztype = z["type"]
                if ztype in ["climax", "edging", "intense"]:
                    b["in_intense_zone"] = True
                elif ztype in ["speeding_up", "speedy", "fast"]:
                    b["in_speedy_zone"] = True

    return beats


def find_matching_beat_file(video_path: str, search_dirs: Optional[List[str]] = None) -> Optional[str]:
    """
    Finds matching .beat or .json beatmap for a given video path.
    Searches:
    1. Exact base matches (.beat, .json, _V2.json, _beats.json, etc.)
    2. Fuzzy base matches (stripping resolution tags _720p, _1080p, etc.)
    3. Checks search_dirs (defaulting to video directory, parent dirs, '1/', etc.)
    """
    if not video_path:
        return None

    if video_path.lower().endswith(".beat") and os.path.isfile(video_path):
        return os.path.abspath(video_path)

    video_folder = os.path.dirname(os.path.abspath(video_path))
    video_file = os.path.basename(video_path)
    base = os.path.splitext(video_file)[0]

    dirs = [video_folder]
    if search_dirs:
        for d in search_dirs:
            if d and os.path.isdir(d) and d not in dirs:
                dirs.append(os.path.abspath(d))

    suffixes = [
        ".beat",
        ".json",
        "_V2.json",
        "_v2.json",
        "_beats.json",
        "_video_beats.json",
        "_generated.json",
        "_v2_new.json",
    ]

    # Exact candidates first
    for d in dirs:
        for s in suffixes:
            cand = os.path.join(d, f"{base}{s}")
            if os.path.isfile(cand):
                return cand

    # Cleaned candidates (stripping resolutions)
    clean_base = base.lower()
    for tag in ["_720p", "-720p", "_1080p", "-1080p", "_480p", "-480p", "_4k", "-4k"]:
        clean_base = clean_base.replace(tag, "")

    for d in dirs:
        for root_f in os.listdir(d):
            if root_f.lower().endswith((".beat", ".json")):
                f_base = os.path.splitext(root_f)[0].lower()
                clean_f_base = f_base
                for tag in ["_720p", "-720p", "_1080p", "-1080p", "_480p", "-480p", "_4k", "-4k", "_v2", "_beats", "_generated"]:
                    clean_f_base = clean_f_base.replace(tag, "")

                if clean_base and (clean_base == clean_f_base or clean_base in f_base or f_base in clean_base):
                    full = os.path.join(d, root_f)
                    if os.path.isfile(full):
                        return full

    return None
