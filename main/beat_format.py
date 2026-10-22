"""
beat_format.py - Universal .beat Archive Format Handler

The .beat format is a self-contained ZIP archive bundle containing:
  manifest.json        - Metadata: title, video_name, format_version, created_at, has_embedded_video
  beatmap.json         - The full beatmap data (beats, zones, settings, version, audio_file)
  video_name.txt       - Original video filename reference (used when video is external)
  skins/               - SVG and image skin assets (crest_beat.svg, diamond_beat.svg, etc.)
  video.*              - (Optional) embedded full video file (video.mp4, video.mkv, etc.)

Maintained with 100% cross-platform compatibility between Desktop (PyQt6) and Mobile (Android Kivy).
"""

import os
import sys
import json
import zipfile
import shutil
import tempfile
import time
from typing import Optional, Dict, List, Any, Union, Tuple, Callable


BEAT_FORMAT_VERSION = "1.0"
MANIFEST_NAME = "manifest.json"
BEATMAP_NAME = "beatmap.json"
VIDEO_NAME_FILE = "video_name.txt"
EMBEDDED_VIDEO_NAME = "video"
SKINS_PREFIX = "skins/"
SKIN_CONFIG_NAME = "skin.json"

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v"]

# 2 GB limit for embedded video within single zip
MAX_EMBED_VIDEO_BYTES = 2 * 1024 * 1024 * 1024


class BeatFormatError(Exception):
    """Raised when a .beat archive is corrupt, invalid, or missing required entries."""
    pass


class BeatFileReader:
    """
    Context manager for reading and extracting an opened .beat archive.
    Provides cached access to manifest, beatmap data, skin assets, and embedded/referenced video.
    """

    def __init__(self, path: str):
        self._path = os.path.abspath(path)
        self._zf: Optional[zipfile.ZipFile] = None
        self._manifest: Optional[Dict] = None
        self._beatmap: Optional[Dict] = None
        self._temp_dir: Optional[str] = None

    def _ensure_open(self):
        if self._zf is None:
            if not os.path.exists(self._path):
                raise FileNotFoundError(f".beat file not found: {self._path}")
            self._zf = zipfile.ZipFile(self._path, "r")
            self._load_manifest()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._zf:
            try:
                self._zf.close()
            except Exception:
                pass
            self._zf = None
        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _load_manifest(self):
        if MANIFEST_NAME not in self._zf.namelist():
            raise BeatFormatError(f"Missing {MANIFEST_NAME} in .beat archive: {self._path}")
        with self._zf.open(MANIFEST_NAME) as f:
            self._manifest = json.load(f)

    # --------------------------------------------------------------------------
    # Metadata Accessors
    # --------------------------------------------------------------------------

    @property
    def manifest(self) -> Dict:
        """Property returning the parsed manifest dictionary."""
        return self.get_manifest()

    def get_manifest(self) -> Dict:
        """Returns the parsed manifest dictionary."""
        self._ensure_open()
        return self._manifest or {}

    def get_title(self) -> str:
        """Returns human-readable pack title."""
        self._ensure_open()
        if self._manifest and "title" in self._manifest and self._manifest["title"]:
            return self._manifest["title"]
        return os.path.splitext(os.path.basename(self._path))[0]

    def get_author(self) -> str:
        """Returns author name from manifest, beatmap, or skin.json, defaulting to 'User'."""
        self._ensure_open()
        if self._manifest and self._manifest.get("author"):
            return self._manifest["author"]
        try:
            bm = self.get_beatmap()
            if bm and bm.get("author"):
                return bm["author"]
        except Exception:
            pass
        cfg = self.get_skin_config()
        if cfg and cfg.get("author"):
            return cfg["author"]
        return "User"

    def get_video_name(self) -> str:
        """
        Returns original referenced video filename (basename without folder).
        """
        self._ensure_open()
        if VIDEO_NAME_FILE in self._zf.namelist():
            try:
                with self._zf.open(VIDEO_NAME_FILE) as f:
                    name = f.read().decode("utf-8", errors="replace").strip()
                    if name:
                        return name
            except Exception:
                pass
        if self._manifest:
            return self._manifest.get("video_name", "")
        return ""

    def get_beatmap(self) -> Dict:
        """
        Parses and returns the beatmap dictionary.
        Keys: beats (list), zones (list), settings (dict), audio_file (str), version (str)
        """
        if self._beatmap is not None:
            return self._beatmap
        self._ensure_open()
        if BEATMAP_NAME not in self._zf.namelist():
            raise BeatFormatError(f"Missing {BEATMAP_NAME} in .beat archive: {self._path}")
        with self._zf.open(BEATMAP_NAME) as f:
            self._beatmap = json.load(f)
        return self._beatmap

    # --------------------------------------------------------------------------
    # Video Handling (Embedded vs Referenced)
    # --------------------------------------------------------------------------

    def has_embedded_video(self) -> bool:
        """True if archive contains an embedded video binary."""
        return self.get_embedded_video_entry() is not None

    def get_embedded_video_entry(self) -> Optional[str]:
        """Returns zip entry name of embedded video (e.g. 'video.mp4') or None."""
        self._ensure_open()
        if not self._zf:
            return None

        # 1. Explicit entry from manifest
        if self._manifest:
            m_entry = self._manifest.get("embedded_video_entry")
            if m_entry and m_entry in self._zf.namelist():
                return m_entry
            if self._manifest.get("has_embedded_video", False):
                for name in self._zf.namelist():
                    base, ext = os.path.splitext(os.path.basename(name))
                    if base.lower() == EMBEDDED_VIDEO_NAME and ext.lower() in VIDEO_EXTENSIONS:
                        return name

        # 2. Standard 'video.*' entry
        for name in self._zf.namelist():
            base, ext = os.path.splitext(os.path.basename(name))
            if base.lower() == EMBEDDED_VIDEO_NAME and ext.lower() in VIDEO_EXTENSIONS:
                return name

        # 3. Match against referenced video_name
        vid_name = self.get_video_name()
        if vid_name:
            vid_base = os.path.splitext(os.path.basename(vid_name))[0].lower()
            for name in self._zf.namelist():
                entry_base, ext = os.path.splitext(os.path.basename(name))
                if ext.lower() in VIDEO_EXTENSIONS:
                    if entry_base.lower() == vid_base or os.path.basename(name).lower() == os.path.basename(vid_name).lower():
                        return name

        # 4. Any video entry in the root or subfolders
        for name in self._zf.namelist():
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                return name

        return None

    def get_embedded_video_size_bytes(self) -> int:
        """Returns uncompressed size of embedded video in bytes (0 if none)."""
        entry = self.get_embedded_video_entry()
        if not entry:
            return 0
        return self._zf.getinfo(entry).file_size

    def extract_video(self, dest_dir: Optional[str] = None) -> Optional[str]:
        """
        Extracts embedded video to dest_dir (or a dedicated persistent cache directory).
        Returns the absolute path to the extracted video file, or None if no embedded video.
        """
        entry = self.get_embedded_video_entry()
        if not entry:
            return None

        if dest_dir is None:
            # Persistent cache in temp directory tagged with file modification time
            mtime = int(os.path.getmtime(self._path))
            pack_name = os.path.splitext(os.path.basename(self._path))[0]
            dest_dir = os.path.join(tempfile.gettempdir(), "beatmake_cache", f"{pack_name}_{mtime}")

        os.makedirs(dest_dir, exist_ok=True)

        # Name the extracted video cleanly using original video name or entry basename
        clean_ext = os.path.splitext(entry)[1].lower()
        vid_name = self.get_video_name() or (os.path.splitext(os.path.basename(self._path))[0] + clean_ext)
        dest_filename = os.path.basename(vid_name)
        if not any(dest_filename.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
            dest_filename = os.path.splitext(dest_filename)[0] + clean_ext

        dest_path = os.path.join(dest_dir, dest_filename)

        # Extract if not already cached and identical size
        target_size = self._zf.getinfo(entry).file_size
        if not os.path.exists(dest_path) or os.path.getsize(dest_path) != target_size:
            with self._zf.open(entry) as src, open(dest_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

        return os.path.abspath(dest_path)

    def resolve_video(self, search_dirs: Optional[List[str]] = None, dest_dir: Optional[str] = None) -> Tuple[Optional[str], bool]:
        """
        Resolves video path:
        1. If video is embedded, extracts it and returns (path, True).
        2. If video is referenced, searches search_dirs (defaulting to .beat directory and current dir)
           and returns (path, False) if found, or (None, False).
        """
        if self.has_embedded_video():
            ext_path = self.extract_video(dest_dir)
            if ext_path and os.path.exists(ext_path):
                return ext_path, True

        # External video lookup
        vid_name = self.get_video_name()
        if not vid_name:
            return None, False

        dirs = []
        if search_dirs:
            dirs.extend([d for d in search_dirs if d and os.path.isdir(d)])
        beat_dir = os.path.dirname(self._path)
        if beat_dir and os.path.isdir(beat_dir) and beat_dir not in dirs:
            dirs.append(beat_dir)
        cwd = os.getcwd()
        if cwd not in dirs:
            dirs.append(cwd)

        # Search workspace and common video directories
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for sub in ["", "videos", "1"]:
            cand_d = os.path.abspath(os.path.join(base_dir, sub))
            if os.path.isdir(cand_d) and cand_d not in dirs:
                dirs.append(cand_d)

        # Common user directories
        user_home = os.path.expanduser("~")
        for sub in ["Downloads", "Videos", "Desktop"]:
            cand_d = os.path.join(user_home, sub)
            if os.path.isdir(cand_d) and cand_d not in dirs:
                dirs.append(cand_d)

        # Exact match check
        for d in dirs:
            cand = os.path.join(d, vid_name)
            if os.path.exists(cand):
                return os.path.abspath(cand), False

        # Fuzzy basename check (e.g. without extension or with resolution variants)
        base_no_ext = os.path.splitext(vid_name)[0].lower()
        clean_base = base_no_ext.replace("_720p", "").replace("_1080p", "").replace("_480p", "").replace("-720p", "").replace("-1080p", "").replace("-480p", "")
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                f_ext = os.path.splitext(f)[1].lower()
                if f_ext in VIDEO_EXTENSIONS:
                    f_base = os.path.splitext(f)[0].lower()
                    if f_base == base_no_ext or (clean_base and clean_base in f_base):
                        return os.path.abspath(os.path.join(d, f)), False

        return None, False

    # --------------------------------------------------------------------------
    # Skin Assets Handling
    # --------------------------------------------------------------------------

    def list_skins(self) -> List[str]:
        """Returns filenames of all skin assets bundled under skins/."""
        self._ensure_open()
        result = []
        for name in self._zf.namelist():
            if name.startswith(SKINS_PREFIX) and not name.endswith("/"):
                result.append(name[len(SKINS_PREFIX):])
        return result

    def get_skin_bytes(self, skin_filename: str) -> Optional[bytes]:
        """Returns raw bytes of a bundled skin file, or None if not found."""
        self._ensure_open()
        entry = SKINS_PREFIX + skin_filename
        if entry in self._zf.namelist():
            with self._zf.open(entry) as f:
                return f.read()
        if skin_filename in self._zf.namelist():
            with self._zf.open(skin_filename) as f:
                return f.read()
        return None

    def get_skin_config(self) -> Optional[Dict]:
        """
        Retrieves skin.json from the .beat archive.
        Checks 'skin.json' and 'skins/skin.json'.
        If missing, infers component mapping from the files present in skins/.
        """
        self._ensure_open()
        for entry in [SKIN_CONFIG_NAME, SKINS_PREFIX + SKIN_CONFIG_NAME]:
            if entry in self._zf.namelist():
                try:
                    with self._zf.open(entry) as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    print(f"Error parsing {entry} in .beat: {e}")

        # Fallback: infer component mapping from list_skins()
        skin_files = self.list_skins()
        if not skin_files:
            return None

        components = {}
        for f in skin_files:
            fl = f.lower()
            if "panel" in fl and "panel" not in components:
                components["panel"] = f
            elif "target" in fl and "target" not in components:
                components["target"] = f
            elif "left" in fl and "wing_left" not in components:
                components["wing_left"] = f
            elif "right" in fl and "wing_right" not in components:
                components["wing_right"] = f
            elif "beat" in fl and "target" not in fl and "panel" not in fl and "wing" not in fl and "beat" not in components:
                components["beat"] = f

        if components:
            return {
                "format": "beat_skin",
                "version": "1.0",
                "name": "Auto-detected Skin",
                "components": components,
                "palette": {
                    "primary": "#be2edd",
                    "accent": "#e056fd",
                    "target": "#9b51e0",
                    "glow": "#f368e0",
                    "panel_border": "#d434ef",
                    "timeline_fill": "#ffffff"
                }
            }
        return None

    def extract_skins(self, dest_dir: Optional[str] = None) -> str:
        """
        Extracts bundled skins into dest_dir/skins/ and returns the skins directory path.
        Also extracts or creates skin.json inside dest_dir/skins/ for component mapping.
        """
        if dest_dir is None:
            pack_name = os.path.splitext(os.path.basename(self._path))[0]
            dest_dir = os.path.join(tempfile.gettempdir(), "beatmake_skins", pack_name)

        skins_out = os.path.join(dest_dir, "skins")
        os.makedirs(skins_out, exist_ok=True)

        for name in self._zf.namelist():
            if name.endswith("/"):
                continue
            base_ext = os.path.splitext(name)[1].lower()
            if name.startswith(SKINS_PREFIX):
                skin_file = name[len(SKINS_PREFIX):]
            elif base_ext in (".svg", ".png", ".jpg", ".jpeg", ".webp") and not name.lower().startswith("video"):
                skin_file = os.path.basename(name)
            else:
                skin_file = ""

            if skin_file:
                out_path = os.path.join(skins_out, skin_file)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with self._zf.open(name) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())

        # Extract or write skin.json into skins_out
        cfg = self.get_skin_config()
        if cfg:
            cfg_out = os.path.join(skins_out, SKIN_CONFIG_NAME)
            try:
                with open(cfg_out, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
            except Exception as e:
                print(f"Failed to write extracted skin.json: {e}")

        return os.path.abspath(skins_out)


class BeatFormat:
    """
    Main static interface for creating, inspecting, and opening .beat archives.
    """

    @staticmethod
    def open(path: str) -> BeatFileReader:
        """Opens a .beat file as a context manager: with BeatFormat.open(p) as bf: ..."""
        return BeatFileReader(path)

    @staticmethod
    def is_valid(path: str) -> bool:
        """Checks if a path exists and is a valid .beat archive."""
        if not path or not os.path.exists(path):
            return False
        try:
            if not zipfile.is_zipfile(path):
                return False
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                return MANIFEST_NAME in names and BEATMAP_NAME in names
        except Exception:
            return False

    @staticmethod
    def get_info(path: str) -> Dict[str, Any]:
        """Returns summary info about a .beat archive without extracting contents."""
        info = {
            "title": "",
            "author": "User",
            "video_name": "",
            "has_embedded_video": False,
            "embedded_video_size_mb": 0.0,
            "skin_count": 0,
            "beat_count": 0,
            "zone_count": 0,
            "format_version": "?",
            "created_at": "",
            "file_size_mb": 0.0,
        }
        if not os.path.exists(path):
            return info

        info["file_size_mb"] = round(os.path.getsize(path) / (1024 * 1024), 2)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if MANIFEST_NAME in names:
                    with zf.open(MANIFEST_NAME) as f:
                        m = json.load(f)
                        info["title"] = m.get("title", "")
                        info["author"] = m.get("author", "User")
                        info["video_name"] = m.get("video_name", "")
                        info["has_embedded_video"] = m.get("has_embedded_video", False)
                        info["format_version"] = m.get("format_version", "?")
                        info["created_at"] = m.get("created_at", "")
                if BEATMAP_NAME in names:
                    with zf.open(BEATMAP_NAME) as f:
                        bm = json.load(f)
                        info["beat_count"] = len(bm.get("beats", []))
                        info["zone_count"] = len(bm.get("zones", []))
                info["skin_count"] = sum(1 for n in names if n.startswith(SKINS_PREFIX) and not n.endswith("/"))
                for n in names:
                    b, ext = os.path.splitext(n)
                    if b.lower() == EMBEDDED_VIDEO_NAME and ext.lower() in VIDEO_EXTENSIONS:
                        info["embedded_video_size_mb"] = round(zf.getinfo(n).file_size / (1024 * 1024), 2)
                        break
        except Exception:
            pass
        return info

    @staticmethod
    def create(
        output_path: str,
        beatmap_source: Union[str, Dict[str, Any]],
        title: Optional[str] = None,
        author: Optional[str] = None,
        video_path: Optional[str] = None,
        skins_dir: Optional[str] = None,
        extra_skin_files: Optional[List[str]] = None,
        skin_config: Optional[Union[Dict, str]] = None,
        extra_skin_data: Optional[Dict[str, Union[str, bytes]]] = None,
        embed_video: bool = False,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Packs a beatmap, skin assets, metadata, and optional video into a standard .beat ZIP archive.

        Args:
            output_path:       Target file path (automatically ensures .beat extension).
            beatmap_source:    Either a filepath to a JSON beatmap, or an in-memory dictionary.
            title:             Human-readable pack title.
            video_path:        Path to original video. If embed_video=True, binary is embedded.
                               Otherwise, its filename is written to manifest and video_name.txt.
            skins_dir:         Directory containing custom SVG skin files. Defaults to viewer/skins.
            extra_skin_files:  List of individual skin file paths to include.
            embed_video:       Whether to embed the video file binary directly into the archive.
            on_progress:       Callback(written_bytes, total_bytes) for video embedding progress.

        Returns:
            Absolute path to the created .beat archive.
        """
        output_path = os.path.abspath(output_path)
        if not output_path.lower().endswith(".beat"):
            output_path += ".beat"

        # 1. Parse or serialize beatmap JSON data
        if isinstance(beatmap_source, str):
            if not os.path.exists(beatmap_source):
                raise FileNotFoundError(f"Beatmap source file not found: {beatmap_source}")
            with open(beatmap_source, "r", encoding="utf-8") as f:
                beatmap_dict = json.load(f)
            if not title:
                title = os.path.splitext(os.path.basename(beatmap_source))[0]
        elif isinstance(beatmap_source, dict):
            beatmap_dict = beatmap_source
            if not title:
                title = beatmap_dict.get("title") or "Beat Pack"
        else:
            raise TypeError("beatmap_source must be a file path (str) or a dictionary.")

        # Ensure title
        if not title:
            title = os.path.splitext(os.path.basename(output_path))[0]

        # 2. Determine video filename
        video_name = ""
        if video_path:
            video_name = os.path.basename(video_path)
        elif "video_file" in beatmap_dict and beatmap_dict["video_file"]:
            video_name = os.path.basename(beatmap_dict["video_file"])
        elif "audio_file" in beatmap_dict and beatmap_dict["audio_file"]:
            video_name = os.path.basename(beatmap_dict["audio_file"])

        # 3. Build manifest
        if not author:
            if isinstance(skin_config, dict) and skin_config.get("author"):
                author = str(skin_config["author"]).strip()
            elif isinstance(beatmap_dict, dict) and beatmap_dict.get("author"):
                author = str(beatmap_dict["author"]).strip()
            else:
                author = "User"

        manifest = {
            "format": "beat",
            "format_version": BEAT_FORMAT_VERSION,
            "title": title,
            "author": author,
            "video_name": video_name,
            "has_embedded_video": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if isinstance(beatmap_dict, dict):
            beatmap_dict["author"] = author

        # 4. Collect skin files
        skin_files: Dict[str, str] = {}  # dest_name -> src_path

        search_dirs = []
        if skins_dir and os.path.isdir(skins_dir):
            search_dirs.append(skins_dir)

        # Look in viewer/skins and skins
        root_dir = os.path.dirname(os.path.abspath(__file__))
        for candidate in [
            os.path.join(root_dir, "viewer", "skins"),
            os.path.join(root_dir, "skins"),
        ]:
            if os.path.isdir(candidate) and candidate not in search_dirs:
                search_dirs.append(candidate)

        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                ext = os.path.splitext(fname)[1].lower()
                if ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
                    src = os.path.join(d, fname)
                    if fname not in skin_files:
                        skin_files[fname] = src

        if extra_skin_files:
            for ef in extra_skin_files:
                if os.path.exists(ef):
                    skin_files[os.path.basename(ef)] = ef

        # Process / infer skin_config (skin.json)
        skin_cfg_dict = None
        if isinstance(skin_config, dict):
            skin_cfg_dict = skin_config
        elif isinstance(skin_config, str) and os.path.exists(skin_config):
            try:
                with open(skin_config, "r", encoding="utf-8") as f:
                    skin_cfg_dict = json.load(f)
            except Exception as e:
                print(f"Failed to read skin_config file {skin_config}:", e)

        # If not provided, check if skins_dir has skin.json
        if not skin_cfg_dict and skins_dir and os.path.isdir(skins_dir):
            cand_cfg = os.path.join(skins_dir, SKIN_CONFIG_NAME)
            if os.path.exists(cand_cfg):
                try:
                    with open(cand_cfg, "r", encoding="utf-8") as f:
                        skin_cfg_dict = json.load(f)
                except Exception:
                    pass

        # If still none, auto-generate component mapping from collected skin_files
        if not skin_cfg_dict and skin_files:
            components = {}
            for fname in skin_files:
                fl = fname.lower()
                if "panel" in fl and "panel" not in components:
                    components["panel"] = fname
                elif "target" in fl and "target" not in components:
                    components["target"] = fname
                elif "left" in fl and "wing_left" not in components:
                    components["wing_left"] = fname
                elif "right" in fl and "wing_right" not in components:
                    components["wing_right"] = fname
                elif "beat" in fl and "target" not in fl and "panel" not in fl and "wing" not in fl and "beat" not in components:
                    components["beat"] = fname

            if components:
                skin_cfg_dict = {
                    "format": "beat_skin",
                    "version": "1.0",
                    "name": title or "Default Beatbar Skin",
                    "components": components,
                    "palette": {
                        "primary": "#be2edd",
                        "accent": "#e056fd",
                        "target": "#9b51e0",
                        "glow": "#f368e0",
                        "panel_border": "#d434ef",
                        "timeline_fill": "#ffffff"
                    }
                }

        # 5. Write archive
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Beatmap JSON
            beatmap_bytes = json.dumps(beatmap_dict, indent=2, ensure_ascii=False).encode("utf-8")
            zf.writestr(BEATMAP_NAME, beatmap_bytes)

            # 2. Video name reference
            if video_name:
                zf.writestr(VIDEO_NAME_FILE, video_name)

            # 3. Skins
            for dest_name, src_path in skin_files.items():
                zf.write(src_path, SKINS_PREFIX + dest_name)

            # 3a. In-memory / explicit component skin SVGs
            if extra_skin_data:
                for dest_name, data in extra_skin_data.items():
                    raw = data.encode("utf-8") if isinstance(data, str) else data
                    zf.writestr(SKINS_PREFIX + dest_name, raw)
                    zf.writestr(dest_name, raw)

            # 3b. Write skin.json both at root and under skins/
            if skin_cfg_dict:
                cfg_bytes = json.dumps(skin_cfg_dict, indent=2, ensure_ascii=False).encode("utf-8")
                zf.writestr(SKIN_CONFIG_NAME, cfg_bytes)
                zf.writestr(SKINS_PREFIX + SKIN_CONFIG_NAME, cfg_bytes)

            # 4. Embedded video
            if embed_video and video_path and os.path.exists(video_path):
                vsize = os.path.getsize(video_path)
                if vsize > MAX_EMBED_VIDEO_BYTES:
                    raise ValueError(f"Video too large to embed: {vsize / 1e9:.2f} GB > 2 GB limit")

                video_ext = os.path.splitext(video_path)[1].lower()
                embedded_entry = EMBEDDED_VIDEO_NAME + video_ext

                chunk_size = 1024 * 1024  # 1 MB
                written = 0
                with zf.open(embedded_entry, "w", force_zip64=True) as zdst:
                    with open(video_path, "rb") as vsrc:
                        while True:
                            buf = vsrc.read(chunk_size)
                            if not buf:
                                break
                            zdst.write(buf)
                            written += len(buf)
                            if on_progress:
                                on_progress(written, vsize)

                manifest["has_embedded_video"] = True
                manifest["embedded_video_entry"] = embedded_entry

            # 5. Manifest (written once with complete metadata)
            manifest["has_skin_config"] = bool(skin_cfg_dict)
            manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
            zf.writestr(MANIFEST_NAME, manifest_bytes)
        return output_path


# ==============================================================================
# Lightweight Beatmap Data & Loading Functions (Zero DSP Dependencies)
# ==============================================================================

class BeatmapData(tuple):
    """
    Backwards-compatible tuple (beats, audio_file) that also exposes
    rich beatmap metadata: .beats, .audio_file, .settings, .zones, .title, .has_embedded_video,
    .level, .difficulty, .difficulty_stats, .levels (level chapters), and .level_mode.
    """
    def __new__(cls, beats, audio_file="", settings=None, zones=None, title="", has_embedded_video=False,
                beat_path=None, level=1, difficulty="Normal", difficulty_stats=None,
                levels=None, level_mode="ramp_within_level"):
        return super().__new__(cls, (beats, audio_file))

    def __init__(self, beats, audio_file="", settings=None, zones=None, title="", has_embedded_video=False,
                 beat_path=None, level=1, difficulty="Normal", difficulty_stats=None,
                 levels=None, level_mode="ramp_within_level"):
        self.beats = beats
        self.audio_file = audio_file
        self.settings = settings or {}
        self.zones = zones or []
        self.title = title
        self.has_embedded_video = has_embedded_video
        self.beat_path = beat_path
        self.level = level
        self.difficulty = difficulty
        self.difficulty_stats = difficulty_stats or {}
        self.levels = levels or []
        self.level_mode = level_mode


def format_srt_time(seconds):
    """Converts seconds into SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis -= 1000
        secs += 1
    if secs >= 60:
        secs -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def calculate_beat_difficulty(beats, duration=None, bpm=None, close_gap_threshold=0.35, min_group_size=3):
    """
    Auto difficulty determiner based on:
    1. Count of beats
    2. Frequency of beats (average and windowed peak)
    3. Frequency of close beat groups (bursts / streams where consecutive gap <= close_gap_threshold)
    """
    if not beats:
        return {
            'difficulty': 'None',
            'level': 0,
            'score': 0.0,
            'total_beats': 0,
            'duration': 0.0,
            'avg_frequency': 0.0,
            'peak_frequency': 0.0,
            'burst_groups_count': 0,
            'burst_beats_count': 0,
            'burst_frequency': 0.0,
            'max_burst_length': 0,
            'burst_ratio': 0.0,
            'details_str': 'No beats'
        }

    times = []
    for b in beats:
        if isinstance(b, dict):
            t = float(b.get('time', 0.0))
        elif isinstance(b, (int, float)):
            t = float(b)
        else:
            continue
        times.append(t)
    times.sort()

    n = len(times)
    if n == 0:
        return {
            'difficulty': 'None',
            'level': 0,
            'score': 0.0,
            'total_beats': 0,
            'duration': 0.0,
            'avg_frequency': 0.0,
            'peak_frequency': 0.0,
            'burst_groups_count': 0,
            'burst_beats_count': 0,
            'burst_frequency': 0.0,
            'max_burst_length': 0,
            'burst_ratio': 0.0,
            'details_str': 'No beats'
        }

    total_dur = float(duration) if duration and duration > 0 else max(1.0, times[-1] - times[0] + 1.0)
    avg_freq = n / max(1.0, total_dur)

    peak_freq = avg_freq
    w_size = 3.0
    j_end = 0
    for i in range(n):
        while j_end < n and times[j_end] - times[i] <= w_size:
            j_end += 1
        cnt_in_window = j_end - i
        local_freq = cnt_in_window / w_size
        if local_freq > peak_freq:
            peak_freq = local_freq

    burst_groups = []
    i = 0
    while i < n - 1:
        if (times[i + 1] - times[i]) <= close_gap_threshold:
            j = i + 1
            while j < n - 1 and (times[j + 1] - times[j]) <= close_gap_threshold:
                j += 1
            grp_len = j - i + 1
            if grp_len >= min_group_size:
                grp_dur = times[j] - times[i]
                burst_groups.append({
                    'start': times[i],
                    'end': times[j],
                    'count': grp_len,
                    'duration': grp_dur
                })
            i = j + 1
        else:
            i += 1

    burst_groups_count = len(burst_groups)
    burst_beats_count = sum(g['count'] for g in burst_groups)
    max_burst_length = max([g['count'] for g in burst_groups], default=0)
    bursts_per_min = burst_groups_count / max(0.1, total_dur / 60.0)
    burst_ratio = burst_beats_count / max(1, n)

    f_score = min(5.0, avg_freq * 1.5)
    p_score = min(3.0, (peak_freq - avg_freq) * 0.8)
    b_score = min(4.0, (bursts_per_min * 0.25) + (burst_ratio * 2.5))
    total_score = round(max(1.0, min(12.0, f_score + p_score + b_score)), 2)

    if total_score < 2.5:
        diff_name = 'Easy'
        level = 1 if total_score < 1.8 else 2
    elif total_score < 5.0:
        diff_name = 'Normal'
        level = 3 if total_score < 3.8 else 4
    elif total_score < 7.5:
        diff_name = 'Hard'
        level = 5 if total_score < 6.2 else 6
    elif total_score < 10.0:
        diff_name = 'Expert'
        level = 7 if total_score < 8.8 else 8
    else:
        diff_name = 'Master'
        level = 9 if total_score < 11.0 else 10

    details = (
        f"{diff_name} (Lv.{level}) | Score: {total_score:.1f} | "
        f"Beats: {n} ({avg_freq:.1f}/s, peak {peak_freq:.1f}/s) | "
        f"Bursts: {burst_groups_count} ({burst_ratio*100:.0f}% of track, max {max_burst_length})"
    )

    return {
        'difficulty': diff_name,
        'level': level,
        'score': total_score,
        'total_beats': n,
        'duration': round(total_dur, 2),
        'avg_frequency': round(avg_freq, 2),
        'peak_frequency': round(peak_freq, 2),
        'burst_groups_count': burst_groups_count,
        'burst_beats_count': burst_beats_count,
        'burst_frequency': round(bursts_per_min, 2),
        'max_burst_length': max_burst_length,
        'burst_ratio': round(burst_ratio, 3),
        'details_str': details
    }


def infer_or_standardize_levels(duration, title="", level=1, levels=None, difficulty="Normal"):
    """
    Standardizes level chapters. If levels list is provided and valid, normalizes it.
    Otherwise, infers named levels based on title/character/level cues.
    """
    import re
    duration = max(1.0, float(duration))
    diff_str = str(difficulty or "Normal")
    if levels and isinstance(levels, list) and len(levels) > 0:
        cleaned = []
        for i, lv in enumerate(levels):
            if isinstance(lv, dict):
                name = str(lv.get('name', f"Level {i+1}"))
                st = max(0.0, min(duration, float(lv.get('start_time', lv.get('start', 0.0)))))
                et = max(st, min(duration, float(lv.get('end_time', lv.get('end', duration)))))
                diff = str(lv.get('difficulty', diff_str))
                cleaned.append({'name': name, 'start_time': round(st, 3), 'end_time': round(et, 3), 'difficulty': diff})
        if cleaned:
            cleaned.sort(key=lambda x: x['start_time'])
            cleaned[0]['start_time'] = 0.0
            cleaned[-1]['end_time'] = round(duration, 3)
            return cleaned

    t_lower = (str(title) + " " + str(level)).lower()
    char_name = None
    if "d.va" in t_lower or "dva" in t_lower or "d-va" in t_lower:
        char_name = "D.va"
    elif "widow" in t_lower:
        char_name = "Widow"
    elif "mercy" in t_lower:
        char_name = "Mercy"
    elif "tracer" in t_lower:
        char_name = "Tracer"
    elif "allure" in t_lower:
        char_name = "Allure"
    elif "demoness" in t_lower:
        char_name = "Demoness"
    elif "wicked" in t_lower:
        char_name = "Wicked"

    lvl_num = None
    title_m = re.search(r'(?:level|lv|no)[-_ ]*0*(\d+)', str(title), re.IGNORECASE)
    if title_m:
        lvl_num = title_m.group(1)
    else:
        digits = ''.join(filter(str.isdigit, str(level)))
        lvl_num = digits if digits else "1"

    lvl_str = str(level).strip()
    if "-" in lvl_str and "level" in lvl_str.lower():
        default_name = lvl_str
    elif char_name:
        default_name = f"Level {lvl_num} - {char_name}"
    else:
        default_name = f"Level {lvl_num}"

    return [{'name': default_name, 'start_time': 0.0, 'end_time': round(duration, 3), 'difficulty': diff_str}]


def infer_zones_from_beats(beats, duration=None):
    """
    Intelligently generates musical rhythm zones from beat timestamps
    when explicit zones are not defined in the beatmap.
    """
    if not beats:
        return []
    dur = float(duration) if duration and duration > 0 else (float(beats[-1].get('time', 60.0)) + 2.0)
    times = sorted([float(b.get('time', 0.0)) for b in beats])

    win_size = 5.0
    raw_zones = []
    t = 0.0
    while t < dur:
        t_next = min(dur, t + win_size)
        w_beats = [bt for bt in times if t <= bt < t_next]
        count = len(w_beats)
        density = count / max(0.1, (t_next - t))

        if count == 0:
            ztype = 'pause'
            zname = 'Pause / Rest'
        elif density >= 4.5:
            ztype = 'climax'
            zname = 'Climax Burst'
        elif density >= 2.6:
            ztype = 'speeding_up'
            zname = 'Speeding Up'
        elif density >= 1.0:
            ztype = 'normal'
            zname = 'Normal Groove'
        else:
            ztype = 'slowing'
            zname = 'Slowing Down'

        raw_zones.append((t, t_next, ztype, zname))
        t = t_next

    merged = []
    for st, et, ztype, zname in raw_zones:
        if merged and merged[-1]['type'] == ztype:
            merged[-1]['end_time'] = round(et, 2)
        else:
            merged.append({
                'name': zname,
                'type': ztype,
                'start_time': round(st, 2),
                'end_time': round(et, 2)
            })

    if merged:
        merged[0]['start_time'] = 0.0
        merged[-1]['end_time'] = round(dur, 2)
    return merged


def load_beats(file_path):
    """
    Loads beats from JSON or .beat archive.
    Returns: BeatmapData object (acts as tuple (beats, audio_file) with .settings, .zones, .title, .level, .difficulty, .levels, .level_mode)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Beatmap file not found: {file_path}")

    import re
    if file_path.lower().endswith('.beat') or (zipfile.is_zipfile(file_path) and not file_path.lower().endswith('.json')):
        with BeatFormat.open(file_path) as bf:
            data = bf.get_beatmap()
            beats = data.get("beats", [])
            audio_file = bf.get_video_name() or data.get("audio_file", data.get("video_file", ""))
            settings = data.get("settings", {})
            zones = data.get("zones", [])
            title = bf.get_title()
            has_embed = bf.has_embedded_video()
            difficulty_stats = data.get("difficulty_stats", None)
            levels = data.get("levels", [])
            level_mode = data.get("level_mode", "ramp_within_level")
            if not difficulty_stats and beats:
                difficulty_stats = calculate_beat_difficulty(beats)

            # Determine level: prioritize explicit saved level in data, then levels[0], then filename cues
            raw_level = data.get("level")
            m = re.search(r'\b(?:level|lv)[-_ ]*0*(\d+)\b', f"{title} {os.path.basename(file_path)}", re.IGNORECASE)
            if raw_level is not None:
                try:
                    level = int(raw_level)
                except (ValueError, TypeError):
                    level = 1
            elif levels and len(levels) > 0:
                first_lvl = levels[0]
                level = first_lvl.get('level', 1) if isinstance(first_lvl, dict) else getattr(first_lvl, 'level', 1)
            elif m:
                level = int(m.group(1))
            elif difficulty_stats and "level" in difficulty_stats:
                level = int(difficulty_stats["level"])
            else:
                level = 1

            # Determine difficulty: prioritize explicit saved difficulty in data, then levels[0]
            raw_diff = data.get("difficulty")
            if raw_diff is not None and str(raw_diff).strip() != "":
                difficulty = str(raw_diff).strip()
            elif levels and len(levels) > 0:
                first_lvl = levels[0]
                difficulty = first_lvl.get('difficulty', "Normal") if isinstance(first_lvl, dict) else getattr(first_lvl, 'difficulty', "Normal")
            elif difficulty_stats and "difficulty" in difficulty_stats:
                difficulty = difficulty_stats["difficulty"]
            else:
                difficulty = "Normal"

            if not zones and beats:
                zones = infer_zones_from_beats(beats)

            return BeatmapData(
                beats, audio_file, settings, zones,
                title=title, has_embedded_video=has_embed,
                beat_path=os.path.abspath(file_path),
                level=level, difficulty=difficulty, difficulty_stats=difficulty_stats,
                levels=levels, level_mode=level_mode
            )
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        beats = data.get("beats", [])
        audio_file = data.get("audio_file", data.get("video_file", ""))
        settings = data.get("settings", {})
        zones = data.get("zones", [])
        title = data.get("title", os.path.splitext(os.path.basename(file_path))[0])
        difficulty_stats = data.get("difficulty_stats", None)
        levels = data.get("levels", [])
        level_mode = data.get("level_mode", "ramp_within_level")
        if not difficulty_stats and beats:
            difficulty_stats = calculate_beat_difficulty(beats)

        # Determine level: prioritize explicit saved level in data, then levels[0], then filename cues
        raw_level = data.get("level")
        m = re.search(r'\b(?:level|lv)[-_ ]*0*(\d+)\b', f"{title} {os.path.basename(file_path)}", re.IGNORECASE)
        if raw_level is not None:
            try:
                level = int(raw_level)
            except (ValueError, TypeError):
                level = 1
        elif levels and len(levels) > 0:
            first_lvl = levels[0]
            level = first_lvl.get('level', 1) if isinstance(first_lvl, dict) else getattr(first_lvl, 'level', 1)
        elif m:
            level = int(m.group(1))
        elif difficulty_stats and "level" in difficulty_stats:
            level = int(difficulty_stats["level"])
        else:
            level = 1

        # Determine difficulty: prioritize explicit saved difficulty in data, then levels[0]
        raw_diff = data.get("difficulty")
        if raw_diff is not None and str(raw_diff).strip() != "":
            difficulty = str(raw_diff).strip()
        elif levels and len(levels) > 0:
            first_lvl = levels[0]
            difficulty = first_lvl.get('difficulty', "Normal") if isinstance(first_lvl, dict) else getattr(first_lvl, 'difficulty', "Normal")
        elif difficulty_stats and "difficulty" in difficulty_stats:
            difficulty = difficulty_stats["difficulty"]
        else:
            difficulty = "Normal"

        if not zones and beats:
            zones = infer_zones_from_beats(beats)

        return BeatmapData(
            beats, audio_file, settings, zones, title=title,
            beat_path=os.path.abspath(file_path),
            level=level, difficulty=difficulty, difficulty_stats=difficulty_stats,
            levels=levels, level_mode=level_mode
        )
