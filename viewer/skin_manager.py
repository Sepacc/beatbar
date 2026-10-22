"""
skin_manager.py - Skin and Theme Asset Manager for Beatbar Viewer.

Provides customizable themes, SVG/image skins, color palettes, and caching
for the Beatbar panel, beat icons, central target, and hit animations.
"""

import os
import sys
import json
from PyQt6.QtCore import Qt, QRectF, QByteArray
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

VIEWER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(VIEWER_DIR)
MAIN_DIR = os.path.join(ROOT_DIR, "main")
for p in [ROOT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)
ASSETS_SKINS_DIR = os.path.join(ROOT_DIR, "assets", "skins")
SKINS_DIR = ASSETS_SKINS_DIR if os.path.isdir(ASSETS_SKINS_DIR) else os.path.join(VIEWER_DIR, "skins")
CONFIG_PATH = os.path.join(VIEWER_DIR, ".config")
LEGACY_CONFIG_PATH = os.path.join(VIEWER_DIR, "viewer_config.json")

# Built-in Color Palettes
COLOR_PALETTES = {
    "violet": {
        "id": "violet",
        "name": "Violet Amethyst (Default)",
        "primary": "#be2edd",
        "accent": "#e056fd",
        "target": "#9b51e0",
        "glow": "#f368e0",
        "panel_border": "#d434ef",
        "timeline_fill": "#ffffff",
        "swatch": ["#1e102e", "#be2edd", "#e056fd", "#ffffff"]
    },
    "cyber": {
        "id": "cyber",
        "name": "Cyber Synthwave",
        "primary": "#00f3ff",
        "accent": "#ff007f",
        "target": "#00f3ff",
        "glow": "#00d2ff",
        "panel_border": "#00f3ff",
        "timeline_fill": "#00f3ff",
        "swatch": ["#08182b", "#00f3ff", "#ff007f", "#ffffff"]
    },
    "emerald": {
        "id": "emerald",
        "name": "Emerald Groove",
        "primary": "#2ecc40",
        "accent": "#38ef7d",
        "target": "#38ef7d",
        "glow": "#2ecc40",
        "panel_border": "#38ef7d",
        "timeline_fill": "#38ef7d",
        "swatch": ["#0b2413", "#2ecc40", "#38ef7d", "#ffffff"]
    },
    "solar": {
        "id": "solar",
        "name": "Solar Flare",
        "primary": "#ff9f1a",
        "accent": "#ff5252",
        "target": "#ffd32a",
        "glow": "#fffa65",
        "panel_border": "#ff9f1a",
        "timeline_fill": "#fffa65",
        "swatch": ["#2b1b08", "#ff9f1a", "#ff5252", "#fffa65"]
    },
    "crimson": {
        "id": "crimson",
        "name": "Crimson Fury",
        "primary": "#ff1744",
        "accent": "#ff5252",
        "target": "#ff1744",
        "glow": "#ff6b81",
        "panel_border": "#ff1744",
        "timeline_fill": "#ff4d4d",
        "swatch": ["#2e0c12", "#ff1744", "#ff5252", "#ffffff"]
    },
    "golden": {
        "id": "golden",
        "name": "Golden Celestial",
        "primary": "#f1c40f",
        "accent": "#f39c12",
        "target": "#f5cd79",
        "glow": "#f7d794",
        "panel_border": "#f1c40f",
        "timeline_fill": "#ffffff",
        "swatch": ["#2b2207", "#f1c40f", "#f39c12", "#ffffff"]
    },
    "void": {
        "id": "void",
        "name": "Void Phantom",
        "primary": "#7d5fff",
        "accent": "#18dcff",
        "target": "#7158e2",
        "glow": "#c56cf0",
        "panel_border": "#7d5fff",
        "timeline_fill": "#18dcff",
        "swatch": ["#160e29", "#7d5fff", "#18dcff", "#ffffff"]
    }
}

# Built-in Default Skin Bundles (packed as .beat archives or built-in assets)
DEFAULT_SKIN_BUNDLES = {
    "cyber_wings": {
        "id": "cyber_wings",
        "name": "Cyber Wings (Default)",
        "beat_file": os.path.join(SKINS_DIR, "cyber_wings.beat"),
        "panel_skin": "cyber_wings",
        "beats_skin": "crest",
        "target_skin": "crest_gate",
        "palette": "violet"
    }
}

DEFAULT_CONFIG = {
    "palette": "violet",
    "custom_palette": {
        "primary": "#be2edd",
        "accent": "#e056fd",
        "target": "#9b51e0",
        "glow": "#f368e0",
        "panel_border": "#d434ef",
        "timeline_fill": "#ffffff"
    },
    "panel_skin": "cyber_wings",
    "beats_skin": "crest",
    "target_skin": "crest_gate",
    "hit_animation": "shockwave",  # shockwave, burst, scale_pop, ripple
    "custom_panel_path": "",
    "custom_beat_path": "",
    "custom_target_path": "",
    "custom_target_hit_path": "",
    "custom_wing_left_path": "",
    "custom_wing_right_path": "",
    "wing_left_offset_x": 0.0,
    "wing_left_offset_y": 0.0,
    "wing_left_scale": 1.0,
    "wing_right_offset_x": 0.0,
    "wing_right_offset_y": 0.0,
    "wing_right_scale": 1.0,
    "target_offset_x": 0.0,
    "target_offset_y": 0.0,
    "target_scale": 1.0,
    "flip_left_beats": False,
    "flip_right_beats": False,
    "trigger_hit_duration_ms": 180,
    "trigger_hit_pop_scale": 1.35,
    "trigger_hit_indicator_style": "triangle",  # triangle, diamond, glow_bar, hidden
    "trigger_hit_indicator_color": "#ffffff",
    "active_skin_name": "",
    "active_skin_bundle": "cyber_wings",
    "loaded_skin_bundles": {},  # { bundle_id: { id, name, beat_path, extracted_dir, skin_config } }
    "screen_shake_mode": "intense_and_bursts",  # intense_and_bursts, always, off
    "screen_shake_strength": 0.045,  # zoom fraction (1.0 + strength)
    "beat_hit_effect_type": "border_flash",  # border_flash, picture_flash, shake, both, all
    "flash_color": "#e056fd",  # hex color for border and picture flash
    "lead_time": 1.5,  # seconds ahead for beats
    "beat_scale": 1.0,  # 0.4 to 1.6 scaling factor for beat notes
    "anti_overlap_beats": True,  # dynamically scale rapid consecutive beats to avoid overlapping
    "scroll_direction": "rtl",  # rtl (right to left), ltr (left to right)
    "timeline_fill_mode": "left_to_right",  # left_to_right, center_out, reverse_left, reverse_center_out, reverse_center_in
    "intense_zones_direction": "ltr",  # ltr (reverted), both (both sides), rtl (standard)
    "settings_mode": "simple",  # simple (by zone type), extended (per individual zone)
    "zone_type_directions": {
        "climax": "ltr",
        "edging": "ltr",
        "intense": "ltr",
        "speeding_up": "both",
        "fast": "both",
        "normal": "rtl",
        "pause": "rtl"
    },
    "zone_direction_overrides": {},  # { "zone_id_or_name": "ltr" | "both" | "rtl" | "default" }
    "show_timeline_zones": True,  # show colored rhythm zone blocks on timeline
    "fill_timeline_per_zone": False,  # fill timeline bar per individual zone instead of full video
    "volume": 0.2,
    "speed": 1.0,
    "inactivity_delay": 2.5,  # seconds before collapsing bottom bar
    "audio_offset_ms": 0.0,
    "last_video_path": "",
    "last_beatbar_path": ""
}


class SkinManager:
    """Singleton manager for skins, renderers, and user preferences."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
        self._renderer_cache = {}
        self._pixmap_cache = {}

    def load_config(self):
        target = CONFIG_PATH if os.path.exists(CONFIG_PATH) else (LEGACY_CONFIG_PATH if os.path.exists(LEGACY_CONFIG_PATH) else None)
        if target and os.path.exists(target):
            try:
                with open(target, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception as e:
                print(f"[SkinManager] Failed to load config from {target}:", e)
        # Migrate immediately to .config if needed
        if not os.path.exists(CONFIG_PATH):
            self.save_config()

    def save_config(self):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print("[SkinManager] Failed to save .config:", e)

    def get_palette(self):
        default_pal = COLOR_PALETTES["violet"]
        pal_id = self.config.get("palette", "violet")
        if pal_id == "custom":
            p = self.config.get("custom_palette")
            if isinstance(p, dict):
                merged = default_pal.copy()
                merged.update(p)
                return merged
            return default_pal
        return COLOR_PALETTES.get(pal_id, default_pal)

    def get_svg_renderer(self, path):
        if not path or not os.path.exists(path):
            return None
        if path in self._renderer_cache:
            return self._renderer_cache[path]
        try:
            renderer = QSvgRenderer(path)
            if renderer.isValid():
                self._renderer_cache[path] = renderer
                return renderer
        except Exception as e:
            print(f"Error loading SVG {path}:", e)
        return None

    def get_pixmap(self, path, max_width=None, max_height=None):
        if not path or not os.path.exists(path):
            return None
        key = (path, max_width, max_height)
        if key in self._pixmap_cache:
            return self._pixmap_cache[key]
        pix = QPixmap(path)
        if pix.isNull():
            return None
        if max_width and max_height and (pix.width() > max_width or pix.height() > max_height):
            pix = pix.scaled(max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._pixmap_cache[key] = pix
        return pix

    def get_panel_svg_path(self):
        skin = self.config.get("panel_skin", "cyber_wings")
        if self.config.get("custom_panel_path") and os.path.exists(self.config.get("custom_panel_path")):
            if skin == "custom" or str(skin).startswith("bundle_"):
                return self.config.get("custom_panel_path")
        p = os.path.join(SKINS_DIR, "panel_cyber_wings.svg")
        if os.path.exists(p):
            return p
        return ""

    def get_target_svg_path(self):
        skin = self.config.get("target_skin", "crest_gate")
        panel_skin = str(self.config.get("panel_skin", ""))
        if self.config.get("custom_target_path") and os.path.exists(self.config.get("custom_target_path")):
            if skin == "custom" or panel_skin.startswith("bundle_"):
                return self.config.get("custom_target_path")
        return os.path.join(SKINS_DIR, "crest_target.svg")

    def get_target_hit_svg_path(self):
        p = self.config.get("custom_target_hit_path", "")
        if p and os.path.exists(p):
            return p
        return ""

    def get_beat_svg_path(self):
        skin = self.config.get("beats_skin", "crest")
        panel_skin = str(self.config.get("panel_skin", ""))
        if self.config.get("custom_beat_path") and os.path.exists(self.config.get("custom_beat_path")):
            if skin == "custom" or panel_skin.startswith("bundle_"):
                return self.config.get("custom_beat_path")
        if skin == "diamond":
            return os.path.join(SKINS_DIR, "diamond_beat.svg")
        elif skin == "orb":
            return os.path.join(SKINS_DIR, "orb_beat.svg")
        else:
            return os.path.join(SKINS_DIR, "crest_beat.svg")

    def get_wing_sigil_paths(self):
        left = self.config.get("custom_wing_left_path", "")
        right = self.config.get("custom_wing_right_path", "")
        if not left or not os.path.exists(left):
            left = os.path.join(SKINS_DIR, "wing_sigil_left.svg")
        if not right or not os.path.exists(right):
            right = os.path.join(SKINS_DIR, "wing_sigil_right.svg")
        return left, right

    def apply_skin_bundle(self, skins_dir: str, skin_config: dict, bundle_id: str = "custom"):
        """
        Applies a skin bundle (e.g. extracted from a .beat archive or skin.json).
        Maps components according to skin.json:
          - panel -> custom_panel_path, panel_skin=bundle_id
          - wing_left -> custom_wing_left_path
          - wing_right -> custom_wing_right_path
          - target -> custom_target_path, target_skin='custom'
          - beat -> custom_beat_path, beats_skin='custom'
        Applies custom_palette if defined.
        Clears renderer caches.
        """
        if not skin_config or not skins_dir:
            return

        self._renderer_cache.clear()
        self._pixmap_cache.clear()

        comps = skin_config.get("components", {})
        skin_name = skin_config.get("name", "Custom Pack Skin")
        self.config["active_skin_name"] = skin_name
        self.config["active_skin_bundle"] = bundle_id

        def _resolve_path(fname, role=None):
            # 1. Direct path check
            if fname:
                cand = os.path.join(skins_dir, fname)
                if os.path.exists(cand):
                    return os.path.abspath(cand)
                # Subdirectories and case-insensitive check
                for root, _, files in os.walk(skins_dir):
                    for f in files:
                        if f.lower() == fname.lower():
                            return os.path.abspath(os.path.join(root, f))

            # 2. Keyword fallback among extracted SVGs/images
            if role:
                all_files = []
                for root, _, files in os.walk(skins_dir):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
                            all_files.append((f, os.path.abspath(os.path.join(root, f))))

                if role == "panel":
                    for f, p in all_files:
                        if "panel" in f.lower():
                            return p
                elif role == "wing_left":
                    for f, p in all_files:
                        fl = f.lower()
                        if "wing" in fl and ("left" in fl or "_l" in fl or "sigil_left" in fl):
                            return p
                elif role == "wing_right":
                    for f, p in all_files:
                        fl = f.lower()
                        if "wing" in fl and ("right" in fl or "_r" in fl or "sigil_right" in fl):
                            return p
                elif role == "target":
                    for f, p in all_files:
                        fl = f.lower()
                        if any(k in fl for k in ("target", "crest_gate", "reticle", "crosshair")) and "hit" not in fl:
                            return p
                elif role in ("target_hit", "hit"):
                    for f, p in all_files:
                        fl = f.lower()
                        if "hit" in fl and any(k in fl for k in ("target", "crest", "reticle", "crosshair", "wink")):
                            return p
                elif role in ("beat", "beats"):
                    for f, p in all_files:
                        fl = f.lower()
                        if "beat" in fl and not any(k in fl for k in ("panel", "target", "wing")):
                            return p
            return ""

        # 1. Main Panel
        panel_file = comps.get("panel")
        p_path = _resolve_path(panel_file, role="panel")
        if p_path:
            self.config["custom_panel_path"] = p_path
        self.config["panel_skin"] = bundle_id

        # 2. Left and Right Wings
        wing_l_file = comps.get("wing_left") or comps.get("wing_l")
        wl_path = _resolve_path(wing_l_file, role="wing_left")
        if wl_path:
            self.config["custom_wing_left_path"] = wl_path

        wing_r_file = comps.get("wing_right") or comps.get("wing_r")
        wr_path = _resolve_path(wing_r_file, role="wing_right")
        if wr_path:
            self.config["custom_wing_right_path"] = wr_path

        # 3. Center Target & 2nd State Target Hit
        target_file = comps.get("target")
        t_path = _resolve_path(target_file, role="target")
        if t_path:
            self.config["custom_target_path"] = t_path
            self.config["target_skin"] = "custom"

        target_hit_file = comps.get("target_hit") or comps.get("hit")
        th_path = _resolve_path(target_hit_file, role="target_hit")
        if th_path:
            self.config["custom_target_hit_path"] = th_path
        else:
            self.config["custom_target_hit_path"] = ""

        # 4. Beats
        beat_file = comps.get("beat") or comps.get("beats")
        b_path = _resolve_path(beat_file, role="beat")
        if b_path:
            self.config["custom_beat_path"] = b_path
            self.config["beats_skin"] = "custom"

        # 5. Palette
        pal = skin_config.get("palette")
        if pal and isinstance(pal, dict):
            self.config["custom_palette"] = pal.copy()
            self.config["palette"] = "custom"

        # 6. Layout & Trigger Hit Transforms
        layout = skin_config.get("layout", {})
        if isinstance(layout, dict) and layout:
            wl = layout.get("wing_left", {})
            self.config["wing_left_offset_x"] = float(wl.get("offset_x", 0.0))
            self.config["wing_left_offset_y"] = float(wl.get("offset_y", 0.0))
            self.config["wing_left_scale"] = float(wl.get("scale", 1.0))

            wr = layout.get("wing_right", {})
            self.config["wing_right_offset_x"] = float(wr.get("offset_x", 0.0))
            self.config["wing_right_offset_y"] = float(wr.get("offset_y", 0.0))
            self.config["wing_right_scale"] = float(wr.get("scale", 1.0))

            tg = layout.get("target", {})
            self.config["target_offset_x"] = float(tg.get("offset_x", 0.0))
            self.config["target_offset_y"] = float(tg.get("offset_y", 0.0))
            self.config["target_scale"] = float(tg.get("scale", 1.0))

            self.config["flip_left_beats"] = bool(layout.get("flip_left_beats", False))
            self.config["flip_right_beats"] = bool(layout.get("flip_right_beats", False))
        else:
            self.config["wing_left_offset_x"] = 0.0
            self.config["wing_left_offset_y"] = 0.0
            self.config["wing_left_scale"] = 1.0
            self.config["wing_right_offset_x"] = 0.0
            self.config["wing_right_offset_y"] = 0.0
            self.config["wing_right_scale"] = 1.0
            self.config["target_offset_x"] = 0.0
            self.config["target_offset_y"] = 0.0
            self.config["target_scale"] = 1.0
            self.config["flip_left_beats"] = False
            self.config["flip_right_beats"] = False

        trig = skin_config.get("trigger_hit", {})
        if isinstance(trig, dict) and trig:
            if "duration_ms" in trig:
                self.config["trigger_hit_duration_ms"] = int(trig["duration_ms"])
            if "pop_scale" in trig:
                self.config["trigger_hit_pop_scale"] = float(trig["pop_scale"])
            if "indicator_style" in trig:
                self.config["trigger_hit_indicator_style"] = str(trig["indicator_style"])
            if "indicator_color" in trig:
                self.config["trigger_hit_indicator_color"] = str(trig["indicator_color"])

        print(f"[SkinManager] Applied skin bundle '{skin_name}' ({bundle_id}): panel={bool(p_path)}, wings={bool(wl_path and wr_path)}, target={bool(t_path)}, target_hit={bool(th_path)}, beat={bool(b_path)}")

    def apply_bundle(self, bundle_id: str) -> bool:
        """Applies a built-in or loaded .beat skin bundle by ID."""
        self._renderer_cache.clear()
        self._pixmap_cache.clear()

        def _reset_geom():
            self.config["wing_left_offset_x"] = 0.0
            self.config["wing_left_offset_y"] = 0.0
            self.config["wing_left_scale"] = 1.0
            self.config["wing_right_offset_x"] = 0.0
            self.config["wing_right_offset_y"] = 0.0
            self.config["wing_right_scale"] = 1.0
            self.config["target_offset_x"] = 0.0
            self.config["target_offset_y"] = 0.0
            self.config["target_scale"] = 1.0
            self.config["flip_left_beats"] = False
            self.config["flip_right_beats"] = False
            self.config["custom_target_hit_path"] = ""

        if bundle_id == "cyber_wings":
            self.config["active_skin_bundle"] = "cyber_wings"
            self.config["active_skin_name"] = "Cyber Wings"
            self.config["panel_skin"] = "cyber_wings"
            self.config["beats_skin"] = "crest"
            self.config["target_skin"] = "crest_gate"
            self.config["custom_panel_path"] = ""
            self.config["custom_beat_path"] = ""
            self.config["custom_target_path"] = ""
            self.config["custom_wing_left_path"] = ""
            self.config["custom_wing_right_path"] = ""
            self.config["palette"] = "violet"
            _reset_geom()
            self.save_config()
            return True
        elif bundle_id in self.config.get("loaded_skin_bundles", {}):
            binfo = self.config["loaded_skin_bundles"][bundle_id]
            skins_dir = binfo.get("extracted_dir")
            if not skins_dir or not os.path.exists(skins_dir):
                beat_path = binfo.get("beat_path")
                if beat_path and os.path.exists(beat_path):
                    try:
                        from beat_format import BeatFileReader
                        with BeatFileReader(beat_path) as reader:
                            skins_dir = reader.extract_skins()
                            binfo["extracted_dir"] = skins_dir
                    except Exception as e:
                        print(f"Error re-extracting skins for bundle {bundle_id}: {e}")
            if skins_dir and os.path.exists(skins_dir):
                self.apply_skin_bundle(skins_dir, binfo.get("skin_config", {}), bundle_id=bundle_id)
                self.save_config()
                return True
        return False

    def remove_skin_bundle(self, bundle_id: str) -> bool:
        """Removes a custom loaded skin bundle and falls back to cyber_wings if active."""
        if bundle_id in self.config.get("loaded_skin_bundles", {}):
            del self.config["loaded_skin_bundles"][bundle_id]
            if self.config.get("active_skin_bundle") == bundle_id:
                self.apply_bundle("cyber_wings")
            else:
                self.save_config()
            return True
        return False

    def clear_all_custom_skins(self):
        """Purges all custom loaded skin bundles, keeping only standard templates."""
        self.config["loaded_skin_bundles"] = {}
        if self.config.get("active_skin_bundle") != "cyber_wings":
            self.apply_bundle("cyber_wings")
        else:
            self.save_config()

    def load_beat_skin(self, beat_path: str):
        """Loads a .beat file as a skin bundle, extracts assets, registers it, and applies it."""
        if not beat_path or not os.path.exists(beat_path):
            return None
        try:
            try:
                from beat_format import BeatFileReader
            except ImportError:
                from main.beat_format import BeatFileReader
            with BeatFileReader(beat_path) as reader:
                extracted_dir = reader.extract_skins()
                cfg = reader.get_skin_config()

                # Verify that archive contains actual skin assets
                has_skin_files = False
                if extracted_dir and os.path.exists(extracted_dir):
                    for _, _, files in os.walk(extracted_dir):
                        if any(f.lower().endswith(('.svg', '.png', '.jpg', '.jpeg', '.webp')) for f in files):
                            has_skin_files = True
                            break
                if not has_skin_files and not (cfg and cfg.get("components")):
                    print(f"[SkinManager] '{beat_path}' has no skin components or visual assets.")
                    return None

                if not cfg:
                    cfg = {
                        "format": "beat_skin",
                        "version": "1.0",
                        "name": reader.get_title() or os.path.splitext(os.path.basename(beat_path))[0],
                        "components": {},
                        "palette": self.get_palette()
                    }
                skin_name = cfg.get("name") or reader.get_title() or os.path.splitext(os.path.basename(beat_path))[0]
                slug = "".join(c if c.isalnum() else "_" for c in os.path.splitext(os.path.basename(beat_path))[0].lower())
                bundle_id = f"bundle_{slug}"

                bundle_info = {
                    "id": bundle_id,
                    "name": skin_name,
                    "beat_path": os.path.abspath(beat_path),
                    "extracted_dir": extracted_dir,
                    "skin_config": cfg
                }

                if "loaded_skin_bundles" not in self.config:
                    self.config["loaded_skin_bundles"] = {}
                self.config["loaded_skin_bundles"][bundle_id] = bundle_info

                self.apply_skin_bundle(extracted_dir, cfg, bundle_id=bundle_id)
                self.save_config()
                return bundle_info
        except Exception as e:
            print(f"[SkinManager] Error loading .beat skin: {e}")
            return None

