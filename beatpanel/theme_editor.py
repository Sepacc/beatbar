"""
theme_editor.py - Global Theme and Color Palette Management for Beatbar Skin Maker.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QColorDialog, QFrame, QComboBox
)
from PyQt6.QtGui import QColor

from beatpanel.skin_data import BUILTIN_PALETTES
try:
    from icon_utils import get_feather_icon
except (ImportError, ValueError):
    import os, sys
    _p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _d in [_p, os.path.join(_p, "main")]:
        if _d not in sys.path:
            sys.path.insert(0, _d)
    from icon_utils import get_feather_icon


class ThemePaletteWidget(QWidget):
    """
    Global theme color editor for adjusting and applying palettes across all skin SVGs.
    """
    palette_changed = pyqtSignal(dict)  # emitted when a single color or preset changes
    apply_to_all_requested = pyqtSignal()  # request recoloring of all 5 SVGs

    COLOR_ROLES = [
        ("primary", "Primary Color", "Main beat color and prominent accents"),
        ("accent", "Accent Color", "Secondary highlights, wing trims, and details"),
        ("target", "Target Color", "Central target base and reticle elements"),
        ("glow", "Glow & Hit Flare", "Shockwaves, particles, and bright lighting"),
        ("panel_border", "Panel Border", "Outer metallic edge gradient glow"),
        ("timeline_fill", "Timeline Fill", "Progress notch timeline active fill")
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_palette = BUILTIN_PALETTES["violet"].copy()
        self.color_buttons = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with Preset Selector
        header_frame = QFrame(self)
        header_frame.setStyleSheet("""
            QFrame {
                background: #181824;
                border: 1px solid #2e2e40;
                border-radius: 8px;
            }
        """)
        hf_layout = QHBoxLayout(header_frame)
        hf_layout.setContentsMargins(10, 6, 10, 6)

        hf_layout.addWidget(QLabel("Palette Preset:"))
        self.combo_presets = QComboBox()
        for pid, pal in BUILTIN_PALETTES.items():
            self.combo_presets.addItem(pal["name"], pid)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        hf_layout.addWidget(self.combo_presets, stretch=1)

        self.btn_apply_all = QPushButton(" Apply Theme to All SVGs")
        self.btn_apply_all.setIcon(get_feather_icon("check", "#ffffff", 14))
        self.btn_apply_all.setStyleSheet("""
            QPushButton {
                background: #9b51e0;
                border: 1px solid #be2edd;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #b862ff;
            }
        """)
        self.btn_apply_all.clicked.connect(self.apply_to_all_requested.emit)
        hf_layout.addWidget(self.btn_apply_all)

        layout.addWidget(header_frame)

        # Palette Color Pickers Grid
        grid_frame = QFrame(self)
        grid_frame.setStyleSheet("""
            QFrame {
                background: #14141d;
                border: 1px solid #282836;
                border-radius: 8px;
            }
        """)
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setContentsMargins(12, 8, 12, 8)
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(8)

        row = 0
        col = 0
        for role_key, title, desc in self.COLOR_ROLES:
            card = QFrame(self)
            card.setStyleSheet("background: transparent; border: none;")
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(0, 0, 0, 0)
            c_layout.setSpacing(3)

            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 11px;")
            c_layout.addWidget(lbl_title)

            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("color: #7b7b90; font-size: 10px;")
            lbl_desc.setWordWrap(True)
            c_layout.addWidget(lbl_desc)

            btn = QPushButton()
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, r=role_key: self._pick_color(r))
            self.color_buttons[role_key] = btn
            c_layout.addWidget(btn)

            grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        layout.addWidget(grid_frame, stretch=1)

        self._update_button_colors()

    def set_palette(self, palette: dict):
        self.current_palette = palette.copy()
        self._update_button_colors()

    def _update_button_colors(self):
        for role_key, btn in self.color_buttons.items():
            hex_col = self.current_palette.get(role_key, "#be2edd")
            c = QColor(hex_col)
            lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            text_col = "#000000" if lum > 130 else "#ffffff"

            btn.setText(hex_col.upper())
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_col};
                    color: {text_col};
                    border: 1px solid #444458;
                    border-radius: 6px;
                    font-family: monospace;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """)

    def _pick_color(self, role_key: str):
        curr_hex = self.current_palette.get(role_key, "#ffffff")
        new_qcol = QColorDialog.getColor(QColor(curr_hex), self, f"Select {role_key.replace('_', ' ').title()}")
        if new_qcol.isValid():
            self.current_palette[role_key] = new_qcol.name()
            self._update_button_colors()
            self.palette_changed.emit(self.current_palette)

    def _on_preset_selected(self, index: int):
        pid = self.combo_presets.currentData()
        if pid in BUILTIN_PALETTES:
            self.current_palette = BUILTIN_PALETTES[pid].copy()
            self._update_button_colors()
            self.palette_changed.emit(self.current_palette)
