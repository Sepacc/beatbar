"""
viewer.py - Main Window for Beatbar Video Viewer Application.

Integrates all components:
- Video playback container with hardware acceleration and camera punch screen shake.
- Floating centerpiece Beatbar with customizable panel, wings, moving beats, target, and timeline.
- Top bar with video title, next video button, and custom window controls.
- Bottom bar with 5-7 controls, vertical sound changing bar, and timeline knob player.
- Inactivity collapse manager leaving only video and beatbar during playback.
- Settings modal overlay for video, beatbar, skins, animations, and color palettes.
"""

import sys
import os
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QSize, QEvent, qInstallMessageHandler
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox, QSizeGrip, QPushButton
)
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QCursor

# Ensure project root and main directories are in sys.path
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(PARENT_DIR, "main")
for p in [PARENT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from icon_utils import get_feather_icon
from beat_format import infer_or_standardize_levels

try:
    from .skin_manager import SkinManager
    from .beatbar import BeatBarWidget
    from .screen_shake import ScreenShakeController
    from .ui_components import TopBarWidget, BottomBarWidget, VerticalSoundBar, InactivityManager
    from .settings_dialog import SettingsDialog
    from .player_core import PlayerCore
    from .video_canvas import VideoCanvasWidget
    from .library_drawer import LibraryDrawerWidget
except (ImportError, ValueError):
    from skin_manager import SkinManager
    from beatbar import BeatBarWidget
    from screen_shake import ScreenShakeController
    from ui_components import TopBarWidget, BottomBarWidget, VerticalSoundBar, InactivityManager
    from settings_dialog import SettingsDialog
    from player_core import PlayerCore
    from video_canvas import VideoCanvasWidget
    from library_drawer import LibraryDrawerWidget


def silence_ffmpeg():
    """Silences low-level FFmpeg C-library console logging (stderr)."""
    try:
        import ctypes
        import PyQt6
        pyqt_dir = os.path.dirname(PyQt6.__file__)
        for root, _, files in os.walk(pyqt_dir):
            for f in files:
                if f.lower().startswith("avutil") and f.lower().endswith(".dll"):
                    dll_path = os.path.join(root, f)
                    try:
                        av = ctypes.CDLL(dll_path)
                        LOG_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
                        def _dummy(avcl, level, fmt, vl):
                            pass
                        _cb = LOG_CALLBACK(_dummy)
                        setattr(silence_ffmpeg, "_cb", _cb)
                        if hasattr(av, "av_log_set_callback"):
                            av.av_log_set_callback(_cb)
                        if hasattr(av, "av_log_set_level"):
                            av.av_log_set_level(-8)
                    except Exception:
                        pass
    except Exception:
        pass


def _qt_message_filter(msg_type, context, message):
    if any(k in message for k in ["QFFmpeg", "wildcard call disconnects", "corrupted CTTS", "error reading header"]):
        return
    sys.stderr.write(f"{message}\n")


os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
silence_ffmpeg()
qInstallMessageHandler(_qt_message_filter)


class BeatBarViewerWindow(QMainWindow):
    """
    Main Beatbar Video Viewer Application Window.
    """
    def __init__(self, initial_video=None, initial_beats=None):
        super().__init__()
        qInstallMessageHandler(_qt_message_filter)
        self.skin_mgr = SkinManager()

        # Frameless window configuration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(880, 520)
        win_w = int(self.skin_mgr.config.get("window_width", 1280))
        win_h = int(self.skin_mgr.config.get("window_height", 740))
        self.resize(win_w, win_h)
        self.setWindowTitle("BeatBar Viewer")
        try:
            from icon_utils import get_suite_icon
            v_ico = get_suite_icon("beatbar-viewer", size=32)
            if v_ico and not v_ico.isNull():
                self.setWindowIcon(v_ico)
        except Exception:
            pass
        self.setAcceptDrops(True)

        # Window state
        self._is_maximized_custom = False
        self._normal_geom = self.geometry()
        self._drag_pos = None

        # Debounced geometry autosave timer
        self._geom_autosave_timer = QTimer(self)
        self._geom_autosave_timer.setSingleShot(True)
        self._geom_autosave_timer.setInterval(600)
        self._geom_autosave_timer.timeout.connect(self._autosave_geometry)

        self._init_ui()
        self._init_shortcuts()

        # Load initial or default media
        self._load_initial_media(initial_video, initial_beats)

    def _init_ui(self):
        # Central Container Widget
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setStyleSheet("background: #0c0c0e;")
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)

        # 1. Video Canvas (Layer 0) - QPainter direct rendering avoids Direct3D HWND occlusion
        self.video_canvas = VideoCanvasWidget(self.central_widget)
        self.video_canvas.setMouseTracking(True)
        self.video_canvas.clicked.connect(self._on_video_canvas_clicked)
        self.video_canvas.double_clicked.connect(self.toggle_fullscreen)

        # Player Engine
        self.player_core = PlayerCore(self.video_canvas, self)

        # Screen Shake Controller (Punch zoom in-n-out on beat hits)
        self.shake_controller = ScreenShakeController(self.video_canvas, self)

        # 2. Centered Floating Beatbar Widget (Layer 1)
        self.beatbar = BeatBarWidget(self.central_widget)

        # 3. Top Bar (Layer 2)
        self.top_bar = TopBarWidget(self.central_widget)

        # 4. Bottom Bar (Layer 2)
        self.bottom_bar = BottomBarWidget(self.central_widget)

        # 5. Vertical Sound Changing Bar (Layer 3)
        self.sound_bar = VerticalSoundBar(self.central_widget)
        self.sound_bar.hide()

        # 6. Subtle corner size grip for explicit resizing
        self.size_grip = QSizeGrip(self.central_widget)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background: transparent;
                width: 16px;
                height: 16px;
            }
        """)

        # 6b. Skip Credits Overlay Button (Anime streaming site style)
        self.btn_skip_credits = QPushButton("Skip Credits", self.central_widget)
        self.btn_skip_credits.setIcon(get_feather_icon("fast-forward", "#ffffff", 14))
        self.btn_skip_credits.setFixedHeight(36)
        self.btn_skip_credits.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_skip_credits.setStyleSheet("""
            QPushButton {
                background-color: rgba(18, 18, 28, 220);
                border: 1.5px solid #818cf8;
                border-radius: 8px;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #6366f1;
                border-color: #a5b4fc;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #4f46e5;
            }
        """)
        self.btn_skip_credits.clicked.connect(self._skip_credits)
        self.btn_skip_credits.hide()
        self.active_credits_zone = None

        # 6c. Slide-Out Library Drawer & Playlist/Queue Manager
        self.library_drawer = LibraryDrawerWidget(self.central_widget)
        self.library_drawer.hide()

        # Ensure correct Z-stacking order so overlays are always above video
        self.video_canvas.lower()
        self.beatbar.raise_()
        self.top_bar.raise_()
        self.bottom_bar.raise_()
        self.sound_bar.raise_()
        self.btn_skip_credits.raise_()
        self.library_drawer.raise_()
        self.size_grip.raise_()

        # Install event filters for edge resize detection and cursor handling
        self.central_widget.installEventFilter(self)
        self.video_canvas.installEventFilter(self)
        self.top_bar.installEventFilter(self)
        self.bottom_bar.installEventFilter(self)

        # 7. Settings Dialog (Modeless, floating)
        self.settings_dlg = SettingsDialog(self)

        # 8. Inactivity Collapse Manager (Leaves only video and beatbar after idle)
        inact_timeout = float(self.skin_mgr.config.get("inactivity_delay", 2.5))
        self.inactivity_mgr = InactivityManager(
            self.top_bar, self.bottom_bar, self.beatbar, self, timeout_sec=inact_timeout
        )

        # Initialize sound level to 20% on startup
        self.player_core.set_volume(0.20)
        self.sound_bar.set_volume(0.20)
        self.bottom_bar.update_volume_icon(0.20, False)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self):
        # Player signals -> Beatbar and UI
        self.player_core.position_changed.connect(self._on_playback_position)
        self.player_core.duration_changed.connect(self._on_playback_duration)
        self.player_core.playing_state_changed.connect(self._on_playing_state_changed)
        self.player_core.media_loaded.connect(self._on_media_loaded)
        self.player_core.volume_changed.connect(self._on_volume_changed)
        self.player_core.skin_updated.connect(self._on_skin_updated)

        # Beatbar hit signal -> Screen Shake Controller!
        self.beatbar.beat_hit.connect(self.shake_controller.on_beat_hit)

        # Seeking requests from Beatbar timeline & Bottom Bar timeline
        self.beatbar.seek_requested.connect(self.player_core.seek)
        self.bottom_bar.seek_requested.connect(self.player_core.seek)
        self.bottom_bar.play_pause_clicked.connect(self.player_core.toggle_play_pause)

        # Bottom Bar Control Buttons
        self.bottom_bar.sound_clicked.connect(self._toggle_sound_popup)
        if hasattr(self.bottom_bar, 'mute_clicked'):
            self.bottom_bar.mute_clicked.connect(self.player_core.toggle_mute)
        self.bottom_bar.speed_changed.connect(self.player_core.set_playback_rate)
        self.bottom_bar.shake_toggled.connect(self._toggle_screen_shake)
        self.bottom_bar.loop_toggled.connect(self._toggle_loop)
        self.bottom_bar.open_file_clicked.connect(self._open_file_dialog)
        self.bottom_bar.fullscreen_clicked.connect(self.toggle_fullscreen)

        # Sound Bar Slider
        self.sound_bar.volume_changed.connect(self.player_core.set_volume)

        # Top Bar Controls
        self.top_bar.settings_clicked.connect(self._open_settings)
        self.top_bar.library_clicked.connect(self._toggle_library_drawer)
        self.top_bar.next_video_clicked.connect(self.player_core.play_next_video)
        self.top_bar.minimize_clicked.connect(self.showMinimized)
        self.top_bar.maximize_clicked.connect(self._toggle_maximize)
        self.top_bar.close_clicked.connect(self.close)

        # Library Drawer Signals
        self.library_drawer.play_video_requested.connect(self._on_library_play_requested)

        # Player Core Playback Ended Signals
        self.player_core.playback_ended.connect(self._on_playback_ended)

        # Settings Dialog Actions
        self.settings_dlg.settings_changed.connect(self._apply_settings_update)
        self.settings_dlg.video_selected.connect(lambda p: (self.player_core.load_video(p), self.player_core.play()))
        self.settings_dlg.beatbar_selected.connect(lambda p: (self.player_core.load_beatbar(p), self.player_core.play() if (p.lower().endswith(".beat") or self.player_core.video_path) else None))

    def _init_shortcuts(self):
        """Keyboard shortcuts for keyboard and media control."""
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.player_core.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.player_core.seek(self.player_core.player.position() / 1000.0 - 5.0))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.player_core.seek(self.player_core.player.position() / 1000.0 + 5.0))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self.player_core.set_volume(self.player_core.volume + 0.05))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self.player_core.set_volume(self.player_core.volume - 0.05))
        QShortcut(QKeySequence(Qt.Key.Key_M), self, self.player_core.toggle_mute)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self._toggle_screen_shake)
        QShortcut(QKeySequence(Qt.Key.Key_L), self, self._toggle_library_drawer)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_N), self, self.player_core.play_next_video)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._on_escape_pressed)

    def _load_initial_media(self, initial_video, initial_beats):
        """Discovers or loads default video and beatbar."""
        vid = initial_video or self.skin_mgr.config.get("last_video_path")
        bts = initial_beats

        # If no explicit initial_beats provided, verify if last_beatbar_path matches the video
        if not bts and vid:
            last_bts = self.skin_mgr.config.get("last_beatbar_path")
            if last_bts and os.path.exists(last_bts):
                base_v = os.path.splitext(os.path.basename(vid))[0].lower()
                clean_v = base_v.replace("_720p", "").replace("_1080p", "").replace("_480p", "").replace("-720p", "").replace("-1080p", "").replace("-480p", "")
                base_b = os.path.splitext(os.path.basename(last_bts))[0].lower()
                if clean_v and clean_v in base_b:
                    bts = last_bts

        # Fallback to parent directory or videos/ folder files (e.g. wicked-r34-level-1.beat or .mp4)
        if not vid or not os.path.exists(vid):
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for cand in [
                os.path.join(parent_dir, "wicked-r34-level-1.beat"),
                os.path.join(parent_dir, "wicked-r34-level-1.mp4"),
                os.path.join(parent_dir, "videos", "test_bundle.beat"),
                os.path.join(parent_dir, "videos", "wicked-r34-level-1.beat"),
                os.path.join(parent_dir, "videos", "wicked-r34-level-1.mp4"),
            ]:
                if os.path.exists(cand):
                    vid = cand
                    break

        if vid and os.path.exists(vid):
            self.player_core.load_video(vid, bts)
            # Stay paused on opening viewer
            self.player_core.pause()

    # ==========================================================================
    # LAYOUT AND RESIZING
    # ==========================================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_geom_autosave_timer'):
            self._geom_autosave_timer.start()
        W = self.central_widget.width()
        H = self.central_widget.height()

        # 1. Video Canvas fills whole window
        self.video_canvas.setGeometry(0, 0, W, H)
        self.shake_controller.reset_geometry()

        # 2. Top Bar at top
        top_h = 50
        self.top_bar.setGeometry(0, 0, W, top_h)

        # 3. Bottom Bar across bottom
        bot_h = 56
        self.bottom_bar.setGeometry(0, H - bot_h, W, bot_h)

        # 4. Floating Beatbar centered horizontally above the bottom bar
        # Aspect ratio ~20:1 matching 3497 x 174 in beatmake-bar.svg
        bar_w = min(int(W * 0.88), 1640)
        bar_h = max(56, min(92, int(bar_w * (174.0 / 3497.0) * 1.35)))
        bar_x = (W - bar_w) // 2
        bar_y = H - bot_h - bar_h - 18
        if hasattr(self.beatbar, "set_bar_geometry"):
            self.beatbar.set_bar_geometry(bar_x, bar_y, bar_w, bar_h)
        else:
            self.beatbar.setGeometry(bar_x, bar_y, bar_w, bar_h)

        # 5. Position vertical sound bar popup directly above sound button
        self._reposition_sound_bar()

        # 6. Size grip in bottom-right corner
        self.size_grip.move(W - 16, H - 16)
        self.size_grip.raise_()

        # 7. Position Skip Credits button
        self._reposition_skip_credits_btn()

        # 8. Fullscreen Media Library Tab
        self.library_drawer.setGeometry(0, 0, W, H)

    def _reposition_sound_bar(self):
        btn_pos = self.bottom_bar.btn_sound.mapTo(self.central_widget, QPoint(0, 0))
        sb_x = btn_pos.x() + (self.bottom_bar.btn_sound.width() - self.sound_bar.width()) // 2
        sb_y = btn_pos.y() - self.sound_bar.height() - 8
        self.sound_bar.move(sb_x, sb_y)

    def _reposition_skip_credits_btn(self):
        W = self.central_widget.width()
        H = self.central_widget.height()
        bot_h = 56
        btn_w = 140
        btn_h = 36
        self.btn_skip_credits.setGeometry(W - btn_w - 24, H - bot_h - btn_h - 16, btn_w, btn_h)

    def _skip_credits(self):
        if hasattr(self, 'active_credits_zone') and self.active_credits_zone:
            z = self.active_credits_zone
            end_t = float(z.get('end_time', 0.0) if isinstance(z, dict) else getattr(z, 'end_time', 0.0))
            self.player_core.seek(end_t)
            self.btn_skip_credits.hide()
            self.active_credits_zone = None

    # ==========================================================================
    # EVENT HANDLING & RESIZING
    # ==========================================================================

    def _get_resize_edges(self, pos):
        """Determines which edges/corners are targeted within border margin."""
        border = 8
        edges = Qt.Edge(0)
        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()

        if x < border:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - border:
            edges |= Qt.Edge.RightEdge

        if y < border:
            edges |= Qt.Edge.TopEdge
        elif y >= h - border:
            edges |= Qt.Edge.BottomEdge

        return edges

    def eventFilter(self, watched, event):
        """Tracks edge hovering to update resize cursors and initiate native window resizing."""
        if not self.isFullScreen() and not self.isMaximized():
            etype = event.type()
            if etype in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                gpos = event.globalPosition().toPoint()
                lpos = self.mapFromGlobal(gpos)
                edges = self._get_resize_edges(lpos)
                if edges == (Qt.Edge.TopEdge | Qt.Edge.LeftEdge) or edges == (Qt.Edge.BottomEdge | Qt.Edge.RightEdge):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif edges == (Qt.Edge.TopEdge | Qt.Edge.RightEdge) or edges == (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                else:
                    if self.cursor().shape() in (
                        Qt.CursorShape.SizeHorCursor,
                        Qt.CursorShape.SizeVerCursor,
                        Qt.CursorShape.SizeFDiagCursor,
                        Qt.CursorShape.SizeBDiagCursor
                    ):
                        self.unsetCursor()
            elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                gpos = event.globalPosition().toPoint()
                lpos = self.mapFromGlobal(gpos)
                edges = self._get_resize_edges(lpos)
                if edges:
                    wh = self.windowHandle()
                    if wh and hasattr(wh, "startSystemResize"):
                        wh.startSystemResize(edges)
                        return True
        return super().eventFilter(watched, event)

    def _on_video_canvas_clicked(self):
        """Clicking video canvas toggles play/pause or closes sound popup."""
        self.inactivity_mgr.notify_activity()
        if self.sound_bar.isVisible():
            self.sound_bar.hide()
        else:
            self.player_core.toggle_play_pause()

    def mousePressEvent(self, event):
        self.inactivity_mgr.notify_activity()
        if event.button() == Qt.MouseButton.LeftButton and not self.isFullScreen() and not self.isMaximized():
            pos = event.position().toPoint()
            edges = self._get_resize_edges(pos)
            if edges:
                wh = self.windowHandle()
                if wh and hasattr(wh, "startSystemResize"):
                    wh.startSystemResize(edges)
                    return
            # Check for dragging window by top bar area
            if 8 <= pos.y() <= 50 and 8 <= pos.x() <= self.width() - 8:
                wh = self.windowHandle()
                if wh and hasattr(wh, "startSystemMove"):
                    wh.startSystemMove()
                    return
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.inactivity_mgr.notify_activity()
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton and not self.isFullScreen():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.position().y() <= 50 and not self.isFullScreen():
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        self.inactivity_mgr.notify_activity()
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                ext = os.path.splitext(u.toLocalFile())[1].lower()
                if ext in ['.beat', '.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v', '.json']:
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                path = u.toLocalFile()
                if not path or not os.path.exists(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext == '.beat':
                    self.player_core.load_video(path)
                    self.player_core.play()
                    event.acceptProposedAction()
                    return
                elif ext == '.json':
                    self.player_core.load_beatbar(path)
                    event.acceptProposedAction()
                    return
                elif ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v']:
                    self.player_core.load_video(path)
                    self.player_core.play()
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    # ==========================================================================
    # SLOTS & ACTIONS
    # ==========================================================================

    def _update_active_level(self, pos_sec=None):
        """Updates the active Level chapter and difficulty shown on the top bar."""
        if pos_sec is None:
            pos_sec = max(0.0, float(getattr(self.beatbar, 'current_time', 0.0) or 0.0))
        dur = max(1.0, float(getattr(self.player_core, 'duration', 1.0) or 1.0))
        active_ch = None
        if hasattr(self, 'levels') and self.levels:
            for ch in self.levels:
                st = float(ch.get('start_time', 0.0))
                et = float(ch.get('end_time', dur))
                if st <= pos_sec <= et:
                    active_ch = ch
                    break
            if not active_ch and self.levels:
                if pos_sec >= float(self.levels[-1].get('start_time', 0.0)):
                    active_ch = self.levels[-1]
                else:
                    active_ch = self.levels[0]

        lvl_num = getattr(self.player_core, 'level', 1)
        fallback_diff = getattr(self.player_core, 'difficulty', 'Normal')
        if active_ch:
            lvl_name = active_ch.get('name', f"Level {lvl_num}")
            diff = active_ch.get('difficulty', fallback_diff)
            self.top_bar.set_level_name(f"{lvl_name} • {diff}")
        elif fallback_diff:
            self.top_bar.set_level_name(f"Level {lvl_num} • {fallback_diff}")
        else:
            self.top_bar.set_level_name(f"Level {lvl_num}")

    def _on_playback_position(self, pos_sec):
        self.beatbar.set_current_time(pos_sec)
        dur = max(self.player_core.duration, self.beatbar.duration)
        self.bottom_bar.set_time_info(pos_sec, dur)

        # Update active Level chapter in top bar
        self._update_active_level(pos_sec)

        # Check if currently inside a skippable credits zone
        credits_zone = None
        for z in getattr(self.beatbar, 'zones', []):
            ztype = z.get('type') if isinstance(z, dict) else getattr(z, 'zone_type', getattr(z, 'type', ''))
            if ztype == 'credits':
                zs = float(z.get('start_time', 0.0) if isinstance(z, dict) else getattr(z, 'start_time', 0.0))
                ze = float(z.get('end_time', 0.0) if isinstance(z, dict) else getattr(z, 'end_time', 0.0))
                if zs <= pos_sec < ze:
                    credits_zone = z
                    break
        if credits_zone:
            self.active_credits_zone = credits_zone
            self._reposition_skip_credits_btn()
            self.btn_skip_credits.show()
            self.btn_skip_credits.raise_()
        else:
            self.active_credits_zone = None
            self.btn_skip_credits.hide()

    def _on_playback_duration(self, dur_sec):
        self.beatbar.set_duration(dur_sec)
        self.bottom_bar.set_time_info(self.beatbar.current_time, dur_sec)

        # Re-standardize level chapters with the real media duration from QMediaPlayer
        if dur_sec > 1.0:
            title = getattr(self.player_core, 'title', '') or os.path.basename(self.player_core.video_path or self.player_core.beatbar_path or "")
            raw_levels = getattr(self.player_core, 'levels', None)
            lvl_num = getattr(self.player_core, 'level', 1)
            diff = getattr(self.player_core, 'difficulty', 'Normal')
            self.levels = infer_or_standardize_levels(
                duration=dur_sec,
                title=title,
                level=lvl_num,
                difficulty=diff,
                levels=raw_levels
            )
            self.bottom_bar.set_levels(self.levels)
            self._update_active_level(self.beatbar.current_time)

    def _on_playing_state_changed(self, is_playing):
        self.bottom_bar.set_play_state(is_playing)
        self.beatbar.is_playing = is_playing

    def _on_media_loaded(self, video_path, beat_path, beats, zones):
        # Resolve clean display title
        if getattr(self.player_core, 'title', None):
            vid_title = self.player_core.title
        elif beat_path:
            vid_title = os.path.splitext(os.path.basename(beat_path))[0]
        elif video_path:
            base = os.path.basename(video_path)
            clean_base = os.path.splitext(base)[0]
            if clean_base.lower() in ("video", "audio") and beat_path:
                vid_title = os.path.splitext(os.path.basename(beat_path))[0]
            else:
                vid_title = base
        else:
            vid_title = "No Video"

        self.top_bar.set_video_title(vid_title)
        self.beatbar.set_beats_and_zones(beats, zones)
        self.bottom_bar.set_zones(zones)
        self.settings_dlg.set_current_files(video_path, beat_path, zones)

        # Estimate duration if player_core duration not yet populated by QMediaPlayer
        dur = max(float(self.player_core.duration or 0.0), float(beats[-1].get('time', 0.0) + 2.0) if beats else 60.0)
        raw_levels = getattr(self.player_core, 'levels', None)
        lvl_num = getattr(self.player_core, 'level', 1)
        diff = getattr(self.player_core, 'difficulty', 'Normal')
        std_levels = infer_or_standardize_levels(
            duration=dur,
            title=vid_title,
            level=lvl_num,
            difficulty=diff,
            levels=raw_levels
        )
        self.levels = std_levels
        self.bottom_bar.set_levels(std_levels)
        self._update_active_level(0.0)


    def _on_volume_changed(self, vol, is_muted):
        self.sound_bar.set_volume(0.0 if is_muted else vol)
        self.bottom_bar.update_volume_icon(vol, is_muted)

    def _toggle_sound_popup(self):
        if self.sound_bar.isVisible():
            self.sound_bar.hide()
        else:
            self._reposition_sound_bar()
            self.sound_bar.show()
            self.sound_bar.raise_()

    def _toggle_screen_shake(self):
        cur_mode = self.skin_mgr.config.get("screen_shake_mode", "intense_and_bursts")
        new_mode = "off" if cur_mode != "off" else "intense_and_bursts"
        self.skin_mgr.config["screen_shake_mode"] = new_mode
        self.skin_mgr.save_config()
        self.bottom_bar.update_shake_state(new_mode != "off")

    def _toggle_loop(self):
        new_loop = not self.player_core.loop_enabled
        self.player_core.set_loop(new_loop)
        self.bottom_bar.update_loop_state(new_loop)

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video or Beatbar", "",
            "Media Files (*.mp4 *.mkv *.webm *.beat *.json);;Beat Archives (*.beat);;Video Files (*.mp4 *.mkv *.webm);;JSON Beatmaps (*.json);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith(".beat"):
            # A .beat archive contains both beats and embedded/referenced video
            self.player_core.load_video(path)
            self.player_core.play()
        elif path.lower().endswith(".json"):
            self.player_core.load_beatbar(path)
        else:
            self.player_core.load_video(path)
            self.player_core.play()

    def _open_settings(self):
        self.inactivity_mgr.notify_activity()
        self.settings_dlg.set_zones(self.beatbar.zones)
        if self.settings_dlg.isVisible():
            self.settings_dlg.raise_()
            self.settings_dlg.activateWindow()
        else:
            px = self.x() + (self.width() - self.settings_dlg.width()) // 2
            py = self.y() + (self.height() - self.settings_dlg.height()) // 2
            self.settings_dlg.move(max(20, px), max(20, py))
            self.settings_dlg.show()
            self.settings_dlg.raise_()
            self.settings_dlg.activateWindow()

    def _on_skin_updated(self, skin_cfg):
        """Called when a .beat archive loads bundled skin components."""
        if hasattr(self.beatbar, "_recompute_geometry"):
            self.beatbar._recompute_geometry()
        self.beatbar.update()
        if hasattr(self, "settings_dlg") and self.settings_dlg:
            try:
                self.settings_dlg._load_current_values()
            except Exception:
                pass

    def _apply_settings_update(self):
        inact_timeout = float(self.skin_mgr.config.get("inactivity_delay", 2.5))
        self.inactivity_mgr.set_timeout(inact_timeout)
        if hasattr(self.beatbar, "_recompute_geometry"):
            self.beatbar._recompute_geometry()
        self.beatbar.update()
        self.bottom_bar.timeline_track.update()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.top_bar.btn_max.setIcon(get_feather_icon("square", "#ffffff", 13))
        else:
            self.showMaximized()
            self.top_bar.btn_max.setIcon(get_feather_icon("minimize-2", "#ffffff", 13))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_escape_pressed(self):
        if self.library_drawer.isVisible():
            self.library_drawer.hide()
        elif self.isFullScreen():
            self.showNormal()
        elif self.sound_bar.isVisible():
            self.sound_bar.hide()

    def _toggle_library_drawer(self):
        self.inactivity_mgr.notify_activity()
        if self.library_drawer.isVisible():
            self.library_drawer.hide()
        else:
            W = self.central_widget.width()
            H = self.central_widget.height()
            self.library_drawer.setGeometry(0, 0, W, H)
            self.library_drawer.scan_library()
            self.library_drawer.show()
            self.library_drawer.raise_()

    def _on_library_play_requested(self, video_path, beat_path):
        self.player_core.load_video(video_path, beat_path)
        self.player_core.play()

    def _on_playback_ended(self):
        """Advances to next queued track or next video in folder when playback ends."""
        if self.library_drawer.has_next_queued():
            self.library_drawer.pop_and_play_next()
        elif not self.player_core.loop_enabled:
            self.player_core.play_next_video()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, '_geom_autosave_timer'):
            self._geom_autosave_timer.start()

    def _autosave_geometry(self):
        try:
            if hasattr(self, 'skin_mgr') and self.skin_mgr:
                if not self.isFullScreen() and not self.isMaximized():
                    self.skin_mgr.config["window_width"] = self.width()
                    self.skin_mgr.config["window_height"] = self.height()
                    self.skin_mgr.config["window_x"] = self.pos().x()
                    self.skin_mgr.config["window_y"] = self.pos().y()
                self.skin_mgr.config["is_maximized"] = self.isMaximized()
                self.skin_mgr.save_config()
        except Exception:
            pass

    def closeEvent(self, event):
        self._autosave_geometry()
        if hasattr(self, 'settings_dlg') and self.settings_dlg:
            self.settings_dlg.close()
        super().closeEvent(event)
