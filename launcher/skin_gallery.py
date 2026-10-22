"""
skin_gallery.py - Skin Picker & Viewer Gallery Tab for Suite Launcher.

Features:
- Scans skins across assets/skins, viewer/skins, and web/skins
- Source badge indicators: "Viewer", "Web", "Assets", or "Shared (Merged)"
- Source filter and intelligent deduplication to prevent duplicate entries
- 4-Color palette preview swatches and component list badges
- Direct 1-click actions: "Activate in Viewer" and "Edit in Skin Maker"
- Zero emojis: Clean Feather SVG icons throughout
"""

import os
import sys
import zipfile
import json
from typing import List, Dict, Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QScrollArea, QFrame, QPushButton, QGridLayout, QMessageBox
)
from PyQt6.QtGui import QCursor, QColor, QFont, QPixmap

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(ROOT_DIR, "main")
for p in [ROOT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from icon_utils import get_feather_icon
from launcher.process_manager import process_manager


class SkinCard(QFrame):
    """Visual card representing a theme/skin pack with source badge and palette swatches."""
    activate_requested = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)

    def __init__(self, skin_data: dict, parent=None):
        super().__init__(parent)
        self.data = skin_data
        self.setObjectName("SkinCard")
        self.setStyleSheet("""
            QFrame#SkinCard {
                background-color: #161b22;
                border: none;
                border-radius: 8px;
            }
            QFrame#SkinCard:hover {
                background-color: #1c2128;
                border: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header Row: Title + Source Badge
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        name_lbl = QLabel(skin_data.get("name", "Unknown Skin"))
        name_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        author_lbl = QLabel(f"by {skin_data.get('author', 'User')}")
        author_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
        title_box.addWidget(name_lbl)
        title_box.addWidget(author_lbl)
        hdr.addLayout(title_box)

        hdr.addStretch()

        # Source Badge
        sources = skin_data.get("sources", [])
        if len(sources) > 1:
            badge_text = "Shared (" + " + ".join(sources) + ")"
            badge_color = "#00f3ff"
            badge_bg = "rgba(0, 243, 255, 0.12)"
        else:
            src = sources[0] if sources else "Local"
            badge_text = src
            badge_color = "#58a6ff" if src == "Web" else "#a371f7"
            badge_bg = "rgba(88, 166, 255, 0.12)" if src == "Web" else "rgba(163, 113, 247, 0.12)"

        badge_lbl = QLabel(badge_text)
        badge_lbl.setStyleSheet(f"""
            color: {badge_color};
            background-color: {badge_bg};
            border: none;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            padding: 2px 8px;
        """)
        hdr.addWidget(badge_lbl)

        layout.addLayout(hdr)

        # Description
        desc = skin_data.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #c9d1d9; font-size: 11px;")
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)

        # Color Palette Swatches
        palette = skin_data.get("palette", {})
        if palette:
            p_layout = QHBoxLayout()
            p_layout.setSpacing(6)
            for role in ["primary", "accent", "target", "glow"]:
                col_hex = palette.get(role, "#ffffff")
                swatch = QLabel()
                swatch.setFixedSize(16, 16)
                swatch.setStyleSheet(f"""
                    background-color: {col_hex};
                    border: none;
                    border-radius: 8px;
                """)
                swatch.setToolTip(f"{role.capitalize()}: {col_hex}")
                p_layout.addWidget(swatch)

            p_label = QLabel(palette.get("name", "Custom Palette"))
            p_label.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 600; margin-left: 4px;")
            p_layout.addWidget(p_label)
            p_layout.addStretch()
            layout.addLayout(p_layout)

        # Components Row
        comps = skin_data.get("components", [])
        if comps:
            c_layout = QHBoxLayout()
            c_layout.setSpacing(4)
            for c in comps[:5]:
                comp_lbl = QLabel(c.replace("_", " "))
                comp_lbl.setStyleSheet("""
                    background: rgba(255, 255, 255, 0.05);
                    border: none;
                    border-radius: 4px;
                    color: #8b949e;
                    font-size: 9.5px;
                    padding: 1px 6px;
                """)
                c_layout.addWidget(comp_lbl)
            c_layout.addStretch()
            layout.addLayout(c_layout)

        layout.addStretch()

        # Action Buttons Row
        actions = QHBoxLayout()
        actions.setSpacing(8)

        btn_activate = QPushButton("Activate in Viewer")
        btn_activate.setFixedHeight(26)
        btn_activate.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_activate.setIcon(get_feather_icon("check", "#ffffff", 12))
        btn_activate.setStyleSheet("""
            QPushButton {
                background: #238636;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover { background: #2ea043; }
        """)
        btn_activate.clicked.connect(lambda: self.activate_requested.emit(self.data))
        actions.addWidget(btn_activate)

        btn_edit = QPushButton("Edit in Skin Maker")
        btn_edit.setFixedHeight(26)
        btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_edit.setIcon(get_feather_icon("tool", "#c9d1d9", 12))
        btn_edit.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #c9d1d9;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: #30363d;
                color: #ffffff;
            }
        """)
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.data))
        actions.addWidget(btn_edit)

        layout.addLayout(actions)


class SkinGalleryWidget(QWidget):
    """
    Skin Picker & Viewer Gallery Tab: scans, deduplicates, and manages skins.
    """
    skin_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_skins: List[dict] = []
        self.display_skins: List[dict] = []

        self._init_ui()
        self.scan_skins()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Controls Row: Search + Source Filter + Rescan
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(10)

        # Search Input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search skins by name or author...")
        self.search_input.setFixedHeight(30)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #ffffff;
                padding: 0 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        self.search_input.textChanged.connect(self._apply_filters)
        ctrl_bar.addWidget(self.search_input)

        # Source Filter
        self.cb_source = QComboBox()
        self.cb_source.setFixedHeight(30)
        self.cb_source.addItems([
            "Deduplicated (Best Match)",
            "All Sources (Include Duplicates)",
            "Assets Only",
            "Web Only",
            "Viewer Only"
        ])
        self.cb_source.setStyleSheet("""
            QComboBox {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 0 10px;
                font-size: 11.5px;
                font-weight: 500;
            }
            QComboBox:hover { border-color: #58a6ff; }
            QComboBox QAbstractItemView {
                background: #161b22;
                color: #ffffff;
                selection-background-color: #1f6feb;
            }
        """)
        self.cb_source.currentIndexChanged.connect(self._apply_filters)
        ctrl_bar.addWidget(self.cb_source)

        # Rescan Button
        self.btn_rescan = QPushButton("Rescan Skins")
        self.btn_rescan.setFixedHeight(30)
        self.btn_rescan.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_rescan.setIcon(get_feather_icon("refresh-cw", "#c9d1d9", 13))
        self.btn_rescan.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #c9d1d9;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11.5px;
                font-weight: 600;
            }
            QPushButton:hover { background: #30363d; color: #ffffff; }
        """)
        self.btn_rescan.clicked.connect(self.scan_skins)
        ctrl_bar.addWidget(self.btn_rescan)

        layout.addLayout(ctrl_bar)

        # Scroll Area for Grid of Skin Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.scroll_content = QWidget()
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_layout.setSpacing(12)

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

    def scan_skins(self):
        """Scans assets/skins, viewer/skins, and web/skins for skin packs."""
        search_dirs = [
            (os.path.join(ROOT_DIR, "assets", "skins"), "Assets"),
            (os.path.join(ROOT_DIR, "viewer", "skins"), "Viewer"),
            (os.path.join(ROOT_DIR, "web", "skins"), "Web"),
        ]

        found = []
        for dir_path, src_label in search_dirs:
            if not os.path.isdir(dir_path):
                continue
            for fname in os.listdir(dir_path):
                if not fname.lower().endswith(".beat"):
                    continue
                fpath = os.path.join(dir_path, fname)
                skin_id = os.path.splitext(fname)[0]

                meta = {
                    "id": skin_id,
                    "filename": fname,
                    "filepath": fpath,
                    "source": src_label,
                    "name": skin_id.replace("_", " ").title(),
                    "author": "User",
                    "description": "",
                    "palette": {},
                    "components": []
                }

                try:
                    with zipfile.ZipFile(fpath, "r") as z:
                        namelist = z.namelist()
                        # Read manifest / skin.json
                        if "skin.json" in namelist:
                            cfg = json.loads(z.read("skin.json").decode("utf-8"))
                            meta["name"] = cfg.get("name", meta["name"])
                            meta["author"] = cfg.get("author", meta["author"])
                            meta["description"] = cfg.get("description", "")
                            meta["palette"] = cfg.get("palette", {})
                        elif "manifest.json" in namelist:
                            cfg = json.loads(z.read("manifest.json").decode("utf-8"))
                            if "skin" in cfg:
                                s = cfg["skin"]
                                meta["name"] = s.get("name", meta["name"])
                                meta["author"] = s.get("author", meta["author"])
                                meta["description"] = s.get("description", "")
                                meta["palette"] = s.get("palette", {})

                        # Inspect component roles
                        comps = set()
                        for n in namelist:
                            low = n.lower()
                            if "beat" in low: comps.add("beat")
                            if "target" in low: comps.add("target")
                            if "panel" in low: comps.add("panel")
                            if "wing" in low: comps.add("wings")
                        meta["components"] = sorted(list(comps))
                except Exception:
                    pass

                found.append(meta)

        self.raw_skins = found
        self._apply_filters()

    def _apply_filters(self):
        query = self.search_input.text().strip().lower()
        mode = self.cb_source.currentText()

        # 1. Filter by source or deduplicate
        if mode == "Deduplicated (Best Match)":
            # Group by skin ID / name to deduplicate
            merged_dict = {}
            for s in self.raw_skins:
                k = s["id"]
                if k not in merged_dict:
                    entry = dict(s)
                    entry["sources"] = [s["source"]]
                    merged_dict[k] = entry
                else:
                    if s["source"] not in merged_dict[k]["sources"]:
                        merged_dict[k]["sources"].append(s["source"])
            pool = list(merged_dict.values())
        elif mode == "Assets Only":
            pool = [dict(s, sources=[s["source"]]) for s in self.raw_skins if s["source"] == "Assets"]
        elif mode == "Web Only":
            pool = [dict(s, sources=[s["source"]]) for s in self.raw_skins if s["source"] == "Web"]
        elif mode == "Viewer Only":
            pool = [dict(s, sources=[s["source"]]) for s in self.raw_skins if s["source"] == "Viewer"]
        else:  # All Sources
            pool = [dict(s, sources=[s["source"]]) for s in self.raw_skins]

        # 2. Text Search
        filtered = []
        for s in pool:
            if query and query not in s["name"].lower() and query not in s["author"].lower():
                continue
            filtered.append(s)

        self.display_skins = filtered
        self._render_grid()

    def _render_grid(self):
        # Clear existing cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        cols = 2
        for idx, s in enumerate(self.display_skins):
            row = idx // cols
            col = idx % cols
            card = SkinCard(s, self.scroll_content)
            card.activate_requested.connect(self._on_activate_skin)
            card.edit_requested.connect(self._on_edit_skin)
            self.grid_layout.addWidget(card, row, col)

    def _on_activate_skin(self, data: dict):
        fpath = data.get("filepath", "")
        skin_id = data.get("id", "")
        name = data.get("name", skin_id)
        try:
            from viewer.skin_manager import SkinManager
            mgr = SkinManager()
            success = False
            if skin_id == "cyber_wings":
                success = mgr.apply_bundle(skin_id)
            elif fpath and os.path.exists(fpath):
                res = mgr.load_beat_skin(fpath)
                success = (res is not None)
            elif skin_id in mgr.config.get("loaded_skin_bundles", {}):
                success = mgr.apply_bundle(skin_id)

            if success:
                QMessageBox.information(self, "Skin Activated", f"Skin '{name}' is now active for Beatbar Viewer!")
            else:
                QMessageBox.warning(self, "Activation Failed", f"Could not activate skin '{name}'. Check that it contains valid visual assets.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to activate skin: {e}")

    def _on_edit_skin(self, data: dict):
        fpath = data.get("filepath", "")
        process_manager.launch_program("skin_maker", extra_args=[fpath])
