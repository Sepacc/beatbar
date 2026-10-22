"""
launcher.py - Modern Compact Library Panel & Suite Launcher for Beatbar Applications.

Optimized for 1366x768 screens, styled with Feather SVG icons and dark theme.
Launches silently with zero console popups.
"""

import os
import sys
import json
import subprocess
from typing import Dict, Optional

# Ensure project root is in sys.path
LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LAUNCHER_DIR)
MAIN_DIR = os.path.join(ROOT_DIR, "main")
for p in [ROOT_DIR, LAUNCHER_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtCore import Qt, QTimer, QSize, QPoint
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QMessageBox, QSizePolicy, QTabWidget
)
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette, QCursor, QPixmap

CONFIG_PATH = os.path.join(LAUNCHER_DIR, ".config")

DEFAULT_LAUNCHER_CONFIG = {
    "window_width": 960,
    "window_height": 620,
    "window_x": None,
    "window_y": None,
    "is_maximized": False,
    "active_tab": 0
}

from launcher.version_manager import (
    PROGRAM_REGISTRY, ProgramConfig, COMPILED_DIR,
    compare_program_version, VersionComparison
)
from launcher.process_manager import process_manager
from launcher.compiler_dialog import CompilerDialog
from launcher.beat_dropzone import BeatDropZoneWidget
from launcher.skin_gallery import SkinGalleryWidget

try:
    from icon_utils import get_feather_icon, get_suite_icon, get_suite_pixmap
except ImportError:
    get_feather_icon = lambda name, color="#ffffff", size=16: None
    get_suite_icon = lambda name, size=32, dark_mode=True: None
    get_suite_pixmap = lambda name, size=24, dark_mode=True, tile=False: None


def get_feather_pixmap(name: str, color: str = "#ffffff", size: int = 14) -> QPixmap:
    ico = get_feather_icon(name, color=color, size=size)
    if ico and not ico.isNull():
        return ico.pixmap(size, size)
    return QPixmap()


class ProgramCard(QFrame):
    """Compact library card representing a program in the suite."""

    def __init__(self, prog: ProgramConfig, parent=None):
        super().__init__(parent)
        self.prog = prog
        self.comp: Optional[VersionComparison] = None
        self._is_running = False

        self.setObjectName("ProgramCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(180)
        self.setStyleSheet(f"""
            QFrame#ProgramCard {{
                background-color: #161b22;
                border: none;
                border-radius: 8px;
            }}
            QFrame#ProgramCard:hover {{
                background-color: #1c2128;
                border: none;
            }}
        """)

        self._build_card()
        self.refresh()

    def _build_card(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header Row: Icon + Title + Status Badge
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # Icon box
        self.icon_frame = QFrame()
        self.icon_frame.setFixedSize(36, 36)
        self.icon_frame.setStyleSheet(f"""
            background-color: rgba({int(self.prog.theme_color[1:3], 16)}, {int(self.prog.theme_color[3:5], 16)}, {int(self.prog.theme_color[5:7], 16)}, 0.15);
            border: none;
            border-radius: 6px;
        """)
        icon_layout = QVBoxLayout(self.icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suite_svg = getattr(self.prog, "icon_svg", None) or self.prog.id
        suite_pm = get_suite_pixmap(suite_svg, size=24, dark_mode=True)
        if suite_pm and not suite_pm.isNull():
            self.icon_label.setPixmap(suite_pm)
        else:
            ico = get_feather_icon(self.prog.icon_name, color=self.prog.theme_color, size=18)
            if ico and not ico.isNull():
                self.icon_label.setPixmap(ico.pixmap(18, 18))
        icon_layout.addWidget(self.icon_label)
        top_layout.addWidget(self.icon_frame)

        # Title and Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.title_label = QLabel(self.prog.name)
        self.title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        title_box.addWidget(self.title_label)

        self.subtitle_label = QLabel(self.prog.subtitle)
        self.subtitle_label.setStyleSheet("font-size: 10px; color: #8b949e;")
        title_box.addWidget(self.subtitle_label)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        # Status Badge Pill (with Feather Icon)
        self.badge_frame = QFrame()
        self.badge_frame.setObjectName("StatusBadge")
        self.badge_frame.setFixedHeight(22)
        badge_layout = QHBoxLayout(self.badge_frame)
        badge_layout.setContentsMargins(8, 0, 10, 0)
        badge_layout.setSpacing(5)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.badge_icon = QLabel()
        self.badge_icon.setFixedSize(12, 12)
        self.badge_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_icon.setStyleSheet("background: transparent; border: none;")
        badge_layout.addWidget(self.badge_icon)

        self.badge_text = QLabel("Checking...")
        self.badge_text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.badge_text.setStyleSheet("background: transparent; border: none; font-size: 10px; font-weight: 600;")
        badge_layout.addWidget(self.badge_text)

        top_layout.addWidget(self.badge_frame)
        main_layout.addLayout(top_layout)

        # Description
        self.desc_label = QLabel(self.prog.description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #8b949e; font-size: 10.5px; line-height: 1.2;")
        main_layout.addWidget(self.desc_label)

        # Version Comparison Panel
        self.version_panel = QFrame()
        self.version_panel.setStyleSheet("""
            background-color: #0d1117;
            border: none;
            border-radius: 6px;
        """)
        v_layout = QVBoxLayout(self.version_panel)
        v_layout.setContentsMargins(8, 5, 8, 5)
        v_layout.setSpacing(3)

        row_v = QHBoxLayout()
        row_v.setSpacing(6)

        # Source version
        self.ico_src = QLabel()
        self.ico_src.setPixmap(get_feather_pixmap("file-text", color="#8b949e", size=12))
        row_v.addWidget(self.ico_src)

        self.lbl_src_ver = QLabel("Source: v—")
        self.lbl_src_ver.setStyleSheet("font-size: 10.5px; color: #c9d1d9; font-weight: bold;")
        row_v.addWidget(self.lbl_src_ver)

        row_v.addSpacing(10)

        # Compiled version
        self.ico_comp = QLabel()
        self.ico_comp.setPixmap(get_feather_pixmap("hard-drive", color="#8b949e", size=12))
        row_v.addWidget(self.ico_comp)

        self.lbl_comp_ver = QLabel("Compiled: None")
        self.lbl_comp_ver.setStyleSheet("font-size: 10.5px; color: #8b949e;")
        row_v.addWidget(self.lbl_comp_ver)

        row_v.addStretch()

        # Running indicator
        self.ico_running = QLabel()
        self.ico_running.setPixmap(get_feather_pixmap("zap", color="#38ef7d", size=12))
        self.ico_running.setVisible(False)
        row_v.addWidget(self.ico_running)

        self.lbl_running_indicator = QLabel("Active")
        self.lbl_running_indicator.setStyleSheet("color: #38ef7d; font-size: 10px; font-weight: bold;")
        self.lbl_running_indicator.setVisible(False)
        row_v.addWidget(self.lbl_running_indicator)

        v_layout.addLayout(row_v)

        self.lbl_details = QLabel("Comparing versions...")
        self.lbl_details.setStyleSheet("font-size: 9.5px; color: #6e7681; font-style: italic;")
        v_layout.addWidget(self.lbl_details)
        main_layout.addWidget(self.version_panel)

        main_layout.addStretch()

        # Bottom Action Buttons
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(6)

        # Primary Launch Button
        self.btn_primary = QPushButton("Launch")
        self.btn_primary.setFixedHeight(28)
        self.btn_primary.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_primary.clicked.connect(self._on_primary_action)
        self.action_layout.addWidget(self.btn_primary)

        # Secondary Button (Run Python script)
        self.btn_secondary = QPushButton("Run .py")
        self.btn_secondary.setFixedHeight(28)
        self.btn_secondary.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        code_ico = get_feather_icon("code", color="#c9d1d9", size=12)
        if code_ico and not code_ico.isNull():
            self.btn_secondary.setIcon(code_ico)
            self.btn_secondary.setIconSize(QSize(12, 12))
        self.btn_secondary.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: none;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_secondary.clicked.connect(self._run_python_script)
        self.action_layout.addWidget(self.btn_secondary)

        # Compile Button (if compilable)
        if self.prog.can_compile:
            self.btn_compile_card = QPushButton("Compile")
            self.btn_compile_card.setFixedHeight(28)
            self.btn_compile_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            tool_ico = get_feather_icon("tool", color="#58a6ff", size=12)
            if tool_ico and not tool_ico.isNull():
                self.btn_compile_card.setIcon(tool_ico)
                self.btn_compile_card.setIconSize(QSize(12, 12))
            self.btn_compile_card.setStyleSheet("""
                QPushButton {
                    background-color: #1f242c;
                    color: #58a6ff;
                    border: none;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1f6feb; color: #ffffff; }
            """)
            self.btn_compile_card.clicked.connect(self._open_compiler_for_this)
            self.action_layout.addWidget(self.btn_compile_card)

        # Web Stop Server Button
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedHeight(28)
        self.btn_stop.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        stop_ico = get_feather_icon("square", color="#f85149", size=11)
        if stop_ico and not stop_ico.isNull():
            self.btn_stop.setIcon(stop_ico)
            self.btn_stop.setIconSize(QSize(11, 11))
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #3d1b1b;
                color: #f85149;
                border: none;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #da3633; color: #ffffff; }
        """)
        self.btn_stop.clicked.connect(self._stop_running_process)
        self.btn_stop.setVisible(False)
        self.action_layout.addWidget(self.btn_stop)

        main_layout.addLayout(self.action_layout)

    def refresh(self):
        """Updates the version comparison and status display."""
        self.comp = compare_program_version(self.prog)
        self._is_running = process_manager.is_running(self.prog.id)

        # Source version label
        self.lbl_src_ver.setText(f"Source: v{self.comp.source_version}")

        # Compiled version label
        if self.prog.is_web:
            self.lbl_comp_ver.setText("Web Application")
            self.lbl_comp_ver.setStyleSheet("font-size: 10.5px; color: #2ed573;")
            self.btn_secondary.setVisible(False)
        elif self.comp.has_compiled and self.comp.compiled_version:
            self.lbl_comp_ver.setText(f"Compiled: v{self.comp.compiled_version}")
            self.lbl_comp_ver.setStyleSheet("font-size: 10.5px; color: #58a6ff; font-weight: bold;")
            self.btn_secondary.setVisible(True)
        else:
            self.lbl_comp_ver.setText("Compiled: None")
            self.lbl_comp_ver.setStyleSheet("font-size: 10.5px; color: #8b949e;")
            self.btn_secondary.setVisible(False)

        # Details
        self.lbl_details.setText(self.comp.details)

        # Running indicator
        self.ico_running.setVisible(self._is_running)
        self.lbl_running_indicator.setVisible(self._is_running)

        # Status badge & Feather icon
        badge_text = self.comp.status_label
        badge_color = self.comp.status_color
        icon_name = "box"

        if self._is_running:
            badge_text = f"Active ({self.comp.status_label})"
            badge_color = "#38ef7d"
            icon_name = "zap"
        elif self.comp.status_code == "UP_TO_DATE":
            icon_name = "check-circle"
        elif self.comp.status_code == "OUTDATED":
            icon_name = "alert-circle"
        elif self.comp.status_code == "WEB_NATIVE":
            icon_name = "globe"
        else:
            icon_name = "box"

        self.badge_icon.setPixmap(get_feather_pixmap(icon_name, color=badge_color, size=11))
        self.badge_text.setText(badge_text)
        self.badge_text.setStyleSheet(f"""
            QLabel {{
                color: {badge_color};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        r, g, b = int(badge_color[1:3], 16), int(badge_color[3:5], 16), int(badge_color[5:7], 16)
        self.badge_frame.setStyleSheet(f"""
            QFrame#StatusBadge {{
                background-color: rgba({r}, {g}, {b}, 0.12);
                border: 1px solid rgba({r}, {g}, {b}, 0.35);
                border-radius: 11px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        # Primary button appearance and Feather icon
        if self.prog.is_web:
            if self._is_running:
                self.btn_primary.setText("Open Browser")
                ext_ico = get_feather_icon("external-link", color="#ffffff", size=13)
                if ext_ico and not ext_ico.isNull():
                    self.btn_primary.setIcon(ext_ico)
                    self.btn_primary.setIconSize(QSize(13, 13))
                self.btn_primary.setStyleSheet("""
                    QPushButton {
                        background-color: #1f6feb;
                        color: #ffffff;
                        border: none;
                        border-radius: 4px;
                        padding: 0 12px;
                        font-weight: bold;
                        font-size: 11.5px;
                    }
                    QPushButton:hover { background-color: #388bfd; }
                """)
                self.btn_stop.setVisible(True)
            else:
                self.btn_primary.setText("Launch Web Viewer")
                globe_ico = get_feather_icon("globe", color="#ffffff", size=13)
                if globe_ico and not globe_ico.isNull():
                    self.btn_primary.setIcon(globe_ico)
                    self.btn_primary.setIconSize(QSize(13, 13))
                self.btn_primary.setStyleSheet("""
                    QPushButton {
                        background-color: #238636;
                        color: #ffffff;
                        border: none;
                        border-radius: 4px;
                        padding: 0 12px;
                        font-weight: bold;
                        font-size: 11.5px;
                    }
                    QPushButton:hover { background-color: #2ea043; }
                """)
                self.btn_stop.setVisible(False)
        else:
            if self.comp.has_compiled:
                self.btn_primary.setText("Launch App")
                play_ico = get_feather_icon("play", color="#0b0e14", size=13)
                if play_ico and not play_ico.isNull():
                    self.btn_primary.setIcon(play_ico)
                    self.btn_primary.setIconSize(QSize(13, 13))
                self.btn_primary.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {self.prog.theme_color}, stop:1 {self.prog.accent_color});
                        color: #0b0e14;
                        border: none;
                        border-radius: 4px;
                        padding: 0 12px;
                        font-weight: bold;
                        font-size: 11.5px;
                    }}
                    QPushButton:hover {{
                        opacity: 0.9;
                        border: 1px solid #ffffff;
                    }}
                """)
            else:
                self.btn_primary.setText("Run Python")
                term_ico = get_feather_icon("terminal", color="#58a6ff", size=13)
                if term_ico and not term_ico.isNull():
                    self.btn_primary.setIcon(term_ico)
                    self.btn_primary.setIconSize(QSize(13, 13))
                self.btn_primary.setStyleSheet("""
                    QPushButton {
                        background-color: #21262d;
                        color: #58a6ff;
                        border: 1px solid #30363d;
                        border-radius: 4px;
                        padding: 0 12px;
                        font-weight: bold;
                        font-size: 11.5px;
                    }
                    QPushButton:hover {
                        background-color: #30363d;
                        color: #ffffff;
                    }
                """)
            self.btn_stop.setVisible(self._is_running)

    def _on_primary_action(self):
        if self.prog.is_web:
            if self._is_running:
                process_manager.open_web_in_browser()
            else:
                ok, msg = process_manager.launch_web_viewer(auto_open_browser=True)
                if not ok:
                    QMessageBox.warning(self, "Error", msg)
        else:
            ok, msg = process_manager.launch_program(self.prog.id, force_python=False)
            if not ok:
                QMessageBox.warning(self, "Error", msg)
        self.refresh()

    def _run_python_script(self):
        ok, msg = process_manager.launch_program(self.prog.id, force_python=True)
        if not ok:
            QMessageBox.warning(self, "Error", msg)
        self.refresh()

    def _stop_running_process(self):
        ok, msg = process_manager.stop_program(self.prog.id)
        self.refresh()

    def _open_compiler_for_this(self):
        window = self.window()
        if hasattr(window, "open_compiler"):
            window.open_compiler(target_prog_id=self.prog.id)


class BeatbarLauncherWindow(QMainWindow):
    """Main Dashboard Window for the Beatbar Suite Launcher."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BeatBar Suite - Launcher & Studio Hub")
        suite_ico = get_suite_icon("beatbar-main", size=32)
        if suite_ico and not suite_ico.isNull():
            self.setWindowIcon(suite_ico)
        self.setMinimumSize(820, 500)
        self.card_widgets: Dict[str, ProgramCard] = {}

        self.config = self._load_config()

        self._geom_autosave_timer = QTimer(self)
        self._geom_autosave_timer.setSingleShot(True)
        self._geom_autosave_timer.setInterval(600)
        self._geom_autosave_timer.timeout.connect(self._save_config)

        self._apply_global_styles()
        self._build_ui()
        self._apply_saved_settings()

        # Status polling timer for live running indicators
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self._poll_running_status)
        self.poll_timer.start()

    def _apply_global_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0e14;
            }
            QWidget#CentralWidget {
                background-color: #0b0e14;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #0b0e14;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #21262d;
                min-height: 16px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #30363d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 12, 14, 12)
        root_layout.setSpacing(10)

        # Header Bar
        header = QFrame()
        header.setObjectName("LauncherHeaderBar")
        header.setStyleSheet("""
            QFrame#LauncherHeaderBar {
                background-color: #161b22;
                border: none;
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                padding: 0px;
                margin: 0px;
                border: none;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(12)

        # Brand Icon
        brand_icon = QLabel()
        brand_icon.setObjectName("LauncherBrandIcon")
        brand_icon.setStyleSheet("background: transparent; padding: 0px; margin: 0px; border: none;")
        b_pm = get_suite_pixmap("beatbar-main", size=34, dark_mode=True)
        if b_pm and not b_pm.isNull():
            brand_icon.setPixmap(b_pm)
            brand_icon.setFixedSize(34, 34)
            brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            b_ico = get_feather_icon("sliders", color="#00f3ff", size=22)
            if b_ico and not b_ico.isNull():
                brand_icon.setPixmap(b_ico.pixmap(22, 22))
        h_layout.addWidget(brand_icon)

        # Suite Brand
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(1)
        brand_title = QLabel("BEATBAR SUITE")
        brand_title.setStyleSheet("""
            font-size: 15px;
            font-weight: 900;
            color: #ffffff;
            letter-spacing: 0.5px;
        """)
        brand_layout.addWidget(brand_title)

        brand_sub = QLabel("Desktop Rhythm Production & Video Sync Studio")
        brand_sub.setStyleSheet("font-size: 10.5px; color: #8b949e;")
        brand_layout.addWidget(brand_sub)
        h_layout.addLayout(brand_layout)

        h_layout.addStretch()

        # Top Action Buttons with Feather Icons
        # 1. Compile All Button
        self.btn_compile_all = QPushButton("Compile Programs...")
        self.btn_compile_all.setFixedHeight(28)
        self.btn_compile_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        pkg_ico = get_feather_icon("package", color="#ffffff", size=13)
        if pkg_ico and not pkg_ico.isNull():
            self.btn_compile_all.setIcon(pkg_ico)
            self.btn_compile_all.setIconSize(QSize(13, 13))
        self.btn_compile_all.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #8957e5);
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 0 12px;
                font-size: 11.5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #388bfd, stop:1 #a371f7);
            }
        """)
        self.btn_compile_all.clicked.connect(lambda: self.open_compiler(None))
        h_layout.addWidget(self.btn_compile_all)

        # 2. Open Compiled Folder
        self.btn_open_folder = QPushButton("Compiled Folder")
        self.btn_open_folder.setFixedHeight(28)
        self.btn_open_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        fld_ico = get_feather_icon("folder", color="#c9d1d9", size=13)
        if fld_ico and not fld_ico.isNull():
            self.btn_open_folder.setIcon(fld_ico)
            self.btn_open_folder.setIconSize(QSize(13, 13))
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_open_folder.clicked.connect(self._open_compiled_dir)
        h_layout.addWidget(self.btn_open_folder)

        # 3. Refresh Button
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedHeight(28)
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ref_ico = get_feather_icon("refresh-cw", color="#c9d1d9", size=13)
        if ref_ico and not ref_ico.isNull():
            self.btn_refresh.setIcon(ref_ico)
            self.btn_refresh.setIconSize(QSize(13, 13))
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_refresh.clicked.connect(self.refresh_all)
        h_layout.addWidget(self.btn_refresh)

        root_layout.addWidget(header)

        # Main Tabbed Container
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #0b0e14;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 7px 18px;
                border: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #21262d;
                color: #58a6ff;
            }
            }
            QTabBar::tab:hover:!selected {
                background: #1c2128;
                color: #c9d1d9;
            }
        """)

        # TAB 1: Programs Hub
        tab_programs = QWidget()
        tab_prog_layout = QVBoxLayout(tab_programs)
        tab_prog_layout.setContentsMargins(10, 10, 10, 10)
        tab_prog_layout.setSpacing(10)

        # Drag and Drop Area for .beat files
        self.dropzone = BeatDropZoneWidget(tab_programs)
        tab_prog_layout.addWidget(self.dropzone)

        # Sub-header / Library overview label
        sub_bar = QHBoxLayout()
        overview_label = QLabel("Program Suite")
        overview_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #e6edf3;")
        sub_bar.addWidget(overview_label)

        sub_bar.addStretch()

        self.summary_badge = QLabel("Scanning library...")
        self.summary_badge.setStyleSheet("font-size: 10.5px; color: #8b949e;")
        sub_bar.addWidget(self.summary_badge)
        tab_prog_layout.addLayout(sub_bar)

        # Library Cards Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        cards_container = QWidget()
        cards_layout = QGridLayout(cards_container)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(0, 0, 0, 0)

        # Place 4 cards in a 2x2 responsive grid
        prog_keys = list(PROGRAM_REGISTRY.keys())
        for idx, key in enumerate(prog_keys):
            prog = PROGRAM_REGISTRY[key]
            card = ProgramCard(prog, self)
            self.card_widgets[key] = card
            row = idx // 2
            col = idx % 2
            cards_layout.addWidget(card, row, col)

        scroll.setWidget(cards_container)
        tab_prog_layout.addWidget(scroll)

        tab_ico_prog = get_feather_icon("grid", "#58a6ff", 14)
        if tab_ico_prog and not tab_ico_prog.isNull():
            self.tabs.addTab(tab_programs, tab_ico_prog, "Programs Hub")
        else:
            self.tabs.addTab(tab_programs, "Programs Hub")

        # TAB 2: Skin Picker & Gallery
        self.skin_gallery = SkinGalleryWidget(self)
        tab_ico_skin = get_feather_icon("palette", "#e056fd", 14)
        if tab_ico_skin and not tab_ico_skin.isNull():
            self.tabs.addTab(self.skin_gallery, tab_ico_skin, "Skin Picker & Gallery")
        else:
            self.tabs.addTab(self.skin_gallery, "Skin Picker & Gallery")

        root_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._update_summary()

    def _on_tab_changed(self, index: int):
        if hasattr(self, "config"):
            self.config["active_tab"] = index
            self._save_config()

    def refresh_all(self):
        """Refreshes all program cards and summary stats."""
        for card in self.card_widgets.values():
            card.refresh()
        self._update_summary()

    def _update_summary(self):
        total = len(self.card_widgets)
        compilable = sum(1 for c in PROGRAM_REGISTRY.values() if c.can_compile)
        compiled_count = 0
        up_to_date_count = 0

        for key, prog in PROGRAM_REGISTRY.items():
            if not prog.can_compile:
                continue
            comp = compare_program_version(prog)
            if comp.has_compiled:
                compiled_count += 1
                if comp.status_code == "UP_TO_DATE":
                    up_to_date_count += 1

        self.summary_badge.setText(
            f"{total} Programs Available | {compiled_count} of {compilable} Desktop Binaries Compiled ({up_to_date_count} Up to date)"
        )

    def _poll_running_status(self):
        for card in self.card_widgets.values():
            is_run = process_manager.is_running(card.prog.id)
            if is_run != card._is_running:
                card.refresh()

    def open_compiler(self, target_prog_id: Optional[str] = None):
        """Opens the PyInstaller compilation dialog."""
        dialog = CompilerDialog(target_prog_id=target_prog_id, parent=self)
        dialog.compilation_completed.connect(self.refresh_all)
        dialog.exec()
        self.refresh_all()

    def _open_compiled_dir(self):
        os.makedirs(COMPILED_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(COMPILED_DIR)
        else:
            subprocess.Popen(["xdg-open", COMPILED_DIR])

    def _apply_saved_settings(self):
        w = int(self.config.get("window_width", 960))
        h = int(self.config.get("window_height", 620))
        self.resize(w, h)

        wx = self.config.get("window_x")
        wy = self.config.get("window_y")
        if wx is not None and wy is not None:
            self.move(QPoint(int(wx), int(wy)))

        if self.config.get("is_maximized", False):
            self.showMaximized()

        tab_idx = self.config.get("active_tab", 0)
        if hasattr(self, "tabs") and 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)

    def _load_config(self) -> dict:
        cfg = DEFAULT_LAUNCHER_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cfg.update(data)
            except Exception as e:
                print(f"[Launcher] Failed to load config from {CONFIG_PATH}:", e)
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

        if hasattr(self, "tabs") and self.tabs:
            self.config["active_tab"] = self.tabs.currentIndex()

        self._save_config_dict(self.config)

    def _save_config_dict(self, cfg: dict):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            print(f"[Launcher] Failed to save config to {CONFIG_PATH}:", e)

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
        self.poll_timer.stop()
        super().closeEvent(event)


def main():
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Beatbar Suite Launcher")
    app.setStyle("Fusion")

    # Dark Fusion Palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(11, 14, 20))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(201, 209, 217))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 27, 34))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(13, 17, 23))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(22, 27, 34))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(201, 209, 217))
    palette.setColor(QPalette.ColorRole.Text, QColor(201, 209, 217))
    palette.setColor(QPalette.ColorRole.Button, QColor(33, 38, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(201, 209, 217))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(31, 111, 235))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = BeatbarLauncherWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log_path = os.path.join(LAUNCHER_DIR, "launcher_error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Launcher error:\n\n{traceback.format_exc()}", "Beatbar Launcher Error", 0x10)
        except Exception:
            pass
        sys.exit(1)
