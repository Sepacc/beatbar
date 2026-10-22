"""
web/skin_manager.py - Beatbar Skin Manager for Web Viewer.

Scans C:\\HDD\\code\\gemini antigrav\\beatmake\\web\\skins for .beat format skins,
extracts metadata (palette, components, layout), and serves SVG/image assets.
"""

import os
import json
import zipfile
from typing import List, Dict, Any, Optional, Tuple

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(WEB_DIR)
ASSETS_SKINS_DIR = os.path.join(ROOT_DIR, "assets", "skins")
LOCAL_SKINS_DIR = os.path.join(WEB_DIR, "skins")
SKIN_DIRS = [ASSETS_SKINS_DIR, LOCAL_SKINS_DIR]
SKINS_DIR = ASSETS_SKINS_DIR if os.path.isdir(ASSETS_SKINS_DIR) else LOCAL_SKINS_DIR

# Default procedural palette if none provided
DEFAULT_PALETTE = {
    "primary": "#be2edd",
    "accent": "#e056fd",
    "target": "#9b51e0",
    "glow": "#f368e0",
    "panel_border": "#d434ef",
    "timeline_fill": "#ffffff"
}


def _find_skin_file(skin_id: str) -> Optional[str]:
    """
    Locates a .beat skin file by ID across project skin directories,
    checking assets/skins first then web/skins.
    """
    skin_file = f"{skin_id}.beat" if not skin_id.endswith(".beat") else skin_id
    for s_dir in SKIN_DIRS:
        if not os.path.isdir(s_dir):
            continue
        direct = os.path.join(s_dir, skin_file)
        if os.path.isfile(direct):
            return direct
        for f in os.listdir(s_dir):
            if f.lower() == skin_file.lower():
                cand = os.path.join(s_dir, f)
                if os.path.isfile(cand):
                    return cand
    return None


def list_skins() -> List[Dict[str, Any]]:
    """
    Scans project skin directories (assets/skins and web/skins) for *.beat skin bundles
    and returns detailed metadata for each, prioritizing assets/skins without duplicates.
    """
    for s_dir in SKIN_DIRS:
        os.makedirs(s_dir, exist_ok=True)
    skins = []
    seen_ids = set()

    for s_dir in SKIN_DIRS:
        if not os.path.isdir(s_dir):
            continue
        for f in sorted(os.listdir(s_dir)):
            if not f.lower().endswith(".beat"):
                continue

            skin_id = os.path.splitext(f)[0]
            if skin_id in seen_ids:
                continue

            full_path = os.path.join(s_dir, f)
            if not os.path.isfile(full_path):
                continue

            skin_info = _read_skin_from_zip(full_path, f)
            if skin_info:
                seen_ids.add(skin_id)
                skins.append(skin_info)

    return skins


def get_skin(skin_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns full skin details with asset URLs for the given skin ID.
    """
    full_path = _find_skin_file(skin_id)
    if not full_path:
        return None

    return _read_skin_from_zip(full_path, os.path.basename(full_path))


def get_skin_asset(skin_id: str, asset_name: str) -> Optional[Tuple[bytes, str]]:
    """
    Extracts raw bytes and mimetype of an SVG/image component from a skin .beat archive.
    """
    full_path = _find_skin_file(skin_id)
    if not full_path:
        return None

    return _extract_asset_from_zip(full_path, asset_name)


def get_video_pack_skin(video_path: str) -> Optional[Dict[str, Any]]:
    """
    If a video .beat file contains an embedded skin, returns its skin configuration.
    """
    if not video_path or not os.path.isfile(video_path) or not video_path.lower().endswith(".beat"):
        return None

    skin_info = _read_skin_from_zip(video_path, os.path.basename(video_path), is_pack_skin=True)
    return skin_info


def get_video_pack_skin_asset(video_path: str, asset_name: str) -> Optional[Tuple[bytes, str]]:
    """
    Extracts raw bytes and mimetype of an SVG/image component from a video's .beat archive.
    """
    if not video_path or not os.path.isfile(video_path) or not video_path.lower().endswith(".beat"):
        return None

    return _extract_asset_from_zip(video_path, asset_name)


def _read_skin_from_zip(zip_path: str, filename: str, is_pack_skin: bool = False) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()

            skin_cfg = {}
            if "skin.json" in namelist:
                try:
                    skin_cfg = json.loads(zf.read("skin.json").decode("utf-8", errors="replace"))
                except Exception:
                    skin_cfg = {}
            elif "skins/skin.json" in namelist:
                try:
                    skin_cfg = json.loads(zf.read("skins/skin.json").decode("utf-8", errors="replace"))
                except Exception:
                    skin_cfg = {}

            manifest = {}
            if "manifest.json" in namelist:
                try:
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8", errors="replace"))
                except Exception:
                    manifest = {}

            # If it's a video pack, verify it actually contains skin components
            comps = skin_cfg.get("components", {})
            has_svg = any(n.lower().endswith(".svg") for n in namelist)
            if is_pack_skin and not skin_cfg and not has_svg:
                return None

            skin_id = "pack_skin" if is_pack_skin else os.path.splitext(filename)[0]
            title = skin_cfg.get("name") or manifest.get("title") or skin_id.replace("_", " ").title()

            # Ensure palette defaults
            palette = {**DEFAULT_PALETTE, **(skin_cfg.get("palette", {}))}

            # Build component asset URLs with cache-busting timestamp
            asset_prefix = f"/api/video_skin/{filename}/asset" if is_pack_skin else f"/api/skin/{skin_id}/asset"
            mtime = int(os.path.getmtime(zip_path)) if os.path.isfile(zip_path) else 0

            comp_urls = {}
            standard_roles = ["panel", "wing_left", "wing_right", "target", "target_hit", "beat"]
            for role in standard_roles:
                # Check if component is in comps or exists in zip
                raw_file = comps.get(role)
                if raw_file or _find_zip_entry(zf, role) is not None:
                    comp_urls[role] = f"{asset_prefix}/{role}?v={mtime}"

            return {
                "id": skin_id,
                "name": title,
                "filename": filename,
                "description": skin_cfg.get("description", ""),
                "author": skin_cfg.get("author", "User"),
                "is_pack_skin": is_pack_skin,
                "palette": palette,
                "components": comp_urls,
                "layout": skin_cfg.get("layout", {}),
                "trigger_hit": skin_cfg.get("trigger_hit", {})
            }
    except Exception as e:
        print(f"Error reading skin from {zip_path}: {e}")
        return None


def _find_zip_entry(zf: zipfile.ZipFile, query_name: str) -> Optional[str]:
    names = zf.namelist()

    # 1. Exact match
    if query_name in names:
        return query_name

    # 2. In skins/ folder
    if f"skins/{query_name}" in names:
        return f"skins/{query_name}"

    # 3. Basename match
    query_lower = query_name.lower()
    for n in names:
        if os.path.basename(n).lower() == query_lower:
            return n

    # 4. Check skin.json component mapping if query_name is a role ("panel", "beat", "target", etc.)
    skin_cfg = {}
    if "skin.json" in names:
        try:
            skin_cfg = json.loads(zf.read("skin.json").decode("utf-8", errors="replace"))
        except Exception:
            skin_cfg = {}
    elif "skins/skin.json" in names:
        try:
            skin_cfg = json.loads(zf.read("skins/skin.json").decode("utf-8", errors="replace"))
        except Exception:
            skin_cfg = {}

    role_target = skin_cfg.get("components", {}).get(query_name)
    if role_target:
        if role_target in names:
            return role_target
        if f"skins/{role_target}" in names:
            return f"skins/{role_target}"
        for n in names:
            if os.path.basename(n).lower() == os.path.basename(role_target).lower():
                return n

    # 5. Fuzzy role fallback search among SVGs
    for n in names:
        ext = os.path.splitext(n)[1].lower()
        if ext not in (".svg", ".png", ".jpg", ".webp"):
            continue
        base = os.path.splitext(os.path.basename(n))[0].lower()
        if query_name == "panel" and "panel" in base:
            return n
        elif query_name == "wing_left" and "wing" in base and ("left" in base or "_l" in base or "sigil_left" in base):
            return n
        elif query_name == "wing_right" and "wing" in base and ("right" in base or "_r" in base or "sigil_right" in base):
            return n
        elif query_name == "target" and "target" in base and "hit" not in base:
            return n
        elif query_name == "target_hit" and "target" in base and "hit" in base:
            return n
        elif query_name == "beat" and ("beat" in base or "crest" in base or "diamond" in base or "orb" in base):
            return n

    return None


def _extract_asset_from_zip(zip_path: str, asset_name: str) -> Optional[Tuple[bytes, str]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            entry = _find_zip_entry(zf, asset_name)
            if not entry:
                return None

            ext = os.path.splitext(entry)[1].lower()
            mimes = {
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp"
            }
            mimetype = mimes.get(ext, "application/octet-stream")
            data = zf.read(entry)
            return data, mimetype
    except Exception as e:
        print(f"Error extracting asset {asset_name} from {zip_path}: {e}")
        return None
