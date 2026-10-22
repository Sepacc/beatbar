"""
settings_dialog.py - Settings Overlay Window for Beatbar Viewer.

Faithfully implements the settings modal depicted in beatmake-settings.jpg:
- choose video file
- choose beatbar file
- choose beatbar skin
- choose beats skin
- some setting (shake mode, strength, hit animation, lead time, inactivity timeout, audio sync)
- some pallete (theme color palettes and custom color pickers)
"""

import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFileDialog, QComboBox, QSlider, QDoubleSpinBox,
    QColorDialog, QFrame, QScrollArea, QGroupBox, QCheckBox,
    QGraphicsDropShadowEffect, QTabWidget
)
from PyQt6.QtGui import QColor, QFont, QCursor
try:
    from .skin_manager import SkinManager, COLOR_PALETTES
except (ImportError, ValueError):
    from skin_manager import SkinManager, COLOR_PALETTES

import sys
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_main_dir = os.path.join(_parent_dir, "main")
for _p in [_parent_dir, _main_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from icon_utils import get_feather_icon


class SettingsDialog(QDialog):
    """
    Settings overlay modal styled after beatmake-settings.jpg:
    Frameless, sleek dark rounded card with drop shadow.
    """
    settings_changed = pyqtSignal()
    video_selected = pyqtSignal(str)
    beatbar_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.skin_mgr = SkinManager()
        self.setWindowTitle("Settings & Customization")
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(880, 680)
        self.current_zones = []
        self._drag_pos = None
        self.setStyleSheet("""
            QFrame#settingsCard {
                background: #18181f;
                border: 1px solid #363644;
                border-radius: 16px;
            }
            QLabel {
                color: #e0e0e6;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton {
                background: #1e1e24;
                border: 1px solid #383844;
                border-radius: 8px;
                color: #ffffff;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2e2e38;
                border-color: #9b51e0;
            }
            QPushButton:pressed {
                background: #141418;
            }
            QComboBox {
                background: #1e1e24;
                border: 1px solid #383844;
                border-radius: 8px;
                color: #ffffff;
                padding: 6px 12px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #9b51e0;
            }
            QComboBox QAbstractItemView {
                background: #1e1e24;
                border: 1px solid #383844;
                color: #ffffff;
                selection-background-color: #9b51e0;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #14141c;
                border: 1px solid #282836;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7928ca, stop:1 #be2edd);
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: #161622;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.65 #e056fd, stop:1.0 #9b51e0);
                border: 2px solid #be2edd;
                width: 16px;
                height: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.75 #ffffff, stop:1.0 #e056fd);
                border: 2px solid #ffffff;
            }
            QSlider::handle:horizontal:pressed {
                background: #be2edd;
                border: 2px solid #ffffff;
            }
            QCheckBox {
                color: #dcdce6;
                font-size: 11px;
                font-weight: 500;
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                background: #18181f;
                border: 1px solid #3e3e4c;
                border-radius: 4px;
            }
            QCheckBox::indicator:hover {
                border-color: #9b51e0;
            }
            QCheckBox::indicator:checked {
                background: #9b51e0;
                border-color: #be2edd;
            }
        """)

        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        self.main_card = QFrame(self)
        self.main_card.setObjectName("settingsCard")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 8)
        self.main_card.setGraphicsEffect(shadow)

        self.card_layout = QVBoxLayout(self.main_card)
        self.card_layout.setContentsMargins(22, 16, 22, 18)
        self.card_layout.setSpacing(14)

        # Header Title with Icon & Clean Close Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        lbl_head = QLabel("Viewer Settings & Customization")
        lbl_head.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(lbl_head)

        header_layout.addStretch()

        self.btn_close_head = QPushButton()
        self.btn_close_head.setIcon(get_feather_icon("x", "#888894", 14))
        self.btn_close_head.setFixedSize(28, 28)
        self.btn_close_head.setToolTip("Close Settings")
        self.btn_close_head.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #888894;
                font-size: 15px;
                font-weight: bold;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #e81123;
                color: #ffffff;
            }
        """)
        self.btn_close_head.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close_head)

        self.card_layout.addLayout(header_layout)

        # Content Grid: Left Column (Choosers & Settings) | Right Column (Beatbar Theme)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)

        # ----------------------------------------------------------------------
        # TABS: Base & Advanced
        # ----------------------------------------------------------------------
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #30303e;
                background: #15151c;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #1c1c24;
                border: 1px solid #323242;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                color: #9494a8;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 11px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #252534;
                color: #ffffff;
                border-bottom: 2px solid #be2edd;
            }
            QTabBar::tab:hover {
                color: #ffffff;
                background: #20202c;
            }
        """)

        scroll_style = """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #18181e;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3e3e4a;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9b51e0;
            }
        """

        # ======================================================================
        # 1. BASE TAB: Core media, skins, timeline, and basic playback options
        # ======================================================================
        base_container = QWidget()
        base_layout = QVBoxLayout(base_container)
        base_layout.setContentsMargins(10, 10, 10, 10)
        base_layout.setSpacing(12)

        # Row 1: Choose Video File
        row_video = QHBoxLayout()
        self.btn_choose_video = QPushButton(" Choose Video File")
        self.btn_choose_video.setIcon(get_feather_icon("film", "#9b51e0", 16))
        self.btn_choose_video.clicked.connect(self._browse_video)
        row_video.addWidget(self.btn_choose_video)

        self.lbl_video_name = QLabel("Default Video")
        self.lbl_video_name.setStyleSheet("color: #aaaaaf; font-size: 11px;")
        row_video.addWidget(self.lbl_video_name, stretch=1)
        base_layout.addLayout(row_video)

        # Row 2: Choose Beatbar File
        row_beats = QHBoxLayout()
        self.btn_choose_beats = QPushButton(" Choose Beatbar File")
        self.btn_choose_beats.setIcon(get_feather_icon("music", "#9b51e0", 16))
        self.btn_choose_beats.clicked.connect(self._browse_beatbar)
        row_beats.addWidget(self.btn_choose_beats)

        self.lbl_beats_name = QLabel("Default Beatbar")
        self.lbl_beats_name.setStyleSheet("color: #aaaaaf; font-size: 11px;")
        row_beats.addWidget(self.lbl_beats_name, stretch=1)

        self.btn_pack_beat = QPushButton(" Pack .beat")
        self.btn_pack_beat.setIcon(get_feather_icon("package", "#be2edd", 14))
        self.btn_pack_beat.setToolTip("Export current video + beats into a portable .beat archive")
        self.btn_pack_beat.clicked.connect(self._export_current_to_beat)
        row_beats.addWidget(self.btn_pack_beat)
        base_layout.addLayout(row_beats)

        # Row 3: Choose Beatbar Skin Bundle & Load / Remove Custom Skin
        row_panel_skin = QHBoxLayout()
        row_panel_skin.setSpacing(6)
        lbl_ps = QLabel("Beatbar Skin:")
        lbl_ps.setFixedWidth(105)
        row_panel_skin.addWidget(lbl_ps)

        self.combo_panel_skin = QComboBox()
        self._populate_skin_combos()
        self.combo_panel_skin.currentIndexChanged.connect(self._on_panel_skin_changed)
        row_panel_skin.addWidget(self.combo_panel_skin, stretch=1)

        self.btn_load_beat_skin = QPushButton(" Load .beat")
        self.btn_load_beat_skin.setIcon(get_feather_icon("upload", "#be2edd", 14))
        self.btn_load_beat_skin.setToolTip("Load and add custom skin bundle from a .beat archive")
        self.btn_load_beat_skin.clicked.connect(self._load_beat_skin_file)
        row_panel_skin.addWidget(self.btn_load_beat_skin)

        self.btn_remove_skin = QPushButton(" Reset Skins")
        self.btn_remove_skin.setIcon(get_feather_icon("trash-2", "#ff5252", 13))
        self.btn_remove_skin.setToolTip("Remove custom loaded skins and reset dropdown to standard templates")
        self.btn_remove_skin.clicked.connect(self._on_remove_skin_clicked)
        row_panel_skin.addWidget(self.btn_remove_skin)
        base_layout.addLayout(row_panel_skin)

        # Row 4: Choose Beats Skin
        row_beats_skin = QHBoxLayout()
        lbl_bs = QLabel("Beats Skin:")
        lbl_bs.setFixedWidth(110)
        row_beats_skin.addWidget(lbl_bs)

        self.combo_beats_skin = QComboBox()
        self.combo_beats_skin.addItem("Active Skin Beats (Bundle)", "custom")
        self.combo_beats_skin.addItem("Purple Demonic Crests", "crest")
        self.combo_beats_skin.addItem("Neon Diamonds / Gems", "diamond")
        self.combo_beats_skin.addItem("Colored Rhythm Bars", "lane_bar")
        self.combo_beats_skin.addItem("Radiant Energy Orbs", "orb")
        current_beat = self.skin_mgr.config.get("beats_skin", "crest")
        idx_b = self.combo_beats_skin.findData(current_beat)
        if idx_b >= 0:
            self.combo_beats_skin.setCurrentIndex(idx_b)
        else:
            self.combo_beats_skin.setCurrentIndex(1)
        self.combo_beats_skin.currentIndexChanged.connect(self._on_beats_skin_changed)
        row_beats_skin.addWidget(self.combo_beats_skin, stretch=1)
        base_layout.addLayout(row_beats_skin)

        # Row 5: Timeline Fill Mode
        row_time_mode = QHBoxLayout()
        lbl_tm = QLabel("Timeline Fill:")
        lbl_tm.setFixedWidth(110)
        row_time_mode.addWidget(lbl_tm)

        self.combo_timeline_mode = QComboBox()
        self.combo_timeline_mode.addItem("Left to Right (Fill)", "left_to_right")
        self.combo_timeline_mode.addItem("Center Out (Fill to Left & Right)", "center_out")
        self.combo_timeline_mode.addItem("Reverse Left (Draining)", "reverse_left")
        self.combo_timeline_mode.addItem("Reverse Center (Gap from Center)", "reverse_center_out")
        self.combo_timeline_mode.addItem("Reverse Edges (Drain to Center)", "reverse_center_in")
        cur_tm = self.skin_mgr.config.get("timeline_fill_mode", "left_to_right")
        idx_tm = self.combo_timeline_mode.findData(cur_tm)
        if idx_tm >= 0:
            self.combo_timeline_mode.setCurrentIndex(idx_tm)
        self.combo_timeline_mode.currentIndexChanged.connect(self._on_timeline_mode_changed)
        row_time_mode.addWidget(self.combo_timeline_mode, stretch=1)
        base_layout.addLayout(row_time_mode)

        # Row 5b: Timeline Display Options
        row_time_opts = QVBoxLayout()
        row_time_opts.setContentsMargins(110, 0, 0, 4)
        row_time_opts.setSpacing(6)

        self.chk_timeline_zones = QCheckBox("Show rhythm zones on timeline")
        self.chk_timeline_zones.setChecked(self.skin_mgr.config.get("show_timeline_zones", True))
        self.chk_timeline_zones.toggled.connect(self._on_toggle_timeline_zones)
        row_time_opts.addWidget(self.chk_timeline_zones)

        self.chk_fill_per_zone = QCheckBox("Fill beatbar notch per active zone (instead of full video)")
        self.chk_fill_per_zone.setToolTip("The small timeline notch under the beatbar will fill from 0% to 100% for each active rhythm zone, while the bottom player timeline always scrubs the full video.")
        self.chk_fill_per_zone.setChecked(self.skin_mgr.config.get("fill_timeline_per_zone", False))
        self.chk_fill_per_zone.toggled.connect(self._on_toggle_fill_per_zone)
        row_time_opts.addWidget(self.chk_fill_per_zone)
        base_layout.addLayout(row_time_opts)

        # Row 6: Screen Shake Mode
        row_shake = QHBoxLayout()
        lbl_sm = QLabel("Screen Shake:")
        lbl_sm.setFixedWidth(110)
        row_shake.addWidget(lbl_sm)

        self.combo_shake_mode = QComboBox()
        self.combo_shake_mode.addItem("Intense Zones & 5+ Bursts", "intense_and_bursts")
        self.combo_shake_mode.addItem("All Beats", "always")
        self.combo_shake_mode.addItem("Disabled (Off)", "off")
        current_shake = self.skin_mgr.config.get("screen_shake_mode", "intense_and_bursts")
        idx_s = self.combo_shake_mode.findData(current_shake)
        if idx_s >= 0:
            self.combo_shake_mode.setCurrentIndex(idx_s)
        self.combo_shake_mode.currentIndexChanged.connect(self._on_shake_mode_changed)
        row_shake.addWidget(self.combo_shake_mode, stretch=1)
        base_layout.addLayout(row_shake)

        # Row 7: Shake Strength (Zoom level)
        row_shake_str = QHBoxLayout()
        lbl_ss = QLabel("Shake Strength:")
        lbl_ss.setFixedWidth(110)
        row_shake_str.addWidget(lbl_ss)

        self.slider_shake_str = QSlider(Qt.Orientation.Horizontal)
        self.slider_shake_str.setRange(15, 80)
        cur_str = int(float(self.skin_mgr.config.get("screen_shake_strength", 0.045)) * 1000)
        self.slider_shake_str.setValue(cur_str)
        self.lbl_shake_str_val = QLabel(f"{cur_str / 10.0:.1f}%")
        self.slider_shake_str.valueChanged.connect(self._on_shake_str_slider)
        row_shake_str.addWidget(self.slider_shake_str, stretch=1)
        row_shake_str.addWidget(self.lbl_shake_str_val)
        base_layout.addLayout(row_shake_str)

        # Row 7b: Beat Hit Effect Type (Screen Border Flash / Picture Wash / Camera Zoom)
        row_hit_effect = QHBoxLayout()
        lbl_he = QLabel("Hit Flash Effect:")
        lbl_he.setFixedWidth(110)
        row_hit_effect.addWidget(lbl_he)

        self.combo_hit_effect = QComboBox()
        self.combo_hit_effect.addItem("Border Glow (Edges Vignette Only)", "border_flash")
        self.combo_hit_effect.addItem("Full Screen Flash (Entire Frame Strobe)", "picture_flash")
        self.combo_hit_effect.addItem("Camera Punch Zoom (Shake Only)", "shake")
        self.combo_hit_effect.addItem("Border Glow + Camera Zoom", "both")
        self.combo_hit_effect.addItem("All Combined (Border Glow + Full Screen Flash + Zoom)", "all")
        cur_eff = self.skin_mgr.config.get("beat_hit_effect_type", "border_flash")
        idx_eff = self.combo_hit_effect.findData(cur_eff)
        if idx_eff >= 0:
            self.combo_hit_effect.setCurrentIndex(idx_eff)
        self.combo_hit_effect.currentIndexChanged.connect(self._on_hit_effect_changed)
        row_hit_effect.addWidget(self.combo_hit_effect, stretch=1)
        base_layout.addLayout(row_hit_effect)

        # Row 7c: Screen Flash Color
        row_flash_col = QHBoxLayout()
        lbl_fc = QLabel("Flash Color:")
        lbl_fc.setFixedWidth(110)
        row_flash_col.addWidget(lbl_fc)

        cur_fcol = self.skin_mgr.config.get("flash_color", "#e056fd")

        # Swatch Button opening QColorDialog
        self.btn_flash_color = QPushButton()
        self.btn_flash_color.setFixedSize(54, 28)
        self.btn_flash_color.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_flash_color.setToolTip("Click to pick custom flash color")
        self._update_flash_color_btn(cur_fcol)
        self.btn_flash_color.clicked.connect(self._pick_flash_color)
        row_flash_col.addWidget(self.btn_flash_color)

        # Quick preset color buttons
        presets = [
            ("Neon Pink", "#e056fd"),
            ("Cyan", "#00f3ff"),
            ("Gold", "#ffd32a"),
            ("Lime", "#38ef7d"),
            ("Crimson", "#ff1744"),
            ("White", "#ffffff"),
        ]
        preset_container = QWidget()
        p_layout = QHBoxLayout(preset_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(4)
        for p_name, p_hex in presets:
            p_btn = QPushButton()
            p_btn.setFixedSize(22, 22)
            p_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            p_btn.setToolTip(f"Preset: {p_name} ({p_hex})")
            p_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {p_hex};
                    border: 1px solid #ffffff44;
                    border-radius: 11px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """)
            p_btn.clicked.connect(lambda checked, col=p_hex: self._set_flash_color(col))
            p_layout.addWidget(p_btn)
        row_flash_col.addWidget(preset_container)

        # "Test Flash" preview button
        self.btn_test_flash = QPushButton(" Test Flash")
        self.btn_test_flash.setIcon(get_feather_icon("zap", "#ffd32a", 13))
        self.btn_test_flash.setFixedHeight(28)
        self.btn_test_flash.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_test_flash.setStyleSheet("""
            QPushButton {
                background: #232034;
                border: 1px solid #3d3856;
                border-radius: 6px;
                color: #d1d5db;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: #2d2844;
                border-color: #8b5cf6;
                color: #ffffff;
            }
        """)
        self.btn_test_flash.clicked.connect(self._test_hit_flash)
        row_flash_col.addWidget(self.btn_test_flash)

        row_flash_col.addStretch()
        base_layout.addLayout(row_flash_col)

        # Row 8: Note Speed / Lead Time
        row_lead = QHBoxLayout()
        lbl_lt = QLabel("Note Lead Time:")
        lbl_lt.setFixedWidth(110)
        row_lead.addWidget(lbl_lt)

        self.slider_lead = QSlider(Qt.Orientation.Horizontal)
        self.slider_lead.setRange(6, 30)  # 0.6s to 3.0s
        cur_lead = int(float(self.skin_mgr.config.get("lead_time", 1.5)) * 10)
        self.slider_lead.setValue(cur_lead)
        self.lbl_lead_val = QLabel(f"{cur_lead / 10.0:.1f}s")
        self.slider_lead.valueChanged.connect(self._on_lead_slider)
        row_lead.addWidget(self.slider_lead, stretch=1)
        row_lead.addWidget(self.lbl_lead_val)
        base_layout.addLayout(row_lead)

        # Row 8b: Beat Note Size
        row_beat_size = QHBoxLayout()
        lbl_bsz = QLabel("Beat Note Size:")
        lbl_bsz.setFixedWidth(110)
        row_beat_size.addWidget(lbl_bsz)

        self.slider_beat_size_base = QSlider(Qt.Orientation.Horizontal)
        self.slider_beat_size_base.setRange(40, 160)  # 40% to 160%
        cur_bsz = int(float(self.skin_mgr.config.get("beat_scale", 1.0)) * 100)
        self.slider_beat_size_base.setValue(cur_bsz)
        self.lbl_beat_size_base_val = QLabel(f"{cur_bsz}%")
        self.lbl_beat_size_base_val.setFixedWidth(50)
        self.lbl_beat_size_base_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace; font-size: 11px;")
        self.slider_beat_size_base.valueChanged.connect(self._on_beat_size_base_slider)
        row_beat_size.addWidget(self.slider_beat_size_base, stretch=1)
        row_beat_size.addWidget(self.lbl_beat_size_base_val)
        base_layout.addLayout(row_beat_size)

        # Row 9: Inactivity Collapse Delay
        row_inac = QHBoxLayout()
        lbl_id_inac = QLabel("Inactivity Hide:")
        lbl_id_inac.setFixedWidth(110)
        row_inac.addWidget(lbl_id_inac)

        self.combo_inactivity = QComboBox()
        self.combo_inactivity.addItem("1.5 Seconds", 1.5)
        self.combo_inactivity.addItem("2.5 Seconds (Default)", 2.5)
        self.combo_inactivity.addItem("4.0 Seconds", 4.0)
        self.combo_inactivity.addItem("Never Collapse", 0.0)
        cur_inac = float(self.skin_mgr.config.get("inactivity_delay", 2.5))
        idx_i = self.combo_inactivity.findData(cur_inac)
        if idx_i >= 0:
            self.combo_inactivity.setCurrentIndex(idx_i)
        self.combo_inactivity.currentIndexChanged.connect(self._on_inactivity_changed)
        row_inac.addWidget(self.combo_inactivity, stretch=1)
        base_layout.addLayout(row_inac)

        base_layout.addStretch()

        base_scroll = QScrollArea()
        base_scroll.setWidgetResizable(True)
        base_scroll.setStyleSheet(scroll_style)
        base_scroll.setWidget(base_container)
        self.settings_tabs.addTab(base_scroll, get_feather_icon("sliders", "#00f3ff", 14), "Base")

        # ======================================================================
        # 2. ADVANCED TAB: Direction rules, flips, geometry & hit customizations
        # ======================================================================
        adv_container = QWidget()
        adv_layout = QVBoxLayout(adv_container)
        adv_layout.setContentsMargins(10, 10, 10, 10)
        adv_layout.setSpacing(10)

        # Beat Direction Settings Card (Simple vs Extended Mode)
        self.dir_group = QGroupBox("Beat Direction Settings")
        self.dir_group.setStyleSheet("""
            QGroupBox {
                background: #18181f;
                border: 1px solid #363644;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                color: #e0e0e8;
                font-weight: bold;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        dir_main_layout = QVBoxLayout(self.dir_group)
        dir_main_layout.setContentsMargins(8, 8, 8, 8)
        dir_main_layout.setSpacing(8)

        # Mode Selector Buttons: [ Simple (By Zone Type) ] [ Extended (Per Zone) ]
        mode_btn_row = QHBoxLayout()
        mode_btn_row.setSpacing(6)

        self.btn_mode_simple = QPushButton("Simple (By Zone Type)")
        self.btn_mode_simple.setFixedHeight(28)
        self.btn_mode_simple.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_simple.clicked.connect(lambda: self._set_direction_mode("simple"))

        self.btn_mode_extended = QPushButton("Extended (Per Zone)")
        self.btn_mode_extended.setFixedHeight(28)
        self.btn_mode_extended.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_extended.clicked.connect(lambda: self._set_direction_mode("extended"))

        mode_btn_row.addWidget(self.btn_mode_simple, stretch=1)
        mode_btn_row.addWidget(self.btn_mode_extended, stretch=1)
        dir_main_layout.addLayout(mode_btn_row)

        # --- A. SIMPLE MODE CONTAINER (By Zone Type) ---
        self.simple_container = QWidget()
        simple_layout = QVBoxLayout(self.simple_container)
        simple_layout.setContentsMargins(0, 4, 0, 0)
        simple_layout.setSpacing(6)

        zone_type_dirs = self.skin_mgr.config.get("zone_type_directions", {
            "climax": "ltr",
            "speeding_up": "both",
            "normal": "rtl",
            "pause": "rtl"
        })

        self.combo_type_climax = self._create_dir_combo(
            simple_layout, "Climax / Intense:", zone_type_dirs.get("climax", "ltr"),
            lambda val: self._on_zone_type_dir_changed("climax", val)
        )
        self.combo_type_speed = self._create_dir_combo(
            simple_layout, "Speeding Up / Fast:", zone_type_dirs.get("speeding_up", "both"),
            lambda val: self._on_zone_type_dir_changed("speeding_up", val)
        )
        self.combo_type_normal = self._create_dir_combo(
            simple_layout, "Normal Zones:", zone_type_dirs.get("normal", "rtl"),
            lambda val: self._on_zone_type_dir_changed("normal", val)
        )
        self.combo_type_pause = self._create_dir_combo(
            simple_layout, "Pause / Slow:", zone_type_dirs.get("pause", "rtl"),
            lambda val: self._on_zone_type_dir_changed("pause", val)
        )

        dir_main_layout.addWidget(self.simple_container)

        # --- B. EXTENDED MODE CONTAINER (Per Individual Zone) ---
        self.extended_container = QWidget()
        extended_layout = QVBoxLayout(self.extended_container)
        extended_layout.setContentsMargins(0, 4, 0, 0)
        extended_layout.setSpacing(6)

        self.zones_scroll = QScrollArea()
        self.zones_scroll.setWidgetResizable(True)
        self.zones_scroll.setMaximumHeight(160)
        self.zones_scroll.setStyleSheet("background: transparent; border: none;")
        self.zones_list_widget = QWidget()
        self.zones_layout = QVBoxLayout(self.zones_list_widget)
        self.zones_layout.setContentsMargins(0, 0, 0, 0)
        self.zones_layout.setSpacing(4)
        self.zones_scroll.setWidget(self.zones_list_widget)

        self.lbl_no_zones = QLabel("No zones loaded (open a video/beatbar to configure)")
        self.lbl_no_zones.setStyleSheet("color: #888892; font-size: 11px; font-style: italic;")
        self.zones_layout.addWidget(self.lbl_no_zones)

        extended_layout.addWidget(self.zones_scroll)
        dir_main_layout.addWidget(self.extended_container)

        # Beat Directional Flipping
        row_flips = QHBoxLayout()
        row_flips.setSpacing(14)
        self.chk_flip_left = QCheckBox("Flip Left Beats")
        self.chk_flip_left.setToolTip("Flips beats traveling towards center from left horizontally")
        self.chk_flip_left.setChecked(bool(self.skin_mgr.config.get("flip_left_beats", False)))
        self.chk_flip_left.toggled.connect(self._on_flip_left_toggled)
        row_flips.addWidget(self.chk_flip_left)

        self.chk_flip_right = QCheckBox("Flip Right Beats")
        self.chk_flip_right.setToolTip("Flips beats traveling towards center from right horizontally")
        self.chk_flip_right.setChecked(bool(self.skin_mgr.config.get("flip_right_beats", False)))
        self.chk_flip_right.toggled.connect(self._on_flip_right_toggled)
        row_flips.addWidget(self.chk_flip_right)
        row_flips.addStretch()
        dir_main_layout.addLayout(row_flips)

        adv_layout.addWidget(self.dir_group)

        # Beat Notes & Overlap Settings Card
        self._build_beat_notes_settings_card(adv_layout)

        # Wings & Target Geometry Card
        self._build_geometry_settings_card(adv_layout)

        # Trigger Hit & 2nd State Card
        self._build_trigger_hit_settings_card(adv_layout)

        adv_layout.addStretch()

        adv_scroll = QScrollArea()
        adv_scroll.setWidgetResizable(True)
        adv_scroll.setStyleSheet(scroll_style)
        adv_scroll.setWidget(adv_container)
        self.settings_tabs.addTab(adv_scroll, get_feather_icon("tool", "#e056fd", 14), "Advanced")

        content_layout.addWidget(self.settings_tabs, stretch=1)

        self.card_layout.addLayout(content_layout)

        # ----------------------------------------------------------------------
        # BOTTOM ACTION BUTTONS
        # ----------------------------------------------------------------------
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.btn_reset = QPushButton(" Reset to Defaults")
        self.btn_reset.setIcon(get_feather_icon("rotate-ccw", "#ffffff", 14))
        self.btn_reset.clicked.connect(self._reset_defaults)
        bottom_bar.addWidget(self.btn_reset)

        bottom_bar.addStretch()

        self.btn_apply = QPushButton(" Done")
        self.btn_apply.setIcon(get_feather_icon("check", "#ffffff", 14))
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: #9b51e0;
                border: 1px solid #be2edd;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 26px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #be2edd;
                border-color: #e056fd;
            }
        """)
        self.btn_apply.clicked.connect(self.close)
        bottom_bar.addWidget(self.btn_apply)

        self.card_layout.addLayout(bottom_bar)
        outer_layout.addWidget(self.main_card)
        self._set_direction_mode(self.skin_mgr.config.get("settings_mode", "simple"))

    def _create_dir_combo(self, parent_layout, label_text, current_val, callback):
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(130)
        lbl.setStyleSheet("color: #dcdce2; font-size: 11px;")
        row.addWidget(lbl)

        cb = QComboBox()
        cb.addItem("Left -> Right (Reverted)", "ltr")
        cb.addItem("Both Sides (Duel Stream)", "both")
        cb.addItem("Right -> Left (Standard)", "rtl")
        idx = cb.findData(current_val)
        if idx >= 0:
            cb.setCurrentIndex(idx)
        cb.currentIndexChanged.connect(lambda: callback(cb.currentData()))
        row.addWidget(cb, stretch=1)
        parent_layout.addLayout(row)
        return cb

    def _set_direction_mode(self, mode):
        is_simple = (mode == "simple")
        self.skin_mgr.config["settings_mode"] = mode
        self.skin_mgr.save_config()

        self.simple_container.setVisible(is_simple)
        self.extended_container.setVisible(not is_simple)

        active_btn_style = """
            QPushButton {
                background: #9b51e0;
                border: 1px solid #be2edd;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 4px;
            }
        """
        inactive_btn_style = """
            QPushButton {
                background: #1e1e24;
                border: 1px solid #383844;
                border-radius: 6px;
                color: #888894;
                font-size: 11px;
                padding: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #282832;
                border-color: #9b51e0;
            }
        """
        self.btn_mode_simple.setStyleSheet(active_btn_style if is_simple else inactive_btn_style)
        self.btn_mode_extended.setStyleSheet(inactive_btn_style if is_simple else active_btn_style)

    def _on_zone_type_dir_changed(self, ztype, val):
        if "zone_type_directions" not in self.skin_mgr.config:
            self.skin_mgr.config["zone_type_directions"] = {}
        self.skin_mgr.config["zone_type_directions"][ztype] = val
        if ztype in ["climax", "intense"]:
            self.skin_mgr.config["zone_type_directions"]["intense"] = val
            self.skin_mgr.config["intense_zones_direction"] = val
        elif ztype in ["speeding_up", "fast"]:
            self.skin_mgr.config["zone_type_directions"]["fast"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_toggle_timeline_zones(self, checked):
        self.skin_mgr.config["show_timeline_zones"] = checked
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_toggle_fill_per_zone(self, checked):
        self.skin_mgr.config["fill_timeline_per_zone"] = checked
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def set_current_files(self, video_path, beats_path, zones=None):
        if video_path:
            self.lbl_video_name.setText(os.path.basename(video_path))
        if beats_path:
            self.lbl_beats_name.setText(os.path.basename(beats_path))
        if zones is not None:
            self.set_zones(zones)

    def set_zones(self, zones):
        """Populates the individual zone directions list with clean, shortened names."""
        self.current_zones = zones or []
        # Clear existing items in zones_layout
        while self.zones_layout.count():
            item = self.zones_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        if not self.current_zones:
            lbl = QLabel("No zones loaded in current beatbar")
            lbl.setStyleSheet("color: #888892; font-size: 11px; font-style: italic;")
            self.zones_layout.addWidget(lbl)
            return

        overrides = self.skin_mgr.config.get("zone_direction_overrides", {})

        def fmt_sec(t):
            m = int(t // 60)
            s = t % 60
            return f"{m}:{s:04.1f}" if m > 0 else f"{s:.1f}s"

        for i, z in enumerate(self.current_zones):
            zid = str(z.get('id', ''))
            zname = str(z.get('name', '')).strip()
            ztype = str(z.get('type', z.get('zone_type', 'normal'))).replace('_', ' ').title()
            st = float(z.get('start_time', z.get('start', 0.0)))
            et = float(z.get('end_time', z.get('end', 0.0)))

            # Clean and short naming (avoid messy hex hashes like "#9ecb91dd Zone 9ecb91dd")
            if not zname or zname.lower().startswith("zone ") or zname == zid or zname.startswith("#"):
                disp_title = f"Zone {i + 1} ({ztype}) • {fmt_sec(st)} - {fmt_sec(et)}"
            else:
                disp_title = f"{zname} ({ztype}) • {fmt_sec(st)} - {fmt_sec(et)}"

            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(disp_title)
            lbl.setStyleSheet("color: #dcdce2; font-size: 11px;")
            row.addWidget(lbl, stretch=1)

            cb = QComboBox()
            cb.setFixedWidth(135)
            cb.addItem("Default (Inherit)", "default")
            cb.addItem("Left -> Right", "ltr")
            cb.addItem("Both Sides", "both")
            cb.addItem("Right -> Left", "rtl")

            cur_override = overrides.get(zid, overrides.get(zname, "default"))
            idx = cb.findData(cur_override)
            if idx >= 0:
                cb.setCurrentIndex(idx)

            cb.currentIndexChanged.connect(lambda _, key=zid, combo=cb: self._on_zone_override_changed(key, combo.currentData()))
            row.addWidget(cb)
            self.zones_layout.addLayout(row)

    def _on_timeline_mode_changed(self, idx):
        val = self.combo_timeline_mode.currentData()
        self.skin_mgr.config["timeline_fill_mode"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()


    def _on_zone_override_changed(self, zone_key, val):
        if "zone_direction_overrides" not in self.skin_mgr.config:
            self.skin_mgr.config["zone_direction_overrides"] = {}
        self.skin_mgr.config["zone_direction_overrides"][zone_key] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Video or Beat Archive", "",
            "Video & Beat Archives (*.mp4 *.mkv *.webm *.avi *.mov *.m4v *.beat);;Video Files (*.mp4 *.mkv *.webm);;Beat Archives (*.beat);;All Files (*)"
        )
        if path:
            self.lbl_video_name.setText(os.path.basename(path))
            self.skin_mgr.config["last_video_path"] = path
            self.skin_mgr.save_config()
            self.video_selected.emit(path)

    def _browse_beatbar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Beatbar File", "",
            "Beatbar Files (*.beat *_beats.json *.json);;Beat Archives (*.beat);;JSON Beatmaps (*.json);;All Files (*)"
        )
        if path:
            self.lbl_beats_name.setText(os.path.basename(path))
            self.skin_mgr.config["last_beatbar_path"] = path
            self.skin_mgr.save_config()
            self.beatbar_selected.emit(path)

    def _export_current_to_beat(self):
        """Packs currently loaded video, beatbar, and skins into a .beat archive."""
        from PyQt6.QtWidgets import QMessageBox
        from beat_format import BeatFormat

        current_beat = self.skin_mgr.config.get("last_beatbar_path", "")
        current_video = self.skin_mgr.config.get("last_video_path", "")

        if not current_beat or not os.path.exists(current_beat):
            QMessageBox.warning(self, "No Beatbar Loaded", "Please load a beatbar file first before packing into .beat.")
            return

        default_name = os.path.splitext(current_beat)[0] + ".beat"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Pack to .beat Archive", default_name,
            "Beat Archive (*.beat);;All Files (*)"
        )
        if not save_path:
            return
        if not save_path.lower().endswith(".beat"):
            save_path += ".beat"

        embed_video = False
        if current_video and os.path.exists(current_video):
            reply = QMessageBox.question(
                self, "Embed Video?",
                "Do you want to embed the full video binary directly into the .beat archive?\n\n"
                "• Yes: Completely self-contained pack (can be copied to Android or shared).\n"
                "• No: Lightweight pack referencing the video by filename.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            embed_video = (reply == QMessageBox.StandardButton.Yes)

        # Prepare skin configuration mapping
        target_hit_file = self.skin_mgr.get_target_hit_svg_path()
        skin_cfg = {
            "format": "beat_skin",
            "version": "1.0",
            "name": self.skin_mgr.config.get("active_skin_name") or "Beatbar Skin",
            "components": {
                "panel": os.path.basename(self.skin_mgr.get_panel_svg_path()) if self.skin_mgr.get_panel_svg_path() else "panel_cyber_wings.svg",
                "wing_left": os.path.basename(self.skin_mgr.get_wing_sigil_paths()[0]),
                "wing_right": os.path.basename(self.skin_mgr.get_wing_sigil_paths()[1]),
                "target": os.path.basename(self.skin_mgr.get_target_svg_path()) if self.skin_mgr.get_target_svg_path() else "crest_target.svg",
                "target_hit": os.path.basename(target_hit_file) if target_hit_file else "",
                "beat": os.path.basename(self.skin_mgr.get_beat_svg_path()) if self.skin_mgr.get_beat_svg_path() else "crest_beat.svg"
            },
            "palette": self.skin_mgr.get_palette(),
            "layout": {
                "wing_left": {
                    "offset_x": float(self.skin_mgr.config.get("wing_left_offset_x", 0.0)),
                    "offset_y": float(self.skin_mgr.config.get("wing_left_offset_y", 0.0)),
                    "scale": float(self.skin_mgr.config.get("wing_left_scale", 1.0))
                },
                "wing_right": {
                    "offset_x": float(self.skin_mgr.config.get("wing_right_offset_x", 0.0)),
                    "offset_y": float(self.skin_mgr.config.get("wing_right_offset_y", 0.0)),
                    "scale": float(self.skin_mgr.config.get("wing_right_scale", 1.0))
                },
                "target": {
                    "offset_x": float(self.skin_mgr.config.get("target_offset_x", 0.0)),
                    "offset_y": float(self.skin_mgr.config.get("target_offset_y", 0.0)),
                    "scale": float(self.skin_mgr.config.get("target_scale", 1.0))
                },
                "flip_left_beats": bool(self.skin_mgr.config.get("flip_left_beats", False)),
                "flip_right_beats": bool(self.skin_mgr.config.get("flip_right_beats", False))
            },
            "trigger_hit": {
                "indicator_style": self.skin_mgr.config.get("trigger_hit_indicator_style", "triangle"),
                "indicator_color": self.skin_mgr.config.get("trigger_hit_indicator_color", "#ffffff"),
                "duration_ms": int(self.skin_mgr.config.get("trigger_hit_duration_ms", 180)),
                "pop_scale": float(self.skin_mgr.config.get("trigger_hit_pop_scale", 1.35))
            }
        }
        extra_files = []
        for p in [self.skin_mgr.get_panel_svg_path(), self.skin_mgr.get_wing_sigil_paths()[0], self.skin_mgr.get_wing_sigil_paths()[1], self.skin_mgr.get_target_svg_path(), target_hit_file, self.skin_mgr.get_beat_svg_path()]:
            if p and os.path.exists(p) and p not in extra_files:
                extra_files.append(p)

        try:
            out = BeatFormat.create(
                save_path,
                beatmap_source=current_beat,
                video_path=current_video if os.path.exists(current_video) else None,
                skin_config=skin_cfg,
                extra_skin_files=extra_files,
                embed_video=embed_video,
            )
            size_mb = os.path.getsize(out) / (1024 * 1024)
            embed_msg = "with embedded video" if embed_video else "with video reference"
            QMessageBox.information(
                self, "Pack Created",
                f"Successfully created .beat archive ({size_mb:.1f} MB, {embed_msg}):\n{out}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Pack Error", f"Failed to create .beat archive:\n{str(e)}")

    def _populate_skin_combos(self):
        """Populates the skin bundle dropdown with default bundles and loaded .beat bundles."""
        self.combo_panel_skin.blockSignals(True)
        self.combo_panel_skin.clear()

        # Built-in Default Skin Bundles
        self.combo_panel_skin.addItem("Cyber Wings (Default)", "cyber_wings")

        # Custom Loaded .beat Skin Bundles
        loaded = self.skin_mgr.config.get("loaded_skin_bundles", {})
        for bid, binfo in loaded.items():
            name = binfo.get("name", bid)
            self.combo_panel_skin.addItem(f"{name} (.beat)", bid)

        # Custom standalone SVG/Image
        self.combo_panel_skin.addItem("Custom SVG / Image...", "custom")

        # Set selection to current active bundle
        cur = self.skin_mgr.config.get("active_skin_bundle") or self.skin_mgr.config.get("panel_skin", "cyber_wings")
        idx = self.combo_panel_skin.findData(cur)
        if idx >= 0:
            self.combo_panel_skin.setCurrentIndex(idx)
        else:
            self.combo_panel_skin.setCurrentIndex(0)
        self.combo_panel_skin.blockSignals(False)

    def _load_beat_skin_file(self):
        """Prompts user to select a .beat archive to load as a skin bundle."""
        from PyQt6.QtWidgets import QMessageBox
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load .beat Skin Bundle", "",
            "Beat Archive (*.beat);;All Files (*)"
        )
        if not file_path:
            return

        binfo = self.skin_mgr.load_beat_skin(file_path)
        if binfo:
            self._populate_skin_combos()
            idx = self.combo_panel_skin.findData(binfo["id"])
            if idx >= 0:
                self.combo_panel_skin.setCurrentIndex(idx)
            self.settings_changed.emit()
            QMessageBox.information(
                self, "Skin Loaded",
                f"Successfully loaded and applied beat skin '{binfo.get('name')}'!\nIt is now saved in your skin options."
            )
        else:
            QMessageBox.warning(
                self, "Skin Load Error",
                f"Could not load skin bundle from:\n{file_path}\n\n"
                "Please verify that this .beat archive contains skin components (SVGs or skin configuration). "
                "Plain video beatmaps without custom skins cannot be loaded as skin packs."
            )

    def _on_remove_skin_clicked(self):
        """Removes the selected custom skin or purges all custom skins to leave only standard templates."""
        from PyQt6.QtWidgets import QMessageBox
        cur_bundle = self.combo_panel_skin.currentData()
        loaded = self.skin_mgr.config.get("loaded_skin_bundles", {})

        if cur_bundle in loaded:
            bname = loaded[cur_bundle].get("name", cur_bundle)
            reply = QMessageBox.question(
                self, "Remove Custom Skin",
                f"Remove custom skin '{bname}' from skin options and revert to default?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.skin_mgr.remove_skin_bundle(cur_bundle)
                self._populate_skin_combos()
                self._sync_controls_from_config()
                self.settings_changed.emit()
        else:
            if loaded:
                reply = QMessageBox.question(
                    self, "Reset Skins to Standard",
                    f"Remove all {len(loaded)} custom loaded skins and keep only standard templates (Cyber Wings & Clean Minimal)?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.skin_mgr.clear_all_custom_skins()
                    self._populate_skin_combos()
                    self._sync_controls_from_config()
                    self.settings_changed.emit()
            else:
                QMessageBox.information(
                    self, "Standard Templates Active",
                    "Only standard templates ('Cyber Wings' and 'Clean Minimal Template') are present. No custom skins to remove."
                )

    def _on_panel_skin_changed(self, idx):
        val = self.combo_panel_skin.currentData()
        if not val:
            return
        if val == "custom":
            custom_path, _ = QFileDialog.getOpenFileName(
                self, "Choose Custom Beatbar SVG or Image Skin", "",
                "SVG / Image Files (*.svg *.png *.jpg *.jpeg);;All Files (*)"
            )
            if custom_path:
                self.skin_mgr.config["custom_panel_path"] = custom_path
                self.skin_mgr.config["panel_skin"] = "custom"
                self.skin_mgr.config["active_skin_bundle"] = "custom"
            else:
                self._populate_skin_combos()
                return
        elif val == "cyber_wings":
            self.skin_mgr.apply_bundle(val)
        elif val in self.skin_mgr.config.get("loaded_skin_bundles", {}):
            self.skin_mgr.apply_bundle(val)
        else:
            self.skin_mgr.config["panel_skin"] = val
            self.skin_mgr.config["active_skin_bundle"] = val

        # Synchronize beats skin dropdown with current bundle's beats skin
        cur_beat = self.skin_mgr.config.get("beats_skin", "crest")
        idx_b = self.combo_beats_skin.findData(cur_beat)
        if idx_b >= 0:
            self.combo_beats_skin.blockSignals(True)
            self.combo_beats_skin.setCurrentIndex(idx_b)
            self.combo_beats_skin.blockSignals(False)

        self._sync_controls_from_config()

        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_beats_skin_changed(self, idx):
        val = self.combo_beats_skin.currentData()
        self.skin_mgr.config["beats_skin"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_hit_anim_changed(self, idx):
        val = self.combo_hit_anim.currentData()
        self.skin_mgr.config["hit_animation"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_shake_mode_changed(self, idx):
        val = self.combo_shake_mode.currentData()
        self.skin_mgr.config["screen_shake_mode"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_shake_str_slider(self, val):
        self.lbl_shake_str_val.setText(f"{val / 10.0:.1f}%")
        self.skin_mgr.config["screen_shake_strength"] = val / 1000.0
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_hit_effect_changed(self, idx):
        val = self.combo_hit_effect.currentData()
        self.skin_mgr.config["beat_hit_effect_type"] = val
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _update_flash_color_btn(self, hex_col):
        self.btn_flash_color.setStyleSheet(f"""
            QPushButton {{
                background-color: {hex_col};
                border: 2px solid #ffffff;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 2px solid #e056fd;
            }}
        """)

    def _set_flash_color(self, hex_col):
        self.skin_mgr.config["flash_color"] = hex_col
        self.skin_mgr.save_config()
        self._update_flash_color_btn(hex_col)
        self.settings_changed.emit()
        self._test_hit_flash()

    def _pick_flash_color(self):
        cur = QColor(self.skin_mgr.config.get("flash_color", "#e056fd"))
        chosen = QColorDialog.getColor(cur, self, "Select Beat Hit Flash Color")
        if chosen.isValid():
            self._set_flash_color(chosen.name())

    def _test_hit_flash(self):
        win = self.parent()
        if win and hasattr(win, 'shake_controller'):
            win.shake_controller.trigger_shake()
        elif win and hasattr(win, 'video_canvas'):
            flash_col = QColor(self.skin_mgr.config.get("flash_color", "#e056fd"))
            mode = self.skin_mgr.config.get("beat_hit_effect_type", "border_flash")
            win.video_canvas.set_flash(1.0, flash_col, mode=mode)

    def _on_lead_slider(self, val):
        self.lbl_lead_val.setText(f"{val / 10.0:.1f}s")
        self.skin_mgr.config["lead_time"] = val / 10.0
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_inactivity_changed(self, idx):
        val = self.combo_inactivity.currentData()
        self.skin_mgr.config["inactivity_delay"] = float(val)
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _select_palette(self, pal_id):
        self.skin_mgr.config["palette"] = pal_id
        self.skin_mgr.save_config()
        if hasattr(self, 'cb_quick_palette'):
            idx = self.cb_quick_palette.findData(pal_id)
            if idx >= 0:
                self.cb_quick_palette.blockSignals(True)
                self.cb_quick_palette.setCurrentIndex(idx)
                self.cb_quick_palette.blockSignals(False)
        self.settings_changed.emit()

    def _on_quick_palette_changed(self, index):
        if hasattr(self, 'cb_quick_palette'):
            pal_id = self.cb_quick_palette.currentData()
            if pal_id:
                if pal_id == "custom":
                    self._open_custom_color_picker()
                else:
                    self._select_palette(pal_id)

    def _open_custom_color_picker(self):
        col = QColorDialog.getColor(QColor(self.skin_mgr.get_palette()["primary"]), self, "Pick Primary Beat Color")
        if col.isValid():
            cur_cust = self.skin_mgr.config.get("custom_palette", {}).copy()
            cur_cust["primary"] = col.name()
            cur_cust["glow"] = col.lighter(130).name()
            cur_cust["accent"] = col.lighter(120).name()
            self.skin_mgr.config["custom_palette"] = cur_cust
            self.skin_mgr.config["palette"] = "custom"
            self.skin_mgr.save_config()
            if hasattr(self, 'cb_quick_palette'):
                idx = self.cb_quick_palette.findData("custom")
                if idx >= 0:
                    self.cb_quick_palette.blockSignals(True)
                    self.cb_quick_palette.setCurrentIndex(idx)
                    self.cb_quick_palette.blockSignals(False)
            self.settings_changed.emit()

    def _on_beat_size_base_slider(self, val):
        self.lbl_beat_size_base_val.setText(f"{val}%")
        if hasattr(self, 'slider_beat_size_adv') and self.slider_beat_size_adv.value() != val:
            self.slider_beat_size_adv.blockSignals(True)
            self.slider_beat_size_adv.setValue(val)
            self.lbl_beat_size_adv_val.setText(f"{val}%")
            self.slider_beat_size_adv.blockSignals(False)
        self.skin_mgr.config["beat_scale"] = val / 100.0
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_beat_size_adv_slider(self, val):
        self.lbl_beat_size_adv_val.setText(f"{val}%")
        if hasattr(self, 'slider_beat_size_base') and self.slider_beat_size_base.value() != val:
            self.slider_beat_size_base.blockSignals(True)
            self.slider_beat_size_base.setValue(val)
            self.lbl_beat_size_base_val.setText(f"{val}%")
            self.slider_beat_size_base.blockSignals(False)
        self.skin_mgr.config["beat_scale"] = val / 100.0
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_anti_overlap_toggled(self, checked):
        self.skin_mgr.config["anti_overlap_beats"] = checked
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _build_beat_notes_settings_card(self, parent_layout):
        self.beats_group = QGroupBox("Beat Notes & Overlap Settings")
        self.beats_group.setStyleSheet("""
            QGroupBox {
                background: #18181f;
                border: 1px solid #363644;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                color: #e0e0e8;
                font-weight: bold;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        blayout = QVBoxLayout(self.beats_group)
        blayout.setContentsMargins(8, 8, 8, 8)
        blayout.setSpacing(8)

        # Beat Size Slider
        row_sz = QHBoxLayout()
        lbl_sz = QLabel("Beat Note Size:")
        lbl_sz.setFixedWidth(115)
        lbl_sz.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        row_sz.addWidget(lbl_sz)

        self.slider_beat_size_adv = QSlider(Qt.Orientation.Horizontal)
        self.slider_beat_size_adv.setRange(40, 160)
        cur_bsz = int(float(self.skin_mgr.config.get("beat_scale", 1.0)) * 100)
        self.slider_beat_size_adv.setValue(cur_bsz)

        self.lbl_beat_size_adv_val = QLabel(f"{cur_bsz}%")
        self.lbl_beat_size_adv_val.setFixedWidth(50)
        self.lbl_beat_size_adv_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace; font-size: 11px;")

        self.slider_beat_size_adv.valueChanged.connect(self._on_beat_size_adv_slider)
        row_sz.addWidget(self.slider_beat_size_adv, stretch=1)
        row_sz.addWidget(self.lbl_beat_size_adv_val)
        blayout.addLayout(row_sz)

        # Prevent Beat Overlap Checkbox (Smart Scaling)
        self.chk_anti_overlap = QCheckBox("Prevent Beat Overlap (Smart Scaling)")
        self.chk_anti_overlap.setToolTip(
            "Automatically scales down notes when 2 or 3 beats occur in rapid succession so they do not overlap each other."
        )
        self.chk_anti_overlap.setChecked(bool(self.skin_mgr.config.get("anti_overlap_beats", True)))
        self.chk_anti_overlap.toggled.connect(self._on_anti_overlap_toggled)
        blayout.addWidget(self.chk_anti_overlap)

        parent_layout.addWidget(self.beats_group)

    def _build_geometry_settings_card(self, parent_layout):
        self.geom_group = QGroupBox("Wings & Target Geometry")
        self.geom_group.setStyleSheet("""
            QGroupBox {
                background: #18181f;
                border: 1px solid #363644;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                color: #e0e0e8;
                font-weight: bold;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        glayout = QVBoxLayout(self.geom_group)
        glayout.setContentsMargins(8, 8, 8, 8)
        glayout.setSpacing(6)

        rst_row = QHBoxLayout()
        rst_row.addWidget(QLabel("Component Positioning & Scaling:"))
        rst_row.addStretch()
        btn_reset_geom = QPushButton("Reset Geometry")
        btn_reset_geom.setStyleSheet("padding: 3px 8px; font-size: 10px; background: #22222e;")
        btn_reset_geom.clicked.connect(self._reset_geometry)
        rst_row.addWidget(btn_reset_geom)
        glayout.addLayout(rst_row)

        # Left Wing
        lbl_lw = QLabel("• Left Wing:")
        lbl_lw.setStyleSheet("font-weight: bold; color: #be2edd; font-size: 11px;")
        glayout.addWidget(lbl_lw)
        self.slider_wl_x, _ = self._create_geom_slider_row(
            glayout, "Offset X:", -200, 200,
            int(self.skin_mgr.config.get("wing_left_offset_x", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("wing_left_offset_x", float(v))
        )
        self.slider_wl_y, _ = self._create_geom_slider_row(
            glayout, "Offset Y:", -100, 100,
            int(self.skin_mgr.config.get("wing_left_offset_y", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("wing_left_offset_y", float(v))
        )
        self.slider_wl_scale, _ = self._create_geom_slider_row(
            glayout, "Scale:", 20, 300,
            int(float(self.skin_mgr.config.get("wing_left_scale", 1.0)) * 100), "%",
            lambda v: self._update_cfg_and_emit("wing_left_scale", float(v) / 100.0)
        )

        # Right Wing
        lbl_rw = QLabel("• Right Wing:")
        lbl_rw.setStyleSheet("font-weight: bold; color: #be2edd; font-size: 11px;")
        glayout.addWidget(lbl_rw)
        self.slider_wr_x, _ = self._create_geom_slider_row(
            glayout, "Offset X:", -200, 200,
            int(self.skin_mgr.config.get("wing_right_offset_x", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("wing_right_offset_x", float(v))
        )
        self.slider_wr_y, _ = self._create_geom_slider_row(
            glayout, "Offset Y:", -100, 100,
            int(self.skin_mgr.config.get("wing_right_offset_y", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("wing_right_offset_y", float(v))
        )
        self.slider_wr_scale, _ = self._create_geom_slider_row(
            glayout, "Scale:", 20, 300,
            int(float(self.skin_mgr.config.get("wing_right_scale", 1.0)) * 100), "%",
            lambda v: self._update_cfg_and_emit("wing_right_scale", float(v) / 100.0)
        )

        # Center Target
        lbl_ct = QLabel("• Center Target:")
        lbl_ct.setStyleSheet("font-weight: bold; color: #be2edd; font-size: 11px;")
        glayout.addWidget(lbl_ct)
        self.slider_tg_x, _ = self._create_geom_slider_row(
            glayout, "Offset X:", -200, 200,
            int(self.skin_mgr.config.get("target_offset_x", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("target_offset_x", float(v))
        )
        self.slider_tg_y, _ = self._create_geom_slider_row(
            glayout, "Offset Y:", -100, 100,
            int(self.skin_mgr.config.get("target_offset_y", 0.0)), " px",
            lambda v: self._update_cfg_and_emit("target_offset_y", float(v))
        )
        self.slider_tg_scale, _ = self._create_geom_slider_row(
            glayout, "Scale:", 20, 300,
            int(float(self.skin_mgr.config.get("target_scale", 1.0)) * 100), "%",
            lambda v: self._update_cfg_and_emit("target_scale", float(v) / 100.0)
        )

        parent_layout.addWidget(self.geom_group)

    def _build_trigger_hit_settings_card(self, parent_layout):
        self.hit_group = QGroupBox("Trigger Hit & Target 2nd State")
        self.hit_group.setStyleSheet("""
            QGroupBox {
                background: #18181f;
                border: 1px solid #363644;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                color: #e0e0e8;
                font-weight: bold;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        hlayout = QVBoxLayout(self.hit_group)
        hlayout.setContentsMargins(8, 8, 8, 8)
        hlayout.setSpacing(6)

        # Hit Effects
        row_anim = QHBoxLayout()
        lbl_ha = QLabel("Hit Effects:")
        lbl_ha.setFixedWidth(110)
        row_anim.addWidget(lbl_ha)

        self.combo_hit_anim = QComboBox()
        self.combo_hit_anim.addItem("Shockwave Ring", "shockwave")
        self.combo_hit_anim.addItem("Radiant Sparkle Burst", "burst")
        self.combo_hit_anim.addItem("All (Shockwave + Burst)", "all")
        current_anim = self.skin_mgr.config.get("hit_animation", "shockwave")
        idx_a = self.combo_hit_anim.findData(current_anim)
        if idx_a >= 0:
            self.combo_hit_anim.setCurrentIndex(idx_a)
        self.combo_hit_anim.currentIndexChanged.connect(self._on_hit_anim_changed)
        row_anim.addWidget(self.combo_hit_anim, stretch=1)
        hlayout.addLayout(row_anim)

        # Indicator Style
        row_ind = QHBoxLayout()
        lbl_ind = QLabel("Hit Indicator:")
        lbl_ind.setFixedWidth(110)
        row_ind.addWidget(lbl_ind)
        self.combo_ind_style = QComboBox()
        self.combo_ind_style.addItem("▲ Triangle (Default)", "triangle")
        self.combo_ind_style.addItem("◆ Diamond", "diamond")
        self.combo_ind_style.addItem("━ Glow Bar", "glow_bar")
        self.combo_ind_style.addItem("Hidden", "hidden")
        cur_style = self.skin_mgr.config.get("trigger_hit_indicator_style", "triangle")
        idx_style = self.combo_ind_style.findData(cur_style)
        if idx_style >= 0:
            self.combo_ind_style.setCurrentIndex(idx_style)
        self.combo_ind_style.currentIndexChanged.connect(self._on_indicator_style_changed)
        row_ind.addWidget(self.combo_ind_style, stretch=1)
        hlayout.addLayout(row_ind)

        # Indicator Color
        row_col = QHBoxLayout()
        lbl_col = QLabel("Indicator Color:")
        lbl_col.setFixedWidth(110)
        row_col.addWidget(lbl_col)
        self.btn_trig_color = QPushButton(self.skin_mgr.config.get("trigger_hit_indicator_color", "#ffffff").upper())
        self.btn_trig_color.setFixedHeight(26)
        self._update_trig_color_btn()
        self.btn_trig_color.clicked.connect(self._pick_trig_color)
        row_col.addWidget(self.btn_trig_color, stretch=1)
        hlayout.addLayout(row_col)

        # Hit Duration
        self.slider_hit_dur, _ = self._create_geom_slider_row(
            hlayout, "Hit Duration:", 50, 500,
            int(self.skin_mgr.config.get("trigger_hit_duration_ms", 180)), " ms",
            lambda v: self._update_cfg_and_emit("trigger_hit_duration_ms", int(v))
        )

        # Pop Scale
        self.slider_pop_scale, _ = self._create_geom_slider_row(
            hlayout, "Pop Scale:", 100, 250,
            int(float(self.skin_mgr.config.get("trigger_hit_pop_scale", 1.35)) * 100), "%",
            lambda v: self._update_cfg_and_emit("trigger_hit_pop_scale", float(v) / 100.0)
        )

        # 2nd State SVG (target_hit.svg)
        row_hit_svg = QHBoxLayout()
        lbl_svg = QLabel("Hit State SVG:")
        lbl_svg.setFixedWidth(110)
        row_hit_svg.addWidget(lbl_svg)

        cur_hit_path = self.skin_mgr.config.get("custom_target_hit_path", "")
        self.lbl_hit_svg_name = QLabel(os.path.basename(cur_hit_path) if cur_hit_path else "(Bundle / Default)")
        self.lbl_hit_svg_name.setStyleSheet("color: #aaaaaf; font-size: 11px;")
        row_hit_svg.addWidget(self.lbl_hit_svg_name, stretch=1)

        btn_browse_hit = QPushButton(" Browse...")
        btn_browse_hit.setIcon(get_feather_icon("folder", "#00d2ff", 12))
        btn_browse_hit.clicked.connect(self._browse_custom_target_hit)
        row_hit_svg.addWidget(btn_browse_hit)

        btn_clear_hit = QPushButton("Reset")
        btn_clear_hit.clicked.connect(self._clear_custom_target_hit)
        row_hit_svg.addWidget(btn_clear_hit)
        hlayout.addLayout(row_hit_svg)

        parent_layout.addWidget(self.hit_group)

    def _create_geom_slider_row(self, layout, label_text, min_val, max_val, cur_val, val_suffix, callback):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(90)
        lbl.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        row.addWidget(lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(cur_val)

        lbl_v = QLabel(f"{cur_val:+d}{val_suffix}" if min_val < 0 else f"{cur_val}{val_suffix}")
        lbl_v.setFixedWidth(60)
        lbl_v.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace; font-size: 11px;")

        def on_change(val):
            lbl_v.setText(f"{val:+d}{val_suffix}" if min_val < 0 else f"{val}{val_suffix}")
            callback(val)

        slider.valueChanged.connect(on_change)
        row.addWidget(slider, stretch=1)
        row.addWidget(lbl_v)
        layout.addLayout(row)
        return slider, lbl_v

    def _update_cfg_and_emit(self, key, value):
        self.skin_mgr.config[key] = value
        self.skin_mgr.save_config()
        self.settings_changed.emit()

    def _on_flip_left_toggled(self, checked):
        self._update_cfg_and_emit("flip_left_beats", checked)

    def _on_flip_right_toggled(self, checked):
        self._update_cfg_and_emit("flip_right_beats", checked)

    def _on_indicator_style_changed(self):
        style = self.combo_ind_style.currentData()
        self._update_cfg_and_emit("trigger_hit_indicator_style", style)

    def _update_trig_color_btn(self):
        col_hex = self.skin_mgr.config.get("trigger_hit_indicator_color", "#ffffff")
        c = QColor(col_hex)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        txt_col = "#000000" if lum > 130 else "#ffffff"
        self.btn_trig_color.setText(col_hex.upper())
        self.btn_trig_color.setStyleSheet(f"""
            QPushButton {{
                background-color: {col_hex};
                color: {txt_col};
                border: 1px solid #444458;
                border-radius: 6px;
                font-family: monospace;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

    def _pick_trig_color(self):
        cur_hex = self.skin_mgr.config.get("trigger_hit_indicator_color", "#ffffff")
        c = QColorDialog.getColor(QColor(cur_hex), self, "Select Hit Indicator Color")
        if c.isValid():
            self._update_cfg_and_emit("trigger_hit_indicator_color", c.name())
            self._update_trig_color_btn()

    def _browse_custom_target_hit(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select 2nd State Target Hit SVG", "", "SVG Files (*.svg)")
        if path:
            self._update_cfg_and_emit("custom_target_hit_path", path)
            self.lbl_hit_svg_name.setText(os.path.basename(path))

    def _clear_custom_target_hit(self):
        self._update_cfg_and_emit("custom_target_hit_path", "")
        self.lbl_hit_svg_name.setText("(Bundle / Default)")

    def _reset_geometry(self):
        for k in ["wing_left_offset_x", "wing_left_offset_y", "wing_right_offset_x", "wing_right_offset_y", "target_offset_x", "target_offset_y"]:
            self.skin_mgr.config[k] = 0.0
        for k in ["wing_left_scale", "wing_right_scale", "target_scale"]:
            self.skin_mgr.config[k] = 1.0
        self.skin_mgr.save_config()
        if hasattr(self, 'slider_wl_x'):
            self.slider_wl_x.setValue(0)
            self.slider_wl_y.setValue(0)
            self.slider_wl_scale.setValue(100)
            self.slider_wr_x.setValue(0)
            self.slider_wr_y.setValue(0)
            self.slider_wr_scale.setValue(100)
            self.slider_tg_x.setValue(0)
            self.slider_tg_y.setValue(0)
            self.slider_tg_scale.setValue(100)
        self.settings_changed.emit()

    def _load_current_values(self):
        """Reloads skin combos and all UI control values from current skin_mgr.config."""
        self._populate_skin_combos()
        self._sync_controls_from_config()

    def _sync_controls_from_config(self):
        """Synchronizes all UI controls from current skin_mgr.config without emitting signals."""
        if not hasattr(self, 'slider_wl_x'):
            return
        cfg = self.skin_mgr.config
        self.chk_flip_left.blockSignals(True)
        self.chk_flip_right.blockSignals(True)
        self.chk_flip_left.setChecked(bool(cfg.get("flip_left_beats", False)))
        self.chk_flip_right.setChecked(bool(cfg.get("flip_right_beats", False)))
        self.chk_flip_left.blockSignals(False)
        self.chk_flip_right.blockSignals(False)

        # Block signals on geometry sliders to prevent re-entrant clobbering
        geom_sliders = [
            (self.slider_wl_x, int(cfg.get("wing_left_offset_x", 0.0))),
            (self.slider_wl_y, int(cfg.get("wing_left_offset_y", 0.0))),
            (self.slider_wl_scale, int(float(cfg.get("wing_left_scale", 1.0)) * 100)),
            (self.slider_wr_x, int(cfg.get("wing_right_offset_x", 0.0))),
            (self.slider_wr_y, int(cfg.get("wing_right_offset_y", 0.0))),
            (self.slider_wr_scale, int(float(cfg.get("wing_right_scale", 1.0)) * 100)),
            (self.slider_tg_x, int(cfg.get("target_offset_x", 0.0))),
            (self.slider_tg_y, int(cfg.get("target_offset_y", 0.0))),
            (self.slider_tg_scale, int(float(cfg.get("target_scale", 1.0)) * 100)),
            (self.slider_hit_dur, int(cfg.get("trigger_hit_duration_ms", 180))),
            (self.slider_pop_scale, int(float(cfg.get("trigger_hit_pop_scale", 1.35)) * 100)),
        ]
        for slider, val in geom_sliders:
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)

        cur_style = cfg.get("trigger_hit_indicator_style", "triangle")
        idx_s = self.combo_ind_style.findData(cur_style)
        if idx_s >= 0:
            self.combo_ind_style.blockSignals(True)
            self.combo_ind_style.setCurrentIndex(idx_s)
            self.combo_ind_style.blockSignals(False)

        self._update_trig_color_btn()
        cur_hit_path = cfg.get("custom_target_hit_path", "")
        self.lbl_hit_svg_name.setText(os.path.basename(cur_hit_path) if cur_hit_path else "(Bundle / Default)")

        cur_bsz = int(float(cfg.get("beat_scale", 1.0)) * 100)
        if hasattr(self, 'slider_beat_size_base'):
            self.slider_beat_size_base.blockSignals(True)
            self.slider_beat_size_base.setValue(cur_bsz)
            self.lbl_beat_size_base_val.setText(f"{cur_bsz}%")
            self.slider_beat_size_base.blockSignals(False)
        if hasattr(self, 'slider_beat_size_adv'):
            self.slider_beat_size_adv.blockSignals(True)
            self.slider_beat_size_adv.setValue(cur_bsz)
            self.lbl_beat_size_adv_val.setText(f"{cur_bsz}%")
            self.slider_beat_size_adv.blockSignals(False)
        if hasattr(self, 'chk_anti_overlap'):
            self.chk_anti_overlap.blockSignals(True)
            self.chk_anti_overlap.setChecked(bool(cfg.get("anti_overlap_beats", True)))
            self.chk_anti_overlap.blockSignals(False)
        if hasattr(self, 'combo_hit_effect'):
            cur_eff = cfg.get("beat_hit_effect_type", "border_flash")
            idx_eff = self.combo_hit_effect.findData(cur_eff)
            if idx_eff >= 0:
                self.combo_hit_effect.blockSignals(True)
                self.combo_hit_effect.setCurrentIndex(idx_eff)
                self.combo_hit_effect.blockSignals(False)
        if hasattr(self, 'btn_flash_color'):
            cur_fcol = cfg.get("flash_color", "#e056fd")
            self._update_flash_color_btn(cur_fcol)

    def _reset_defaults(self):
        try:
            from .skin_manager import DEFAULT_CONFIG
        except (ImportError, ValueError):
            from skin_manager import DEFAULT_CONFIG
        self.skin_mgr.config = DEFAULT_CONFIG.copy()
        self.skin_mgr.save_config()
        self._populate_skin_combos()
        self.combo_panel_skin.setCurrentIndex(0)
        self.combo_beats_skin.setCurrentIndex(0)
        self.combo_timeline_mode.setCurrentIndex(0)
        self.chk_timeline_zones.setChecked(True)
        self.chk_fill_per_zone.setChecked(False)
        self.chk_flip_left.setChecked(False)
        self.chk_flip_right.setChecked(False)
        self._set_direction_mode("simple")
        self.combo_type_climax.setCurrentIndex(self.combo_type_climax.findData("ltr"))
        self.combo_type_speed.setCurrentIndex(self.combo_type_speed.findData("both"))
        self.combo_type_normal.setCurrentIndex(self.combo_type_normal.findData("rtl"))
        self.combo_type_pause.setCurrentIndex(self.combo_type_pause.findData("rtl"))
        self.combo_hit_anim.setCurrentIndex(0)
        self.combo_shake_mode.setCurrentIndex(0)
        if hasattr(self, 'combo_hit_effect'):
            self.combo_hit_effect.setCurrentIndex(0)
        if hasattr(self, 'btn_flash_color'):
            self._update_flash_color_btn("#e056fd")
        self.slider_shake_str.setValue(45)
        self.slider_lead.setValue(15)
        if hasattr(self, 'slider_beat_size_base'):
            self.slider_beat_size_base.setValue(100)
        if hasattr(self, 'slider_beat_size_adv'):
            self.slider_beat_size_adv.setValue(100)
        if hasattr(self, 'chk_anti_overlap'):
            self.chk_anti_overlap.setChecked(True)
        self.combo_inactivity.setCurrentIndex(1)
        self._reset_geometry()
        if hasattr(self, 'slider_hit_dur'):
            self.slider_hit_dur.setValue(180)
            self.slider_pop_scale.setValue(135)
            self.combo_ind_style.setCurrentIndex(0)
            self._update_trig_color_btn()
            self.lbl_hit_svg_name.setText("(Bundle / Default)")
        if hasattr(self, 'current_zones'):
            self.set_zones(self.current_zones)
        self.settings_changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 65:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
