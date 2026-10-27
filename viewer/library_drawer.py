"""
library_drawer.py - Fullscreen Visual Media Library & Playlist/Queue Manager for Desktop Viewer.

Features:
- Fullscreen tab interface matching modern Web & Desktop streaming apps:
  - Spacious top navigation bar with "Back to Player" (Esc / L), tabs, search, and rescan
  - Filter & Sort Bar: Difficulty, Duration, Rating, and Multi-attribute Sorting
  - Dynamic responsive multi-column grid of rich widescreen cards (1-5 columns based on window width)
- 100% Accurate .beat & Video Parsing using VideoScanner:
  - Real beat counts and rhythm zones from beatmap.json
  - Probed media durations and resolutions
  - High-quality pre-generated 16:9 thumbnail previews
- 5-Second Hover Preview:
  - Skips first 30s and last 30s
  - Smooth muted video preview loop using extracted media source
  - Reverts seamlessly to crisp static thumbnail when mouse leaves
- Interactive 5-Star Ratings on cards and in queue, syncing with ratings_manager
- Up Next Playlist / Queue Manager with reordering, removal, and auto-playback
- Zero emojis: Clean Feather SVG icons throughout
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal, QSize, QEvent, QUrl, QPoint, QThread
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QScrollArea, QFrame, QPushButton, QSizePolicy, QTabWidget, QListWidget,
    QListWidgetItem, QGridLayout, QStackedWidget
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QCursor, QImage, QPixmap,
    QPainterPath, QIcon, QLinearGradient
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

# Project paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(ROOT_DIR, "main")
for p in [ROOT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from icon_utils import get_feather_icon
from web.video_scanner import VideoScanner
try:
    from .skin_manager import SkinManager
except (ImportError, ValueError):
    from skin_manager import SkinManager


def clean_display_title(raw_title: str) -> str:
    if not raw_title:
        return "Untitled Track"
    t = raw_title.strip()
    for ext in [".beat", ".mp4", ".mkv", ".webm", ".avi", ".mov"]:
        if t.lower().endswith(ext):
            t = t[:-len(ext)]
    for suffix in ["_beats", "-beats", ".beats", "_beat", "-beat", "_720p", "_1080p", "-720p", "-1080p"]:
        if t.lower().endswith(suffix):
            t = t[:-len(suffix)]
    if " " not in t and ("_" in t or "-" in t):
        t = t.replace("_", " ").replace("-", " ")
        t = " ".join(word.capitalize() if not word.isupper() else word for word in t.split())
    elif "_" in t:
        t = t.replace("_", " ")
    return t


def _calc_preview_range(dur: float):
    dur = float(dur) if dur and dur > 0 else 60.0
    if dur >= 65.0:
        return 30.0, 35.0
    if dur > 35.0:
        return 30.0, min(dur, 35.0)
    start = max(0.0, (dur - 5.0) / 2.0)
    return start, min(dur, start + 5.0)


class HoverPreviewWidget(QWidget):
    """
    16:9 Thumbnail and Video Sink Widget.
    Renders high-quality static thumbnail with rounded corners by default,
    and smoothly transitions to a 5-second muted video loop on hover.
    """
    clicked = pyqtSignal()

    def __init__(self, thumbnail_path: str = "", parent=None):
        super().__init__(parent)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self.current_frame = None
        self.is_hovered = False

        self.thumbnail_pixmap = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            self.thumbnail_pixmap = QPixmap(thumbnail_path)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def set_thumbnail_path(self, path: str):
        if path and os.path.exists(path):
            self.thumbnail_pixmap = QPixmap(path)
            self.update()

    def set_hovered(self, hovered: bool):
        if self.is_hovered != hovered:
            self.is_hovered = hovered
            self.update()

    def _on_frame(self, frame):
        if frame.isValid():
            self.current_frame = frame.toImage()
            self.update()

    def clear_video(self):
        self.current_frame = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        W, H = self.width(), self.height()

        # Rounded container clipping path (anti-aliased 8px rounded corners)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 8.0, 8.0)
        painter.setClipPath(path)

        # Background fill
        painter.fillRect(0, 0, W, H, QColor("#090810"))

        # 1. Render active video frame if currently playing hover preview
        # Balanced zoom: expands horizontally to fill card width while preserving framing
        if self.current_frame and not self.current_frame.isNull():
            vw, vh = self.current_frame.width(), self.current_frame.height()
            if vw > 0 and vh > 0:
                min_scale = min(W / vw, H / vh)
                max_scale = max(W / vw, H / vh)
                scale = min_scale + (max_scale - min_scale) * 0.45
                dw, dh = vw * scale, vh * scale
                dx = (W - dw) / 2.0
                dy = (H - dh) / 2.0
                painter.drawImage(QRectF(dx, dy, dw, dh), self.current_frame)
        # 2. Render static thumbnail pixmap
        elif self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            pw, ph = self.thumbnail_pixmap.width(), self.thumbnail_pixmap.height()
            if pw > 0 and ph > 0:
                min_scale = min(W / pw, H / ph)
                max_scale = max(W / pw, H / ph)
                scale = min_scale + (max_scale - min_scale) * 0.45
                dw, dh = pw * scale, ph * scale
                dx = (W - dw) / 2.0
                dy = (H - dh) / 2.0
                painter.drawPixmap(QRectF(dx, dy, dw, dh), self.thumbnail_pixmap, QRectF(0, 0, pw, ph))
        else:
            # Elegant placeholder if thumbnail is missing
            painter.setPen(QColor("#52525b"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
            painter.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, "Video Preview")

        # Soft bottom gradient overlay for duration badge clarity
        b_grad = QLinearGradient(0, H - 45, 0, H)
        b_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        b_grad.setColorAt(1.0, QColor(0, 0, 0, 140))
        painter.fillRect(QRectF(0, H - 45, W, 45), b_grad)

        painter.end()


class VideoCardWidget(QFrame):
    """
    Widescreen Media Card displaying 16:9 thumbnail, duration pill,
    difficulty badge, beat count, resolution/size chips, interactive 5-star rating,
    and action buttons (Play Now, + Queue).
    """
    play_requested = pyqtSignal(dict)
    queue_requested = pyqtSignal(dict)
    hover_started = pyqtSignal(dict, object)
    hover_stopped = pyqtSignal()

    def __init__(self, video_data: dict, parent=None):
        super().__init__(parent)
        self.data = video_data
        self.filepath = video_data.get("filepath", "")
        self.filename = video_data.get("filename", "")
        self.title = video_data.get("title", "")

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(270)

        self.setStyleSheet("""
            VideoCardWidget {
                background: #151322;
                border: none;
                border-radius: 12px;
            }
            VideoCardWidget:hover {
                background: #1e1b30;
            }
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(7)

        # 1. 16:9 Thumbnail Container
        self.thumb_container = QWidget(self)
        self.thumb_container.setFixedHeight(154)
        self.thumb_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.thumb_container.setStyleSheet("background: #090810; border-radius: 8px;")
        t_layout = QVBoxLayout(self.thumb_container)
        t_layout.setContentsMargins(0, 0, 0, 0)

        thumb_path = video_data.get("thumbnail_path", "")
        self.preview_widget = HoverPreviewWidget(thumb_path, self.thumb_container)
        self.preview_widget.clicked.connect(lambda: self.play_requested.emit(self.data))
        t_layout.addWidget(self.preview_widget)

        # Top-Left Pill: Difficulty & Beat count badge
        beat_info = video_data.get("beat_info", {})
        beat_count = beat_info.get("beat_count", 0)
        diff = beat_info.get("difficulty", "Normal")
        diff_colors = {
            "easy": "#10b981",
            "normal": "#8b5cf6",
            "hard": "#f59e0b",
            "expert": "#ef4444",
            "master": "#ec4899",
        }
        badge_accent = diff_colors.get(diff.lower(), "#8b5cf6")
        if beat_count > 0:
            badge_text = f"{beat_count} Beats • {diff}"
            badge_bg = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {badge_accent}, stop:1 #9333ea)"
            badge_color = "#ffffff"
        else:
            badge_text = "No Beatmap"
            badge_bg = "rgba(39, 39, 46, 0.88)"
            badge_color = "#a1a1aa"

        self.lbl_badge = QLabel(badge_text, self.thumb_container)
        self.lbl_badge.setStyleSheet(f"""
            background: {badge_bg};
            border: none;
            color: {badge_color};
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
        """)
        self.lbl_badge.adjustSize()
        self.lbl_badge.move(8, 8)

        # Bottom-Right Pill: Duration
        dur_fmt = video_data.get("duration_formatted", "00:00")
        self.lbl_dur = QLabel(dur_fmt, self.thumb_container)
        self.lbl_dur.setStyleSheet("""
            background: rgba(0, 0, 0, 0.78);
            border: none;
            color: #f1f5f9;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 4px;
        """)
        self.lbl_dur.adjustSize()
        self.lbl_dur.move(self.thumb_container.width() - self.lbl_dur.width() - 8, 126)

        card_layout.addWidget(self.thumb_container)

        # 2. Metadata Section
        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(2, 0, 2, 0)
        meta_layout.setSpacing(3)

        # Clean display title
        disp_title = clean_display_title(self.title)
        self.lbl_title = QLabel(disp_title)
        self.lbl_title.setStyleSheet("""
            color: #f8fafc;
            font-weight: 700;
            font-size: 13px;
        """)
        self.lbl_title.setToolTip(f"{self.title}\n{self.filepath}")
        self.lbl_title.setWordWrap(False)
        meta_layout.addWidget(self.lbl_title)

        # Subtitle: Difficulty, File Size, and Bundle Type
        size_fmt = video_data.get("file_size_formatted", "")
        is_bundle = video_data.get("is_bundle", False)
        bundle_tag = ".beat pack" if is_bundle else "video"
        sub_items = [x for x in [diff if beat_count > 0 else "", size_fmt, bundle_tag] if x]
        sub_text = " • ".join(sub_items)

        self.lbl_sub = QLabel(sub_text)
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub.setStyleSheet("""
            color: #9490af;
            font-size: 11px;
            font-weight: 500;
            padding: 3px 6px;
        """)
        meta_layout.addWidget(self.lbl_sub)

        # 3. Action Buttons Row (Queue and Play)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(8)

        # "Queue" Button (SVG icon provides the + symbol)
        self.btn_queue = QPushButton(" Queue")
        self.btn_queue.setIcon(get_feather_icon("plus", "#d1d5db", 13))
        self.btn_queue.setFixedHeight(30)
        self.btn_queue.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_queue.setToolTip("Add to Up Next Queue")
        self.btn_queue.setStyleSheet("""
            QPushButton {
                background: #252238;
                border: none;
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #332d4e;
                color: #ffffff;
            }
        """)
        self.btn_queue.clicked.connect(self._on_queue_clicked)
        footer_layout.addWidget(self.btn_queue, stretch=1)

        # "Play" Button
        self.btn_play = QPushButton(" Play")
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 12))
        self.btn_play.setFixedHeight(30)
        self.btn_play.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_play.setToolTip("Play in Viewer")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #9333ea);
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 11.5px;
                font-weight: bold;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #a855f7);
            }
            QPushButton:pressed {
                background: #6d28d9;
            }
        """)
        self.btn_play.clicked.connect(lambda: self.play_requested.emit(self.data))
        footer_layout.addWidget(self.btn_play, stretch=2)

        meta_layout.addLayout(footer_layout)
        card_layout.addLayout(meta_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep duration overlay pinned to bottom-right corner on resize
        tw = self.thumb_container.width()
        self.lbl_dur.move(tw - self.lbl_dur.width() - 8, 126)

    def _on_queue_clicked(self):
        self.queue_requested.emit(self.data)
        # Temporary visual feedback
        self.btn_queue.setText(" Added!")
        self.btn_queue.setIcon(get_feather_icon("check", "#10b981", 13))
        self.btn_queue.setStyleSheet("""
            QPushButton {
                background: #064e3b;
                border: none;
                border-radius: 6px;
                color: #10b981;
                font-size: 11px;
                font-weight: bold;
                padding: 0 12px;
            }
        """)
        QTimer.singleShot(1200, self._reset_queue_btn)

    def _reset_queue_btn(self):
        self.btn_queue.setText(" Queue")
        self.btn_queue.setIcon(get_feather_icon("plus", "#d1d5db", 13))
        self.btn_queue.setStyleSheet("""
            QPushButton {
                background: #252238;
                border: none;
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #332d4e;
                color: #ffffff;
            }
        """)

    def enterEvent(self, event):
        self.preview_widget.set_hovered(True)
        self.hover_started.emit(self.data, self.preview_widget)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.preview_widget.set_hovered(False)
        self.hover_stopped.emit()
        super().leaveEvent(event)


class QueueRowWidget(QFrame):
    """Horizontal row widget for the Up Next Queue management view."""
    play_requested = pyqtSignal(dict)
    remove_requested = pyqtSignal(dict)
    move_up_requested = pyqtSignal(dict)
    move_down_requested = pyqtSignal(dict)

    def __init__(self, index: int, data: dict, parent=None):
        super().__init__(parent)
        self.index = index
        self.data = data

        self.setStyleSheet("""
            QueueRowWidget {
                background: #151322;
                border: none;
                border-radius: 8px;
            }
            QueueRowWidget:hover {
                background: #1e1b30;
            }
        """)
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Index badge
        lbl_idx = QLabel(f"#{index + 1}")
        lbl_idx.setStyleSheet("color: #8b5cf6; font-weight: bold; font-size: 13px; min-width: 28px;")
        layout.addWidget(lbl_idx)

        # Mini thumbnail
        thumb_path = data.get("thumbnail_path", "")
        lbl_thumb = QLabel()
        lbl_thumb.setFixedSize(88, 50)
        lbl_thumb.setStyleSheet("background: #090810; border-radius: 4px;")
        if thumb_path and os.path.exists(thumb_path):
            pix = QPixmap(thumb_path).scaled(88, 50, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            lbl_thumb.setPixmap(pix)
            lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_thumb)

        # Title & details
        v_box = QVBoxLayout()
        v_box.setContentsMargins(0, 2, 0, 2)
        v_box.setSpacing(2)

        raw_title = data.get("title", "Unknown Track")
        disp_title = clean_display_title(raw_title)
        lbl_title = QLabel(disp_title)
        lbl_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        lbl_title.setToolTip(raw_title)
        v_box.addWidget(lbl_title)

        beat_info = data.get("beat_info", {})
        beat_count = beat_info.get("beat_count", 0)
        diff = beat_info.get("difficulty", "Normal")
        dur_fmt = data.get("duration_formatted", "00:00")
        info_text = f"{dur_fmt}  •  {beat_count} Beats  •  {diff}"
        lbl_info = QLabel(info_text)
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_box.addWidget(lbl_info)

        layout.addLayout(v_box, 1)

        # Controls: Move Up, Move Down, Remove, Play
        self.btn_up = QPushButton()
        self.btn_up.setFixedSize(28, 28)
        self.btn_up.setIcon(get_feather_icon("chevron-up", "#d1d5db", 14))
        self.btn_up.setToolTip("Move Up in Queue")
        self.btn_up.setStyleSheet("QPushButton { background: #252238; border: none; border-radius: 4px; } QPushButton:hover { background: #353050; }")
        self.btn_up.clicked.connect(lambda: self.move_up_requested.emit(self.data))
        layout.addWidget(self.btn_up)

        self.btn_down = QPushButton()
        self.btn_down.setFixedSize(28, 28)
        self.btn_down.setIcon(get_feather_icon("chevron-down", "#d1d5db", 14))
        self.btn_down.setToolTip("Move Down in Queue")
        self.btn_down.setStyleSheet("QPushButton { background: #252238; border: none; border-radius: 4px; } QPushButton:hover { background: #353050; }")
        self.btn_down.clicked.connect(lambda: self.move_down_requested.emit(self.data))
        layout.addWidget(self.btn_down)

        self.btn_remove = QPushButton()
        self.btn_remove.setFixedSize(28, 28)
        self.btn_remove.setIcon(get_feather_icon("trash-2", "#f87171", 14))
        self.btn_remove.setToolTip("Remove from Queue")
        self.btn_remove.setStyleSheet("QPushButton { background: #252238; border: none; border-radius: 4px; } QPushButton:hover { background: #451a1a; }")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.data))
        layout.addWidget(self.btn_remove)

        self.btn_play = QPushButton("Play")
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 12))
        self.btn_play.setFixedHeight(28)
        self.btn_play.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #9333ea);
                border: none;
                border-radius: 4px;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #a855f7);
            }
        """)
        self.btn_play.clicked.connect(lambda: self.play_requested.emit(self.data))
        layout.addWidget(self.btn_play)


class LibraryScanWorker(QThread):
    """Background worker that scans media and thumbnails off the main GUI thread."""
    item_scanned = pyqtSignal(dict, int, int)
    scan_finished = pyqtSignal(list, int, int)

    def __init__(self, videos_dir: str, parent=None):
        super().__init__(parent)
        self.videos_dir = videos_dir
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not os.path.exists(self.videos_dir):
            self.scan_finished.emit([], 0, 0)
            return

        scanner = VideoScanner(self.videos_dir)
        raw_items = scanner.scan()
        total = len(raw_items)

        items = []
        with_beats = 0
        missing_beats = 0

        for idx, it in enumerate(raw_items, start=1):
            if self._is_cancelled:
                return

            fpath = it.get("filepath")
            if not fpath:
                fpath = os.path.join(self.videos_dir, it["filename"])
                it["filepath"] = fpath

            # Background thumbnail creation with FFmpeg
            if not it.get("thumbnail_path"):
                it["thumbnail_path"] = scanner.ensure_thumbnail(fpath, it["filename"], it.get("duration", 0))

            b_info = it.get("beat_info", {})
            has_beats = b_info.get("has_beats", False) and b_info.get("beat_count", 0) > 0
            if has_beats:
                with_beats += 1
            else:
                missing_beats += 1

            items.append(it)
            self.item_scanned.emit(it, idx, total)

        if not self._is_cancelled:
            self.scan_finished.emit(items, with_beats, missing_beats)


class LibraryDrawerWidget(QWidget):
    """
    Fullscreen Visual Media Library Tab & Up Next Queue Manager.
    Replaces the narrow slide-out drawer with a complete, modern fullscreen interface.
    """
    play_video_requested = pyqtSignal(str, str)  # video_path, beat_path
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.videos_data = []
        self.filtered_data = []
        self.queue = []
        self.current_tab = "all"  # "all", "beats", "missing", "queue"

        self._scan_worker = None
        self._progressive_filter_timer = QTimer(self)
        self._progressive_filter_timer.setSingleShot(True)
        self._progressive_filter_timer.setInterval(80)
        self._progressive_filter_timer.timeout.connect(self._apply_filters)

        # Background preview player
        self.preview_player = QMediaPlayer(self)
        self.preview_audio = QAudioOutput(self)
        self.preview_audio.setVolume(0.0)  # Muted preview loop
        self.preview_player.setAudioOutput(self.preview_audio)
        self.active_preview_widget = None
        self.preview_range = (30.0, 35.0)

        # Hover preview debounce & loop timer
        self.preview_debounce_timer = QTimer(self)
        self.preview_debounce_timer.setSingleShot(True)
        self.preview_debounce_timer.setInterval(150)
        self.preview_debounce_timer.timeout.connect(self._start_preview_playback)

        self.preview_loop_timer = QTimer(self)
        self.preview_loop_timer.setInterval(100)
        self.preview_loop_timer.timeout.connect(self._check_preview_loop)

        self._pending_preview_data = None
        self._pending_preview_widget = None
        self.skin_manager = SkinManager()

        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main Fullscreen Background Glass Panel
        self.bg_panel = QFrame(self)
        self.bg_panel.setStyleSheet("""
            QFrame#bg_panel {
                background-color: #0b0914;
                border: none;
            }
        """)
        self.bg_panel.setObjectName("bg_panel")
        panel_layout = QVBoxLayout(self.bg_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # =====================================================================
        # 1. TOP NAVIGATION APP BAR (Header)
        # =====================================================================
        self.header = QFrame(self.bg_panel)
        self.header.setFixedHeight(56)
        self.header.setStyleSheet("""
            QFrame {
                background: #100e1b;
                border-bottom: 1px solid #232032;
            }
        """)
        hdr_layout = QHBoxLayout(self.header)
        hdr_layout.setContentsMargins(16, 0, 16, 0)
        hdr_layout.setSpacing(12)

        # Back to Player Button
        self.btn_back = QPushButton(" Back to Player")
        self.btn_back.setIcon(get_feather_icon("arrow-left", "#ffffff", 16))
        self.btn_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_back.setToolTip("Return to Player (Esc or L)")
        self.btn_back.setFixedHeight(34)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background: #232034;
                border: 1px solid #3d3856;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #7c3aed;
                border-color: #8b5cf6;
            }
        """)
        self.btn_back.clicked.connect(self._close_library)
        hdr_layout.addWidget(self.btn_back)

        # Vertical divider
        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.VLine)
        div1.setFixedHeight(24)
        div1.setStyleSheet("color: #2b273e;")
        hdr_layout.addWidget(div1)

        # Title / Brand
        lbl_brand_icon = QLabel()
        lbl_brand_icon.setPixmap(get_feather_icon("film", "#a855f7", 20).pixmap(20, 20))
        hdr_layout.addWidget(lbl_brand_icon)

        lbl_title = QLabel("Media Library")
        lbl_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 16px;")
        hdr_layout.addWidget(lbl_title)

        hdr_layout.addStretch()

        # Search Input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tracks by title, filename, artist...")
        self.search_input.setFixedHeight(32)
        self.search_input.setFixedWidth(280)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #181527;
                border: 1px solid #332d4a;
                border-radius: 16px;
                color: #ffffff;
                padding: 0 14px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8b5cf6;
                background: #1d1a30;
            }
        """)
        self.search_input.textChanged.connect(self._apply_filters)
        hdr_layout.addWidget(self.search_input)

        # Rescan button
        self.btn_rescan = QPushButton()
        self.btn_rescan.setFixedSize(32, 32)
        self.btn_rescan.setIcon(get_feather_icon("refresh-cw", "#c4b5fd", 15))
        self.btn_rescan.setToolTip("Rescan Videos Folder")
        self.btn_rescan.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_rescan.setStyleSheet("""
            QPushButton {
                background: #1e1b2f;
                border: 1px solid #332d4a;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #2a2542;
                border-color: #8b5cf6;
            }
        """)
        self.btn_rescan.clicked.connect(self.scan_library)
        hdr_layout.addWidget(self.btn_rescan)

        # Window Controls (in frameless mode)
        self.btn_min = self._create_win_btn("minus", "#94a3b8", "Minimize", self._on_min_clicked)
        self.btn_max = self._create_win_btn("square", "#94a3b8", "Maximize/Restore", self._on_max_clicked)
        self.btn_close_win = self._create_win_btn("x", "#94a3b8", "Close Viewer", self._on_close_clicked)
        hdr_layout.addWidget(self.btn_min)
        hdr_layout.addWidget(self.btn_max)
        hdr_layout.addWidget(self.btn_close_win)

        panel_layout.addWidget(self.header)

        # =====================================================================
        # 2. FILTER & SORT TOOLBAR
        # =====================================================================
        self.filter_bar = QFrame(self.bg_panel)
        self.filter_bar.setFixedHeight(44)
        self.filter_bar.setStyleSheet("""
            QFrame {
                background: #0e0c17;
                border-bottom: 1px solid #1e1b2c;
            }
        """)
        fb_layout = QHBoxLayout(self.filter_bar)
        fb_layout.setContentsMargins(18, 0, 18, 0)
        fb_layout.setSpacing(10)

        # Filter icon & label
        lbl_filter = QLabel("Filters:")
        lbl_filter.setStyleSheet("color: #71717a; font-weight: 600; font-size: 11px;")
        fb_layout.addWidget(lbl_filter)

        combo_style = """
            QComboBox {
                background: #161324;
                border: 1px solid #2a253c;
                border-radius: 6px;
                color: #d1d5db;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 500;
                min-width: 90px;
            }
            QComboBox:hover {
                border-color: #8b5cf6;
            }
            QComboBox QAbstractItemView {
                background: #161324;
                color: #ffffff;
                selection-background-color: #7c3aed;
                border: 1px solid #363248;
            }
        """

        self.cb_diff = QComboBox()
        self.cb_diff.addItems(["All Difficulties", "Easy", "Normal", "Hard", "Expert", "Master"])
        self.cb_diff.setStyleSheet(combo_style)
        saved_diff = self.skin_manager.config.get("library_diff_filter", "All Difficulties")
        idx_diff = self.cb_diff.findText(saved_diff)
        if idx_diff >= 0:
            self.cb_diff.setCurrentIndex(idx_diff)
        self.cb_diff.currentIndexChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.cb_diff)

        self.cb_dur = QComboBox()
        self.cb_dur.addItems(["All Durations", "Short (<2m)", "Medium (2-4m)", "Long (>4m)"])
        self.cb_dur.setStyleSheet(combo_style)
        saved_dur = self.skin_manager.config.get("library_dur_filter", "All Durations")
        idx_dur = self.cb_dur.findText(saved_dur)
        if idx_dur >= 0:
            self.cb_dur.setCurrentIndex(idx_dur)
        self.cb_dur.currentIndexChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.cb_dur)

        # Sort dropdown
        fb_layout.addSpacing(12)
        lbl_sort = QLabel("Sort by:")
        lbl_sort.setStyleSheet("color: #71717a; font-weight: 600; font-size: 11px;")
        fb_layout.addWidget(lbl_sort)

        self.cb_sort = QComboBox()
        self.cb_sort.addItems(["Date (Newest)", "Date (Oldest)", "Title (A-Z)", "Duration (Longest)", "Duration (Shortest)", "Beat Count (Most)"])
        self.cb_sort.setStyleSheet(combo_style)
        saved_sort = self.skin_manager.config.get("library_sort_order", "Date (Newest)")
        idx_sort = self.cb_sort.findText(saved_sort)
        if idx_sort >= 0:
            self.cb_sort.setCurrentIndex(idx_sort)
        self.cb_sort.currentIndexChanged.connect(self._apply_filters)
        fb_layout.addWidget(self.cb_sort)

        # Vertical divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.VLine)
        div2.setFixedHeight(22)
        div2.setStyleSheet("color: #2b273e;")
        fb_layout.addWidget(div2)

        # Navigation Category Tabs moved to toolbar (highlighted area)
        fb_layout.addSpacing(4)
        self.tab_btn_all = self._create_nav_pill("All Tracks (0)", "all", True)
        self.tab_btn_beats = self._create_nav_pill("With Beats (0)", "beats")
        self.tab_btn_missing = self._create_nav_pill("Missing Beats (0)", "missing")
        self.tab_btn_queue = self._create_nav_pill("Up Next Queue (0)", "queue")

        fb_layout.addWidget(self.tab_btn_all)
        fb_layout.addWidget(self.tab_btn_beats)
        fb_layout.addWidget(self.tab_btn_missing)
        fb_layout.addWidget(self.tab_btn_queue)

        fb_layout.addStretch()

        # Track count status
        self.lbl_status = QLabel("Showing 0 tracks")
        self.lbl_status.setStyleSheet("color: #71717a; font-size: 11px;")
        fb_layout.addWidget(self.lbl_status)

        panel_layout.addWidget(self.filter_bar)

        # =====================================================================
        # 3. STACKED MAIN BODY (Grid Cards vs Up Next Queue)
        # =====================================================================
        self.stack = QStackedWidget(self.bg_panel)

        # PAGE 0: Responsive Card Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #0b0914;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #282438;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8b5cf6;
            }
        """)

        self.scroll_content = QWidget()
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        self.grid_layout.setSpacing(16)
        self.scroll_area.setWidget(self.scroll_content)
        self.stack.addWidget(self.scroll_area)

        # PAGE 1: Up Next Queue Management
        self.queue_page = QWidget()
        qp_layout = QVBoxLayout(self.queue_page)
        qp_layout.setContentsMargins(24, 16, 24, 16)
        qp_layout.setSpacing(12)

        # Queue toolbar
        q_hdr = QHBoxLayout()
        lbl_q_title = QLabel("Up Next Playlist Queue")
        lbl_q_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 16px;")
        q_hdr.addWidget(lbl_q_title)

        q_hdr.addStretch()

        self.btn_clear_q = QPushButton(" Clear Queue")
        self.btn_clear_q.setIcon(get_feather_icon("trash-2", "#f87171", 13))
        self.btn_clear_q.setFixedHeight(30)
        self.btn_clear_q.setStyleSheet("""
            QPushButton {
                background: #201d2d;
                border: 1px solid #3d2328;
                border-radius: 6px;
                color: #f87171;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #3b181d;
                border-color: #f87171;
            }
        """)
        self.btn_clear_q.clicked.connect(self.clear_queue)
        q_hdr.addWidget(self.btn_clear_q)

        self.btn_play_next = QPushButton(" Play Next")
        self.btn_play_next.setIcon(get_feather_icon("play", "#ffffff", 13))
        self.btn_play_next.setFixedHeight(30)
        self.btn_play_next.setStyleSheet("""
            QPushButton {
                background: #7c3aed;
                border: 1px solid #8b5cf6;
                border-radius: 6px;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: #9333ea;
            }
        """)
        self.btn_play_next.clicked.connect(self.pop_and_play_next)
        q_hdr.addWidget(self.btn_play_next)

        qp_layout.addLayout(q_hdr)

        # Queue items scroll area
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.queue_content = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_content)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(8)
        self.queue_layout.addStretch()
        self.queue_scroll.setWidget(self.queue_content)
        qp_layout.addWidget(self.queue_scroll)

        self.stack.addWidget(self.queue_page)
        panel_layout.addWidget(self.stack)

        root_layout.addWidget(self.bg_panel)

    def _create_nav_pill(self, text: str, tab_id: str, is_active: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(28)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setProperty("tab_id", tab_id)
        self._update_pill_style(btn, is_active)
        btn.clicked.connect(lambda: self._on_nav_pill_clicked(tab_id))
        return btn

    def _update_pill_style(self, btn: QPushButton, is_active: bool):
        if is_active:
            btn.setStyleSheet("""
                QPushButton {
                    background: #7c3aed;
                    border: none;
                    border-radius: 14px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 0 11px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: #181527;
                    border: 1px solid #2a253c;
                    border-radius: 14px;
                    color: #94a3b8;
                    font-size: 11px;
                    font-weight: 500;
                    padding: 0 11px;
                }
                QPushButton:hover {
                    border-color: #8b5cf6;
                    color: #ffffff;
                }
            """)

    def _create_win_btn(self, icon_name: str, color: str, tip: str, callback) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(30, 30)
        btn.setIcon(get_feather_icon(icon_name, color, 14))
        btn.setToolTip(tip)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background: #262238; }
        """)
        btn.clicked.connect(callback)
        return btn

    def _on_nav_pill_clicked(self, tab_id: str):
        self.current_tab = tab_id
        self._update_pill_style(self.tab_btn_all, tab_id == "all")
        self._update_pill_style(self.tab_btn_beats, tab_id == "beats")
        self._update_pill_style(self.tab_btn_missing, tab_id == "missing")
        self._update_pill_style(self.tab_btn_queue, tab_id == "queue")

        if tab_id == "queue":
            self.cb_diff.setEnabled(False)
            self.cb_dur.setEnabled(False)
            self.cb_sort.setEnabled(False)
            self.stack.setCurrentIndex(1)
            self._render_queue()
        else:
            self.cb_diff.setEnabled(True)
            self.cb_dur.setEnabled(True)
            self.cb_sort.setEnabled(True)
            self.stack.setCurrentIndex(0)
            self._apply_filters()

    def _close_library(self):
        self.hide()
        self.closed.emit()

    def _on_min_clicked(self):
        win = self.window()
        if win and hasattr(win, "showMinimized"):
            win.showMinimized()

    def _on_max_clicked(self):
        win = self.window()
        if win and hasattr(win, "_toggle_maximize"):
            win._toggle_maximize()

    def _on_close_clicked(self):
        win = self.window()
        if win and hasattr(win, "close"):
            win.close()

    # =========================================================================
    # SCANNING & FILTERING
    # =========================================================================

    def scan_library(self):
        """Scans videos folder in background QThread, streaming parsed cards to UI progressively."""
        videos_dir = os.path.join(ROOT_DIR, "videos")
        if not os.path.exists(videos_dir):
            self.videos_data = []
            self._apply_filters()
            return

        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.cancel()
            self._scan_worker.wait(300)

        self.videos_data = []
        self.btn_rescan.setEnabled(False)
        self.lbl_status.setText("Scanning library...")

        self._scan_worker = LibraryScanWorker(videos_dir, self)
        self._scan_worker.item_scanned.connect(self._on_item_scanned)
        self._scan_worker.scan_finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_item_scanned(self, item: dict, current: int, total: int):
        self.videos_data.append(item)
        self.lbl_status.setText(f"Scanning media ({current}/{total})...")
        self.tab_btn_all.setText(f"All Tracks ({len(self.videos_data)})")
        if not self._progressive_filter_timer.isActive():
            self._progressive_filter_timer.start()

    def _on_scan_finished(self, items: list, with_beats: int, missing_beats: int):
        self.videos_data = items
        self.btn_rescan.setEnabled(True)
        self.tab_btn_all.setText(f"All Tracks ({len(items)})")
        self.tab_btn_beats.setText(f"With Beats ({with_beats})")
        self.tab_btn_missing.setText(f"Missing Beats ({missing_beats})")
        self.tab_btn_queue.setText(f"Up Next Queue ({len(self.queue)})")
        self._apply_filters()
        self._scan_worker = None

    def hideEvent(self, event):
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.cancel()
            self._scan_worker.wait(300)
        super().hideEvent(event)

    def wait_for_scan(self, timeout_ms: int = 10000):
        """Helper to block until background scanning finishes (for test runners and sync callers)."""
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.wait(timeout_ms)
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.processEvents()

    def _apply_filters(self):
        """Applies category tabs, text search, difficulty, duration, rating, and sorting."""
        if self.current_tab == "queue":
            return

        query = self.search_input.text().strip().lower()
        diff_filter = self.cb_diff.currentText()
        dur_filter = self.cb_dur.currentText()
        sort_opt = self.cb_sort.currentText()

        # Autosave filter preferences to SkinManager config
        if hasattr(self, "skin_manager") and self.skin_manager:
            self.skin_manager.config["library_diff_filter"] = diff_filter
            self.skin_manager.config["library_dur_filter"] = dur_filter
            self.skin_manager.config["library_sort_order"] = sort_opt
            self.skin_manager.save_config()

        res = []
        for v in self.videos_data:
            # 1. Category Tab Filter
            b_info = v.get("beat_info", {})
            has_b = b_info.get("has_beats", False) and b_info.get("beat_count", 0) > 0
            if self.current_tab == "beats" and not has_b:
                continue
            if self.current_tab == "missing" and has_b:
                continue

            # 2. Text Search
            if query:
                title = v.get("title", "").lower()
                fname = v.get("filename", "").lower()
                diff_str = b_info.get("difficulty", "").lower()
                if query not in title and query not in fname and query not in diff_str:
                    continue

            # 3. Difficulty Filter
            v_diff = b_info.get("difficulty", "Normal")
            if diff_filter != "All Difficulties" and v_diff.lower() != diff_filter.lower():
                continue

            # 4. Duration Filter
            dur = v.get("duration", 0)
            if dur_filter == "Short (<2m)" and dur >= 120:
                continue
            if dur_filter == "Medium (2-4m)" and (dur < 120 or dur > 240):
                continue
            if dur_filter == "Long (>4m)" and dur <= 240:
                continue

            res.append(v)

        # 5. Sorting
        if sort_opt == "Date (Newest)":
            res.sort(key=lambda x: x.get("mtime", 0), reverse=True)
        elif sort_opt == "Date (Oldest)":
            res.sort(key=lambda x: x.get("mtime", 0))
        elif sort_opt == "Title (A-Z)":
            res.sort(key=lambda x: x.get("title", "").lower())
        elif sort_opt == "Duration (Longest)":
            res.sort(key=lambda x: x.get("duration", 0), reverse=True)
        elif sort_opt == "Duration (Shortest)":
            res.sort(key=lambda x: x.get("duration", 0))
        elif sort_opt == "Beat Count (Most)":
            res.sort(key=lambda x: x.get("beat_info", {}).get("beat_count", 0), reverse=True)

        self.filtered_data = res
        self.lbl_status.setText(f"Showing {len(res)} of {len(self.videos_data)} tracks")
        self._render_cards()

    # =========================================================================
    # RESPONSIVE CARD GRID
    # =========================================================================

    def _render_cards(self):
        """Renders filtered cards into a multi-column responsive grid."""
        # Clear existing widgets from grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.filtered_data:
            empty_lbl = QLabel("No media tracks match the selected filters.")
            empty_lbl.setStyleSheet("color: #71717a; font-size: 14px; font-weight: 500; padding: 40px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(empty_lbl, 0, 0, 1, 1)
            return

        cols = self._calc_column_count()
        for idx, v in enumerate(self.filtered_data):
            row = idx // cols
            col = idx % cols
            card = VideoCardWidget(v, self.scroll_content)
            card.play_requested.connect(self._on_card_play)
            card.queue_requested.connect(self.add_to_queue)
            card.hover_started.connect(self._on_card_hover_start)
            card.hover_stopped.connect(self._on_card_hover_stop)
            self.grid_layout.addWidget(card, row, col)

    def _calc_column_count(self) -> int:
        viewport_w = self.scroll_area.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.width() or 1000
        cols = max(1, min(5, viewport_w // 320))
        return cols

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-layout grid if column count changes on window resize
        if self.isVisible() and self.stack.currentIndex() == 0 and self.filtered_data:
            new_cols = self._calc_column_count()
            current_cols = self.grid_layout.columnCount()
            if new_cols != current_cols:
                self._render_cards()

    def _on_card_play(self, data: dict):
        self._on_card_hover_stop()
        fpath = data.get("filepath", "")
        self.play_video_requested.emit(fpath, "")
        self.hide()

    # =========================================================================
    # UP NEXT QUEUE MANAGEMENT
    # =========================================================================

    def add_to_queue(self, data: dict):
        self.queue.append(data)
        self.tab_btn_queue.setText(f"Up Next Queue ({len(self.queue)})")
        if self.current_tab == "queue":
            self._render_queue()

    def clear_queue(self):
        self.queue.clear()
        self.tab_btn_queue.setText("Up Next Queue (0)")
        self._render_queue()

    def pop_and_play_next(self) -> Optional[dict]:
        if not self.queue:
            return None
        data = self.queue.pop(0)
        self.tab_btn_queue.setText(f"Up Next Queue ({len(self.queue)})")
        self._render_queue()
        self.play_video_requested.emit(data["filepath"], "")
        self.hide()
        return data

    def has_next_queued(self) -> bool:
        return len(self.queue) > 0

    def _render_queue(self):
        # Clear existing rows
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.queue:
            empty_w = QLabel("Your Up Next Queue is empty.\nClick '+ Queue' on any library card to add tracks.")
            empty_w.setStyleSheet("color: #71717a; font-size: 14px; font-weight: 500; padding: 60px;")
            empty_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.queue_layout.insertWidget(0, empty_w)
            return

        for idx, item in enumerate(self.queue):
            row = QueueRowWidget(idx, item, self.queue_content)
            row.play_requested.connect(self._on_queue_row_play)
            row.remove_requested.connect(self._on_queue_row_remove)
            row.move_up_requested.connect(self._on_queue_row_up)
            row.move_down_requested.connect(self._on_queue_row_down)
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, row)

    def _on_queue_row_play(self, data: dict):
        if data in self.queue:
            self.queue.remove(data)
            self.tab_btn_queue.setText(f"Up Next Queue ({len(self.queue)})")
        self.play_video_requested.emit(data["filepath"], "")
        self.hide()

    def _on_queue_row_remove(self, data: dict):
        if data in self.queue:
            self.queue.remove(data)
            self.tab_btn_queue.setText(f"Up Next Queue ({len(self.queue)})")
            self._render_queue()

    def _on_queue_row_up(self, data: dict):
        idx = self.queue.index(data)
        if idx > 0:
            self.queue[idx], self.queue[idx - 1] = self.queue[idx - 1], self.queue[idx]
            self._render_queue()

    def _on_queue_row_down(self, data: dict):
        idx = self.queue.index(data)
        if idx < len(self.queue) - 1:
            self.queue[idx], self.queue[idx + 1] = self.queue[idx + 1], self.queue[idx]
            self._render_queue()

    # =========================================================================
    # 5-SECOND HOVER PREVIEW CONTROLLER
    # =========================================================================

    def _on_card_hover_start(self, data: dict, preview_widget: HoverPreviewWidget):
        self._pending_preview_data = data
        self._pending_preview_widget = preview_widget
        self.preview_debounce_timer.start()

    def _on_card_hover_stop(self):
        self.preview_debounce_timer.stop()
        self.preview_loop_timer.stop()
        self.preview_player.stop()
        if self.active_preview_widget:
            self.active_preview_widget.clear_video()
            self.active_preview_widget = None

    def _start_preview_playback(self):
        if not self._pending_preview_data or not self._pending_preview_widget:
            return

        # Stop any previous active preview
        if self.active_preview_widget and self.active_preview_widget != self._pending_preview_widget:
            self.active_preview_widget.clear_video()

        self.active_preview_widget = self._pending_preview_widget
        self.preview_player.setVideoSink(self.active_preview_widget.sink)

        dur = self._pending_preview_data.get("duration", 60.0)
        self.preview_range = _calc_preview_range(dur)

        # Video source: prefer extracted_video_path for .beat packs, fallback to filepath
        source_path = self._pending_preview_data.get("extracted_video_path") or self._pending_preview_data.get("filepath", "")
        if not source_path or not os.path.exists(source_path):
            return

        self.preview_player.setSource(QUrl.fromLocalFile(source_path))
        self.preview_player.setPosition(int(self.preview_range[0] * 1000))
        self.preview_player.play()
        self.preview_loop_timer.start()

    def _check_preview_loop(self):
        pos_sec = self.preview_player.position() / 1000.0
        if pos_sec >= self.preview_range[1] or pos_sec < self.preview_range[0] - 0.5:
            self.preview_player.setPosition(int(self.preview_range[0] * 1000))


# Alias for explicit naming
LibraryViewWidget = LibraryDrawerWidget
