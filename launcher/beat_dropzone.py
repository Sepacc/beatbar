"""
beat_dropzone.py - Drag-and-Drop Area & Action Chooser for .beat Files in Suite Launcher.

Features:
- Drag-and-drop zone accepting .beat archives (with file browse fallback)
- BeatActionDialog with Feather SVG icons and modern dark styling:
  1. Play in Beatbar Viewer (viewer)
  2. Edit Beats in Beat Maker (main)
  3. Customize Skin in Skin Maker (beatpanel)
  4. Stream in Web Viewer (web)
- Zero emojis: Clean Feather SVG icons throughout
"""

import os
import sys
import zipfile
import json
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QDialog, QMessageBox, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QCursor, QColor, QFont

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(ROOT_DIR, "main")
for p in [ROOT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from icon_utils import get_feather_icon, get_suite_pixmap
from launcher.process_manager import process_manager


class BeatActionDialog(QDialog):
    """
    Action chooser dialog shown when a .beat file is dropped or selected.
    Presents 4 choices: Play in Viewer, Edit in Beat Maker, Customize in Skin Maker, Stream in Web Viewer.
    """
    def __init__(self, beat_path: str, parent=None):
        super().__init__(parent)
        self.beat_path = os.path.abspath(beat_path)
        self.setWindowTitle("Choose Action for .beat File")
        self.setFixedSize(540, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 10px;
            }
        """)

        self._read_metadata()
        self._init_ui()

    def _read_metadata(self):
        self.filename = os.path.basename(self.beat_path)
        self.file_size = os.path.getsize(self.beat_path) if os.path.exists(self.beat_path) else 0
        size_mb = self.file_size / (1024 * 1024)
        self.size_fmt = f"{size_mb:.1f} MB"

        self.duration_fmt = "Unknown"
        self.beat_count = 0
        self.difficulty = "Normal"
        self.has_video = False

        if os.path.exists(self.beat_path) and self.beat_path.lower().endswith(".beat"):
            try:
                with zipfile.ZipFile(self.beat_path, "r") as z:
                    names = z.namelist()
                    if "manifest.json" in names:
                        data = json.loads(z.read("manifest.json").decode("utf-8"))
                        dur = float(data.get("duration", 0))
                        if dur > 0:
                            m, s = int(dur // 60), int(dur % 60)
                            self.duration_fmt = f"{m:02d}:{s:02d}"
                        self.beat_count = int(data.get("beat_count", 0))
                        self.difficulty = data.get("difficulty", "Normal")
                    # Check for embedded video
                    for n in names:
                        if n.startswith("video/") or n.lower().endswith((".mp4", ".mkv", ".webm")):
                            self.has_video = True
                            break
            except Exception:
                pass

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header: Icon + Title
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_feather_icon("package", "#58a6ff", 26).pixmap(26, 26))
        hdr.addWidget(icon_lbl)

        hdr_text = QVBoxLayout()
        hdr_text.setSpacing(2)
        lbl_title = QLabel(self.filename)
        lbl_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        hdr_text.addWidget(lbl_title)

        v_text = "Embedded Video" if self.has_video else "Beatmap Pack"
        lbl_sub = QLabel(f"{self.size_fmt} • {self.beat_count} Beats • {self.difficulty} • {v_text}")
        lbl_sub.setStyleSheet("color: #8b949e; font-size: 11px;")
        hdr_text.addWidget(lbl_sub)
        hdr.addLayout(hdr_text)

        layout.addLayout(hdr)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #21262d; border: none; height: 1px;")
        layout.addWidget(sep)

        # Prompt
        lbl_prompt = QLabel("Choose what you would like to do with this file:")
        lbl_prompt.setStyleSheet("color: #c9d1d9; font-size: 12px; font-weight: 600;")
        layout.addWidget(lbl_prompt)

        # Action Buttons
        self._add_action_btn(
            layout,
            title="Play in BeatBar Viewer",
            subtitle="Watch with synchronized animated beatbar and audio",
            icon_name="beatbar-viewer",
            accent_color="#39ed4e",
            handler=self._play_viewer
        )

        self._add_action_btn(
            layout,
            title="Edit Beats in BeatBar Maker",
            subtitle="Open editor to tweak rhythm markers, BPM, and zones",
            icon_name="beatbar-maker",
            accent_color="#39bfed",
            handler=self._edit_maker
        )

        self._add_action_btn(
            layout,
            title="Customize in BeatBar Skin Maker",
            subtitle="Inspect or inject custom SVG skins and themes into this pack",
            icon_name="beatbar-skins",
            accent_color="#ed8139",
            handler=self._customize_skin
        )

        self._add_action_btn(
            layout,
            title="Stream in BeatBar Web Viewer",
            subtitle="Start Web Viewer server and stream to mobile or browser",
            icon_name="beatbar-web",
            accent_color="#3f39ed",
            handler=self._stream_web
        )

        layout.addStretch()

        # Bottom Cancel Button
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(30)
        btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #8b949e;
                font-size: 11px;
                padding: 4px 16px;
            }
            QPushButton:hover {
                background: #30363d;
                color: #ffffff;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

    def _add_action_btn(self, layout, title: str, subtitle: str, icon_name: str, accent_color: str, handler):
        btn = QPushButton()
        btn.setFixedHeight(50)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background-color: #21262d;
                border-color: {accent_color};
            }}
        """)

        b_layout = QHBoxLayout(btn)
        b_layout.setContentsMargins(10, 6, 12, 6)
        b_layout.setSpacing(12)

        ico_lbl = QLabel()
        s_pm = get_suite_pixmap(icon_name, size=22, dark_mode=True)
        if s_pm and not s_pm.isNull():
            ico_lbl.setPixmap(s_pm)
        else:
            ico_lbl.setPixmap(get_feather_icon(icon_name, accent_color, 20).pixmap(20, 20))
        b_layout.addWidget(ico_lbl)

        txt_layout = QVBoxLayout()
        txt_layout.setSpacing(1)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: #ffffff; font-size: 12px; font-weight: bold;")
        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
        txt_layout.addWidget(t_lbl)
        txt_layout.addWidget(s_lbl)
        b_layout.addLayout(txt_layout)

        b_layout.addStretch()

        arr_lbl = QLabel()
        arr_lbl.setPixmap(get_feather_icon("chevron-right", "#484f58", 16).pixmap(16, 16))
        b_layout.addWidget(arr_lbl)

        btn.clicked.connect(handler)
        layout.addWidget(btn)

    def _play_viewer(self):
        self.accept()
        process_manager.launch_program("beatbar_viewer", extra_args=[self.beat_path])

    def _edit_maker(self):
        self.accept()
        process_manager.launch_program("beatbar_maker", extra_args=[self.beat_path])

    def _customize_skin(self):
        self.accept()
        process_manager.launch_program("beatbar_skins", extra_args=[self.beat_path])

    def _stream_web(self):
        self.accept()
        process_manager.launch_web_viewer(auto_open_browser=True)


class BeatDropZoneWidget(QFrame):
    """
    Styled Drag-and-Drop Area for .beat files with browse fallback.
    """
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("BeatDropZone")
        self.setMinimumHeight(80)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.normal_style = """
            QFrame#BeatDropZone {
                background-color: #11141c;
                border: 2px dashed #30363d;
                border-radius: 8px;
            }
            QFrame#BeatDropZone:hover {
                border-color: #58a6ff;
                background-color: #161b22;
            }
        """
        self.active_style = """
            QFrame#BeatDropZone {
                background-color: #1a2233;
                border: 2px dashed #58a6ff;
                border-radius: 8px;
            }
        """
        self.setStyleSheet(self.normal_style)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        # Upload Cloud Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(get_feather_icon("upload-cloud", "#58a6ff", 28).pixmap(28, 28))
        layout.addWidget(self.icon_lbl)

        # Text prompt
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_lbl = QLabel("Drag & Drop a .beat File Here")
        self.title_lbl.setStyleSheet("color: #ffffff; font-size: 12.5px; font-weight: bold;")
        self.sub_lbl = QLabel("Drop to play in Viewer, edit beats, customize skins, or stream on Web")
        self.sub_lbl.setStyleSheet("color: #8b949e; font-size: 10.5px;")
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.sub_lbl)
        layout.addLayout(text_layout)

        layout.addStretch()

        # Browse Button
        self.btn_browse = QPushButton("Browse .beat...")
        self.btn_browse.setFixedHeight(28)
        self.btn_browse.setIcon(get_feather_icon("folder", "#c9d1d9", 13))
        self.btn_browse.setStyleSheet("""
            QPushButton {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                color: #c9d1d9;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #30363d;
                color: #ffffff;
                border-color: #58a6ff;
            }
        """)
        self.btn_browse.clicked.connect(self._browse_file)
        layout.addWidget(self.btn_browse)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse_file()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".beat"):
                    event.acceptProposedAction()
                    self.setStyleSheet(self.active_style)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.normal_style)
        event.accept()

    def dropEvent(self, event):
        self.setStyleSheet(self.normal_style)
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fpath = url.toLocalFile()
                if fpath.lower().endswith(".beat"):
                    event.acceptProposedAction()
                    self.handle_file(fpath)
                    return
        event.ignore()

    def _browse_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Select .beat File", ROOT_DIR, "Beat Archives (*.beat);;All Files (*)"
        )
        if fpath:
            self.handle_file(fpath)

    def handle_file(self, fpath: str):
        self.file_dropped.emit(fpath)
        dlg = BeatActionDialog(fpath, self.window())
        dlg.exec()
