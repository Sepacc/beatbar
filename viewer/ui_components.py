"""
ui_components.py - Top Bar, Bottom Bar, Sound Changing Bar, and Inactivity Collapse Manager.

Implements all user-requested controls from the design images:
1 - Video title / next video button (capsule in top center)
2 - Window buttons (minimize, maximize, close in top right)
3 - 5-7 control buttons including sound changing bar, speed (0.3x-3x), shake, loop, fullscreen
4 - Timeline with player knob (white rounded square with play triangle)
5 - Settings button (white rounded square in top left)
Collapse after inactivity leaving only video and beatbar.
"""

import sys
import os
import math

from PyQt6.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, pyqtSignal, QTimer, QSize, QPropertyAnimation, QEasingCurve,
    QObject, QEvent
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QToolTip, QMenu, QSlider, QSizePolicy
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPainterPath, QPolygonF, QCursor, QIcon
)

# Ensure parent and main directories are accessible for icon_utils
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(PARENT_DIR, "main")
for p in [PARENT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from icon_utils import get_feather_icon, draw_feather_icon

try:
    from .skin_manager import SkinManager
except (ImportError, ValueError):
    from skin_manager import SkinManager


# ==============================================================================
# 1. VERTICAL SOUND CHANGING BAR
# ==============================================================================

class VerticalSoundBar(QWidget):
    """
    Vertical popup sound changing bar matching beatmake.jpg & beatmake-2.jpg:
    - Dark vertical pill container directly above the volume button.
    - Vertical track with a white slider thumb.
    - Mouse drag, click, and wheel support.
    """
    volume_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(40, 150)

        self.volume = 0.8
        self._is_dragging = False

        # Hide delay timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(400)
        self.hide_timer.timeout.connect(self.hide)

    def set_volume(self, val):
        self.volume = max(0.0, min(1.0, float(val)))
        self.update()

    def enterEvent(self, event):
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_dragging:
            self.hide_timer.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())

        # Outer Dark Pill Background
        bg_rect = QRectF(2, 2, W - 4, H - 4)
        painter.setBrush(QBrush(QColor("#141414")))
        painter.setPen(QPen(QColor("#3a3a42"), 1.2))
        painter.drawRoundedRect(bg_rect, 16, 16)

        # Percentage Text at Top
        pct = int(round(self.volume * 100))
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 6, W, 16), Qt.AlignmentFlag.AlignCenter, f"{pct}%")

        # Inner Slider Groove
        track_w = 6.0
        track_x = (W - track_w) / 2.0
        track_y = 26.0
        track_h = H - 38.0

        track_rect = QRectF(track_x, track_y, track_w, track_h)
        painter.setBrush(QBrush(QColor("#222228")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, 3, 3)

        # Active Fill
        fill_h = track_h * self.volume
        fill_y = track_y + track_h - fill_h
        if fill_h > 1.0:
            fill_rect = QRectF(track_x, fill_y, track_w, fill_h)
            painter.setBrush(QBrush(QColor("#9b51e0")))
            painter.drawRoundedRect(fill_rect, 3, 3)

        # White Thumb Pill (matches beatmake-2.jpg)
        thumb_w = 18.0
        thumb_h = 10.0
        thumb_x = (W - thumb_w) / 2.0
        thumb_y = fill_y - (thumb_h / 2.0)
        thumb_y = max(track_y - 2, min(track_y + track_h - thumb_h + 2, thumb_y))

        thumb_rect = QRectF(thumb_x, thumb_y, thumb_w, thumb_h)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#9b51e0"), 1.0))
        painter.drawRoundedRect(thumb_rect, 4, 4)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self.hide_timer.stop()
            self._update_from_mouse(event.position().y())

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._update_from_mouse(event.position().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.hide_timer.start()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 1200.0
        self.set_volume(self.volume + delta)
        self.volume_changed.emit(self.volume)

    def _update_from_mouse(self, my):
        H = float(self.height())
        track_y = 26.0
        track_h = H - 38.0
        norm = 1.0 - max(0.0, min(1.0, (my - track_y) / track_h))
        self.set_volume(norm)
        self.volume_changed.emit(self.volume)


# ==============================================================================
# 2. PLAYER TIMELINE WITH KNOB
# ==============================================================================

class TimelineTrackWidget(QWidget):
    """
    Player Timeline with interactive Knob matching beatmake.jpg & beatmake-2.jpg:
    - Dark horizontal track with progress fill.
    - White rounded square knob with a black play triangle inside it!
    - Clicking the knob toggles play/pause.
    - Dragging scrubs the timeline.
    - Clicking anywhere seeks to position.
    """
    seek_requested = pyqtSignal(float)
    play_pause_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMouseTracking(True)
        self.skin_mgr = SkinManager()

        self.current_time = 0.0
        self.duration = 1.0
        self.is_playing = False
        self._is_scrubbing = False
        self.zones = []
        self.levels = []

        self.knob_rect = QRectF()

    def set_zones(self, zones):
        self.zones = zones or []
        self.update()

    def set_levels(self, levels):
        self.levels = levels or []
        self.update()

    def set_time_and_duration(self, current_time, duration):
        if not self._is_scrubbing:
            self.current_time = max(0.0, float(current_time))
        self.duration = max(0.1, float(duration))
        self.update()

    def set_playing_state(self, is_playing):
        self.is_playing = is_playing
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())

        track_margin_x = 14.0
        track_w = W - 2 * track_margin_x
        track_h = 10.0
        track_y = (H - track_h) / 2.0

        # 1. Dark Rounded Track Background
        track_rect = QRectF(track_margin_x, track_y, track_w, track_h)
        painter.setBrush(QBrush(QColor("#121217")))
        painter.setPen(QPen(QColor("#262632"), 1.0))
        painter.drawRoundedRect(track_rect, 4.0, 4.0)

        # 1b. Rhythm Zones Visualization on Timeline
        show_zones = self.skin_mgr.config.get("show_timeline_zones", True)
        has_zones = show_zones and bool(self.zones) and self.duration > 0

        if has_zones:
            def _get_zone_colors(ztype):
                zt = str(ztype).lower()
                if zt in ['climax', 'intense']:
                    return (QColor(255, 23, 68, 245), QColor(255, 23, 68, 105))      # Crimson
                elif zt in ['edging']:
                    return (QColor(224, 86, 253, 245), QColor(224, 86, 253, 105))   # Purple
                elif zt in ['speeding_up', 'speedy', 'fast']:
                    return (QColor(255, 159, 26, 245), QColor(255, 159, 26, 105))   # Amber
                elif zt in ['pause', 'slow']:
                    return (QColor(115, 125, 140, 235), QColor(70, 78, 90, 100))    # Slate
                elif zt in ['credits', 'outro']:
                    return (QColor(99, 102, 241, 235), QColor(99, 102, 241, 100))   # Indigo
                else:
                    return (QColor(46, 213, 115, 245), QColor(46, 213, 115, 105))   # Emerald

            for z in self.zones:
                st = float(z.get('start_time', z.get('start', 0.0)))
                et = float(z.get('end_time', z.get('end', 0.0)))
                st = max(0.0, min(self.duration, st))
                et = max(0.0, min(self.duration, et))
                if et <= st:
                    continue

                zx1 = track_margin_x + track_w * (st / self.duration)
                zx2 = track_margin_x + track_w * (et / self.duration)
                zw = max(1.5, zx2 - zx1)

                ztype = z.get('type', z.get('zone_type', 'normal'))
                col_vibrant, col_dim = _get_zone_colors(ztype)

                # Segment based on current playback progress
                if self.current_time <= st:
                    # Entire zone is in unplayed future -> subtle translucent tone
                    painter.fillRect(QRectF(zx1, track_y, zw, track_h), col_dim)
                elif self.current_time >= et:
                    # Entire zone has been played -> full vibrant tone with subtle top highlight
                    painter.fillRect(QRectF(zx1, track_y, zw, track_h), col_vibrant)
                    painter.fillRect(QRectF(zx1, track_y, zw, 1.5), QColor(255, 255, 255, 75))
                else:
                    # Current playhead is inside this zone!
                    mid_x = track_margin_x + track_w * (self.current_time / self.duration)
                    p_w = max(0.0, mid_x - zx1)
                    u_w = max(0.0, zx2 - mid_x)
                    if p_w > 0:
                        painter.fillRect(QRectF(zx1, track_y, p_w, track_h), col_vibrant)
                        painter.fillRect(QRectF(zx1, track_y, p_w, 1.5), QColor(255, 255, 255, 75))
                    if u_w > 0:
                        painter.fillRect(QRectF(mid_x, track_y, u_w, track_h), col_dim)

                # Subtle divider line between zones
                painter.setPen(QPen(QColor(16, 16, 22, 180), 1.0))
                painter.drawLine(QPointF(zx1, track_y), QPointF(zx1, track_y + track_h))
        else:
            # Standard Progress Fill when no zones are loaded
            progress = max(0.0, min(1.0, self.current_time / max(0.1, self.duration)))
            fill_w = track_w * progress
            if fill_w > 1.0:
                fill_rect = QRectF(track_margin_x, track_y, fill_w, track_h)
                grad = QLinearGradient(track_margin_x, track_y, track_margin_x + fill_w, track_y)
                grad.setColorAt(0.0, QColor("#be2edd"))
                grad.setColorAt(1.0, QColor("#e056fd"))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(fill_rect, 4.0, 4.0)

        # 1c. YouTube-Style Level Chapters on Timeline Track (Dividers & Gaps)
        # Drawn on top of both track and zones so level chapter breaks are always prominent!
        if self.levels and self.duration > 0:
            gap_w = 4.0
            for idx in range(1, len(self.levels)):
                ch = self.levels[idx]
                st = float(ch.get('start_time', 0.0))
                if 0.0 < st < self.duration:
                    cx = track_margin_x + track_w * (st / self.duration)
                    # Clean YouTube chapter separation gap cutting through entire track
                    painter.fillRect(QRectF(cx - gap_w / 2.0, track_y - 2.0, gap_w, track_h + 4.0), QColor("#101014"))

                    # 1px subtle divider lines on border of the gap
                    painter.setPen(QPen(QColor("#2c2c3a"), 1.0))
                    painter.drawLine(QPointF(cx - gap_w / 2.0, track_y), QPointF(cx - gap_w / 2.0, track_y + track_h))
                    painter.drawLine(QPointF(cx + gap_w / 2.0, track_y), QPointF(cx + gap_w / 2.0, track_y + track_h))

                    # Neon Cyan top and bottom notch markers for instant recognition
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor("#00e5ff")))
                    painter.drawRoundedRect(QRectF(cx - 2.0, track_y - 2.5, 4.0, 3.0), 1.0, 1.0)
                    painter.drawRoundedRect(QRectF(cx - 2.0, track_y + track_h - 0.5, 4.0, 2.5), 1.0, 1.0)

        # 2. Knob: White Rounded Square with Black Play Triangle (beatmake-2.jpg)
        progress = max(0.0, min(1.0, self.current_time / max(0.1, self.duration)))
        fill_w = track_w * progress
        knob_size = 22.0
        knob_x = track_margin_x + fill_w - (knob_size / 2.0)
        knob_x = max(track_margin_x - knob_size / 2.0, min(track_margin_x + track_w - knob_size / 2.0, knob_x))
        knob_y = (H - knob_size) / 2.0

        self.knob_rect = QRectF(knob_x, knob_y, knob_size, knob_size)

        # White square knob with soft shadow border
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#3a3a42"), 1.2))
        painter.drawRoundedRect(self.knob_rect, 5.0, 5.0)

        # Inside icon on knob: Feather play/pause vector icon
        center_kx = knob_x + knob_size / 2.0
        center_ky = knob_y + knob_size / 2.0
        icon_name = "pause" if self.is_playing else "play"
        icon_rect = QRectF(center_kx - 6.5, center_ky - 6.5, 13.0, 13.0)
        draw_feather_icon(painter, icon_name, icon_rect, color="#141414", stroke_width=2.5)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            # If clicked directly inside the knob: toggle play/pause!
            if self.knob_rect.contains(pos):
                self.play_pause_clicked.emit()
            else:
                self._is_scrubbing = True
                self._seek_from_mouse(pos.x())

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._is_scrubbing:
            self._seek_from_mouse(pos.x())
        else:
            # Rich hover popup tooltip showing level chapter and rhythm zone info
            W = float(self.width())
            track_margin_x = 14.0
            track_w = W - 2 * track_margin_x
            norm = max(0.0, min(1.0, (pos.x() - track_margin_x) / max(1.0, track_w)))
            hover_t = norm * self.duration

            def _fmt_time(sec):
                m, s = divmod(int(sec), 60)
                return f"{m:02d}:{s:02d}"

            tip_lines = []

            # 1. Level Chapter at hover position
            if self.levels:
                found_ch = None
                for ch in self.levels:
                    st = float(ch.get('start_time', 0.0))
                    et = float(ch.get('end_time', self.duration))
                    if st <= hover_t <= et:
                        found_ch = ch
                        break
                if not found_ch and hover_t >= float(self.levels[-1].get('start_time', 0.0)):
                    found_ch = self.levels[-1]

                if found_ch:
                    st = float(found_ch.get('start_time', 0.0))
                    et = float(found_ch.get('end_time', self.duration))
                    lvl_name = found_ch.get('name', 'Level')
                    diff = found_ch.get('difficulty', 'Normal')
                    tip_lines.append(f"{lvl_name} • {diff} [{_fmt_time(st)} - {_fmt_time(et)}]")

            # 2. Rhythm Zone at hover position
            if self.zones:
                found_z = None
                for z in self.zones:
                    st = float(z.get('start_time', z.get('start', 0.0)))
                    et = float(z.get('end_time', z.get('end', self.duration)))
                    if st <= hover_t <= et:
                        found_z = z
                        break
                if found_z:
                    ztype = str(found_z.get('type', found_z.get('zone_type', 'normal'))).replace('_', ' ').title()
                    st = float(found_z.get('start_time', z.get('start', 0.0)))
                    et = float(found_z.get('end_time', z.get('end', self.duration)))
                    tip_lines.append(f"{ztype} Zone [{_fmt_time(st)} - {_fmt_time(et)}]")

            if not tip_lines:
                tip_lines.append(_fmt_time(hover_t))

            self.setToolTip("\n".join(tip_lines))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_scrubbing:
            self._is_scrubbing = False

    def _seek_from_mouse(self, mouse_x):
        track_margin_x = 14.0
        track_w = float(self.width()) - 2 * track_margin_x
        norm = max(0.0, min(1.0, (mouse_x - track_margin_x) / track_w))
        target_time = norm * self.duration
        self.current_time = target_time
        self.seek_requested.emit(target_time)
        self.update()


# ==============================================================================
# 3. TOP BAR (SETTINGS, VIDEO TITLE / NEXT VIDEO, WINDOW BUTTONS)
# ==============================================================================

class TopBarWidget(QWidget):
    """
    Top Bar matching beatmake.jpg & beatmake-2.jpg:
    1 - settings button (top left, white rounded square)
    2 - video title / next video button (top center, dark capsule)
    3 - window buttons (top right, minimize, maximize, close)
    """
    settings_clicked = pyqtSignal()
    library_clicked = pyqtSignal()
    next_video_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        # 1. Settings Button (Dark rounded button, matching theme)
        self.btn_settings = QPushButton()
        self.btn_settings.setFixedSize(36, 36)
        self.btn_settings.setIcon(get_feather_icon("settings", "#ffffff", 20))
        self.btn_settings.setToolTip("Open Settings & Customization")
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background: #141414;
                border: 1px solid #2e2e36;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #25252e;
                border-color: #9b51e0;
            }
            QPushButton:pressed {
                background: #0d0d10;
            }
        """)
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.btn_settings)

        # 1b. Library & Queue Drawer Button
        self.btn_library = QPushButton()
        self.btn_library.setFixedSize(36, 36)
        self.btn_library.setIcon(get_feather_icon("film", "#ffffff", 18))
        self.btn_library.setToolTip("Open Library & Playlists (Hotkey: L)")
        self.btn_library.setStyleSheet("""
            QPushButton {
                background: #141414;
                border: 1px solid #2e2e36;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #25252e;
                border-color: #9b51e0;
            }
            QPushButton:pressed {
                background: #0d0d10;
            }
        """)
        self.btn_library.clicked.connect(self.library_clicked.emit)
        layout.addWidget(self.btn_library)

        layout.addStretch()

        # 2. Video Title / Next Video Button Capsule (Top Center)
        self.title_capsule = QWidget()
        self.title_capsule.setObjectName("titleCapsule")
        self.title_capsule.setFixedHeight(46)
        self.title_capsule.setStyleSheet("""
            QWidget#titleCapsule {
                background: #141414;
                border: 1px solid #2e2e36;
                border-radius: 23px;
            }
        """)
        capsule_layout = QHBoxLayout(self.title_capsule)
        capsule_layout.setContentsMargins(14, 2, 10, 2)
        capsule_layout.setSpacing(8)

        self.lbl_icon = QLabel()
        self.lbl_icon.setStyleSheet("border: none; background: transparent; padding: 0;")
        self.lbl_icon.setPixmap(get_feather_icon("film", "#9b51e0", 16).pixmap(16, 16))
        capsule_layout.addWidget(self.lbl_icon)

        # Title and Level stacked vertically
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.lbl_title = QLabel("No Video Loaded")
        self.lbl_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        self.lbl_title.setToolTip("Current Video Title (Click Next arrow to play next video)")
        text_layout.addWidget(self.lbl_title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.lbl_level = QLabel("")
        self.lbl_level.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 10px; border: none; background: transparent;")
        self.lbl_level.hide()
        text_layout.addWidget(self.lbl_level, alignment=Qt.AlignmentFlag.AlignHCenter)

        capsule_layout.addLayout(text_layout)

        self.btn_next_video = QPushButton()
        self.btn_next_video.setFixedSize(26, 26)
        self.btn_next_video.setIcon(get_feather_icon("skip-forward", "#ffffff", 14))
        self.btn_next_video.setToolTip("Play Next Video in Folder")
        self.btn_next_video.setStyleSheet("""
            QPushButton {
                background: #25252b;
                border: 1px solid #3c3c46;
                border-radius: 13px;
            }
            QPushButton:hover {
                background: #9b51e0;
                border-color: #e056fd;
            }
        """)
        self.btn_next_video.clicked.connect(self.next_video_clicked.emit)
        capsule_layout.addWidget(self.btn_next_video)

        layout.addWidget(self.title_capsule)

        layout.addStretch()

        # 3. Window Buttons Capsule (Top Right)
        self.win_capsule = QWidget()
        self.win_capsule.setFixedHeight(36)
        self.win_capsule.setStyleSheet("""
            QWidget {
                background: #141414;
                border: 1px solid #2e2e36;
                border-radius: 18px;
            }
        """)
        win_layout = QHBoxLayout(self.win_capsule)
        win_layout.setContentsMargins(6, 0, 6, 0)
        win_layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 12px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2d2d36;
            }
        """

        # Minimize
        self.btn_min = QPushButton()
        self.btn_min.setFixedSize(28, 28)
        self.btn_min.setIcon(get_feather_icon("minus", "#ffffff", 14))
        self.btn_min.setStyleSheet(btn_style)
        self.btn_min.clicked.connect(self.minimize_clicked.emit)
        win_layout.addWidget(self.btn_min)

        # Maximize / Restore
        self.btn_max = QPushButton()
        self.btn_max.setFixedSize(28, 28)
        self.btn_max.setIcon(get_feather_icon("square", "#ffffff", 13))
        self.btn_max.setStyleSheet(btn_style)
        self.btn_max.clicked.connect(self.maximize_clicked.emit)
        win_layout.addWidget(self.btn_max)

        # Close
        self.btn_close = QPushButton()
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setIcon(get_feather_icon("x", "#ffffff", 14))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover {
                background: #e74c3c;
            }
        """)
        self.btn_close.clicked.connect(self.close_clicked.emit)
        win_layout.addWidget(self.btn_close)

        layout.addWidget(self.win_capsule)

    def set_video_title(self, title):
        display_title = title if len(title) <= 45 else title[:42] + "..."
        self.lbl_title.setText(display_title)
        self.title_capsule.setToolTip(f"Video: {title}\nClick next arrow to advance")

    def set_level_name(self, level_str):
        if level_str:
            self.lbl_level.setText(level_str)
            self.lbl_level.show()
        else:
            self.lbl_level.setText("")
            self.lbl_level.hide()

    def set_inactivity_collapsed(self, collapsed: bool):
        if collapsed:
            self.btn_settings.hide()
            self.win_capsule.hide()
            self.btn_next_video.hide()
            self.title_capsule.show()
            self.title_capsule.setStyleSheet("""
                QWidget#titleCapsule {
                    background: rgba(14, 14, 20, 0.78);
                    border: 1px solid rgba(46, 46, 54, 0.5);
                    border-radius: 23px;
                }
            """)
        else:
            self.btn_settings.show()
            self.win_capsule.show()
            self.btn_next_video.show()
            self.title_capsule.show()
            self.title_capsule.setStyleSheet("""
                QWidget#titleCapsule {
                    background: #141414;
                    border: 1px solid #2e2e36;
                    border-radius: 23px;
                }
            """)

    def mousePressEvent(self, event):
        w = self.window()
        if event.button() == Qt.MouseButton.LeftButton and w and not w.isFullScreen() and not w.isMaximized():
            pos = event.position()
            edges = Qt.Edge(0)
            if pos.y() < 8:
                edges |= Qt.Edge.TopEdge
            if pos.x() < 8:
                edges |= Qt.Edge.LeftEdge
            elif pos.x() > self.width() - 8:
                edges |= Qt.Edge.RightEdge

            if edges:
                wh = w.windowHandle()
                if wh and hasattr(wh, "startSystemResize"):
                    wh.startSystemResize(edges)
                    return

            wh = w.windowHandle()
            if wh and hasattr(wh, "startSystemMove"):
                wh.startSystemMove()
                return
            w._drag_pos = event.globalPosition().toPoint() - w.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        w = self.window()
        if w and hasattr(w, '_drag_pos') and w._drag_pos and event.buttons() == Qt.MouseButton.LeftButton and not w.isFullScreen():
            w.move(event.globalPosition().toPoint() - w._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        w = self.window()
        if w and hasattr(w, '_drag_pos'):
            w._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        w = self.window()
        if w and hasattr(w, '_toggle_maximize') and not w.isFullScreen():
            w._toggle_maximize()
        super().mouseDoubleClickEvent(event)


# ==============================================================================
# 4. BOTTOM BAR (COLLAPSIBLE, BUTTONS + TIMELINE)
# ==============================================================================

class BottomBarWidget(QWidget):
    """
    Bottom Bar matching beatmake.jpg & beatmake-2.jpg:
    - 5-7 rounded dark buttons on left (Sound, Play, Speed, Shake, Loop, Open, Fullscreen).
    - Player Timeline with White Play Knob on right.
    - Connected to vertical sound changing bar.
    """
    play_pause_clicked = pyqtSignal()
    sound_clicked = pyqtSignal()
    mute_clicked = pyqtSignal()
    speed_changed = pyqtSignal(float)
    shake_toggled = pyqtSignal()
    loop_toggled = pyqtSignal()
    open_file_clicked = pyqtSignal()
    fullscreen_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)

        # State
        self.speed_list = [0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
        self.current_speed_idx = 3  # 1.0x
        self.shake_enabled = True
        self.loop_enabled = True
        self.is_muted = False
        self.volume = 0.8

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 6, 16, 6)
        main_layout.setSpacing(10)

        # Style for the dark rounded control buttons (beatmake-2.jpg)
        btn_style = """
            QPushButton {
                background: #141414;
                border: 1px solid #2e2e36;
                border-radius: 8px;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #25252e;
                border-color: #9b51e0;
            }
            QPushButton:pressed {
                background: #0d0d10;
            }
        """

        # 1. File Group: Open File Button
        self.btn_open = QPushButton()
        self.btn_open.setFixedSize(38, 38)
        self.btn_open.setIcon(get_feather_icon("folder", "#ffffff", 18))
        self.btn_open.setStyleSheet(btn_style)
        self.btn_open.setToolTip("Open Video or Beatbar... (Ctrl+O)")
        self.btn_open.clicked.connect(self.open_file_clicked.emit)
        main_layout.addWidget(self.btn_open)

        # 2. Playback Group: Play / Pause & Playback Speed
        self.btn_play = QPushButton()
        self.btn_play.setFixedSize(38, 38)
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 18))
        self.btn_play.setStyleSheet(btn_style)
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_play.clicked.connect(self.play_pause_clicked.emit)
        main_layout.addWidget(self.btn_play)

        self.btn_speed = QPushButton(" 1.0x")
        self.btn_speed.setFixedSize(62, 38)
        self.btn_speed.setIcon(get_feather_icon("fast-forward", "#ffffff", 14))
        self.btn_speed.setStyleSheet(btn_style)
        self.btn_speed.setToolTip("Playback Speed (0.3x - 3x) | Click to cycle")
        self.btn_speed.clicked.connect(self._cycle_speed)
        main_layout.addWidget(self.btn_speed)

        # 3. Audio Group: Sound / Volume Button
        self.btn_sound = QPushButton()
        self.btn_sound.setFixedSize(38, 38)
        self.btn_sound.setIcon(get_feather_icon("volume-2", "#ffffff", 18))
        self.btn_sound.setStyleSheet(btn_style)
        self.btn_sound.setToolTip("Volume & Sound (Click to open slider | Right-click or 'M' to mute)")
        self.btn_sound.clicked.connect(self.sound_clicked.emit)
        self.btn_sound.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_sound.customContextMenuRequested.connect(lambda pos: self.mute_clicked.emit())
        main_layout.addWidget(self.btn_sound)

        # 4. FX & Display Group: Screen Shake & Fullscreen
        self.btn_shake = QPushButton()
        self.btn_shake.setFixedSize(38, 38)
        self.btn_shake.setIcon(get_feather_icon("zap", "#be2edd", 18))
        self.btn_shake.setStyleSheet(btn_style)
        self.btn_shake.setToolTip("Screen Shake on Beat Hits (Zoom In-n-Out) | On/Off (S)")
        self.btn_shake.clicked.connect(self.shake_toggled.emit)
        main_layout.addWidget(self.btn_shake)

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setFixedSize(38, 38)
        self.btn_fullscreen.setIcon(get_feather_icon("maximize", "#ffffff", 18))
        self.btn_fullscreen.setStyleSheet(btn_style)
        self.btn_fullscreen.setToolTip("Toggle Fullscreen (F / F11)")
        self.btn_fullscreen.clicked.connect(self.fullscreen_clicked.emit)
        main_layout.addWidget(self.btn_fullscreen)

        # Legacy compatibility aliases
        self.btn_blank1 = QPushButton()
        self.btn_blank2 = self.btn_fullscreen

        # 5. Timeline Track with Knob (beatmake-2.jpg)
        self.timeline_track = TimelineTrackWidget()
        self.timeline_track.seek_requested.connect(self.seek_requested.emit)
        self.timeline_track.play_pause_clicked.connect(self.play_pause_clicked.emit)
        main_layout.addWidget(self.timeline_track, stretch=1)

        # 6. Timecode Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(100)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_time.setStyleSheet("color: #aaaaaf; font-family: monospace; font-size: 11px;")
        main_layout.addWidget(self.lbl_time)

    def paintEvent(self, event):
        """Draws the dark bottom strip background matching beatmake.jpg."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#101014")))
        painter.setPen(QPen(QColor("#24242a"), 1.0))
        painter.drawRect(self.rect())
        painter.end()

    def set_play_state(self, is_playing):
        self.timeline_track.set_playing_state(is_playing)
        icon_name = "pause" if is_playing else "play"
        self.btn_play.setIcon(get_feather_icon(icon_name, "#ffffff", 18))

    def set_time_info(self, cur_sec, dur_sec):
        self.timeline_track.set_time_and_duration(cur_sec, dur_sec)
        c_m, c_s = divmod(int(cur_sec), 60)
        d_m, d_s = divmod(int(dur_sec), 60)
        self.lbl_time.setText(f"{c_m:02d}:{c_s:02d} / {d_m:02d}:{d_s:02d}")

    def update_volume_icon(self, vol, is_muted):
        self.volume = vol
        self.is_muted = is_muted
        if is_muted or vol <= 0.01:
            self.btn_sound.setIcon(get_feather_icon("volume-x", "#ff4757", 18))
        else:
            self.btn_sound.setIcon(get_feather_icon("volume-2", "#ffffff", 18))

    def update_shake_state(self, enabled):
        self.shake_enabled = enabled
        col = "#be2edd" if enabled else "#666670"
        self.btn_shake.setIcon(get_feather_icon("zap", col, 18))

    def update_loop_state(self, enabled):
        self.loop_enabled = enabled

    def set_zones(self, zones):
        self.timeline_track.set_zones(zones)

    def set_levels(self, levels):
        self.timeline_track.set_levels(levels)

    def set_speed_display(self, speed):
        self.btn_speed.setText(f" {speed:.1f}x" if speed != int(speed) else f" {int(speed)}.0x")

    def _cycle_speed(self):
        self.current_speed_idx = (self.current_speed_idx + 1) % len(self.speed_list)
        spd = self.speed_list[self.current_speed_idx]
        self.set_speed_display(spd)
        self.speed_changed.emit(spd)


# ==============================================================================
# 5. INACTIVITY COLLAPSE MANAGER
# ==============================================================================

class InactivityManager(QObject):
    """
    Manages auto-collapsing of the bottom bar and top controls after user inactivity:
    'the bottom bar (timeline, buttons) should collapse after some inactivity on the video,
    leaving user with only the video and beatbar'
    Automatically monitors mouse movement across all child widgets via event filtering.
    """
    def __init__(self, top_bar, bottom_bar, beatbar, window, timeout_sec=2.5):
        super().__init__(window)
        self.top_bar = top_bar
        self.bottom_bar = bottom_bar
        self.beatbar = beatbar
        self.window = window
        self.timeout_sec = timeout_sec
        self.is_collapsed = False

        self.timer = QTimer(self)
        self.timer.setInterval(int(self.timeout_sec * 1000))
        self.timer.timeout.connect(self._on_inactivity)
        if self.timeout_sec > 0:
            self.timer.start()

        # Install global application event filter to catch any mouse movement instantly
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def eventFilter(self, watched, event):
        etype = event.type()
        if etype in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.Wheel
        ):
            self.notify_activity()
        return super().eventFilter(watched, event)

    def set_timeout(self, timeout_sec):
        self.timeout_sec = float(timeout_sec)
        if self.timeout_sec > 0:
            self.timer.setInterval(int(self.timeout_sec * 1000))
            self.timer.start()
        else:
            self.timer.stop()
            if self.is_collapsed:
                self.reveal_bars()

    def notify_activity(self):
        """Called upon mouse movement, clicks, or keypresses."""
        self.timer.stop()
        if self.is_collapsed:
            self.reveal_bars()
        if self.timeout_sec > 0:
            self.timer.start()

    def _on_inactivity(self):
        """Collapses bars when inactive, leaving only video and beatbar."""
        if self.timeout_sec <= 0:
            return
        if not self.is_collapsed:
            self.collapse_bars()

    def collapse_bars(self):
        """Hides bottom bar while keeping video title + level capsule visible (does not collapse on inactivity)."""
        if hasattr(self.window, 'settings_dlg') and self.window.settings_dlg and self.window.settings_dlg.isVisible():
            return
        self.is_collapsed = True
        self.bottom_bar.hide()
        if hasattr(self.top_bar, 'set_inactivity_collapsed'):
            self.top_bar.set_inactivity_collapsed(True)
        else:
            self.top_bar.hide()
        self.window.setCursor(Qt.CursorShape.BlankCursor)

    def reveal_bars(self):
        """Restores bottom bar and top bar controls."""
        self.is_collapsed = False
        self.bottom_bar.show()
        if hasattr(self.top_bar, 'set_inactivity_collapsed'):
            self.top_bar.set_inactivity_collapsed(False)
        self.top_bar.show()
        self.window.unsetCursor()
        self.window.setCursor(Qt.CursorShape.ArrowCursor)
