"""
skin_data.py - Data Model, Skin Bundling, Palettes, and Presets for Beatbar Skin Maker.
"""

import os
import json
from copy import deepcopy
from beatpanel.templates import get_template_library
from beatpanel.svg_utils import replace_multiple_colors, validate_svg, format_svg

# Palette Presets
BUILTIN_PALETTES = {
    "violet": {
        "id": "violet",
        "name": "Violet Amethyst (Default)",
        "primary": "#be2edd",
        "accent": "#e056fd",
        "target": "#9b51e0",
        "glow": "#f368e0",
        "panel_border": "#d434ef",
        "timeline_fill": "#ffffff"
    },
    "cyber": {
        "id": "cyber",
        "name": "Cyber Synthwave",
        "primary": "#00f3ff",
        "accent": "#ff007f",
        "target": "#00f3ff",
        "glow": "#00d2ff",
        "panel_border": "#00f3ff",
        "timeline_fill": "#00f3ff"
    },
    "emerald": {
        "id": "emerald",
        "name": "Emerald Matrix",
        "primary": "#2ecc40",
        "accent": "#38ef7d",
        "target": "#38ef7d",
        "glow": "#2ecc40",
        "panel_border": "#38ef7d",
        "timeline_fill": "#38ef7d"
    },
    "solar": {
        "id": "solar",
        "name": "Solar Flare",
        "primary": "#ff9f1a",
        "accent": "#ff5252",
        "target": "#ffd32a",
        "glow": "#fffa65",
        "panel_border": "#ff9f1a",
        "timeline_fill": "#fffa65"
    },
    "crimson": {
        "id": "crimson",
        "name": "Crimson Fury",
        "primary": "#ff1744",
        "accent": "#ff5252",
        "target": "#ff1744",
        "glow": "#ff6b81",
        "panel_border": "#ff1744",
        "timeline_fill": "#ff4d4d"
    },
    "golden": {
        "id": "golden",
        "name": "Golden Celestial",
        "primary": "#f1c40f",
        "accent": "#f39c12",
        "target": "#f5cd79",
        "glow": "#f7d794",
        "panel_border": "#f1c40f",
        "timeline_fill": "#ffffff"
    },
    "void": {
        "id": "void",
        "name": "Void Phantom",
        "primary": "#7d5fff",
        "accent": "#18dcff",
        "target": "#7158e2",
        "glow": "#c56cf0",
        "panel_border": "#7d5fff",
        "timeline_fill": "#18dcff"
    }
}


class BeatbarSkin:
    """
    Encapsulates all 5 core beatbar components:
    - panel_svg: Main angled panel
    - wing_left_svg: Left wing sigil in corner
    - wing_right_svg: Right wing sigil in corner
    - target_svg: Central target / reticle
    - beat_svg: Approaching beat icon
    plus color palette and skin metadata.
    """

    COMPONENT_KEYS = ["panel", "wing_left", "wing_right", "target", "target_hit", "beat"]
    COMPONENT_FILENAMES = {
        "panel": "panel.svg",
        "wing_left": "wing_left.svg",
        "wing_right": "wing_right.svg",
        "target": "target.svg",
        "target_hit": "target_hit.svg",
        "beat": "beat.svg"
    }
    COMPONENT_LABELS = {
        "panel": "Main Panel",
        "wing_left": "Left Wing",
        "wing_right": "Right Wing",
        "target": "Center Target",
        "target_hit": "Target Hit (2nd State)",
        "beat": "Beats"
    }

    def __init__(self, name: str = "New Custom Skin", author: str = "User"):
        self.name = name
        self.author = author
        self.description = "Custom skin designed with BeatPanel Skin Maker."
        self.version = "1.2.1"
        self.palette = deepcopy(BUILTIN_PALETTES["violet"])

        # Layout transforms (offsets & scale for wings and center target, plus beat flipping)
        self.layout = {
            "wing_left": {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0},
            "wing_right": {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0},
            "target": {"offset_x": 0.0, "offset_y": 0.0, "scale": 1.0},
            "flip_left_beats": False,
            "flip_right_beats": False,
            "timeline_fill_mode": "left_to_right"
        }

        # Trigger hit settings (animation, pop scale, indicator style & color)
        self.trigger_hit = {
            "pop_scale": 1.35,
            "duration_ms": 180,
            "indicator_style": "triangle",  # triangle, diamond, glow_bar, hidden
            "indicator_color": "#ffffff",
            "show_indicator": True
        }

        # Load default base components
        tpl = get_template_library()
        self.components = {
            "panel": tpl["panel"]["Cyber Wings (Default)"],
            "wing_left": tpl["wing_left"]["W-Sigil Metal Left (Default)"],
            "wing_right": tpl["wing_right"]["W-Sigil Metal Right (Default)"],
            "target": tpl["target"]["Demonic Crest Skull (Default)"],
            "target_hit": tpl["target_hit"]["Demonic Crest Skull (Hit Ignited)"],
            "beat": tpl["beat"]["Demonic Crest (Default)"]
        }

    def get_component(self, key: str) -> str:
        return self.components.get(key, "")

    def set_component(self, key: str, svg_content: str):
        if key in self.components:
            self.components[key] = svg_content

    def apply_palette(self, target_palette: dict):
        """
        Translates colors in all components from current palette to target palette.
        """
        old_pal = self.palette
        new_pal = target_palette

        # Build color replacement dictionary
        color_map = {}
        for role in ["primary", "accent", "target", "glow", "panel_border", "timeline_fill"]:
            if role in old_pal and role in new_pal:
                color_map[old_pal[role]] = new_pal[role]

        for k in self.components:
            self.components[k] = replace_multiple_colors(self.components[k], color_map)

        self.palette = deepcopy(new_pal)

    def save_to_folder(self, folder_path: str):
        """Saves skin bundle (skin.json + SVGs) to directory."""
        os.makedirs(folder_path, exist_ok=True)

        meta = {
            "name": self.name,
            "author": self.author,
            "description": self.description,
            "version": self.version,
            "palette": self.palette,
            "layout": self.layout,
            "trigger_hit": self.trigger_hit,
            "components": self.COMPONENT_FILENAMES
        }

        with open(os.path.join(folder_path, "skin.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        for key, fname in self.COMPONENT_FILENAMES.items():
            svg_content = self.components.get(key, "")
            if svg_content:
                with open(os.path.join(folder_path, fname), "w", encoding="utf-8") as f:
                    f.write(format_svg(svg_content))

    def load_from_folder(self, folder_path: str):
        """Loads skin bundle from directory."""
        meta_path = os.path.join(folder_path, "skin.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    self.name = meta.get("name", self.name)
                    self.author = meta.get("author", self.author)
                    self.description = meta.get("description", self.description)
                    self.version = meta.get("version", self.version)
                    if "palette" in meta:
                        self.palette = meta["palette"]
                    if "layout" in meta:
                        self.layout.update(meta["layout"])
                    if "trigger_hit" in meta:
                        self.trigger_hit.update(meta["trigger_hit"])
            except Exception as e:
                print("Error loading skin.json:", e)

        for key, fname in self.COMPONENT_FILENAMES.items():
            fpath = os.path.join(folder_path, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        self.components[key] = f.read()
                except Exception as e:
                    print(f"Error reading {fname}:", e)

    def load_from_beat(self, beat_path: str):
        """Loads skin bundle, SVGs, layout, and trigger hit directly from a .beat archive."""
        import zipfile
        with zipfile.ZipFile(beat_path, "r") as zf:
            namelist = zf.namelist()
            cfg_bytes = None
            if "skin.json" in namelist:
                cfg_bytes = zf.read("skin.json")
            elif "skins/skin.json" in namelist:
                cfg_bytes = zf.read("skins/skin.json")

            if cfg_bytes:
                try:
                    meta = json.loads(cfg_bytes.decode("utf-8"))
                    self.name = meta.get("name", self.name)
                    self.author = meta.get("author", self.author)
                    self.description = meta.get("description", self.description)
                    self.version = meta.get("version", self.version)
                    if "palette" in meta and isinstance(meta["palette"], dict):
                        self.palette = meta["palette"]
                    if "layout" in meta and isinstance(meta["layout"], dict):
                        self.layout.update(meta["layout"])
                    if "trigger_hit" in meta and isinstance(meta["trigger_hit"], dict):
                        self.trigger_hit.update(meta["trigger_hit"])
                except Exception as e:
                    print("Error parsing skin.json in .beat:", e)

            # Load component SVGs
            for key, fname in self.COMPONENT_FILENAMES.items():
                for cand in [fname, f"skins/{fname}"]:
                    if cand in namelist:
                        try:
                            self.components[key] = zf.read(cand).decode("utf-8", errors="replace")
                            break
                        except Exception as e:
                            print(f"Error reading {cand} from .beat:", e)

    def to_skin_config_dict(self) -> dict:
        """Returns JSON-serializable dictionary matching the skin.json specification."""
        return {
            "format": "beat_skin",
            "version": self.version,
            "name": self.name,
            "author": self.author,
            "description": self.description,
            "components": self.COMPONENT_FILENAMES.copy(),
            "palette": deepcopy(self.palette),
            "layout": deepcopy(self.layout),
            "trigger_hit": deepcopy(self.trigger_hit)
        }

    def save_to_beat(self, beat_path: str) -> str:
        """
        Embeds or updates this skin bundle (skin.json + 5 SVGs) directly into a .beat file.
        If file exists, updates skin.json and replaces skin assets while preserving video and beatmap.
        """
        import zipfile
        import tempfile

        skin_cfg = self.to_skin_config_dict()
        cfg_bytes = json.dumps(skin_cfg, indent=2, ensure_ascii=False).encode("utf-8")

        # Map component filenames to formatted SVG content
        component_data = {}
        for key, fname in self.COMPONENT_FILENAMES.items():
            svg_content = self.components.get(key, "")
            component_data[fname] = format_svg(svg_content)

        if os.path.exists(beat_path) and zipfile.is_zipfile(beat_path):
            temp_zip = beat_path + ".tmp"
            with zipfile.ZipFile(beat_path, "r") as zin:
                with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                    skip_entries = set([
                        "skin.json", "skins/skin.json"
                    ] + [f"skins/{fname}" for fname in self.COMPONENT_FILENAMES.values()]
                      + list(self.COMPONENT_FILENAMES.values()))

                    for item in zin.infolist():
                        if item.filename not in skip_entries:
                            zout.writestr(item, zin.read(item.filename))

                    # Write skin.json both at root and in skins/
                    zout.writestr("skin.json", cfg_bytes)
                    zout.writestr("skins/skin.json", cfg_bytes)

                    # Write 5 component SVGs both under skins/ and at root
                    for fname, content in component_data.items():
                        svg_b = content.encode("utf-8")
                        zout.writestr(f"skins/{fname}", svg_b)
                        zout.writestr(fname, svg_b)

                    existing_names = set(zin.namelist())
                    if "manifest.json" not in existing_names:
                        import time
                        manifest = {
                            "format": "beat",
                            "format_version": "1.0",
                            "title": self.name,
                            "video_name": "",
                            "has_embedded_video": False,
                            "has_skin_config": True,
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        }
                        zout.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
                    if "beatmap.json" not in existing_names:
                        dummy_bm = {"beats": [], "zones": [], "version": "1.0", "title": self.name}
                        zout.writestr("beatmap.json", json.dumps(dummy_bm, indent=2).encode("utf-8"))

            os.replace(temp_zip, beat_path)
            return beat_path
        else:
            # Create a new minimal .beat with this skin and 5 component SVGs
            try:
                from beat_format import BeatFormat
            except ImportError:
                from main.beat_format import BeatFormat
            dummy_beatmap = {"beats": [], "zones": [], "version": "1.0", "title": self.name}
            return BeatFormat.create(
                beat_path,
                beatmap_source=dummy_beatmap,
                title=self.name,
                skin_config=skin_cfg,
                extra_skin_data=component_data
            )

    def export_to_viewer(self, viewer_skins_dir: str = None, viewer_config_path: str = None):
        """
        Exports skin assets to viewer so that Beatbar Viewer can use them directly.
        Optionally updates viewer/.config and viewer_config.json to point to the new custom skin.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not viewer_skins_dir:
            assets_skins = os.path.join(base_dir, "assets", "skins")
            viewer_skins_dir = assets_skins if os.path.isdir(assets_skins) else os.path.join(base_dir, "viewer", "skins")
        if not viewer_config_path:
            viewer_config_path = os.path.join(base_dir, "viewer", "viewer_config.json")
        viewer_dot_config = os.path.join(base_dir, "viewer", ".config")

        os.makedirs(viewer_skins_dir, exist_ok=True)

        # Sanitize skin name for filename prefix
        safe_name = "".join(c if c.isalnum() else "_" for c in self.name.lower()).strip("_")
        if not safe_name:
            safe_name = "custom_skin"

        panel_path = os.path.join(viewer_skins_dir, f"{safe_name}_panel.svg")
        target_path = os.path.join(viewer_skins_dir, f"{safe_name}_target.svg")
        target_hit_path = os.path.join(viewer_skins_dir, f"{safe_name}_target_hit.svg")
        beat_path = os.path.join(viewer_skins_dir, f"{safe_name}_beat.svg")
        wing_l_path = os.path.join(viewer_skins_dir, f"{safe_name}_wing_l.svg")
        wing_r_path = os.path.join(viewer_skins_dir, f"{safe_name}_wing_r.svg")

        with open(panel_path, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["panel"]))
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["target"]))
        if self.components.get("target_hit"):
            with open(target_hit_path, "w", encoding="utf-8") as f:
                f.write(format_svg(self.components["target_hit"]))
        with open(beat_path, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["beat"]))
        with open(wing_l_path, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["wing_left"]))
        with open(wing_r_path, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["wing_right"]))

        # Also backup/write directly to default wing sigils if user wants full active replacement
        default_wing_l = os.path.join(viewer_skins_dir, "wing_sigil_left.svg")
        default_wing_r = os.path.join(viewer_skins_dir, "wing_sigil_right.svg")
        with open(default_wing_l, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["wing_left"]))
        with open(default_wing_r, "w", encoding="utf-8") as f:
            f.write(format_svg(self.components["wing_right"]))

        # Ensure viewer/.config exists on fresh installs if neither .config nor viewer_config.json exists
        if not (os.path.exists(viewer_dot_config) or os.path.exists(viewer_config_path)):
            try:
                from viewer.skin_manager import DEFAULT_CONFIG
                initial_cfg = dict(DEFAULT_CONFIG)
            except Exception:
                initial_cfg = {
                    "palette": "violet",
                    "panel_skin": "cyber_wings",
                    "beats_skin": "crest",
                    "target_skin": "crest_gate",
                    "hit_animation": "shockwave"
                }
            try:
                os.makedirs(os.path.dirname(viewer_dot_config), exist_ok=True)
                with open(viewer_dot_config, "w", encoding="utf-8") as f:
                    json.dump(initial_cfg, f, indent=2)
            except Exception as e:
                print(f"Failed to create default {viewer_dot_config}:", e)

        # Update viewer configs (.config and legacy viewer_config.json)
        for cfg_file in [viewer_dot_config, viewer_config_path]:
            if cfg_file and os.path.exists(cfg_file):
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    cfg["panel_skin"] = "custom"
                    cfg["custom_panel_path"] = panel_path
                    cfg["target_skin"] = "custom"
                    cfg["custom_target_path"] = target_path
                    if self.components.get("target_hit"):
                        cfg["custom_target_hit_path"] = target_hit_path
                    cfg["beats_skin"] = "custom"
                    cfg["custom_beat_path"] = beat_path
                    cfg["custom_palette"] = self.palette
                    cfg["palette"] = "custom"

                    # Layout and trigger hit settings
                    cfg["wing_left_offset_x"] = self.layout["wing_left"].get("offset_x", 0.0)
                    cfg["wing_left_offset_y"] = self.layout["wing_left"].get("offset_y", 0.0)
                    cfg["wing_left_scale"] = self.layout["wing_left"].get("scale", 1.0)
                    cfg["wing_right_offset_x"] = self.layout["wing_right"].get("offset_x", 0.0)
                    cfg["wing_right_offset_y"] = self.layout["wing_right"].get("offset_y", 0.0)
                    cfg["wing_right_scale"] = self.layout["wing_right"].get("scale", 1.0)
                    cfg["target_offset_x"] = self.layout["target"].get("offset_x", 0.0)
                    cfg["target_offset_y"] = self.layout["target"].get("offset_y", 0.0)
                    cfg["target_scale"] = self.layout["target"].get("scale", 1.0)
                    cfg["flip_left_beats"] = self.layout.get("flip_left_beats", False)
                    cfg["flip_right_beats"] = self.layout.get("flip_right_beats", False)
                    cfg["trigger_hit_duration_ms"] = self.trigger_hit.get("duration_ms", 180)
                    cfg["trigger_hit_pop_scale"] = self.trigger_hit.get("pop_scale", 1.35)
                    cfg["trigger_hit_indicator_style"] = self.trigger_hit.get("indicator_style", "triangle")
                    cfg["trigger_hit_indicator_color"] = self.trigger_hit.get("indicator_color", "#ffffff")

                    with open(cfg_file, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2)
                except Exception as e:
                    print(f"Failed to update {cfg_file}:", e)

        # Also auto-package/update {safe_name}.beat in assets/skins so that Web Viewer & bundle loaders see it!
        beat_bundle_path = os.path.join(viewer_skins_dir, f"{safe_name}.beat")
        try:
            self.save_to_beat(beat_bundle_path)
            # Also copy to web/skins if that folder exists
            web_skins_dir = os.path.join(base_dir, "web", "skins")
            if os.path.isdir(web_skins_dir) and os.path.abspath(web_skins_dir) != os.path.abspath(viewer_skins_dir):
                import shutil
                shutil.copy2(beat_bundle_path, os.path.join(web_skins_dir, f"{safe_name}.beat"))
        except Exception as e:
            print("Failed to auto-update .beat bundle on export:", e)

        return {
            "panel": panel_path,
            "target": target_path,
            "target_hit": target_hit_path if self.components.get("target_hit") else "",
            "beat": beat_path,
            "wing_left": wing_l_path,
            "wing_right": wing_r_path
        }

    @classmethod
    def create_preset(cls, preset_id: str) -> "BeatbarSkin":
        """Generates a complete pre-configured skin preset."""
        tpl = get_template_library()
        skin = cls()

        if preset_id == "cyber":
            skin.name = "Cyber Synthwave"
            skin.components["panel"] = tpl["panel"].get("Hex Blade Tech", tpl["panel"]["Cyber Wings (Default)"])
            skin.components["wing_left"] = tpl["wing_left"].get("Cyber Blade Left", tpl["wing_left"]["W-Sigil Metal Left (Default)"])
            skin.components["wing_right"] = tpl["wing_right"].get("Cyber Blade Right", tpl["wing_right"]["W-Sigil Metal Right (Default)"])
            skin.components["target"] = tpl["target"].get("Neon Crosshair Reticle", tpl["target"]["Demonic Crest Skull (Default)"])
            skin.components["target_hit"] = tpl["target_hit"].get("Neon Crosshair Reticle (Target Locked)", "")
            skin.components["beat"] = tpl["beat"].get("Neon Diamond", tpl["beat"]["Demonic Crest (Default)"])
            skin.apply_palette(BUILTIN_PALETTES["cyber"])

        elif preset_id == "emerald":
            skin.name = "Emerald Matrix"
            skin.components["beat"] = tpl["beat"].get("Energy Orb", tpl["beat"]["Demonic Crest (Default)"])
            skin.apply_palette(BUILTIN_PALETTES["emerald"])

        elif preset_id == "solar":
            skin.name = "Solar Flare"
            skin.components["beat"] = tpl["beat"].get("Cyber Shard", tpl["beat"]["Demonic Crest (Default)"])
            skin.apply_palette(BUILTIN_PALETTES["solar"])

        elif preset_id == "crimson":
            skin.name = "Crimson Fury"
            skin.apply_palette(BUILTIN_PALETTES["crimson"])

        elif preset_id == "golden":
            skin.name = "Golden Celestial"
            skin.apply_palette(BUILTIN_PALETTES["golden"])

        elif preset_id == "void":
            skin.name = "Void Phantom"
            skin.components["target_hit"] = tpl["target_hit"].get("Demonic Crest Skull (Hit Ignited)", "")
            skin.apply_palette(BUILTIN_PALETTES["void"])

        elif preset_id == "clean":
            skin.name = "Clean Minimal"
            skin.components["panel"] = tpl["panel"].get("Clean Template", tpl["panel"]["Cyber Wings (Default)"])
            skin.components["target"] = tpl["target"].get("Neon Crosshair Reticle", tpl["target"]["Demonic Crest Skull (Default)"])
            skin.components["target_hit"] = tpl["target_hit"].get("Neon Crosshair Reticle (Target Locked)", "")
            skin.components["beat"] = tpl["beat"].get("Neon Diamond", tpl["beat"]["Demonic Crest (Default)"])

        else:  # default violet
            skin.name = "Violet Amethyst (Default)"
            skin.apply_palette(BUILTIN_PALETTES["violet"])

        return skin
