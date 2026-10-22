"""
skin_maker_window.py - Main Window for BeatPanel Skin Maker & Previewer Application.
"""

import os
import json
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTabWidget, QFileDialog, QMessageBox, QFrame,
    QStatusBar, QSplitter, QMenu
)
from PyQt6.QtGui import QIcon, QFont

from beatpanel.skin_data import BeatbarSkin, BUILTIN_PALETTES
from beatpanel.beatbar_preview import BeatBarPreviewWidget
from beatpanel.component_editor_widget import ComponentEditorWidget
from beatpanel.theme_editor import ThemePaletteWidget
from beatpanel.skin_replace_dialog import SkinReplaceDialog, inspect_beat_skin, inject_skin_into_beat_file
try:
    from icon_utils import get_feather_icon
except (ImportError, ValueError):
    import os, sys
    _p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _d in [_p, os.path.join(_p, "main")]:
        if _d not in sys.path:
            sys.path.insert(0, _d)
    from icon_utils import get_feather_icon

BEATPANEL_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BEATPANEL_DIR)
CONFIG_PATH = os.path.join(BEATPANEL_DIR, ".config")

DEFAULT_BEATPANEL_CONFIG = {
    "window_width": 990,
    "window_height": 720,
    "window_x": None,
    "window_y": None,
    "is_maximized": False,
    "splitter_sizes": [180, 480],
    "active_tab": 0,
    "last_preset": "violet",
    "last_folder": ""
}


class SkinMakerWindow(QMainWindow):
    """
    Main Application Window for BeatPanel Beatbar Skin Maker.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BeatBar Skin Maker")
        try:
            from icon_utils import get_suite_icon
            s_ico = get_suite_icon("beatbar-skins", size=32)
            if s_ico and not s_ico.isNull():
                self.setWindowIcon(s_ico)
        except Exception:
            pass
        self.setMinimumSize(850, 560)

        self.config = self._load_config()
        self.current_skin = BeatbarSkin()
        self.component_editors = {}

        self._geom_autosave_timer = QTimer(self)
        self._geom_autosave_timer.setSingleShot(True)
        self._geom_autosave_timer.setInterval(600)
        self._geom_autosave_timer.timeout.connect(self._save_config)

        self._apply_dark_theme()
        self._build_ui()
        self._apply_saved_settings()
        self._load_skin_into_ui()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #101017;
            }
            QWidget {
                color: #e4e4ee;
                font-family: 'Segoe UI', sans-serif;
            }
            QTabWidget::pane {
                border: none;
                background: #14141d;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #1a1a24;
                color: #9090a8;
                padding: 6px 14px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 600;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #242436;
                color: #ffffff;
                border-bottom: 2px solid #be2edd;
            }
            QTabBar::tab:hover {
                color: #ffffff;
                background: #1f1f2c;
            }
            QPushButton {
                background: #222230;
                border: 1px solid #36364a;
                border-radius: 6px;
                color: #ffffff;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #303044;
                border-color: #9b51e0;
            }
            QPushButton:pressed {
                background: #181822;
            }
            QPushButton::menu-indicator {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 5px;
                width: 8px;
                height: 8px;
            }
            QLineEdit, QComboBox {
                background: #181824;
                border: 1px solid #343448;
                border-radius: 6px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #be2edd;
            }
            QComboBox QAbstractItemView {
                background: #181824;
                border: 1px solid #343448;
                color: #ffffff;
                selection-background-color: #9b51e0;
            }
            QStatusBar {
                background: #0d0d12;
                color: #7b7b92;
                border-top: 1px solid #20202c;
                font-size: 11px;
            }
        """)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # ----------------------------------------------------------------------
        # 1. TOP HEADER TOOLBAR (Clean 2-row layout for 1366x768 & compact screens)
        # ----------------------------------------------------------------------
        top_bar = QFrame(self)
        top_bar.setStyleSheet("""
            QFrame#skin_top_bar {
                background: #161622;
                border: 1px solid #252538;
                border-radius: 8px;
            }
        """)
        top_bar.setObjectName("skin_top_bar")
        tb_layout = QVBoxLayout(top_bar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(6)

        # ------------------ Row 1: Brand, File Lifecycle & Export to Viewer ------------------
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)

        # Title / Brand with BeatBar Skin Maker icon
        try:
            from icon_utils import get_suite_pixmap
            brand_icon = QLabel()
            s_pm = get_suite_pixmap("beatbar-skins", size=22, dark_mode=True)
            if s_pm and not s_pm.isNull():
                brand_icon.setPixmap(s_pm)
                brand_icon.setFixedSize(22, 22)
                row1.addWidget(brand_icon)
        except Exception:
            pass

        lbl_brand = QLabel("BEATBAR")
        lbl_brand.setStyleSheet("font-size: 13px; font-weight: bold; color: #ed8139; letter-spacing: 1px;")
        row1.addWidget(lbl_brand)

        lbl_sub = QLabel("Skin Maker")
        lbl_sub.setStyleSheet("font-size: 11px; color: #a0a0b8; margin-right: 6px; font-weight: 600;")
        row1.addWidget(lbl_sub)

        # File actions: New
        self.btn_new = QPushButton(" New")
        self.btn_new.setIcon(get_feather_icon("file-plus", "#ffffff", 14))
        self.btn_new.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        self.btn_new.setToolTip("Create a new blank skin bundle")
        self.btn_new.clicked.connect(self._on_new_skin)
        row1.addWidget(self.btn_new)

        # Dropdown button style with compact, modern chevron indicator matching feather icons
        chev_norm_path = os.path.join(ROOT_DIR, "assets", "feather", "chevron-down-small.svg").replace("\\", "/")
        chev_hover_path = os.path.join(ROOT_DIR, "assets", "feather", "chevron-down-hover.svg").replace("\\", "/")
        dropdown_btn_style = f"""
            QPushButton {{
                background: #222230;
                border: 1px solid #36364a;
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 18px 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #303044;
                border-color: #9b51e0;
            }}
            QPushButton::menu-indicator {{
                image: url("{chev_norm_path}");
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 5px;
                width: 8px;
                height: 8px;
            }}
            QPushButton::menu-indicator:hover {{
                image: url("{chev_hover_path}");
            }}
        """

        # File actions: Open... (with menu for .beat bundle and unpacked folder)
        self.btn_open = QPushButton(" Open...")
        self.btn_open.setIcon(get_feather_icon("folder", "#ffffff", 14))
        self.btn_open.setStyleSheet(dropdown_btn_style)
        self.btn_open.setToolTip("Open skin from .beat bundle archive, skin.json, or loose folder")

        open_menu = QMenu(self)
        open_menu.setStyleSheet("""
            QMenu {
                background: #181824;
                border: 1px solid #343448;
                color: #ffffff;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #be2edd;
                color: #ffffff;
            }
        """)
        act_open_bundle = open_menu.addAction(get_feather_icon("package", "#ffffff", 14), "Open Skin Bundle (.beat, .json)...")
        act_open_folder = open_menu.addAction(get_feather_icon("folder", "#ffffff", 14), "Open Unpacked Skin Folder...")
        act_open_bundle.triggered.connect(self._on_open_skin_file)
        act_open_folder.triggered.connect(self._on_open_skin_folder)
        self.btn_open.setMenu(open_menu)
        self.btn_load_beat = self.btn_open
        row1.addWidget(self.btn_open)

        # Save... (with menu for .beat bundle and loose folder)
        self.btn_save = QPushButton(" Save...")
        self.btn_save.setIcon(get_feather_icon("save", "#ffffff", 14))
        self.btn_save.setStyleSheet(dropdown_btn_style)
        self.btn_save.setToolTip("Save skin bundle into a standalone .beat file or export unpacked folder")

        save_menu = QMenu(self)
        save_menu.setStyleSheet("""
            QMenu {
                background: #181824;
                border: 1px solid #343448;
                color: #ffffff;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #be2edd;
                color: #ffffff;
            }
        """)
        act_save_beat = save_menu.addAction(get_feather_icon("package", "#ffffff", 14), "Save as .beat Bundle (Recommended)...")
        act_save_folder = save_menu.addAction(get_feather_icon("folder", "#ffffff", 14), "Export Unpacked Folder...")
        act_save_beat.triggered.connect(self._on_pack_to_beat)
        act_save_folder.triggered.connect(self._on_save_skin)
        self.btn_save.setMenu(save_menu)
        self.btn_pack_beat = self.btn_save
        row1.addWidget(self.btn_save)

        # Inject into existing .beat pack button
        self.btn_inject_beat = QPushButton(" Inject .beat...")
        self.btn_inject_beat.setIcon(get_feather_icon("layers", "#ffffff", 14))
        self.btn_inject_beat.setToolTip("Add or selectively replace skins in an existing .beat file with side-by-side preview")
        self.btn_inject_beat.setStyleSheet("""
            QPushButton {
                background: #10b981;
                border: 1px solid #34d399;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        self.btn_inject_beat.clicked.connect(self._on_inject_into_beat)
        row1.addWidget(self.btn_inject_beat)

        row1.addStretch(1)

        # Export to Viewer button (Prominent on top row, guaranteed no clipping)
        self.btn_export_viewer = QPushButton(" Export to Viewer")
        self.btn_export_viewer.setMinimumWidth(130)
        self.btn_export_viewer.setIcon(get_feather_icon("send", "#ffffff", 14))
        self.btn_export_viewer.setToolTip("Instantly export and activate this skin in Beatbar Viewer (viewer_config.json)")
        self.btn_export_viewer.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #be2edd, stop:1 #9b51e0);
                border: 1px solid #e056fd;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                padding: 5px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d434ef, stop:1 #ae5cf0);
                border-color: #f472b6;
            }
        """)
        self.btn_export_viewer.clicked.connect(self._on_export_to_viewer)
        row1.addWidget(self.btn_export_viewer)

        tb_layout.addLayout(row1)

        # ------------------ Row 2: Presets & Skin Metadata ------------------
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        # Presets Dropdown
        lbl_preset = QLabel("Preset:")
        lbl_preset.setStyleSheet("font-size: 12px; font-weight: 600; color: #d0d0e0;")
        row2.addWidget(lbl_preset)
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("Violet Amethyst (Default)", "violet")
        self.combo_presets.addItem("Cyber Synthwave", "cyber")
        self.combo_presets.addItem("Emerald Matrix", "emerald")
        self.combo_presets.addItem("Solar Flare", "solar")
        self.combo_presets.addItem("Crimson Fury", "crimson")
        self.combo_presets.addItem("Golden Celestial", "golden")
        self.combo_presets.addItem("Void Phantom", "void")
        self.combo_presets.addItem("Clean Minimal", "clean")
        self.combo_presets.setMinimumWidth(160)
        self.combo_presets.setMaximumWidth(220)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        row2.addWidget(self.combo_presets)

        # Skin Name Edit
        lbl_name = QLabel("Name:")
        lbl_name.setStyleSheet("font-size: 12px; font-weight: 600; color: #d0d0e0;")
        row2.addWidget(lbl_name)
        self.edit_skin_name = QLineEdit(self.current_skin.name)
        self.edit_skin_name.setMinimumWidth(130)
        self.edit_skin_name.setMaximumWidth(220)
        self.edit_skin_name.setToolTip("Skin display name.")
        self.edit_skin_name.textChanged.connect(self._on_skin_name_changed)
        row2.addWidget(self.edit_skin_name)

        # Skin Author Edit
        lbl_author = QLabel("Author:")
        lbl_author.setStyleSheet("font-size: 12px; font-weight: 600; color: #d0d0e0;")
        row2.addWidget(lbl_author)
        initial_author = self.config.get("default_author") or getattr(self.current_skin, 'author', 'User')
        self.edit_skin_author = QLineEdit(initial_author)
        self.edit_skin_author.setMinimumWidth(75)
        self.edit_skin_author.setMaximumWidth(120)
        self.edit_skin_author.setToolTip("Author name saved into skin metadata.")
        self.edit_skin_author.textChanged.connect(self._on_skin_author_changed)
        row2.addWidget(self.edit_skin_author)

        row2.addStretch(1)

        tb_layout.addLayout(row2)

        main_layout.addWidget(top_bar)

        # Splitter between Preview and Component Editors
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)

        # ----------------------------------------------------------------------
        # 2. CENTER SECTION: LIVE BEATBAR PREVIEW
        # ----------------------------------------------------------------------
        self.preview_widget = BeatBarPreviewWidget(self)
        self.splitter.addWidget(self.preview_widget)

        # ----------------------------------------------------------------------
        # 3. BOTTOM SECTION: COMPONENT EDITORS TABS
        # ----------------------------------------------------------------------
        self.tabs = QTabWidget(self)

        # Tab: Main Panel
        self.tab_panel = ComponentEditorWidget("panel", self)
        self.tab_panel.svg_modified.connect(self._on_component_svg_modified)
        self.tabs.addTab(self.tab_panel, get_feather_icon("square", "#00f3ff", 14), "Main Panel")
        self.component_editors["panel"] = self.tab_panel

        # Tab: Left Wing
        self.tab_wing_left = ComponentEditorWidget("wing_left", self)
        self.tab_wing_left.svg_modified.connect(self._on_component_svg_modified)
        self.tab_wing_left.layout_modified.connect(self._on_layout_modified)
        self.tab_wing_left.request_mirror_to_opposite.connect(self._on_mirror_wing)
        self.tabs.addTab(self.tab_wing_left, get_feather_icon("chevron-left", "#00f3ff", 14), "Left Wing")
        self.component_editors["wing_left"] = self.tab_wing_left

        # Tab: Right Wing
        self.tab_wing_right = ComponentEditorWidget("wing_right", self)
        self.tab_wing_right.svg_modified.connect(self._on_component_svg_modified)
        self.tab_wing_right.layout_modified.connect(self._on_layout_modified)
        self.tab_wing_right.request_mirror_to_opposite.connect(self._on_mirror_wing)
        self.tabs.addTab(self.tab_wing_right, get_feather_icon("chevron-right", "#00f3ff", 14), "Right Wing")
        self.component_editors["wing_right"] = self.tab_wing_right

        # Tab: Center Target
        self.tab_target = ComponentEditorWidget("target", self)
        self.tab_target.svg_modified.connect(self._on_component_svg_modified)
        self.tab_target.layout_modified.connect(self._on_layout_modified)
        self.tabs.addTab(self.tab_target, get_feather_icon("target", "#00f3ff", 14), "Center Target")
        self.component_editors["target"] = self.tab_target

        # Tab: Target Hit (2nd State)
        self.tab_target_hit = ComponentEditorWidget("target_hit", self)
        self.tab_target_hit.svg_modified.connect(self._on_component_svg_modified)
        self.tab_target_hit.trigger_hit_modified.connect(self._on_trigger_hit_modified)
        self.tabs.addTab(self.tab_target_hit, get_feather_icon("zap", "#00f3ff", 14), "Target Hit (2nd State)")
        self.component_editors["target_hit"] = self.tab_target_hit

        # Tab: Beats
        self.tab_beat = ComponentEditorWidget("beat", self)
        self.tab_beat.svg_modified.connect(self._on_component_svg_modified)
        self.tab_beat.beat_flip_modified.connect(self._on_beat_flip_modified)
        self.tabs.addTab(self.tab_beat, get_feather_icon("music", "#00f3ff", 14), "Beats")
        self.component_editors["beat"] = self.tab_beat

        # Tab: Global Theme & Palette
        self.tab_theme = ThemePaletteWidget(self)
        self.tab_theme.palette_changed.connect(self._on_palette_changed)
        self.tab_theme.apply_to_all_requested.connect(self._on_apply_theme_to_all)
        self.tabs.addTab(self.tab_theme, get_feather_icon("droplet", "#00f3ff", 14), "Global Palette")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([180, 480])

        main_layout.addWidget(self.splitter, stretch=1)

        # Status Bar
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready. Select a component tab to edit SVGs.")

    def _load_skin_into_ui(self):
        """Refreshes all UI tabs and preview widget with current skin data."""
        self.edit_skin_name.setText(self.current_skin.name)
        if hasattr(self, 'edit_skin_author'):
            self.edit_skin_author.blockSignals(True)
            self.edit_skin_author.setText(getattr(self.current_skin, 'author', 'User'))
            self.edit_skin_author.blockSignals(False)
        self.preview_widget.set_skin(self.current_skin)

        for key, editor in self.component_editors.items():
            svg_content = self.current_skin.get_component(key)
            editor.set_svg_content(svg_content)

        lay = getattr(self.current_skin, "layout", {})
        self.tab_wing_left.set_layout_data(lay.get("wing_left", {}))
        self.tab_wing_right.set_layout_data(lay.get("wing_right", {}))
        self.tab_target.set_layout_data(lay.get("target", {}))
        self.tab_beat.set_beat_flip_data(lay.get("flip_left_beats", False), lay.get("flip_right_beats", False))
        self.tab_target_hit.set_trigger_hit_data(getattr(self.current_skin, "trigger_hit", {}))

        self.tab_theme.set_palette(self.current_skin.palette)
        self.status.showMessage(f"Loaded skin: {self.current_skin.name}")

    def _on_layout_modified(self, key: str, layout_dict: dict):
        if not hasattr(self.current_skin, "layout"):
            self.current_skin.layout = {}
        self.current_skin.layout[key] = layout_dict
        self.preview_widget.set_skin(self.current_skin)

    def _on_beat_flip_modified(self, flip_left: bool, flip_right: bool):
        if not hasattr(self.current_skin, "layout"):
            self.current_skin.layout = {}
        self.current_skin.layout["flip_left_beats"] = flip_left
        self.current_skin.layout["flip_right_beats"] = flip_right
        self.preview_widget.set_skin(self.current_skin)

    def _on_trigger_hit_modified(self, trigger_dict: dict):
        if not hasattr(self.current_skin, "trigger_hit"):
            self.current_skin.trigger_hit = {}
        self.current_skin.trigger_hit.update(trigger_dict)
        self.preview_widget.set_skin(self.current_skin)

    def _on_skin_name_changed(self, text: str):
        self.current_skin.name = text.strip() or "Untitled Skin"

    def _on_skin_author_changed(self, text: str):
        val = text.strip() or "User"
        self.current_skin.author = val
        if hasattr(self, "config"):
            self.config["default_author"] = val
            self._save_config()

    def _on_component_svg_modified(self, key: str, new_svg: str):
        """Called whenever an SVG is updated via code editor, template, or swatch."""
        self.current_skin.set_component(key, new_svg)
        self.preview_widget.set_skin(self.current_skin)
        label = BeatbarSkin.COMPONENT_LABELS.get(key, key)
        self.status.showMessage(f"Updated {label} SVG.")

    def _on_mirror_wing(self, target_key: str, mirrored_svg: str):
        """Copies mirrored wing to the opposite wing component."""
        self.current_skin.set_component(target_key, mirrored_svg)
        if target_key in self.component_editors:
            self.component_editors[target_key].set_svg_content(mirrored_svg)
        self.preview_widget.set_skin(self.current_skin)
        target_name = BeatbarSkin.COMPONENT_LABELS.get(target_key, target_key)
        self.status.showMessage(f"Mirrored wing copied to {target_name}.")

    def _on_palette_changed(self, new_pal: dict):
        """Called when a color in the theme tab is changed."""
        self.current_skin.palette = new_pal.copy()
        self.preview_widget.set_skin(self.current_skin)
        self.status.showMessage("Global palette updated.")

    def _on_apply_theme_to_all(self):
        """Recolors all 5 components using current palette."""
        self.current_skin.apply_palette(self.tab_theme.current_palette)
        self._load_skin_into_ui()
        QMessageBox.information(self, "Theme Applied", "Palette colors successfully applied across all 5 SVGs!")

    def _on_preset_changed(self, idx: int):
        preset_id = self.combo_presets.currentData()
        if preset_id:
            self.current_skin = BeatbarSkin.create_preset(preset_id)
            self._load_skin_into_ui()
            if hasattr(self, "config"):
                self.config["last_preset"] = preset_id
                self._save_config()

    def _on_new_skin(self):
        ret = QMessageBox.question(self, "New Skin", "Create a new skin from default template?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            def_author = self.config.get("default_author", "User") if hasattr(self, "config") else "User"
            self.current_skin = BeatbarSkin("Untitled Skin", author=def_author)
            self._load_skin_into_ui()

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        is_hit_tab = (widget == self.tab_target_hit)
        is_hold = getattr(self.preview_widget, "chk_hold_hit", None) and self.preview_widget.chk_hold_hit.isChecked()
        self.preview_widget.canvas.preview_hit_state = is_hit_tab or is_hold
        self.preview_widget.canvas.update()
        if hasattr(self, "config"):
            self.config["active_tab"] = index
            self._save_config()

    def _on_open_skin(self):
        """Universal skin opener: triggers file bundle loader directly."""
        self._on_open_skin_file()

    def _on_open_skin_file(self):
        start_dir = self.config.get("last_folder", "") if hasattr(self, "config") else ""
        if not start_dir or not os.path.isdir(start_dir):
            cand = os.path.join(ROOT_DIR, "web", "skins")
            if os.path.isdir(cand):
                start_dir = cand

        path, _ = QFileDialog.getOpenFileName(
            self, "Open Skin (.beat bundle or skin.json)", start_dir,
            "Skin Files (*.beat skin.json *.json);;Beat Archive (*.beat);;Skin JSON (skin.json *.json);;All Files (*)"
        )
        if not path or not os.path.exists(path):
            return

        if hasattr(self, "config"):
            self.config["last_folder"] = os.path.dirname(path)
            self._save_config()

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".beat":
                self.current_skin.load_from_beat(path)
                self._load_skin_into_ui()
                self.status.showMessage(f"Loaded skin bundle: {os.path.basename(path)}")
                QMessageBox.information(self, "Skin Loaded", f"Successfully loaded skin bundle from:\n{path}")
            elif ext == ".json" or os.path.basename(path).lower() == "skin.json":
                folder = os.path.dirname(path)
                self.current_skin.load_from_folder(folder)
                self._load_skin_into_ui()
                self.status.showMessage(f"Loaded skin: {self.current_skin.name}")
                QMessageBox.information(self, "Skin Loaded", f"Successfully loaded skin from:\n{folder}")
            else:
                try:
                    self.current_skin.load_from_beat(path)
                except Exception:
                    self.current_skin.load_from_folder(os.path.dirname(path))
                self._load_skin_into_ui()
                self.status.showMessage(f"Loaded skin: {self.current_skin.name}")
                QMessageBox.information(self, "Skin Loaded", f"Successfully loaded skin from:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load skin from:\n{path}\n\nError: {e}")

    def _on_open_skin_folder(self):
        start_dir = self.config.get("last_folder", "") if hasattr(self, "config") else ""
        if not start_dir or not os.path.isdir(start_dir):
            cand = os.path.join(ROOT_DIR, "web", "skins")
            if os.path.isdir(cand):
                start_dir = cand

        folder = QFileDialog.getExistingDirectory(self, "Select Unpacked Skin Folder", start_dir)
        if not folder or not os.path.isdir(folder):
            return

        if hasattr(self, "config"):
            self.config["last_folder"] = folder
            self._save_config()

        has_meta = os.path.exists(os.path.join(folder, "skin.json"))
        has_svg = any(os.path.exists(os.path.join(folder, f)) for f in self.current_skin.COMPONENT_FILENAMES.values())
        beat_files = [f for f in os.listdir(folder) if f.lower().endswith(".beat")]

        if not has_meta and not has_svg:
            if beat_files:
                QMessageBox.information(
                    self,
                    "Select Skin File",
                    f"The folder '{os.path.basename(folder)}' contains .beat skin files.\n\n"
                    f"Please select a specific .beat file to load."
                )
                self._on_open_skin_file()
                return

            QMessageBox.warning(
                self,
                "No Skin Found",
                f"No 'skin.json' or SVG skin components were found in:\n{folder}\n\n"
                f"Please select a folder containing an unpacked skin or select a .beat bundle file."
            )
            return

        try:
            self.current_skin.load_from_folder(folder)
            self._load_skin_into_ui()
            self.status.showMessage(f"Loaded skin from folder: {self.current_skin.name}")
            QMessageBox.information(self, "Skin Loaded", f"Successfully loaded skin from folder:\n{folder}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load skin folder:\n{folder}\n\nError: {e}")

    def _on_load_beat(self):
        self._on_open_skin_file()

    def _on_save_skin(self):
        start_dir = self.config.get("last_folder", "") if hasattr(self, "config") else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Skin Bundle", start_dir)
        if folder:
            if hasattr(self, "config"):
                self.config["last_folder"] = folder
                self._save_config()
            # Create subfolder named after the skin
            safe_name = "".join(c if c.isalnum() else "_" for c in self.current_skin.name.lower()).strip("_")
            target_dir = os.path.join(folder, safe_name)
            self.current_skin.save_to_folder(target_dir)
            QMessageBox.information(self, "Skin Saved", f"Successfully saved skin bundle to:\n{target_dir}\n\nIncludes skin.json and all 5 SVG components.")

    def _on_export_to_viewer(self):
        """Exports the active skin directly to viewer/skins and sets it in viewer_config.json."""
        try:
            paths = self.current_skin.export_to_viewer()
            msg = (
                f"Successfully exported '{self.current_skin.name}' to Beatbar Viewer!\n\n"
                f"Files exported:\n"
                f"• Panel: {os.path.basename(paths['panel'])}\n"
                f"• Target: {os.path.basename(paths['target'])}\n"
                f"• Beats: {os.path.basename(paths['beat'])}\n"
                f"• Wings: {os.path.basename(paths['wing_left'])}, {os.path.basename(paths['wing_right'])}\n\n"
                f"viewer_config.json was automatically updated to use this skin!"
            )
            QMessageBox.information(self, "Export to Viewer", msg)
            self.status.showMessage("Exported skin to Beatbar Viewer.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export to viewer:\n{e}")

    def _on_pack_to_beat(self):
        """Bundles this skin and skin.json directly into an existing or new .beat file."""
        safe_name = "".join(c if c.isalnum() else "_" for c in self.current_skin.name.lower()).strip("_") or "skin"
        default_file = f"{safe_name}.beat"
        path, _ = QFileDialog.getSaveFileName(
            self, "Select or Create .beat File to Inject Skin", default_file,
            "Beat Archive (*.beat);;All Files (*)"
        )
        if path:
            if not path.lower().endswith(".beat"):
                path += ".beat"
            try:
                out = self.current_skin.save_to_beat(path)
                QMessageBox.information(
                    self, "Packed to .beat",
                    f"Successfully embedded skin and skin.json into .beat archive:\n{out}\n\n"
                    f"Skin: {self.current_skin.name}\n"
                    f"Includes: skin.json, panel.svg, wing_left.svg, wing_right.svg, target.svg, beat.svg"
                )
                self.status.showMessage(f"Packed skin into .beat archive: {os.path.basename(out)}")
            except Exception as e:
                QMessageBox.critical(self, "Pack Error", f"Failed to bundle skin into .beat archive:\n{e}")

    def _on_inject_into_beat(self):
        """Injects current skin into an existing .beat file with side-by-side replacement comparison if skin exists."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Existing .beat File to Inject Skin", "",
            "Beat Archive (*.beat);;All Files (*)"
        )
        if not path:
            return

        existing_skin = inspect_beat_skin(path)
        if existing_skin:
            dlg = SkinReplaceDialog(path, existing_skin, self.current_skin, self)
            if dlg.exec():
                selected_keys = dlg.get_selected_components()
                replace_palette = dlg.should_replace_palette()
                if not selected_keys and not replace_palette:
                    self.status.showMessage("No components selected for replacement.")
                    return

                ok = inject_skin_into_beat_file(path, self.current_skin, selected_keys, replace_palette)
                if ok:
                    QMessageBox.information(
                        self, "Skin Injected",
                        f"Successfully replaced {len(selected_keys)} skin component(s) in:\n{os.path.basename(path)}\n\n"
                        f"Embedded video, audio, and beatmaps were fully preserved."
                    )
                    self.status.showMessage(f"Replaced skin components in {os.path.basename(path)}")
                else:
                    QMessageBox.critical(self, "Injection Error", f"Failed to update .beat file:\n{path}")
        else:
            # No skin exists in this .beat yet -> inject all components directly
            all_keys = set(self.current_skin.COMPONENT_FILENAMES.keys())
            ok = inject_skin_into_beat_file(path, self.current_skin, all_keys, True)
            if ok:
                QMessageBox.information(
                    self, "Skin Injected",
                    f"Successfully injected skin '{self.current_skin.name}' into:\n{os.path.basename(path)}\n\n"
                    f"Embedded video, audio, and beatmaps were fully preserved."
                )
                self.status.showMessage(f"Injected skin into {os.path.basename(path)}")
            else:
                QMessageBox.critical(self, "Injection Error", f"Failed to inject skin into {path}")

    def _apply_saved_settings(self):
        w = int(self.config.get("window_width", 990))
        h = int(self.config.get("window_height", 720))
        self.resize(w, h)

        wx = self.config.get("window_x")
        wy = self.config.get("window_y")
        if wx is not None and wy is not None:
            self.move(QPoint(int(wx), int(wy)))

        if self.config.get("is_maximized", False):
            self.showMaximized()

        sp_sizes = self.config.get("splitter_sizes")
        if sp_sizes and isinstance(sp_sizes, list) and len(sp_sizes) == 2 and hasattr(self, "splitter"):
            self.splitter.setSizes(sp_sizes)

        tab_idx = self.config.get("active_tab", 0)
        if 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)

        last_preset = self.config.get("last_preset", "violet")
        idx = self.combo_presets.findData(last_preset)
        if idx >= 0:
            self.combo_presets.blockSignals(True)
            self.combo_presets.setCurrentIndex(idx)
            self.combo_presets.blockSignals(False)
            self.current_skin = BeatbarSkin.create_preset(last_preset)

    def _load_config(self) -> dict:
        cfg = DEFAULT_BEATPANEL_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cfg.update(data)
            except Exception as e:
                print(f"[BeatPanel] Failed to load config from {CONFIG_PATH}:", e)
        else:
            self._save_config_dict(cfg)
        return cfg

    def _save_config(self):
        if not self.isMaximized():
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
            self.config["window_x"] = self.x()
            self.config["window_y"] = self.y()
            self.config["is_maximized"] = False
        else:
            self.config["is_maximized"] = True

        if hasattr(self, "splitter") and self.splitter:
            self.config["splitter_sizes"] = self.splitter.sizes()

        if hasattr(self, "tabs") and self.tabs:
            self.config["active_tab"] = self.tabs.currentIndex()

        if hasattr(self, "combo_presets") and self.combo_presets:
            self.config["last_preset"] = self.combo_presets.currentData() or "violet"

        self._save_config_dict(self.config)

    def _save_config_dict(self, cfg: dict):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            print(f"[BeatPanel] Failed to save config to {CONFIG_PATH}:", e)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_geom_autosave_timer"):
            self._geom_autosave_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_geom_autosave_timer"):
            self._geom_autosave_timer.start()

    def closeEvent(self, event):
        if hasattr(self, "_geom_autosave_timer"):
            self._geom_autosave_timer.stop()
        self._save_config()
        super().closeEvent(event)


