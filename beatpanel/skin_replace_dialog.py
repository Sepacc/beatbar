"""
skin_replace_dialog.py - Side-by-Side Skin Component Replacement Dialog.

Shown when injecting a skin into an existing .beat archive that already contains a skin:
- Side-by-side visual preview of existing vs. new component SVGs
- Checkboxes to choose exactly which components to replace:
  - Panel, Left Wing, Right Wing, Target, Beat Icon, Theme Palette
- Preserves all embedded video and beatmap streams byte-for-byte
- Zero emojis: Clean Feather SVG icons throughout
"""

import os
import sys
import zipfile
import json
from copy import deepcopy
from typing import List, Dict, Set, Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QFrame, QGridLayout, QMessageBox
)
from PyQt6.QtGui import QCursor

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from icon_utils import get_feather_icon
from beatpanel.component_preview import IsolatedComponentCanvas
from beatpanel.svg_utils import format_svg


class ComponentCompareRow(QFrame):
    """Row displaying checkbox, component title, existing SVG preview, arrow, and new SVG preview."""
    def __init__(self, comp_key: str, comp_title: str, existing_svg: str, new_svg: str, parent=None):
        super().__init__(parent)
        self.comp_key = comp_key
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            ComponentCompareRow {
                background: #14141e;
                border: 1px solid #28283a;
                border-radius: 8px;
            }
            ComponentCompareRow:hover {
                border-color: #3e3e58;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(14)

        # 1. Selection Checkbox + Label
        self.checkbox = QCheckBox(comp_title)
        self.checkbox.setChecked(True)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #484860;
                background: #1a1a26;
            }
            QCheckBox::indicator:checked {
                background: #238636;
                border-color: #2ea043;
            }
        """)
        self.checkbox.setFixedWidth(140)
        layout.addWidget(self.checkbox)

        # 2. Existing Preview
        ex_box = QVBoxLayout()
        ex_box.setSpacing(2)
        ex_lbl = QLabel("Existing in .beat")
        ex_lbl.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 600;")
        ex_box.addWidget(ex_lbl)

        self.canvas_existing = IsolatedComponentCanvas(self)
        self.canvas_existing.setFixedSize(130, 65)
        self.canvas_existing.set_svg_content(existing_svg or "")
        ex_box.addWidget(self.canvas_existing)
        layout.addLayout(ex_box)

        # 3. Arrow Indicator
        arrow_lbl = QLabel()
        arrow_lbl.setPixmap(get_feather_icon("arrow-right", "#be2edd", 18).pixmap(18, 18))
        layout.addWidget(arrow_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # 4. New Preview
        new_box = QVBoxLayout()
        new_box.setSpacing(2)
        new_lbl = QLabel("New to Inject")
        new_lbl.setStyleSheet("color: #e056fd; font-size: 10px; font-weight: 600;")
        new_box.addWidget(new_lbl)

        self.canvas_new = IsolatedComponentCanvas(self)
        self.canvas_new.setFixedSize(130, 65)
        self.canvas_new.set_svg_content(new_svg or "")
        new_box.addWidget(self.canvas_new)
        layout.addLayout(new_box)

        layout.addStretch()

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, val: bool):
        self.checkbox.setChecked(val)


class SkinReplaceDialog(QDialog):
    """
    Side-by-side comparison modal allowing selective component replacement.
    """
    COMPONENTS_DEF = [
        ("panel", "Center Panel"),
        ("wing_left", "Left Wing"),
        ("wing_right", "Right Wing"),
        ("target", "Target Reticle"),
        ("beat", "Beat Icon")
    ]

    def __init__(self, beat_path: str, existing_skin: dict, new_skin_data, parent=None):
        super().__init__(parent)
        self.beat_path = beat_path
        self.existing_skin = existing_skin
        self.new_skin = new_skin_data
        self.rows: Dict[str, ComponentCompareRow] = {}

        self.setWindowTitle(f"Replace Skin in {os.path.basename(beat_path)}")
        self.setFixedSize(620, 560)
        self.setStyleSheet("""
            QDialog {
                background: #0d0d14;
                border: 1px solid #2d2d40;
                border-radius: 10px;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 1. Header
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_feather_icon("layers", "#e056fd", 22).pixmap(22, 22))
        hdr.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_t = QLabel(f"Skin Conflict: {os.path.basename(self.beat_path)}")
        lbl_t.setStyleSheet("color: #ffffff; font-size: 13.5px; font-weight: bold;")
        lbl_s = QLabel("This .beat archive already contains a skin. Choose which components to replace:")
        lbl_s.setStyleSheet("color: #8b949e; font-size: 11px;")
        title_box.addWidget(lbl_t)
        title_box.addWidget(lbl_s)
        hdr.addLayout(title_box)

        hdr.addStretch()
        root.addLayout(hdr)

        # Quick selection bar
        sel_bar = QHBoxLayout()
        sel_bar.setSpacing(8)

        btn_all = QPushButton("Select All")
        btn_all.setFixedHeight(24)
        btn_all.setIcon(get_feather_icon("check-square", "#c9d1d9", 11))
        btn_all.setStyleSheet("background: #1c1c28; border: 1px solid #36364a; color: #c9d1d9; font-size: 10.5px; border-radius: 4px; padding: 2px 8px;")
        btn_all.clicked.connect(lambda: self._set_all_selected(True))
        sel_bar.addWidget(btn_all)

        btn_none = QPushButton("Deselect All")
        btn_none.setFixedHeight(24)
        btn_none.setIcon(get_feather_icon("square", "#c9d1d9", 11))
        btn_none.setStyleSheet("background: #1c1c28; border: 1px solid #36364a; color: #c9d1d9; font-size: 10.5px; border-radius: 4px; padding: 2px 8px;")
        btn_none.clicked.connect(lambda: self._set_all_selected(False))
        sel_bar.addWidget(btn_none)

        sel_bar.addStretch()
        root.addLayout(sel_bar)

        # 2. Scroll area with component rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_content = QWidget()
        rows_layout = QVBoxLayout(scroll_content)
        rows_layout.setContentsMargins(0, 0, 4, 0)
        rows_layout.setSpacing(8)

        ex_comps = self.existing_skin.get("components", {})
        new_comps = getattr(self.new_skin, "components", {})

        for key, title in self.COMPONENTS_DEF:
            ex_svg = ex_comps.get(key, "")
            new_svg = new_comps.get(key, "")
            row = ComponentCompareRow(key, title, ex_svg, new_svg, scroll_content)
            self.rows[key] = row
            rows_layout.addWidget(row)

        scroll.setWidget(scroll_content)
        root.addWidget(scroll)

        # Palette & Settings Checkbox
        self.cb_palette = QCheckBox("Replace Color Palette & Theme Configuration")
        self.cb_palette.setChecked(True)
        self.cb_palette.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                font-weight: 600;
                font-size: 11.5px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #484860;
                background: #1a1a26;
            }
            QCheckBox::indicator:checked {
                background: #238636;
                border-color: #2ea043;
            }
        """)
        root.addWidget(self.cb_palette)

        # 3. Action Buttons
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(30)
        btn_cancel.setIcon(get_feather_icon("x", "#c9d1d9", 12))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #1f1f2c;
                border: 1px solid #36364a;
                border-radius: 6px;
                color: #c9d1d9;
                font-size: 11.5px;
                padding: 4px 14px;
            }
            QPushButton:hover { background: #2d2d3e; color: #ffffff; }
        """)
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        btn_confirm = QPushButton("Confirm Replacement")
        btn_confirm.setFixedHeight(30)
        btn_confirm.setIcon(get_feather_icon("check", "#ffffff", 13))
        btn_confirm.setStyleSheet("""
            QPushButton {
                background: #238636;
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 11.5px;
                font-weight: bold;
                padding: 4px 18px;
            }
            QPushButton:hover { background: #2ea043; }
        """)
        btn_confirm.clicked.connect(self.accept)
        actions.addWidget(btn_confirm)

        root.addLayout(actions)

    def _set_all_selected(self, val: bool):
        for r in self.rows.values():
            r.set_selected(val)

    def get_selected_components(self) -> Set[str]:
        return {key for key, r in self.rows.items() if r.is_selected()}

    def should_replace_palette(self) -> bool:
        return self.cb_palette.isChecked()


def inspect_beat_skin(beat_path: str) -> Optional[dict]:
    """
    Inspects a .beat archive. If it contains a skin, returns dict with config and component SVGs.
    Otherwise returns None.
    """
    if not os.path.exists(beat_path) or not zipfile.is_zipfile(beat_path):
        return None

    try:
        with zipfile.ZipFile(beat_path, "r") as z:
            namelist = z.namelist()
            has_skin_json = "skin.json" in namelist or "skins/skin.json" in namelist
            has_svg = any(n.endswith(".svg") for n in namelist)

            if not has_skin_json and not has_svg:
                return None

            skin_dict = {
                "name": os.path.splitext(os.path.basename(beat_path))[0],
                "author": "User",
                "palette": {},
                "components": {}
            }

            # Read skin.json
            for cand in ["skin.json", "skins/skin.json"]:
                if cand in namelist:
                    try:
                        cfg = json.loads(z.read(cand).decode("utf-8", errors="replace"))
                        skin_dict["name"] = cfg.get("name", skin_dict["name"])
                        skin_dict["author"] = cfg.get("author", skin_dict["author"])
                        skin_dict["palette"] = cfg.get("palette", {})
                        break
                    except Exception:
                        pass

            # Read component SVGs
            fn_map = {
                "panel": ["panel_template.svg", "panel.svg", "panel_cyber_wings.svg", "skins/panel_template.svg", "skins/panel.svg"],
                "wing_left": ["wing_left.svg", "wing_sigil_left.svg", "skins/wing_left.svg", "skins/wing_sigil_left.svg"],
                "wing_right": ["wing_right.svg", "wing_sigil_right.svg", "skins/wing_right.svg", "skins/wing_sigil_right.svg"],
                "target": ["target.svg", "crest_target.svg", "skins/target.svg", "skins/crest_target.svg"],
                "beat": ["beat.svg", "crest_beat.svg", "diamond_beat.svg", "orb_beat.svg", "skins/beat.svg", "skins/crest_beat.svg"]
            }

            for role, cands in fn_map.items():
                for c in cands:
                    if c in namelist:
                        try:
                            skin_dict["components"][role] = z.read(c).decode("utf-8", errors="replace")
                            break
                        except Exception:
                            pass

            return skin_dict
    except Exception:
        return None


def inject_skin_into_beat_file(beat_path: str, new_skin, selected_keys: Set[str], replace_palette: bool = True) -> bool:
    """
    Atomically updates the .beat archive, replacing only the selected component SVGs
    and palette/settings, while strictly preserving embedded video, audio, and beatmaps.
    """
    if not os.path.exists(beat_path) or not zipfile.is_zipfile(beat_path):
        return False

    temp_path = beat_path + ".tmp"
    try:
        with zipfile.ZipFile(beat_path, "r") as zin:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                # Build replacement dictionary of filename -> content
                replace_files = {}
                for role in selected_keys:
                    fname = new_skin.COMPONENT_FILENAMES.get(role)
                    if fname and role in new_skin.components:
                        formatted = format_svg(new_skin.components[role])
                        b = formatted.encode("utf-8")
                        replace_files[fname] = b
                        replace_files[f"skins/{fname}"] = b

                # Copy existing items unless targeted for replacement
                for item in zin.infolist():
                    if item.filename in replace_files:
                        continue
                    if item.filename in ["skin.json", "skins/skin.json"] and replace_palette:
                        continue
                    zout.writestr(item, zin.read(item.filename))

                # Write replacement component SVGs
                for fname, content_bytes in replace_files.items():
                    zout.writestr(fname, content_bytes)

                # Write updated skin.json
                if replace_palette:
                    skin_cfg = new_skin.to_skin_config_dict()
                    cfg_bytes = json.dumps(skin_cfg, indent=2, ensure_ascii=False).encode("utf-8")
                    zout.writestr("skin.json", cfg_bytes)
                    zout.writestr("skins/skin.json", cfg_bytes)

        os.replace(temp_path, beat_path)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"Error injecting skin into {beat_path}:", e)
        return False
