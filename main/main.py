import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import unittest
import json
import uuid
import subprocess
import cv2
import numpy as np
from PyQt6.QtCore import (
    Qt, QUrl, QTimer, QSize, QRect, QRectF, QPoint, QPointF, QThread, pyqtSignal, QLine, QLineF
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSlider, QComboBox, QLabel, QScrollArea, QFileDialog,
    QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QCheckBox,
    QProgressDialog, QFrame, QSplitter, QSizePolicy, QLineEdit, QSpinBox, QGroupBox,
    QProgressBar, QRadioButton, QButtonGroup
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPixmap, QImage
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# Import DSP functions
from beat_generator import (
    load_beats, save_beats,
    analyze_audio_v2, analyze_audio_v3, estimate_tempo_and_grid, parse_beats_from_video,
    auto_detect_zones, generate_beats_from_zones, calculate_beat_difficulty
)
from zones_editor import VideoZonesEditorDialog, ZonesCollection, VideoZone
from icon_utils import get_feather_icon, draw_feather_icon

CONFIG_PATH = os.path.join(CURRENT_DIR, ".config")
LEGACY_CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
CRASH_LOG_PATH = os.path.join(CURRENT_DIR, "crash.log")

import traceback
from datetime import datetime

def setup_crash_logger():
    def excepthook(exc_type, exc_value, exc_tb):
        err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("CRITICAL UNCAUGHT EXCEPTION:\n", err_msg)
        try:
            with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*70}\nCRASH REPORT: {datetime.now().isoformat()}\n{'='*70}\n")
                f.write(err_msg)
                f.write("\n")
        except Exception as io_err:
            print("Failed to write to crash.log:", io_err)
        
        app = QApplication.instance()
        if app:
            try:
                QMessageBox.critical(
                    None, "Application Error",
                    f"An unexpected error occurred:\n{exc_value}\n\nTraceback has been recorded in:\n{CRASH_LOG_PATH}"
                )
            except Exception:
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

setup_crash_logger()

DEFAULT_KEYBINDS = {
    'lane_4': '5',
    'lane_0': '1',
    'halve': 'H',
}

DEFAULT_APP_CONFIG = {
    'keybinds': DEFAULT_KEYBINDS,
    'last_audio_path': '',
    'last_video_path': '',
    'last_beats_path': '',
    'recent_files': [],
    'volume': 80,
    'is_muted': False,
    'playback_speed': '1.0x',
    'zoom': 100,
    'level': 5,
    'difficulty': 'Normal',
    'close_gap_threshold': 0.35,
    'min_group_size': 3,
    'auto_recalc_diff': True,
    'screen_shake': True,
    'default_author': 'User',
    'window_width': 1000,
    'window_height': 600,
    'window_x': None,
    'window_y': None,
    'is_maximized': False,
    'splitter_sizes': [260, 440],
    'generator_v2': {
        'bpm': 120.0,
        'sensitivity': 1.0,
        'quantize': '1/4'
    },
    'generator_v3': {
        'bpm': 120.0,
        'mode': 'zone_aware'
    }
}

def load_app_config():
    """Loads full application settings from .config (with fallback to legacy config.json)."""
    cfg = DEFAULT_APP_CONFIG.copy()
    cfg['keybinds'] = DEFAULT_KEYBINDS.copy()
    
    target = CONFIG_PATH if os.path.exists(CONFIG_PATH) else (LEGACY_CONFIG_PATH if os.path.exists(LEGACY_CONFIG_PATH) else None)
    if target and os.path.exists(target):
        try:
            with open(target, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if 'keybinds' in data and isinstance(data['keybinds'], dict):
                        cfg['keybinds'].update(data['keybinds'])
                    for k, v in data.items():
                        if k != 'keybinds':
                            cfg[k] = v
        except Exception as e:
            print(f"Failed to load config from {target}:", e)
            
    # Autosave to .config immediately if it does not exist yet
    if not os.path.exists(CONFIG_PATH):
        save_app_config(cfg)
    return cfg

def save_app_config(cfg):
    """Autosaves application settings to .config."""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print("Failed to save .config:", e)

def load_user_config():
    """Backward compatibility helper for keybindings."""
    cfg = load_app_config()
    return cfg.get('keybinds', DEFAULT_KEYBINDS.copy())

def save_user_config(keybinds):
    """Backward compatibility helper for keybindings."""
    cfg = load_app_config()
    cfg['keybinds'] = keybinds
    save_app_config(cfg)

class AudioLoadThread(QThread):
    """Loads audio using Librosa in the background and computes its peak envelope."""
    finished = pyqtSignal(np.ndarray, float, int, str)  # envelope, duration, sr, final_audio_path
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            import librosa
            
            audio_path = self.file_path
            # If the user loaded an MP4 or other video format, check for existing MP3 or extract using FFmpeg
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v']:
                base = os.path.splitext(self.file_path)[0]
                mp3_path = base + ".mp3"
                wav_path = base + ".wav"
                
                # Check if matching audio already exists to prevent re-extracting every time
                if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1024:
                    print(f"Existing audio found: {mp3_path}. Skipping extraction.")
                    audio_path = mp3_path
                elif os.path.exists(wav_path) and os.path.getsize(wav_path) > 1024:
                    print(f"Existing audio found: {wav_path}. Skipping extraction.")
                    audio_path = wav_path
                else:
                    print(f"Video file detected. Extracting audio to {mp3_path}...")
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", self.file_path,
                        "-vn",
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k",
                        mp3_path
                    ]
                    # Run FFmpeg without popping up a console/terminal window
                    creationflags = 0
                    if sys.platform == "win32":
                        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=creationflags
                    )
                    if result.returncode != 0:
                        raise Exception(f"FFmpeg extraction failed:\n{result.stderr.decode('utf-8', errors='ignore')}")
                    audio_path = mp3_path

            # Load audio using librosa
            y, sr = librosa.load(audio_path, sr=22050)
            duration = librosa.get_duration(y=y, sr=sr)
            
            # Downsample for visualization: vectorized peak envelope (~100 points/sec)
            points_per_second = 100
            chunk_size = max(1, int(sr / points_per_second))
            
            n_chunks = len(y) // chunk_size
            if n_chunks > 0:
                reshaped = np.abs(y[:n_chunks * chunk_size].reshape(n_chunks, chunk_size))
                envelope = np.max(reshaped, axis=1)
                rem = y[n_chunks * chunk_size:]
                if len(rem) > 0:
                    envelope = np.append(envelope, np.max(np.abs(rem)))
            else:
                envelope = np.abs(y)
                
            envelope = np.asarray(envelope, dtype=np.float32)
            max_val = np.max(envelope) if len(envelope) > 0 else 1.0
            if max_val > 0:
                envelope = envelope / max_val
                
            self.finished.emit(envelope, duration, sr, audio_path)
        except Exception as e:
            self.error.emit(str(e))


class AudioAnalyzeThreadV3(QThread):
    """V3 Engine: Runs zone-aware rhythm generator with anti-overlap and steady quarter-note spacing."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int)

    def __init__(self, file_path, target_lane=4, preset="musical_beatbar", bpm=None,
                 density_scale=0.85, quantize_grid="auto", min_gap=0.095, insert_rolls=True,
                 halve_non_intense=True, intro_cutoff=3.8, zones=None, anti_overlap=True,
                 steady_section_cleanup=True, level=5, difficulty="Normal",
                 level_mode="ramp_within_level", use_zones=True, use_levels=True, levels=None,
                 edging_style="rhythmic_tension"):
        super().__init__()
        self.file_path = file_path
        self.target_lane = target_lane
        self.preset = preset
        self.bpm = bpm
        self.density_scale = density_scale
        self.quantize_grid = quantize_grid
        self.min_gap = min_gap
        self.insert_rolls = insert_rolls
        self.halve_non_intense = halve_non_intense
        self.intro_cutoff = intro_cutoff
        self.zones = zones
        self.anti_overlap = anti_overlap
        self.steady_section_cleanup = steady_section_cleanup
        self.level = level
        self.difficulty = difficulty
        self.level_mode = level_mode
        self.use_zones = use_zones
        self.use_levels = use_levels
        self.levels = levels
        self.edging_style = edging_style

    def run(self):
        try:
            def cb(status, pct):
                self.progress.emit(status, pct)

            beats = analyze_audio_v3(
                self.file_path,
                target_lane=self.target_lane,
                preset=self.preset,
                bpm=self.bpm,
                density_scale=self.density_scale,
                quantize_grid=self.quantize_grid,
                min_gap=self.min_gap,
                insert_rolls=self.insert_rolls,
                halve_non_intense=self.halve_non_intense,
                intro_cutoff=self.intro_cutoff,
                zones=self.zones,
                anti_overlap=self.anti_overlap,
                steady_section_cleanup=self.steady_section_cleanup,
                level=self.level,
                difficulty=self.difficulty,
                level_mode=self.level_mode,
                levels=self.levels,
                use_zones=self.use_zones,
                use_levels=self.use_levels,
                edging_style=self.edging_style,
                progress_callback=cb
            )
            self.finished.emit(beats)
        except Exception as e:
            self.error.emit(str(e))


class AudioAnalyzeThreadV2(QThread):
    """V2 Engine: Runs the musical adaptive rhythm beatbar analysis in the background."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int)

    def __init__(self, file_path, target_lane=4, preset="musical_beatbar", bpm=None,
                 density_scale=0.85, quantize_grid="auto", min_gap=0.095, insert_rolls=True,
                 halve_non_intense=True, intro_cutoff=3.8, custom_curve=None):
        super().__init__()
        self.file_path = file_path
        self.target_lane = target_lane
        self.preset = preset
        self.bpm = bpm
        self.density_scale = density_scale
        self.quantize_grid = quantize_grid
        self.min_gap = min_gap
        self.insert_rolls = insert_rolls
        self.halve_non_intense = halve_non_intense
        self.intro_cutoff = intro_cutoff
        self.custom_curve = custom_curve

    def run(self):
        try:
            def cb(status, pct):
                self.progress.emit(status, pct)

            beats = analyze_audio_v2(
                self.file_path,
                target_lane=self.target_lane,
                preset=self.preset,
                bpm=self.bpm,
                density_scale=self.density_scale,
                quantize_grid=self.quantize_grid,
                min_gap=self.min_gap,
                insert_rolls=self.insert_rolls,
                halve_non_intense=self.halve_non_intense,
                intro_cutoff=self.intro_cutoff,
                custom_curve=self.custom_curve,
                progress_callback=cb
            )
            self.finished.emit(beats)
        except Exception as e:
            self.error.emit(str(e))


import bisect


class _TimeKey:
    """Indexable sequence wrapper around beats list for bisect searching by time."""
    __slots__ = ('beats',)

    def __init__(self, beats):
        self.beats = beats

    def __len__(self):
        return len(self.beats)

    def __getitem__(self, i):
        return self.beats[i]['time']


class TimelineWidget(QWidget):
    """Interactive beatbar grid with waveform background, multi-track support (up to 3 tracks), dragging, and selection."""
    time_seek_requested = pyqtSignal(float)
    beats_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    levels_changed = pyqtSignal()
    level_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.pixels_per_second = 100.0  # Zoom factor
        self.playhead_time = 0.0
        
        self.waveform_envelope = np.array([], dtype=np.float32)
        self.waveform_points_per_second = 100.0
        
        self.beats = []  # list of {'time': float, 'lane': int}
        self.selected_beats = []  # list of references to selected beat dictionaries
        
        self.drag_state = None  # None, "seeking", "dragging_beat", "selecting", "dragging_boundary"
        self.drag_anchor_time = 0.0
        self.drag_clicked_beat = None
        self.drag_start_positions = {}  # maps id(beat) -> (start_time, start_lane)
        
        # Rubber-band selection box coordinates
        self.selection_start = QPointF()
        self.selection_end = QPointF()
        
        # Multi-Track Configuration (3 Tracks supported, 1 visible by default)
        self.tracks = [
            {'lane': 4, 'name': 'TRACK 1', 'color': QColor("#B10DC9")},  # Purple (Primary BEATS)
            {'lane': 1, 'name': 'TRACK 2', 'color': QColor("#00E5FF")},  # Cyan
            {'lane': 2, 'name': 'TRACK 3', 'color': QColor("#FFB300")},  # Amber
        ]
        self.visible_track_count = 1  # Default showing 1 track!
        
        # Dimensions
        self.header_height = 46  # 18px for Level chapters bar, 28px for Time ruler
        self.lane_height = 55
        
        # Placed Level & Difficulty chapters (like YouTube chapters)
        self.levels = []  # list of dicts: {'id': str, 'name': str, 'level': int, 'difficulty': str, 'start_time': float, 'end_time': float}
        self.selected_chapter = None
        self.hovered_chapter = None
        self.hovered_boundary_idx = -1
        self.dragging_boundary_idx = -1
        
        # Initial size setup
        self.adjust_height()
        
        # Edge auto-scroll timer for dragging/selecting
        self.edge_scroll_timer = QTimer(self)
        self.edge_scroll_timer.setInterval(20)  # 50 FPS smooth edge scroll
        self.edge_scroll_timer.timeout.connect(self.on_edge_scroll_tick)
        self.edge_scroll_dir = 0
        
        # Keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_levels(self, levels):
        self.levels = levels or []
        self.update()

    def get_level_at(self, t):
        if not self.levels:
            return None
        for lv in self.levels:
            st = float(lv.get('start_time', 0.0))
            et = float(lv.get('end_time', self.duration))
            if st <= t <= et:
                return lv
        if self.levels:
            return self.levels[-1] if t >= self.duration else self.levels[0]
        return None

    def format_time_sec(self, seconds):
        s = max(0, int(seconds))
        m = s // 60
        sec = s % 60
        return f"{m}:{sec:02d}"

    def open_place_level_dialog(self, chapter_or_time=None, current_time=None):
        if isinstance(chapter_or_time, (int, float)):
            t_val = float(chapter_or_time)
            chapter = self.get_level_at(t_val) if self.levels else None
            current_time = t_val
        elif isinstance(chapter_or_time, dict):
            chapter = chapter_or_time
            if current_time is None:
                current_time = chapter.get('start_time', 0.0)
        else:
            chapter = None
            if current_time is None:
                current_time = self.playhead_time

        dlg = PlaceLevelDialog(self, chapter=chapter, current_time=current_time, duration=self.duration)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.deleted and chapter:
                self.delete_level_chapter(chapter)
            else:
                data = dlg.get_data()
                if chapter and not dlg.is_new:
                    chapter.update(data)
                else:
                    self.insert_level_chapter(data)
                self.levels_changed.emit()
                self.update()

    def insert_level_chapter(self, new_ch):
        st = new_ch['start_time']
        et = new_ch['end_time']
        updated = []
        for ch in self.levels:
            if ch['end_time'] <= st or ch['start_time'] >= et:
                updated.append(ch)
            else:
                if ch['start_time'] < st:
                    ch['end_time'] = st
                    updated.append(ch)
                if ch['end_time'] > et:
                    copy_r = dict(ch)
                    copy_r['id'] = str(uuid.uuid4())[:8]
                    copy_r['start_time'] = et
                    updated.append(copy_r)
        updated.append(new_ch)
        updated.sort(key=lambda x: x['start_time'])
        if updated:
            updated[0]['start_time'] = 0.0
            updated[-1]['end_time'] = round(self.duration, 3)
        self.levels = updated

    def split_level_at(self, t):
        if not self.levels or t <= 0.5 or t >= self.duration - 0.5:
            return
        t = round(t, 2)
        target_ch = self.get_level_at(t)
        if not target_ch:
            return
        idx = self.levels.index(target_ch)
        old_end = target_ch['end_time']
        target_ch['end_time'] = t
        
        curr_lvl = target_ch.get('level', 1)
        next_lvl = curr_lvl + 1
        new_name = f"Level {next_lvl} - Widow" if next_lvl == 2 else f"Level {next_lvl}"
        
        new_ch = {
            'id': str(uuid.uuid4())[:8],
            'name': new_name,
            'level': next_lvl,
            'difficulty': target_ch.get('difficulty', 'Normal'),
            'start_time': t,
            'end_time': old_end
        }
        self.levels.insert(idx + 1, new_ch)
        self.levels_changed.emit()
        self.update()

    def delete_level_chapter(self, chapter):
        if not self.levels:
            return
        if len(self.levels) == 1:
            self.levels = []
            self.selected_chapter = None
            self.hovered_chapter = None
            self.levels_changed.emit()
            self.update()
            return
        if isinstance(chapter, int):
            idx = chapter
            if idx < 0 or idx >= len(self.levels):
                return
            target = self.levels[idx]
        else:
            if chapter not in self.levels:
                return
            idx = self.levels.index(chapter)
            target = chapter
        if idx > 0:
            self.levels[idx - 1]['end_time'] = target['end_time']
        elif idx < len(self.levels) - 1:
            self.levels[idx + 1]['start_time'] = target['start_time']
        self.levels.pop(idx)
        if getattr(self, 'selected_chapter', None) == target:
            self.selected_chapter = self.levels[max(0, idx - 1)] if self.levels else None
        if getattr(self, 'hovered_chapter', None) == target:
            self.hovered_chapter = None
        self.levels_changed.emit()
        self.update()

    def set_visible_track_count(self, count):
        self.visible_track_count = max(1, min(3, int(count)))
        self.adjust_height()
        self.updateGeometry()
        self.update()

    def adjust_height(self):
        total_h = self.header_height + self.visible_track_count * self.lane_height + 5
        self.setFixedHeight(total_h)

    def lane_to_track_idx(self, lane):
        """Maps a beat's lane number to a track index (0, 1, or 2)."""
        if lane in (4, 0):
            return 0
        elif lane == 1:
            return 1
        elif lane in (2, 3):
            return 2
        return 0

    def track_idx_to_lane(self, track_idx):
        idx = max(0, min(2, int(track_idx)))
        return self.tracks[idx]['lane']

    def lane_to_y(self, lane=4):
        """Maps lane to visible Y coordinate of the track's top."""
        track_idx = self.lane_to_track_idx(lane)
        if track_idx >= self.visible_track_count:
            track_idx = 0
        return self.header_height + track_idx * self.lane_height

    def y_to_lane(self, y):
        """Maps visual Y coordinate back to lane index."""
        if y < self.header_height:
            return -1
        track_idx = int((y - self.header_height) // self.lane_height)
        track_idx = max(0, min(self.visible_track_count - 1, track_idx))
        return self.tracks[track_idx]['lane']

    def set_audio_data(self, envelope, duration):
        self.waveform_envelope = envelope
        self.duration = duration
        self.playhead_time = 0.0
        self.selected_beats = []
        self.selection_changed.emit()
        self.updateGeometry()
        self.update()

    def set_playhead_time(self, t):
        self.playhead_time = max(0.0, min(t, self.duration))
        self.update()

    def set_pixels_per_second(self, pps):
        self.pixels_per_second = pps
        self.updateGeometry()
        self.update()

    def minimumSizeHint(self):
        w = int(self.duration * self.pixels_per_second)
        h = self.header_height + self.visible_track_count * self.lane_height + 5
        return QSize(max(w, 800), h)

    def sizeHint(self):
        return self.minimumSizeHint()

    def update_beat_neighbor_distances(self):
        """Precomputes intrinsic delta-time distance to neighboring notes per track.
        Guarantees deterministic, uniform anti-overlap scaling without slice-boundary artifacts."""
        tracks_beats = {0: [], 1: [], 2: []}
        for b in self.beats:
            tr_i = self.lane_to_track_idx(b.get('lane', 4))
            if tr_i in tracks_beats:
                tracks_beats[tr_i].append(b)

        for tr_i, tr_beats in tracks_beats.items():
            tr_beats.sort(key=lambda b: b['time'])
            n = len(tr_beats)
            for i in range(n):
                t = tr_beats[i]['time']
                dt_left = abs(t - tr_beats[i - 1]['time']) if i > 0 else 999.0
                dt_right = abs(tr_beats[i + 1]['time'] - t) if i < n - 1 else 999.0
                tr_beats[i]['_min_dt'] = min(dt_left, dt_right)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        visible_rect = event.rect()
        left_x = visible_rect.left()
        right_x = visible_rect.right()
        
        t_start = left_x / self.pixels_per_second
        t_end = right_x / self.pixels_per_second
        
        # 1. Fill Grid Background
        painter.fillRect(visible_rect, QColor("#121214"))
        
        # 1a. Draw YouTube-Style Level Chapters on Timeline Bar (Y=0 to Y=18)
        ch_bar_h = 18
        painter.fillRect(QRect(left_x, 0, visible_rect.width(), ch_bar_h), QColor("#0d0d12"))
        
        diff_colors = {
            "easy": QColor("#2ecc71"),
            "normal": QColor("#00e5ff"),
            "hard": QColor("#f39c12"),
            "expert": QColor("#ff4757"),
            "master": QColor("#a855f7")
        }
        
        if self.levels:
            for idx, ch in enumerate(self.levels):
                st = ch.get('start_time', 0.0)
                et = ch.get('end_time', self.duration)
                x1 = int(st * self.pixels_per_second)
                x2 = int(et * self.pixels_per_second)
                w = max(2, x2 - x1)
                
                if x2 < left_x or x1 > right_x:
                    continue
                    
                diff = str(ch.get('difficulty', 'Normal')).lower()
                base_col = diff_colors.get(diff, QColor("#00e5ff"))
                
                is_active = (st <= self.playhead_time <= et)
                is_hovered = (self.hovered_chapter == ch)
                is_selected = (getattr(self, 'selected_chapter', None) == ch)
                
                alpha = 185 if is_selected else (160 if is_active else (120 if is_hovered else 75))
                fill_col = QColor(base_col.red(), base_col.green(), base_col.blue(), alpha)
                border_col = QColor("#ffffff") if is_selected else QColor(base_col.red(), base_col.green(), base_col.blue(), 230 if is_active else 140)
                
                # Draw chapter segment block with 2px gap (YouTube style)
                ch_rect = QRect(x1 + 1, 2, max(1, w - 2), ch_bar_h - 4)
                painter.fillRect(ch_rect, fill_col)
                painter.setPen(QPen(border_col, 2 if is_selected else 1))
                painter.drawRect(ch_rect)
                
                # Text inside chapter if wide enough
                if w >= 55:
                    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    painter.setPen(QColor("#ffffff" if is_active else "#d0d0e0"))
                    txt = f"{ch.get('name', 'Level')} ({ch.get('difficulty', 'Normal')})"
                    painter.drawText(QRect(x1 + 4, 2, w - 8, ch_bar_h - 4), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)
                    
                # Chapter boundary line gap
                if idx > 0:
                    painter.setPen(QPen(QColor("#08080a"), 2))
                    painter.drawLine(x1, 0, x1, ch_bar_h)
        total_tracks_h = self.visible_track_count * self.lane_height

        # 2. Draw Waveform background across visible tracks
        if len(self.waveform_envelope) > 0:
            painter.setPen(QPen(QColor(0, 229, 255, 25), 1))  # transparent neon cyan
            center_y = self.header_height + total_tracks_h // 2
            max_h = total_tracks_h // 2 - 8
            
            lines = []
            for x in range(left_x, right_x):
                t = x / self.pixels_per_second
                idx = int(t * self.waveform_points_per_second)
                if 0 <= idx < len(self.waveform_envelope):
                    h = int(self.waveform_envelope[idx] * max_h)
                    lines.append(QLine(x, center_y - h, x, center_y + h))
            if lines:
                painter.drawLines(lines)

        # 3. Draw horizontal lanes & lines for visible tracks
        painter.setPen(QPen(QColor("#2d2d35"), 1))
        for i in range(self.visible_track_count + 1):
            ly = self.header_height + i * self.lane_height
            painter.drawLine(left_x, ly, right_x, ly)

        # Subtle sub-lane baseline guide lines
        painter.setPen(QPen(QColor("#1b1b22"), 1, Qt.PenStyle.DotLine))
        for i in range(self.visible_track_count):
            mid_y = int(self.header_height + i * self.lane_height + self.lane_height / 2.0)
            painter.drawLine(left_x, mid_y, right_x, mid_y)

        # 4. Draw vertical grid lines & timeline ruler
        painter.setPen(QPen(QColor("#2d2d35"), 1))
        painter.drawLine(left_x, self.header_height, right_x, self.header_height)

        sec_start = int(t_start)
        sec_end = int(t_end) + 1
        
        # Ticks every 0.1s
        if self.pixels_per_second >= 80:
            painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
            for s in range(sec_start * 10, sec_end * 10):
                t = s / 10.0
                x = int(t * self.pixels_per_second)
                if x >= left_x and x <= right_x and s % 10 != 0:
                    painter.drawLine(x, self.header_height - 5, x, self.header_height)

        # Major ticks & text every 1s
        for s in range(sec_start, sec_end):
            x = int(s * self.pixels_per_second)
            if x >= left_x and x <= right_x:
                # Grid line across tracks
                painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
                painter.drawLine(x, self.header_height, x, self.height())
                
                # Ruler ticks
                painter.setPen(QPen(QColor("#80808a"), 1.5))
                painter.drawLine(x, self.header_height - 8, x, self.header_height)
                
                draw_label = True
                if self.pixels_per_second < 40 and s % 5 != 0:
                    draw_label = False
                elif self.pixels_per_second < 15 and s % 10 != 0:
                    draw_label = False
                    
                if draw_label:
                    minutes = s // 60
                    seconds = s % 60
                    time_str = f"{minutes}:{seconds:02d}"
                    painter.setFont(QFont("Segoe UI", 8))
                    painter.setPen(QColor("#80808a"))
                    painter.drawText(QRect(x - 20, 24, 40, 15), Qt.AlignmentFlag.AlignCenter, time_str)

        # 5. Draw beats on top of waveform/grid across visible tracks
        # Adaptive base radius that scales down smoothly when zoomed out
        zoom_ratio = max(0.4, min(1.0, (self.pixels_per_second / 100.0) ** 0.5))
        base_r = 12.0 * zoom_ratio
        selected_set = {id(b) for b in self.selected_beats}
        
        # Ensure intrinsic neighbor distances are computed
        if any('_min_dt' not in b for b in self.beats):
            self.update_beat_neighbor_distances()

        # Binary search visible beats slice (self.beats sorted by time)
        t_min = (left_x - base_r * 2) / self.pixels_per_second
        t_max = (right_x + base_r * 2) / self.pixels_per_second

        times_view = _TimeKey(self.beats)
        start_idx = bisect.bisect_left(times_view, t_min)
        end_idx = bisect.bisect_right(times_view, t_max)
        
        visible_slice = self.beats[start_idx:end_idx]
        
        # Group beats by visible track index
        beats_by_track = {i: [] for i in range(self.visible_track_count)}
        for b in visible_slice:
            tr_i = self.lane_to_track_idx(b.get('lane', 4))
            if tr_i < self.visible_track_count:
                beats_by_track[tr_i].append(b)

        for tr_i, track_beats in beats_by_track.items():
            if not track_beats:
                continue
            track_color = self.tracks[tr_i]['color']
            y = self.header_height + tr_i * self.lane_height + self.lane_height / 2.0

            # Compute anti-overlap radius and neighbor distance per beat using intrinsic min_dt
            beat_render_items = []
            for b in track_beats:
                x = b['time'] * self.pixels_per_second
                min_dt = b.get('_min_dt', 999.0)
                min_d = min_dt * self.pixels_per_second
                if min_d < 2.0 * base_r:
                    r = max(2.5, min(base_r, min_d * 0.45))
                else:
                    r = base_r
                beat_render_items.append((b, x, r, min_d))

            # Pass 1: Draw circle bodies (fills). Tightly spaced bursts merge smoothly without inner border cuts
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(track_color))
            for b, x, r, min_d in beat_render_items:
                painter.drawEllipse(QPointF(x, y), r, r)

            # Pass 2: Draw borders (selection rings and clean, non-conflicting outlines)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for b, x, r, min_d in beat_render_items:
                if id(b) in selected_set:
                    painter.setPen(QPen(QColor("#FFFFFF"), 3))
                    painter.drawEllipse(QPointF(x, y), r + 2, r + 2)
                    painter.setPen(QPen(QColor(0, 0, 0), 1))
                    painter.drawEllipse(QPointF(x, y), r, r)
                else:
                    if min_d < r * 1.5:
                        # Adjacent notes are touching/overlapping: draw subtle outline so no harsh crescent cuts
                        painter.setPen(QPen(QColor(255, 255, 255, 110), 0.75))
                    else:
                        pen_w = max(0.8, min(1.5, r * 0.18))
                        painter.setPen(QPen(QColor(255, 255, 255, 255), pen_w))
                    painter.drawEllipse(QPointF(x, y), r, r)

        # 6. Draw Playhead
        px = int(self.playhead_time * self.pixels_per_second)
        if left_x - 10 <= px <= right_x + 10:
            painter.setPen(QPen(QColor("#00FFFF"), 2))
            painter.drawLine(px, 0, px, self.height())
            
            painter.setBrush(QBrush(QColor("#00FFFF")))
            painter.setPen(Qt.PenStyle.NoPen)
            points = [
                QPointF(px - 6, 0),
                QPointF(px + 6, 0),
                QPointF(px + 6, 12),
                QPointF(px, 20),
                QPointF(px - 6, 12)
            ]
            painter.drawPolygon(points)

        # 7. Draw Selection Rubber-Band Rectangle
        if self.drag_state == "selecting":
            painter.setPen(QPen(QColor("#00e5ff"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(0, 229, 255, 30)))
            painter.drawRect(QRectF(self.selection_start, self.selection_end))

    def mousePressEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        t = x / self.pixels_per_second
        
        # Check if clicked on Level chapters bar (Y <= 18)
        if y <= 18:
            # Check if clicked on a boundary between chapters (within 5px)
            clicked_boundary = -1
            if self.levels:
                for idx in range(1, len(self.levels)):
                    bx = int(self.levels[idx].get('start_time', 0.0) * self.pixels_per_second)
                    if abs(x - bx) <= 5:
                        clicked_boundary = idx
                        break
            if clicked_boundary != -1 and event.button() == Qt.MouseButton.LeftButton:
                self.drag_state = "dragging_chapter_boundary"
                self.dragging_boundary_idx = clicked_boundary
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                return
            elif event.button() == Qt.MouseButton.LeftButton:
                # Select the clicked chapter
                ch = self.get_level_at(t)
                self.selected_chapter = ch
                self.selected_beats = []
                self.selection_changed.emit()
                if ch:
                    self.level_selected.emit(ch)
                # Seek playhead to clicked spot in chapters bar
                self.drag_state = "seeking"
                self.time_seek_requested.emit(max(0.0, min(t, self.duration)))
                self.update()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                ch = self.get_level_at(t)
                self.selected_chapter = ch
                self.selected_beats = []
                self.selection_changed.emit()
                self.update()
                # Context menu for level chapters
                self.show_chapter_context_menu(event.globalPosition().toPoint(), t)
                return

        # If clicked below chapter bar, clear selected chapter
        if getattr(self, 'selected_chapter', None):
            self.selected_chapter = None
            self.update()

        # Check if clicked on a note circle on any visible track
        r = 14
        clicked_beat = None
        for beat in self.beats:
            tr_i = self.lane_to_track_idx(beat.get('lane', 4))
            if tr_i >= self.visible_track_count:
                continue
            by = self.header_height + tr_i * self.lane_height + self.lane_height / 2.0
            bx = beat['time'] * self.pixels_per_second
            if abs(x - bx) <= r and abs(y - by) <= r:
                clicked_beat = beat
                break
                
        if event.button() == Qt.MouseButton.LeftButton:
            if clicked_beat:
                is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if is_shift:
                    # Toggle selection
                    if clicked_beat in self.selected_beats:
                        self.selected_beats.remove(clicked_beat)
                    else:
                        self.selected_beats.append(clicked_beat)
                else:
                    # Clear selection and select this beat if not already selected
                    if clicked_beat not in self.selected_beats:
                        self.selected_beats = [clicked_beat]
                
                # Start dragging the selected beats
                self.drag_state = "dragging_beat"
                self.drag_anchor_time = t
                self.drag_clicked_beat = clicked_beat
                self.drag_start_positions = {id(b): (b['time'], b.get('lane', 4)) for b in self.selected_beats}
                self.selection_changed.emit()
                self.update()
            else:
                # Clicked empty space
                if y < self.header_height:
                    # Seek playhead to clicked spot in ruler
                    self.selected_beats = []
                    self.drag_state = "seeking"
                    self.time_seek_requested.emit(max(0.0, min(t, self.duration)))
                    self.selection_changed.emit()
                    self.update()
                else:
                    # Start dragging a rubber band selection box
                    is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    if not is_shift:
                        self.selected_beats = []
                    self.drag_state = "selecting"
                    self.selection_start = event.position()
                    self.selection_end = event.position()
                    self.selection_changed.emit()
                    self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right click selects note, or deletes selected beats
            if clicked_beat:
                if clicked_beat not in self.selected_beats:
                    self.selected_beats = [clicked_beat]
                    self.selection_changed.emit()
                self.delete_selected_beats()

    def wheelEvent(self, event):
        # Horizontal timeline scroll with mouse wheel
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta != 0:
            main_app = self.window()
            if hasattr(main_app, 'scroll_area') and main_app.scroll_area:
                sb = main_app.scroll_area.horizontalScrollBar()
                step = -60 if delta > 0 else 60
                sb.setValue(sb.value() + step)

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        t = x / self.pixels_per_second

        # Check hover over chapter boundaries or chapter bar when not dragging
        if not self.drag_state:
            if y <= 18 and self.levels:
                near_b = False
                for idx in range(1, len(self.levels)):
                    bx = int(self.levels[idx].get('start_time', 0.0) * self.pixels_per_second)
                    if abs(x - bx) <= 5:
                        near_b = True
                        break
                if near_b:
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.unsetCursor()
                hovered = self.get_level_at(t)
                if hovered != self.hovered_chapter:
                    self.hovered_chapter = hovered
                    self.update()
            else:
                if self.hovered_chapter is not None:
                    self.hovered_chapter = None
                    self.unsetCursor()
                    self.update()
            return

        # Chapter boundary dragging
        if self.drag_state == "dragging_chapter_boundary" and 1 <= self.dragging_boundary_idx < len(self.levels):
            prev_ch = self.levels[self.dragging_boundary_idx - 1]
            curr_ch = self.levels[self.dragging_boundary_idx]
            min_t = prev_ch.get('start_time', 0.0) + 0.5
            max_t = curr_ch.get('end_time', self.duration) - 0.5
            new_t = round(max(min_t, min(max_t, t)), 3)
            prev_ch['end_time'] = new_t
            curr_ch['start_time'] = new_t
            self.beats_changed.emit()
            self.update()
            return
            
        # Edge scrolling check when selecting or dragging
        if self.drag_state in ["selecting", "dragging_beat"]:
            main_app = self.window()
            if hasattr(main_app, 'scroll_area') and main_app.scroll_area:
                viewport = main_app.scroll_area.viewport()
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else self.mapToGlobal(event.position().toPoint())
                local_vp = viewport.mapFromGlobal(global_pos)
                
                margin = 45  # 45px from viewport edge triggers scroll
                vp_width = viewport.width()
                
                if local_vp.x() > vp_width - margin:
                    self.edge_scroll_dir = 1
                    if not self.edge_scroll_timer.isActive():
                        self.edge_scroll_timer.start()
                elif local_vp.x() < margin:
                    self.edge_scroll_dir = -1
                    if not self.edge_scroll_timer.isActive():
                        self.edge_scroll_timer.start()
                else:
                    self.edge_scroll_dir = 0
                    self.edge_scroll_timer.stop()

        if self.drag_state == "seeking":
            self.time_seek_requested.emit(max(0.0, min(t, self.duration)))
        elif self.drag_state == "selecting":
            self.selection_end = event.position()
            self.update()
        elif self.drag_state == "dragging_beat" and self.drag_clicked_beat:
            dt = t - self.drag_anchor_time
            target_lane = self.y_to_lane(y)
            
            # Move selected beats in time together
            for b in self.selected_beats:
                if id(b) in self.drag_start_positions:
                    start_t, start_l = self.drag_start_positions[id(b)]
                    new_time = max(0.0, min(start_t + dt, self.duration))
                    b['time'] = round(new_time, 3)
                    # Move to target lane if dragging single beat
                    if target_lane != -1 and len(self.selected_beats) == 1:
                        b['lane'] = target_lane
                                
            self.beats_changed.emit()
            self.update()

    def on_edge_scroll_tick(self):
        if self.edge_scroll_dir == 0 or not self.drag_state:
            self.edge_scroll_timer.stop()
            return
            
        main_app = self.window()
        if hasattr(main_app, 'scroll_area') and main_app.scroll_area:
            sb = main_app.scroll_area.horizontalScrollBar()
            scroll_step = self.edge_scroll_dir * 18
            sb.setValue(sb.value() + scroll_step)
            
            # Update cursor position in widget coords
            from PyQt6.QtGui import QCursor
            global_pos = QCursor.pos()
            widget_pos = QPointF(self.mapFromGlobal(global_pos))
            x = widget_pos.x()
            y = widget_pos.y()
            t = x / self.pixels_per_second
            
            if self.drag_state == "selecting":
                self.selection_end = widget_pos
                rect = QRectF(self.selection_start, self.selection_end).normalized()
                for b in self.beats:
                    tr_i = self.lane_to_track_idx(b.get('lane', 4))
                    if tr_i < self.visible_track_count:
                        by = self.header_height + tr_i * self.lane_height + self.lane_height / 2.0
                        bx = b['time'] * self.pixels_per_second
                        if rect.contains(QPointF(bx, by)):
                            if b not in self.selected_beats:
                                self.selected_beats.append(b)
                self.selection_changed.emit()
                self.update()
            elif self.drag_state == "dragging_beat" and self.drag_clicked_beat:
                dt = t - self.drag_anchor_time
                target_lane = self.y_to_lane(y)
                for b in self.selected_beats:
                    if id(b) in self.drag_start_positions:
                        start_t, start_l = self.drag_start_positions[id(b)]
                        new_time = max(0.0, min(start_t + dt, self.duration))
                        b['time'] = round(new_time, 3)
                        if target_lane != -1 and len(self.selected_beats) == 1:
                            b['lane'] = target_lane
                self.beats_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event):
        self.edge_scroll_dir = 0
        if self.edge_scroll_timer.isActive():
            self.edge_scroll_timer.stop()
            
        if self.drag_state == "dragging_chapter_boundary":
            self.drag_state = None
            self.dragging_boundary_idx = -1
            self.unsetCursor()
            self.beats_changed.emit()
            self.update()
            return
        elif self.drag_state == "selecting":
            rect = QRectF(self.selection_start, self.selection_end).normalized()
            for b in self.beats:
                tr_i = self.lane_to_track_idx(b.get('lane', 4))
                if tr_i < self.visible_track_count:
                    by = self.header_height + tr_i * self.lane_height + self.lane_height / 2.0
                    bx = b['time'] * self.pixels_per_second
                    if rect.contains(QPointF(bx, by)):
                        if b not in self.selected_beats:
                            self.selected_beats.append(b)
            self.selection_changed.emit()
            self.update()
        elif self.drag_state == "dragging_beat":
            self.beats.sort(key=lambda x: (x['time'], x['lane']))
            self.beats_changed.emit()
        self.drag_state = None

    def mouseDoubleClickEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        t = x / self.pixels_per_second
        
        # Double clicking in chapter bar opens Place Level Dialog for this segment
        if y <= 18:
            self.open_place_level_dialog(t)
            return

        lane = self.y_to_lane(y)
        if lane != -1 and 0.0 <= t <= self.duration:
            new_beat = {'time': round(t, 3), 'lane': lane}
            self.beats.append(new_beat)
            self.beats.sort(key=lambda x: (x['time'], x['lane']))
            self.selected_beats = [new_beat]
            self.selection_changed.emit()
            self.beats_changed.emit()
            self.update()

    def contextMenuEvent(self, event):
        y = event.position().y() if hasattr(event, 'position') else event.y()
        x = event.position().x() if hasattr(event, 'position') else event.x()
        t = x / self.pixels_per_second
        if y <= 18:
            global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.show_chapter_context_menu(global_pos, t)
            event.accept()
            return
        super().contextMenuEvent(event)

    def show_chapter_context_menu(self, global_pos, t):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                color: #ffffff;
                border: 1px solid #3b3b4f;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #4f46e5;
            }
        """)
        ch = self.get_level_at(t)
        if ch:
            act_edit = menu.addAction(f"✏️ Edit Chapter '{ch.get('name')}'...")
            act_edit.triggered.connect(lambda checked=False, target_ch=ch: self.open_place_level_dialog(target_ch, t))
            act_split = menu.addAction(f"✂️ Split Chapter at {self.format_time_sec(t)}")
            act_split.triggered.connect(lambda checked=False, split_t=t: self.split_level_at(split_t))
            act_del = menu.addAction(f"🗑️ Delete Chapter '{ch.get('name')}'")
            act_del.triggered.connect(lambda checked=False, target_ch=ch: self.delete_level_chapter(target_ch))
            menu.addSeparator()
        act_insert = menu.addAction("➕ Insert New Level Chapter Here...")
        act_insert.triggered.connect(lambda checked=False, ins_t=t: self.open_place_level_dialog(None, ins_t))
        menu.exec(global_pos)

    def keyPressEvent(self, event):
        key = event.key()
        if key in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            if self.selected_beats:
                self.delete_selected_beats()
                return
            elif getattr(self, 'selected_chapter', None):
                self.delete_level_chapter(self.selected_chapter)
                return
            elif getattr(self, 'hovered_chapter', None):
                self.delete_level_chapter(self.hovered_chapter)
                return
        elif key == Qt.Key.Key_Space:
            event.ignore()
            return
        elif key == Qt.Key.Key_Left:
            step = 0.1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.5
            self.time_seek_requested.emit(max(0.0, self.playhead_time - step))
            return
        elif key == Qt.Key.Key_Right:
            step = 0.1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.5
            self.time_seek_requested.emit(min(self.duration, self.playhead_time + step))
            return

        # Configurable keybindings
        key_str = event.text().upper()
        if not key_str:
            super().keyPressEvent(event)
            return

        main_app = self.window()
        if hasattr(main_app, 'keybinds'):
            kb = main_app.keybinds
            
            # Check beat placement hotkeys (1: Track 1, 2: Track 2, 3: Track 3)
            if key_str in ['1', kb.get('lane_4', '5'), kb.get('beat_key')]:
                self.add_beat_at_playhead(4)
                return
            elif key_str in ['2', kb.get('lane_1', '2')]:
                self.add_beat_at_playhead(1)
                return
            elif key_str in ['3', kb.get('lane_2', '3')]:
                self.add_beat_at_playhead(2)
                return
                    
            # Check halve hotkey
            if key_str == kb.get('halve', 'H'):
                self.halve_selected_beats()
                return
                    
        super().keyPressEvent(event)

    def delete_selected_beats(self):
        if self.selected_beats:
            self.beats = [b for b in self.beats if b not in self.selected_beats]
            self.selected_beats = []
            self.selection_changed.emit()
            self.beats_changed.emit()
            self.update()

    def add_beat_at_playhead(self, lane=4):
        if self.duration <= 0:
            return
        t = round(self.playhead_time, 3)
        new_beat = {'time': t, 'lane': lane}
        self.beats.append(new_beat)
        self.beats.sort(key=lambda x: (x['time'], x['lane']))
        self.selected_beats = [new_beat]
        
        tr_idx = self.lane_to_track_idx(lane)
        if tr_idx >= self.visible_track_count:
            main_app = self.window()
            if hasattr(main_app, 'cb_tracks'):
                main_app.cb_tracks.setCurrentIndex(tr_idx)
            else:
                self.set_visible_track_count(tr_idx + 1)

        self.selection_changed.emit()
        self.beats_changed.emit()
        self.update()

    def halve_selected_beats(self):
        """Thins out selected beats by deleting every alternate beat chronologically."""
        if not self.selected_beats:
            return
            
        sorted_beats = sorted(self.selected_beats, key=lambda x: x['time'])
        beats_to_remove = [sorted_beats[i] for i in range(1, len(sorted_beats), 2)]
        if not beats_to_remove:
            return
            
        self.beats = [b for b in self.beats if b not in beats_to_remove]
        self.selected_beats = []
        self.selection_changed.emit()
        self.beats_changed.emit()
        self.update()


class LaneLabelsWidget(QFrame):
    """Side panel displaying the beat track labels (1, 2, or 3 tracks)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lane_labels")
        self.setFixedWidth(95)
        self.header_height = 46  # matches TimelineWidget.header_height
        self.lane_height = 55
        self.visible_track_count = 1
        self.tracks = [
            {'lane': 4, 'name': 'TRACK 1', 'color': QColor("#B10DC9")},
            {'lane': 1, 'name': 'TRACK 2', 'color': QColor("#00E5FF")},
            {'lane': 2, 'name': 'TRACK 3', 'color': QColor("#FFB300")},
        ]
        self.adjust_height()

    def set_visible_track_count(self, count):
        self.visible_track_count = max(1, min(3, int(count)))
        self.adjust_height()
        self.update()

    def adjust_height(self):
        self.setFixedHeight(self.header_height + self.visible_track_count * self.lane_height + 5)

    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Level Chapters Header (Y=0 to 18)
        painter.fillRect(0, 0, self.width(), 18, QColor("#0d0d12"))
        painter.setPen(QPen(QColor("#818cf8")))
        font_lvl = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font_lvl)
        
        # Draw Feather SVG 'layers' icon instead of emoji
        icon_size = 12
        text = "LEVELS"
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        gap = 4
        total_w = icon_size + gap + text_w
        start_x = (self.width() - total_w) / 2
        icon_y = (18 - icon_size) / 2
        draw_feather_icon(painter, "layers", QRectF(start_x, icon_y, icon_size, icon_size), color="#818cf8", stroke_width=2)
        painter.drawText(QRectF(start_x + icon_size + gap, 0, text_w + 4, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        
        # Divider below LEVELS
        painter.setPen(QPen(QColor("#2d2d35"), 1))
        painter.drawLine(0, 18, self.width(), 18)

        # 2. Time Ruler / Tracks Header (Y=18 to 46)
        painter.setPen(QPen(QColor("#80808a")))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRect(0, 18, self.width() - 5, 28), Qt.AlignmentFlag.AlignCenter, "TRACKS")
        
        # Top line (under header)
        painter.setPen(QPen(QColor("#2d2d35"), 1))
        painter.drawLine(0, self.header_height, self.width(), self.header_height)
        
        for i in range(self.visible_track_count):
            y = self.header_height + i * self.lane_height
            # Divider line below
            painter.setPen(QPen(QColor("#2d2d35"), 1))
            painter.drawLine(0, y + self.lane_height, self.width(), y + self.lane_height)
            
            # Indicator dot
            color = self.tracks[i]['color']
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(12, int(y + self.lane_height / 2.0 - 5), 10, 10)
            
            # Label
            painter.setPen(QPen(QColor("#e2e2e7")))
            painter.setFont(font)
            painter.drawText(QRect(28, y, self.width() - 32, self.lane_height), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.tracks[i]['name'])


class GenerateSettingsDialogV2(QDialog):
    """Configuration dialog for V2 Musical Rhythm Beatbar Generation."""
    def __init__(self, parent=None, default_bpm=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Generate Beats (V2 Engine)")
        self.resize(450, 520)
        
        self.layout = QVBoxLayout(self)
        
        # Header banner
        header_lbl = QLabel(
            "<b>Auto-Generate Beats V2 (Musical Engine)</b><br>"
            "<span style='color: #a0a0b0; font-size: 11px;'>"
            "Generates playable rhythm beatbars aligned to BPM and dynamic song energy.<br>"
            "Analyzes song sections: half-notes in breakdowns, quarters in verses, "
            "eighths in drops, and 16th burst rolls in climax sections."
            "</span>"
        )
        header_lbl.setTextFormat(Qt.TextFormat.RichText)
        header_lbl.setWordWrap(True)
        self.layout.addWidget(header_lbl)
        
        self.form = QFormLayout()
        self.form.setSpacing(10)
        
        # 1. Preset Selector
        self.cb_preset = QComboBox()
        self.cb_preset.addItem("Musical Beatbar (Wicked Style - Adaptive)", "musical_beatbar")
        self.cb_preset.addItem("Steady Quarters (4-on-the-Floor)", "steady_quarters")
        self.cb_preset.addItem("Energetic Eighths (Driving Rhythm)", "energetic_eighths")
        self.cb_preset.addItem("Climax Bursts (Dense Rolls)", "climax_bursts")
        self.cb_preset.addItem("Custom Configuration", "custom")
        self.cb_preset.currentIndexChanged.connect(self.on_preset_changed)
        self.form.addRow("Rhythm Preset:", self.cb_preset)
        
        # 2. Target Track
        self.cb_lane = QComboBox()
        self.cb_lane.addItem("Track 1", 4)
        self.cb_lane.addItem("Track 2", 1)
        self.cb_lane.addItem("Track 3", 2)
        self.form.addRow("Target Track:", self.cb_lane)
        
        # 3. BPM Section
        bpm_box = QHBoxLayout()
        self.chk_auto_bpm = QCheckBox("Auto-Detect BPM")
        self.chk_auto_bpm.setChecked(True)
        self.chk_auto_bpm.toggled.connect(self.on_auto_bpm_toggled)
        
        self.spin_bpm = QDoubleSpinBox()
        self.spin_bpm.setRange(40.0, 240.0)
        self.spin_bpm.setValue(default_bpm if default_bpm else 125.0)
        self.spin_bpm.setSingleStep(1.0)
        self.spin_bpm.setEnabled(False)
        self.spin_bpm.setSuffix(" BPM")
        
        bpm_box.addWidget(self.chk_auto_bpm)
        bpm_box.addWidget(self.spin_bpm)
        self.form.addRow("Tempo (BPM):", bpm_box)
        
        # 4. Density / Sensitivity Scale
        density_box = QHBoxLayout()
        self.spin_density = QDoubleSpinBox()
        self.spin_density.setRange(0.3, 2.5)
        self.spin_density.setValue(0.85)
        self.spin_density.setSingleStep(0.05)
        self.spin_density.setToolTip("Note density scaling. 0.85 = Balanced human rhythm game feel, 1.0 = Driving, >1.2 = Dense.")
        self.lbl_density_hint = QLabel("(0.85 = Balanced Human Feel, 1.0 = Driving)")
        self.lbl_density_hint.setStyleSheet("color: #888899;")
        density_box.addWidget(self.spin_density)
        density_box.addWidget(self.lbl_density_hint)
        self.form.addRow("Rhythm Density:", density_box)
        
        # 5. Quantization Grid
        self.cb_grid = QComboBox()
        self.cb_grid.addItem("Adaptive Auto (up to 1/16)", "auto")
        self.cb_grid.addItem("Quarter Notes (1/4)", "1/4")
        self.cb_grid.addItem("Eighth Notes (1/8)", "1/8")
        self.cb_grid.addItem("Sixteenth Notes (1/16)", "1/16")
        self.cb_grid.addItem("None (Micro-timing)", "none")
        self.form.addRow("Grid Quantize:", self.cb_grid)
        
        # 6. Minimum Beat Gap
        self.spin_min_gap = QDoubleSpinBox()
        self.spin_min_gap.setRange(0.04, 0.50)
        self.spin_min_gap.setValue(0.095)
        self.spin_min_gap.setSingleStep(0.01)
        self.spin_min_gap.setSuffix(" s")
        self.form.addRow("Min Beat Gap:", self.spin_min_gap)
        
        # 7. Intro Silence Cutoff
        self.spin_intro_cutoff = QDoubleSpinBox()
        self.spin_intro_cutoff.setRange(0.0, 30.0)
        self.spin_intro_cutoff.setValue(3.8)
        self.spin_intro_cutoff.setSingleStep(0.5)
        self.spin_intro_cutoff.setSuffix(" s")
        self.spin_intro_cutoff.setToolTip("Sets a cutoff threshold so no beats are placed during ambient song intros before the first beat.")
        self.form.addRow("Intro Cutoff:", self.spin_intro_cutoff)
        
        # 8. Checkboxes
        self.chk_halve_non_intense = QCheckBox("Halve beat density in non-intense sections (verses & breakdowns)")
        self.chk_halve_non_intense.setChecked(True)
        self.chk_halve_non_intense.setToolTip("Automatically keeps steady quarter notes or half notes during verses and breakdowns, only accelerating into dense rhythms during intense drops and climaxes.")
        self.form.addRow("", self.chk_halve_non_intense)
        
        self.chk_insert_rolls = QCheckBox("Insert syncopated 16th bursts on drum/synth rolls")
        self.chk_insert_rolls.setChecked(True)
        self.form.addRow("", self.chk_insert_rolls)
        
        self.clear_existing = QCheckBox("Clear existing beats first")
        self.clear_existing.setChecked(True)
        self.form.addRow("", self.clear_existing)
        
        self.layout.addLayout(self.form)
        
        # Preset description label
        self.lbl_desc = QLabel(
            "<b>Preset description:</b><br>"
            "Adapts note density dynamically based on song section energy: "
            "half-notes in breakdowns, quarter-notes in verses, eighth-notes in drops, "
            "and 16th burst rolls in climax sections."
        )
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("background: #1c1c24; padding: 8px; border-radius: 4px; border: 1px solid #2d2d3a; color: #bbbbcc; font-size: 11px;")
        self.layout.addWidget(self.lbl_desc)
        
        # Buttons
        self.btn_layout = QHBoxLayout()
        
        self.btn_video_zones = QPushButton("Open Zones Editor...")
        self.btn_video_zones.setIcon(get_feather_icon("video", "#ffffff", 14))
        self.btn_video_zones.setStyleSheet("""
            QPushButton {
                background: #11998e;
                border: 1px solid #38ef7d;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #13b3a6;
            }
        """)
        self.btn_video_zones.clicked.connect(self.on_open_zones_editor_clicked)
        self.btn_layout.addWidget(self.btn_video_zones)
        
        self.btn_ok = QPushButton("Generate V2 Beats")
        self.btn_ok.setObjectName("generate_btn_v2_dialog")
        self.btn_ok.setStyleSheet("""
            QPushButton#generate_btn_v2_dialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8a2be2, stop:1 #4a00e0);
                border: 1px solid #a855f7;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton#generate_btn_v2_dialog:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9d4edd, stop:1 #5a189a);
            }
        """)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_cancel)
        self.btn_layout.addWidget(self.btn_ok)
        self.layout.addLayout(self.btn_layout)

    def on_open_zones_editor_clicked(self):
        self.reject()
        parent_win = self.parent()
        if parent_win and hasattr(parent_win, 'open_video_zones_dialog'):
            parent_win.open_video_zones_dialog()

    def on_auto_bpm_toggled(self, checked):
        self.spin_bpm.setEnabled(not checked)

    def on_preset_changed(self, idx):
        preset_key = self.cb_preset.currentData()
        if preset_key == "musical_beatbar":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.0)
            self.cb_grid.setCurrentIndex(0)
            self.chk_insert_rolls.setChecked(True)
            self.lbl_desc.setText(
                "<b>Musical Beatbar (Wicked Style):</b><br>"
                "Adapts note density dynamically based on song energy: "
                "half-notes in breakdowns, quarters in verses, eighths in drops, "
                "and 16th burst rolls in climax sections."
            )
        elif preset_key == "steady_quarters":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.0)
            self.cb_grid.setCurrentIndex(1)
            self.chk_insert_rolls.setChecked(False)
            self.lbl_desc.setText(
                "<b>Steady Quarters:</b><br>"
                "Generates classic 4-on-the-floor quarter notes on every active beat."
            )
        elif preset_key == "energetic_eighths":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.2)
            self.cb_grid.setCurrentIndex(2)
            self.chk_insert_rolls.setChecked(False)
            self.lbl_desc.setText(
                "<b>Energetic Eighths:</b><br>"
                "Fast driving rhythm with eighth-note subdivisions across verses and drops."
            )
        elif preset_key == "climax_bursts":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.5)
            self.cb_grid.setCurrentIndex(3)
            self.chk_insert_rolls.setChecked(True)
            self.lbl_desc.setText(
                "<b>Climax Bursts:</b><br>"
                "Dense, frantic chart with fast rolls, rapid sixteenth taps, and high energy."
            )
        elif preset_key == "custom":
            self.lbl_desc.setText(
                "<b>Custom Configuration:</b><br>"
                "Manually configure target lane, tempo, density, grid snapping, and roll behavior."
            )


class GenerateSettingsDialogV3(QDialog):
    """V3 Configuration dialog: Zone-aware rhythm generator with anti-overlap and clean steady quarter notes."""
    def __init__(self, parent=None, default_bpm=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Generate Settings (V3 Engine)")
        self.resize(600, 460)
        self.setMinimumWidth(560)
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(12, 10, 12, 10)
        
        header_lbl = QLabel(
            "<h4 style='margin:0 0 2px 0; color:#ff9f43;'>AUTO-GEN BEATS (V3)</h4>"
            "<span style='color:#a0a0b0; font-size:11px;'>"
            "Zone-aware phrased rhythm engine with anti-overlap protection and clean quarter-note pacing."
            "</span>"
        )
        self.layout.addWidget(header_lbl)
        
        self.form = QFormLayout()
        self.form.setSpacing(6)
        self.form.setContentsMargins(0, 0, 0, 0)
        
        # 1. Preset Selector
        self.cb_preset = QComboBox()
        self.cb_preset.addItem("Musical Beatbar V3 (Adaptive + Clean Quarters)", "musical_beatbar")
        self.cb_preset.addItem("Steady Quarters (Strict 4-on-the-Floor)", "steady_quarters")
        self.cb_preset.addItem("Energetic Eighths (Driving Rhythm)", "energetic_eighths")
        self.cb_preset.addItem("Climax Bursts (Dense Rolls with Anti-Overlap)", "climax_bursts")
        self.cb_preset.addItem("Custom Configuration", "custom")
        self.cb_preset.currentIndexChanged.connect(self.on_preset_changed)
        self.form.addRow("Rhythm Preset:", self.cb_preset)
        
        # 2. Target Track / Lane
        self.cb_lane = QComboBox()
        self.cb_lane.addItem("Track 1", 4)
        self.cb_lane.addItem("Track 2", 1)
        self.cb_lane.addItem("Track 3", 2)
        self.form.addRow("Target Track:", self.cb_lane)
        
        # 2b. Level, Difficulty & Progression Mode (Level & Difficulty combined in 1 row)
        self.cb_level = QComboBox()
        self.cb_level.addItems([f"Level {i}" for i in range(1, 11)])
        parent_lvl = getattr(parent, 'current_level', 5) if parent else 5
        self.cb_level.setCurrentIndex(max(0, min(9, int(parent_lvl) - 1)))

        self.cb_difficulty = QComboBox()
        self.cb_difficulty.addItem("Auto (Determined by Level)", "Auto")
        self.cb_difficulty.addItem("Easy", "Easy")
        self.cb_difficulty.addItem("Normal", "Normal")
        self.cb_difficulty.addItem("Hard", "Hard")
        # Expert and Master commented out to prevent beat spam
        # self.cb_difficulty.addItem("Expert", "Expert")
        # self.cb_difficulty.addItem("Master", "Master")
        parent_diff = getattr(parent, 'current_difficulty', 'Normal') if parent else 'Normal'
        if parent_diff in ("Expert", "Master"):
            parent_diff = "Hard"
        idx_diff = self.cb_difficulty.findText(parent_diff)
        if idx_diff >= 0:
            self.cb_difficulty.setCurrentIndex(idx_diff)

        lvl_diff_box = QHBoxLayout()
        lvl_diff_box.addWidget(self.cb_level, 1)
        lbl_diff = QLabel("Difficulty:")
        lbl_diff.setStyleSheet("color: #a0a0b0; margin-left: 10px;")
        lvl_diff_box.addWidget(lbl_diff)
        lvl_diff_box.addWidget(self.cb_difficulty, 1)
        self.form.addRow("Level & Diff:", lvl_diff_box)

        self.cb_level_mode = QComboBox()
        self.cb_level_mode.addItem("Ramping (Easy to Hard inside section)", "ramp_within_level")
        self.cb_level_mode.addItem("Progressive (Each section gets harder)", "rise_with_level")
        self.cb_level_mode.addItem("Fixed (Manual difficulty per section)", "named_levels")
        self.cb_level_mode.setToolTip("Ramping: Song builds up from easy to hard inside each section. Progressive: Each subsequent section is harder. Fixed: Manual difficulty setting for each section.")
        parent_mode = getattr(parent, 'level_mode', 'ramp_within_level') if parent else 'ramp_within_level'
        idx_m = self.cb_level_mode.findData(parent_mode)
        if idx_m >= 0:
            self.cb_level_mode.setCurrentIndex(idx_m)
        self.form.addRow("Level Mode:", self.cb_level_mode)

        # 2c. Edging Zone Rhythm Style
        self.cb_edging_style = QComboBox()
        self.cb_edging_style.addItem("Rhythmic Tension (Stutter Pulses & Dramatic Pauses)", "rhythmic_tension")
        self.cb_edging_style.addItem("Building Tension (Sparse Pauses Accelerating to Bursts)", "building_tension")
        self.cb_edging_style.setToolTip(
            "Rhythmic Tension: Steady groove foundation with syncopated stutter pulses followed by dramatic breathers.\n"
            "Building Tension: Starts sparse with dramatic tension holds, then accelerates into rapid pulses near the end."
        )
        self.form.addRow("Edging Style:", self.cb_edging_style)

        # 3. BPM Section
        bpm_box = QHBoxLayout()
        self.chk_auto_bpm = QCheckBox("Auto-Detect BPM")
        self.chk_auto_bpm.setChecked(True)
        self.chk_auto_bpm.toggled.connect(self.on_auto_bpm_toggled)
        
        self.spin_bpm = QDoubleSpinBox()
        self.spin_bpm.setRange(40.0, 240.0)
        self.spin_bpm.setValue(default_bpm if default_bpm else 125.0)
        self.spin_bpm.setSingleStep(1.0)
        self.spin_bpm.setEnabled(False)
        self.spin_bpm.setSuffix(" BPM")
        
        bpm_box.addWidget(self.chk_auto_bpm)
        bpm_box.addWidget(self.spin_bpm)
        self.form.addRow("Tempo (BPM):", bpm_box)
        
        # 4. Density / Sensitivity Scale
        density_box = QHBoxLayout()
        self.spin_density = QDoubleSpinBox()
        self.spin_density.setRange(0.3, 2.5)
        self.spin_density.setValue(0.85)
        self.spin_density.setSingleStep(0.05)
        self.spin_density.setToolTip("Note density scaling. 0.85 = Balanced human rhythm game feel, 1.0 = Driving, >1.2 = Dense.")
        self.lbl_density_hint = QLabel("(0.85 = Human Feel, 1.0 = Driving)")
        self.lbl_density_hint.setStyleSheet("color: #888899;")
        density_box.addWidget(self.spin_density)
        density_box.addWidget(self.lbl_density_hint)
        self.form.addRow("Rhythm Density:", density_box)
        
        # 5. Quantization Grid
        self.cb_grid = QComboBox()
        self.cb_grid.addItem("Adaptive Auto (up to 1/16)", "auto")
        self.cb_grid.addItem("Quarter Notes (1/4)", "1/4")
        self.cb_grid.addItem("Eighth Notes (1/8)", "1/8")
        self.cb_grid.addItem("Sixteenth Notes (1/16)", "1/16")
        self.cb_grid.addItem("None (Micro-timing)", "none")
        self.form.addRow("Grid Quantize:", self.cb_grid)
        
        # 6. Minimum Beat Gap & Intro Cutoff (combined in 1 row)
        self.spin_min_gap = QDoubleSpinBox()
        self.spin_min_gap.setRange(0.04, 0.50)
        self.spin_min_gap.setValue(0.11)
        self.spin_min_gap.setSingleStep(0.01)
        self.spin_min_gap.setSuffix(" s")
        self.spin_min_gap.setToolTip("Prevents overlapping note circles in fast rolls (fixes Picture 2 caterpillar collisions).")
        
        self.spin_intro_cutoff = QDoubleSpinBox()
        self.spin_intro_cutoff.setRange(0.0, 30.0)
        self.spin_intro_cutoff.setValue(3.8)
        self.spin_intro_cutoff.setSingleStep(0.5)
        self.spin_intro_cutoff.setSuffix(" s")
        
        gap_cutoff_box = QHBoxLayout()
        gap_cutoff_box.addWidget(self.spin_min_gap, 1)
        lbl_intro = QLabel("Intro Cutoff:")
        lbl_intro.setStyleSheet("color: #a0a0b0; margin-left: 10px;")
        gap_cutoff_box.addWidget(lbl_intro)
        gap_cutoff_box.addWidget(self.spin_intro_cutoff, 1)
        self.form.addRow("Min Gap & Cutoff:", gap_cutoff_box)
        
        self.layout.addLayout(self.form)
        
        # 7. V3 Specific Features: Clean 2-Row Toggles
        toggles_frame = QFrame()
        toggles_frame.setStyleSheet("QFrame { background: #161620; border: 1px solid #2d2d3c; border-radius: 6px; }")
        t_layout = QVBoxLayout(toggles_frame)
        t_layout.setContentsMargins(10, 6, 10, 6)
        t_layout.setSpacing(4)

        lbl_rules = QLabel("<span style='color: #ff9f43; font-weight: bold; font-size: 11px;'>RHYTHM & PROGRESSION RULES</span>")
        t_layout.addWidget(lbl_rules)

        toggles_layout = QGridLayout()
        toggles_layout.setHorizontalSpacing(14)
        toggles_layout.setVerticalSpacing(4)
        
        self.chk_steady_clean = QCheckBox("Clean steady notes")
        self.chk_steady_clean.setToolTip("Clean steady sections (1-pause-1-pause-1, prevents bursts - Picture 1)")
        self.chk_steady_clean.setChecked(True)
        
        self.chk_anti_overlap = QCheckBox("Anti-overlap rolls")
        self.chk_anti_overlap.setToolTip("Anti-overlap spacing in intense rolls (prevents collisions - Picture 2)")
        self.chk_anti_overlap.setChecked(True)

        self.chk_halve_non_intense = QCheckBox("Halve calm density")
        self.chk_halve_non_intense.setToolTip("Halve beat density in non-intense breakdown sections")
        self.chk_halve_non_intense.setChecked(True)
        
        self.chk_insert_rolls = QCheckBox("Insert roll bursts")
        self.chk_insert_rolls.setToolTip("Insert syncopated flams/bursts on drum/synth rolls")
        self.chk_insert_rolls.setChecked(True)
        
        self.chk_use_zones = QCheckBox("Use Rhythm Zones")
        self.chk_use_zones.setToolTip("Generate beats based on defined Rhythm Zones")
        self.chk_use_zones.setChecked(True)

        self.chk_use_levels = QCheckBox("Use Level chapters")
        self.chk_use_levels.setToolTip("Generate beats based on Level/Difficulty chapters")
        self.chk_use_levels.setChecked(True)

        self.clear_existing = QCheckBox("Clear existing beats")
        self.clear_existing.setToolTip("Clear existing beats on target track before placing new beats")
        self.clear_existing.setChecked(True)

        # Row 1: 4 rhythm rules
        toggles_layout.addWidget(self.chk_steady_clean, 0, 0)
        toggles_layout.addWidget(self.chk_anti_overlap, 0, 1)
        toggles_layout.addWidget(self.chk_halve_non_intense, 0, 2)
        toggles_layout.addWidget(self.chk_insert_rolls, 0, 3)

        # Row 2: 3 zones & level rules
        toggles_layout.addWidget(self.chk_use_zones, 1, 0)
        toggles_layout.addWidget(self.chk_use_levels, 1, 1)
        toggles_layout.addWidget(self.clear_existing, 1, 2)
        
        t_layout.addLayout(toggles_layout)
        self.layout.addWidget(toggles_frame)
        
        # Description box
        self.lbl_desc = QLabel(
            "<span style='color:#a0a0b0; font-size:11px;'>"
            "💡 <b>V3 Engine:</b> Keeps steady 1-pause-1-pause-1 quarter notes, separates colliding rolls into clean doublets, and respects zones/levels."
            "</span>"
        )
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("background: #1c1c24; padding: 6px; border-radius: 4px; border: 1px solid #2d2d3a;")
        self.layout.addWidget(self.lbl_desc)
        
        # Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_video_zones = QPushButton("Open Zones Editor...")
        self.btn_video_zones.setIcon(get_feather_icon("video", "#ffffff", 14))
        self.btn_video_zones.setStyleSheet("""
            QPushButton {
                background: #11998e;
                border: 1px solid #38ef7d;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #13b3a6;
            }
        """)
        self.btn_video_zones.clicked.connect(self.on_open_zones_editor_clicked)
        self.btn_layout.addWidget(self.btn_video_zones)
        
        self.btn_ok = QPushButton("Generate V3 Beats")
        self.btn_ok.setObjectName("generate_btn_v3_dialog")
        self.btn_ok.setStyleSheet("""
            QPushButton#generate_btn_v3_dialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff851b, stop:1 #ff4136);
                border: 1px solid #ffa07a;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton#generate_btn_v3_dialog:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff9933, stop:1 #e03224);
            }
        """)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_cancel)
        self.btn_layout.addWidget(self.btn_ok)
        self.layout.addLayout(self.btn_layout)

    def on_open_zones_editor_clicked(self):
        self.reject()
        parent_win = self.parent()
        if parent_win and hasattr(parent_win, 'open_video_zones_dialog'):
            parent_win.open_video_zones_dialog()

    def on_auto_bpm_toggled(self, checked):
        self.spin_bpm.setEnabled(not checked)

    def on_preset_changed(self, idx):
        preset_key = self.cb_preset.currentData()
        if preset_key == "musical_beatbar":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(0.85)
            self.cb_grid.setCurrentIndex(0)
            self.chk_insert_rolls.setChecked(True)
            self.chk_steady_clean.setChecked(True)
            self.chk_anti_overlap.setChecked(True)
        elif preset_key == "steady_quarters":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.0)
            self.cb_grid.setCurrentIndex(1)
            self.chk_insert_rolls.setChecked(False)
            self.chk_steady_clean.setChecked(True)
        elif preset_key == "energetic_eighths":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.2)
            self.cb_grid.setCurrentIndex(2)
            self.chk_insert_rolls.setChecked(False)
        elif preset_key == "climax_bursts":
            self.cb_lane.setCurrentIndex(0)
            self.spin_density.setValue(1.4)
            self.cb_grid.setCurrentIndex(3)
            self.chk_anti_overlap.setChecked(True)

    def get_level(self):
        txt = self.cb_level.currentText()
        digits = ''.join(filter(str.isdigit, txt))
        return int(digits) if digits else 5

    def get_difficulty(self):
        return self.cb_difficulty.currentData() or self.cb_difficulty.currentText()

    def get_level_mode(self):
        return self.cb_level_mode.currentData() or "ramp_within_level"

    def get_edging_style(self):
        return self.cb_edging_style.currentData() or "rhythmic_tension"



class VideoBeatParserThread(QThread):
    """Runs video ROI color/brightness transition analysis in a background thread."""
    progress = pyqtSignal(int, int, int)  # frame_idx, total_frames, percent
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, video_path, roi_coords, mode="baseline_transition",
                 color_name="purple", base_color=None, hit_color=None,
                 threshold=45.0, min_gap=0.15, target_lane=4, deduplicate=True,
                 lead_offset=0.040):
        super().__init__()
        self.video_path = video_path
        self.roi_coords = roi_coords
        self.mode = mode
        self.color_name = color_name
        self.base_color = base_color
        self.hit_color = hit_color
        self.threshold = threshold
        self.min_gap = min_gap
        self.target_lane = target_lane
        self.deduplicate = deduplicate
        self.lead_offset = lead_offset
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    def run(self):
        try:
            def cb(f_idx, total_f, pct):
                if self._is_canceled:
                    return False
                self.progress.emit(f_idx, total_f, pct)
                return True

            beats = parse_beats_from_video(
                video_path=self.video_path,
                roi_coords=self.roi_coords,
                mode=self.mode,
                color_name=self.color_name,
                base_color=self.base_color,
                hit_color=self.hit_color,
                threshold=self.threshold,
                min_gap=self.min_gap,
                target_lane=self.target_lane,
                deduplicate=self.deduplicate,
                lead_offset=self.lead_offset,
                progress_callback=cb
            )
            if not self._is_canceled:
                self.finished.emit(beats)
        except Exception as e:
            self.error.emit(str(e))


class VideoPreviewWidget(QWidget):
    """
    Interactive video frame viewer with mouse-driven Region of Interest (ROI) selection.
    Maps screen display coordinates to actual video pixel coordinates with aspect-ratio preservation.
    """
    roi_changed = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        
        self.cv_frame = None
        self.q_image = None
        self.video_w = 854
        self.video_h = 480
        
        self.roi = (417, 441, 20, 20)
        self.is_dragging = False
        self.drag_start = (0, 0)
        
        self.scale = 1.0
        self.draw_rect = QRect()

    def set_frame(self, frame):
        if frame is None:
            self.cv_frame = None
            self.q_image = None
            self.update()
            return
            
        self.cv_frame = frame
        self.video_h, self.video_w = frame.shape[:2]
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        self.q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self.update()

    def set_roi(self, rx, ry, rw, rh):
        rx = max(0, min(self.video_w - 1, int(rx)))
        ry = max(0, min(self.video_h - 1, int(ry)))
        rw = max(1, min(self.video_w - rx, int(rw)))
        rh = max(1, min(self.video_h - ry, int(rh)))
        self.roi = (rx, ry, rw, rh)
        self.update()

    def widget_to_video_coords(self, wx, wy):
        if self.scale <= 0 or self.draw_rect.isEmpty():
            return 0, 0
        vx = int((wx - self.draw_rect.x()) / self.scale)
        vy = int((wy - self.draw_rect.y()) / self.scale)
        vx = max(0, min(self.video_w - 1, vx))
        vy = max(0, min(self.video_h - 1, vy))
        return vx, vy

    def video_to_widget_coords(self, vx, vy, vw, vh):
        wx = self.draw_rect.x() + int(vx * self.scale)
        wy = self.draw_rect.y() + int(vy * self.scale)
        ww = max(2, int(vw * self.scale))
        wh = max(2, int(vh * self.scale))
        return QRect(wx, wy, ww, wh)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.cv_frame is not None:
            pos = event.position()
            vx, vy = self.widget_to_video_coords(pos.x(), pos.y())
            self.drag_start = (vx, vy)
            self.is_dragging = True
            self.roi = (vx, vy, 1, 1)
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.cv_frame is not None:
            pos = event.position()
            vx, vy = self.widget_to_video_coords(pos.x(), pos.y())
            rx = min(self.drag_start[0], vx)
            ry = min(self.drag_start[1], vy)
            rw = max(2, abs(self.drag_start[0] - vx))
            rh = max(2, abs(self.drag_start[1] - vy))
            self.roi = (rx, ry, rw, rh)
            self.roi_changed.emit(rx, ry, rw, rh)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            rx, ry, rw, rh = self.roi
            if rw <= 4 and rh <= 4:
                vx, vy = self.drag_start
                rw = 20
                rh = 20
                rx = max(0, min(self.video_w - rw, vx - rw // 2))
                ry = max(0, min(self.video_h - rh, vy - rh // 2))
                self.roi = (rx, ry, rw, rh)
            self.roi_changed.emit(self.roi[0], self.roi[1], self.roi[2], self.roi[3])
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0c0c0e"))
        
        if self.q_image is None:
            painter.setPen(QColor("#777788"))
            painter.setFont(QFont("Arial", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video preview available.\nBrowse to select a video file.")
            return
            
        widget_w = self.width()
        widget_h = self.height()
        self.scale = min(widget_w / max(1, self.video_w), widget_h / max(1, self.video_h))
        draw_w = int(self.video_w * self.scale)
        draw_h = int(self.video_h * self.scale)
        offset_x = (widget_w - draw_w) // 2
        offset_y = (widget_h - draw_h) // 2
        self.draw_rect = QRect(offset_x, offset_y, draw_w, draw_h)
        
        painter.drawImage(self.draw_rect, self.q_image)
        
        rx, ry, rw, rh = self.roi
        roi_rect = self.video_to_widget_coords(rx, ry, rw, rh)
        
        # Semi-transparent cyan fill
        painter.fillRect(roi_rect, QColor(0, 255, 255, 45))
        
        # Glowing cyan border
        pen = QPen(QColor("#00ffff"), 2)
        painter.setPen(pen)
        painter.drawRect(roi_rect)
        
        # Center crosshair
        cx = roi_rect.center().x()
        cy = roi_rect.center().y()
        cross_pen = QPen(QColor(255, 220, 0, 230), 1, Qt.PenStyle.DashLine)
        painter.setPen(cross_pen)
        painter.drawLine(roi_rect.left(), cy, roi_rect.right(), cy)
        painter.drawLine(cx, roi_rect.top(), cx, roi_rect.bottom())
        
        # Pill badge with coordinates
        badge_text = f"ROI: X={rx} Y={ry} ({rw}x{rh})"
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        text_w = max(140, roi_rect.width())
        badge_y = roi_rect.top() - 20 if roi_rect.top() >= 22 else roi_rect.bottom() + 4
        text_rect = QRect(roi_rect.left(), badge_y, text_w, 18)
        painter.fillRect(text_rect, QColor(14, 14, 18, 220))
        painter.setPen(QColor("#00ffff"))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, badge_text)


class VideoBeatParserDialog(QDialog):
    """
    Interactive Dialog for extracting beats directly from video.
    Allows user to pick ROI by dragging on preview, calibrate baseline vs hit color,
    live-test detection sensitivity on scrubbed frames, and parse all beats.
    """
    def __init__(self, video_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visual Beat Parser from Video (Color & Brightness Transition)")
        self.resize(1020, 720)
        self.setMinimumSize(850, 600)
        
        self.video_path = video_path
        self.extracted_beats = []
        self.selected_target_lane = 4
        self.clear_target_lane = True
        
        self.base_color = None  # [B, G, R]
        self.hit_color = None   # [B, G, R]
        self.cap = None
        self.total_frames = 0
        self.fps = 60.0
        self.current_frame = None
        self.thread = None
        
        self.setup_ui()
        
        if self.video_path and os.path.exists(self.video_path):
            self.load_video(self.video_path)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 1. Top video selector bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Target Video:</b>"))
        self.txt_video_path = QLineEdit(self.video_path or "")
        self.txt_video_path.setReadOnly(True)
        top_bar.addWidget(self.txt_video_path)
        
        self.btn_browse = QPushButton("Browse Video...")
        self.btn_browse.clicked.connect(self.on_browse_clicked)
        top_bar.addWidget(self.btn_browse)
        main_layout.addLayout(top_bar)
        
        self.lbl_video_info = QLabel("No video loaded.")
        self.lbl_video_info.setStyleSheet("color: #888899; font-style: italic;")
        main_layout.addWidget(self.lbl_video_info)
        
        # 2. Middle Content Area
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)
        
        # Left side: Video Preview & Scrubber
        left_box = QVBoxLayout()
        left_box.setSpacing(6)
        
        self.preview_widget = VideoPreviewWidget(self)
        self.preview_widget.roi_changed.connect(self.on_roi_from_preview)
        left_box.addWidget(self.preview_widget, stretch=1)
        
        # Scrubber bar
        scrub_layout = QHBoxLayout()
        self.btn_step_back_sec = QPushButton("-1s")
        self.btn_step_back_sec.setIcon(get_feather_icon("rewind", "#ffffff", 14))
        self.btn_step_back_sec.setFixedWidth(52)
        self.btn_step_back_sec.clicked.connect(lambda: self.step_frames(-int(self.fps)))
        scrub_layout.addWidget(self.btn_step_back_sec)
        
        self.btn_step_back_frame = QPushButton("-1f")
        self.btn_step_back_frame.setFixedWidth(36)
        self.btn_step_back_frame.clicked.connect(lambda: self.step_frames(-1))
        scrub_layout.addWidget(self.btn_step_back_frame)
        
        self.slider_frame = QSlider(Qt.Orientation.Horizontal)
        self.slider_frame.setRange(0, 0)
        self.slider_frame.valueChanged.connect(self.seek_frame)
        scrub_layout.addWidget(self.slider_frame)
        
        self.btn_step_fwd_frame = QPushButton("+1f")
        self.btn_step_fwd_frame.setFixedWidth(36)
        self.btn_step_fwd_frame.clicked.connect(lambda: self.step_frames(1))
        scrub_layout.addWidget(self.btn_step_fwd_frame)
        
        self.btn_step_fwd_sec = QPushButton("+1s")
        self.btn_step_fwd_sec.setIcon(get_feather_icon("fast-forward", "#ffffff", 14))
        self.btn_step_fwd_sec.setFixedWidth(52)
        self.btn_step_fwd_sec.clicked.connect(lambda: self.step_frames(int(self.fps)))
        scrub_layout.addWidget(self.btn_step_fwd_sec)
        
        left_box.addLayout(scrub_layout)
        
        self.lbl_frame_info = QLabel("Frame: 0 / 0 | Time: 0:00.000")
        self.lbl_frame_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_frame_info.setStyleSheet("color: #00ffff; font-weight: bold;")
        left_box.addWidget(self.lbl_frame_info)
        
        content_layout.addLayout(left_box, stretch=3)
        
        # Right side: Controls & Calibration Panel
        right_box = QVBoxLayout()
        right_box.setSpacing(10)
        
        # Group 1: ROI
        grp_roi = QGroupBox("Target Region of Interest (ROI)")
        v_roi = QVBoxLayout(grp_roi)
        v_roi.setSpacing(6)
        
        lbl_hint = QLabel("Click & drag box on video preview, or enter coordinates:")
        lbl_hint.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        lbl_hint.setWordWrap(True)
        v_roi.addWidget(lbl_hint)
        
        grid_coords = QGridLayout()
        grid_coords.addWidget(QLabel("X:"), 0, 0)
        self.spin_rx = QSpinBox()
        self.spin_rx.setRange(0, 3840)
        self.spin_rx.setValue(417)
        self.spin_rx.valueChanged.connect(self.on_spinboxes_changed)
        grid_coords.addWidget(self.spin_rx, 0, 1)
        
        grid_coords.addWidget(QLabel("Y:"), 0, 2)
        self.spin_ry = QSpinBox()
        self.spin_ry.setRange(0, 2160)
        self.spin_ry.setValue(441)
        self.spin_ry.valueChanged.connect(self.on_spinboxes_changed)
        grid_coords.addWidget(self.spin_ry, 0, 3)
        
        grid_coords.addWidget(QLabel("W:"), 1, 0)
        self.spin_rw = QSpinBox()
        self.spin_rw.setRange(2, 500)
        self.spin_rw.setValue(20)
        self.spin_rw.valueChanged.connect(self.on_spinboxes_changed)
        grid_coords.addWidget(self.spin_rw, 1, 1)
        
        grid_coords.addWidget(QLabel("H:"), 1, 2)
        self.spin_rh = QSpinBox()
        self.spin_rh.setRange(2, 500)
        self.spin_rh.setValue(20)
        self.spin_rh.valueChanged.connect(self.on_spinboxes_changed)
        grid_coords.addWidget(self.spin_rh, 1, 3)
        v_roi.addLayout(grid_coords)
        
        self.btn_preset_center = QPushButton("Center Beatbar Target Preset")
        self.btn_preset_center.setIcon(get_feather_icon("crosshair", "#00d2ff", 14))
        self.btn_preset_center.clicked.connect(self.center_preset_roi)
        v_roi.addWidget(self.btn_preset_center)
        right_box.addWidget(grp_roi)
        
        # Group 2: Mode & Color Calibration
        grp_mode = QGroupBox("Detection Mode & Color Calibration")
        v_mode = QVBoxLayout(grp_mode)
        v_mode.setSpacing(6)
        
        self.cb_mode = QComboBox()
        self.cb_mode.addItems([
            "Baseline Transition (Distance from Empty)",
            "2-Point Vector Projection (Empty -> Hit)",
            "Preset: Purple Note Detection",
            "Preset: Red Note Detection",
            "Preset: Blue Note Detection",
            "Preset: Green Note Detection",
            "Preset: Brightness / Flash"
        ])
        self.cb_mode.currentIndexChanged.connect(self.on_mode_changed)
        v_mode.addWidget(self.cb_mode)
        
        # Baseline Color
        row_base = QHBoxLayout()
        self.btn_sample_base = QPushButton("Sample Baseline (Empty)")
        self.btn_sample_base.clicked.connect(self.sample_baseline_color)
        row_base.addWidget(self.btn_sample_base)
        
        self.lbl_base_swatch = QLabel()
        self.lbl_base_swatch.setFixedSize(28, 22)
        self.lbl_base_swatch.setStyleSheet("background: #606060; border: 1px solid #999; border-radius: 3px;")
        row_base.addWidget(self.lbl_base_swatch)
        
        self.lbl_base_text = QLabel("RGB: Default")
        self.lbl_base_text.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        row_base.addWidget(self.lbl_base_text)
        v_mode.addLayout(row_base)
        
        # Hit Color
        row_hit = QHBoxLayout()
        self.btn_sample_hit = QPushButton("Sample Hit Color (Active)")
        self.btn_sample_hit.clicked.connect(self.sample_hit_color)
        row_hit.addWidget(self.btn_sample_hit)
        
        self.lbl_hit_swatch = QLabel()
        self.lbl_hit_swatch.setFixedSize(28, 22)
        self.lbl_hit_swatch.setStyleSheet("background: #8a2be2; border: 1px solid #999; border-radius: 3px;")
        row_hit.addWidget(self.lbl_hit_swatch)
        
        self.lbl_hit_text = QLabel("RGB: Default")
        self.lbl_hit_text.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        row_hit.addWidget(self.lbl_hit_text)
        v_mode.addLayout(row_hit)
        right_box.addWidget(grp_mode)
        
        # Group 3: Live Verification & Trigger Threshold
        grp_verify = QGroupBox("Live Verification & Trigger Threshold")
        v_verify = QVBoxLayout(grp_verify)
        v_verify.setSpacing(6)
        
        status_row = QHBoxLayout()
        self.lbl_metric_info = QLabel("Metric at Frame: 0.0")
        self.lbl_metric_info.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffffff;")
        status_row.addWidget(self.lbl_metric_info)
        
        self.lbl_hit_status = QLabel("○ NO HIT")
        self.lbl_hit_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hit_status.setFixedWidth(130)
        self.lbl_hit_status.setStyleSheet("background: #25252e; color: #888899; font-weight: bold; border-radius: 4px; padding: 4px;")
        status_row.addWidget(self.lbl_hit_status)
        v_verify.addLayout(status_row)
        
        row_th = QHBoxLayout()
        row_th.addWidget(QLabel("Threshold:"))
        self.slider_th = QSlider(Qt.Orientation.Horizontal)
        self.slider_th.setRange(1, 300)
        self.slider_th.setValue(50)
        self.slider_th.valueChanged.connect(lambda v: self.spin_th.setValue(float(v)))
        row_th.addWidget(self.slider_th)
        
        self.spin_th = QDoubleSpinBox()
        self.spin_th.setRange(0.5, 500.0)
        self.spin_th.setValue(50.0)
        self.spin_th.setSingleStep(2.0)
        self.spin_th.valueChanged.connect(lambda v: (self.slider_th.setValue(int(v)), self.update_live_metric()))
        row_th.addWidget(self.spin_th)
        v_verify.addLayout(row_th)
        
        row_gap = QHBoxLayout()
        row_gap.addWidget(QLabel("Min Gap (sec):"))
        self.spin_min_gap = QDoubleSpinBox()
        self.spin_min_gap.setRange(0.02, 1.00)
        self.spin_min_gap.setValue(0.15)
        self.spin_min_gap.setSingleStep(0.01)
        row_gap.addWidget(self.spin_min_gap)
        v_verify.addLayout(row_gap)

        row_lead = QHBoxLayout()
        row_lead.addWidget(QLabel("Lead Offset (ms):"))
        self.spin_lead = QSpinBox()
        self.spin_lead.setRange(-200, 200)
        self.spin_lead.setValue(40)
        self.spin_lead.setSingleStep(5)
        self.spin_lead.setSuffix(" ms")
        self.spin_lead.setToolTip("Lead timing compensation (default 40ms) shifts detected beat times forward to eliminate visual contact latency.")
        row_lead.addWidget(self.spin_lead)
        v_verify.addLayout(row_lead)
        
        self.chk_dedup = QCheckBox("Deduplicate adjacent hits (prevent double-triggers)")
        self.chk_dedup.setChecked(True)
        self.chk_dedup.setToolTip("Eliminates duplicate or overlapping notes when a note icon passes through the target area.")
        v_verify.addWidget(self.chk_dedup)
        right_box.addWidget(grp_verify)
        
        # Group 4: Target Track / Destination
        grp_dest = QGroupBox("Target Track & Output")
        v_dest = QVBoxLayout(grp_dest)
        v_dest.setSpacing(6)
        
        row_lane = QHBoxLayout()
        row_lane.addWidget(QLabel("Target Track:"))
        self.cb_target_lane = QComboBox()
        self.cb_target_lane.addItem("Lane 4: Beats (Purple)", 4)
        self.cb_target_lane.addItem("Lane 0: Bass (Red)", 0)
        self.cb_target_lane.addItem("Lane 1: Low-Mid (Green)", 1)
        self.cb_target_lane.addItem("Lane 2: High-Mid (Blue)", 2)
        self.cb_target_lane.addItem("Lane 3: Treble (Yellow)", 3)
        row_lane.addWidget(self.cb_target_lane)
        v_dest.addLayout(row_lane)
        
        self.chk_clear_lane = QCheckBox("Clear existing beats on target track first")
        self.chk_clear_lane.setChecked(True)
        v_dest.addWidget(self.chk_clear_lane)
        right_box.addWidget(grp_dest)
        
        right_box.addStretch()
        content_layout.addLayout(right_box, stretch=2)
        main_layout.addLayout(content_layout)
        
        # 3. Bottom Progress Bar & Action Buttons
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(6)
        
        self.lbl_progress_status = QLabel("")
        self.lbl_progress_status.setStyleSheet("color: #00ffff; font-weight: bold;")
        self.lbl_progress_status.hide()
        bottom_layout.addWidget(self.lbl_progress_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                text-align: center;
                background-color: #1a1a1f;
                color: white;
                height: 18px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b4db, stop:1 #0083b0);
                border-radius: 3px;
            }
        """)
        self.progress_bar.hide()
        bottom_layout.addWidget(self.progress_bar)
        
        btn_action_row = QHBoxLayout()
        self.btn_extract = QPushButton("EXTRACT ALL BEATS FROM VIDEO")
        self.btn_extract.setIcon(get_feather_icon("zap", "#ffffff", 14))
        self.btn_extract.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b4db, stop:1 #0083b0);
                border: 1px solid #00d2ff;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00c6ff, stop:1 #0072ff);
                border-color: #80dfff;
            }
            QPushButton:pressed {
                background: #005c8a;
            }
            QPushButton:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
                color: #666677;
            }
        """)
        self.btn_extract.clicked.connect(self.start_extraction)
        btn_action_row.addWidget(self.btn_extract)
        
        self.btn_dialog_cancel = QPushButton("Cancel / Close")
        self.btn_dialog_cancel.clicked.connect(self.on_cancel_clicked)
        btn_action_row.addWidget(self.btn_dialog_cancel)
        bottom_layout.addLayout(btn_action_row)
        
        main_layout.addLayout(bottom_layout)

    def on_browse_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.m4v);;All Files (*)"
        )
        if path:
            self.load_video(path)

    def load_video(self, path):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            
        self.video_path = path
        self.txt_video_path.setText(path)
        
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "Error", f"Could not open video file:\n{path}")
            return
            
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 60.0
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        dur_sec = self.total_frames / max(1.0, self.fps)
        mins = int(dur_sec // 60)
        secs = dur_sec % 60
        self.lbl_video_info.setText(
            f"{os.path.basename(path)} | Resolution: {w}x{h} | FPS: {self.fps:.2f} | Duration: {mins:02d}:{secs:05.2f} ({self.total_frames} frames)"
        )
        
        self.slider_frame.setRange(0, max(0, self.total_frames - 1))
        
        # Preset ROI default to bottom center hit line
        rw = 20
        rh = 20
        rx = max(0, int(w * 0.5 - rw / 2))
        ry = max(0, int(h * 0.94 - rh / 2))
        
        self.spin_rx.setRange(0, max(1, w - 1))
        self.spin_ry.setRange(0, max(1, h - 1))
        self.spin_rw.setRange(2, max(2, w))
        self.spin_rh.setRange(2, max(2, h))
        
        self.spin_rx.setValue(rx)
        self.spin_ry.setValue(ry)
        self.spin_rw.setValue(rw)
        self.spin_rh.setValue(rh)
        self.preview_widget.set_roi(rx, ry, rw, rh)
        
        init_frame = min(int(self.fps), max(0, self.total_frames - 1))
        self.slider_frame.setValue(init_frame)
        self.seek_frame(init_frame)

    def seek_frame(self, frame_idx):
        if self.cap is None or not self.cap.isOpened():
            return
            
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        if ret:
            self.current_frame = frame
            self.preview_widget.set_frame(frame)
            
            time_sec = frame_idx / max(1.0, self.fps)
            mins = int(time_sec // 60)
            secs = time_sec % 60
            self.lbl_frame_info.setText(f"Frame: {frame_idx} / {self.total_frames} | Time: {mins:02d}:{secs:06.3f}")
            self.update_live_metric()

    def step_frames(self, delta):
        if self.cap is None:
            return
        curr = self.slider_frame.value()
        new_f = max(0, min(self.total_frames - 1, curr + delta))
        self.slider_frame.setValue(new_f)

    def on_roi_from_preview(self, rx, ry, rw, rh):
        self.spin_rx.blockSignals(True)
        self.spin_ry.blockSignals(True)
        self.spin_rw.blockSignals(True)
        self.spin_rh.blockSignals(True)
        self.spin_rx.setValue(rx)
        self.spin_ry.setValue(ry)
        self.spin_rw.setValue(rw)
        self.spin_rh.setValue(rh)
        self.spin_rx.blockSignals(False)
        self.spin_ry.blockSignals(False)
        self.spin_rw.blockSignals(False)
        self.spin_rh.blockSignals(False)
        self.update_live_metric()

    def on_spinboxes_changed(self):
        rx = self.spin_rx.value()
        ry = self.spin_ry.value()
        rw = self.spin_rw.value()
        rh = self.spin_rh.value()
        self.preview_widget.set_roi(rx, ry, rw, rh)
        self.update_live_metric()

    def center_preset_roi(self):
        if self.preview_widget.video_w <= 0:
            return
        w = self.preview_widget.video_w
        h = self.preview_widget.video_h
        rw = 20
        rh = 20
        rx = max(0, int(w * 0.5 - rw / 2))
        ry = max(0, int(h * 0.94 - rh / 2))
        self.spin_rx.setValue(rx)
        self.spin_ry.setValue(ry)
        self.spin_rw.setValue(rw)
        self.spin_rh.setValue(rh)
        self.preview_widget.set_roi(rx, ry, rw, rh)
        self.update_live_metric()

    def sample_baseline_color(self):
        if self.current_frame is None:
            return
        rx = self.spin_rx.value()
        ry = self.spin_ry.value()
        rw = self.spin_rw.value()
        rh = self.spin_rh.value()
        roi_crop = self.current_frame[ry:ry+rh, rx:rx+rw]
        if roi_crop.size == 0:
            return
        mean_bgr = np.mean(roi_crop, axis=(0, 1))
        self.base_color = [float(mean_bgr[0]), float(mean_bgr[1]), float(mean_bgr[2])]
        r, g, b = int(round(mean_bgr[2])), int(round(mean_bgr[1])), int(round(mean_bgr[0]))
        self.lbl_base_swatch.setStyleSheet(f"background: rgb({r},{g},{b}); border: 2px solid white; border-radius: 3px;")
        self.lbl_base_text.setText(f"RGB: ({r}, {g}, {b})")
        self.update_live_metric()

    def sample_hit_color(self):
        if self.current_frame is None:
            return
        rx = self.spin_rx.value()
        ry = self.spin_ry.value()
        rw = self.spin_rw.value()
        rh = self.spin_rh.value()
        roi_crop = self.current_frame[ry:ry+rh, rx:rx+rw]
        if roi_crop.size == 0:
            return
        mean_bgr = np.mean(roi_crop, axis=(0, 1))
        self.hit_color = [float(mean_bgr[0]), float(mean_bgr[1]), float(mean_bgr[2])]
        r, g, b = int(round(mean_bgr[2])), int(round(mean_bgr[1])), int(round(mean_bgr[0]))
        self.lbl_hit_swatch.setStyleSheet(f"background: rgb({r},{g},{b}); border: 2px solid white; border-radius: 3px;")
        self.lbl_hit_text.setText(f"RGB: ({r}, {g}, {b})")
        self.update_live_metric()

    def on_mode_changed(self):
        self.update_live_metric()

    def compute_metric_for_roi(self, roi):
        if roi is None or roi.size == 0:
            return 0.0
            
        mode_idx = self.cb_mode.currentIndex()
        if mode_idx == 0:  # baseline_transition
            c0 = np.array(self.base_color if self.base_color is not None else [100.0, 100.0, 100.0], dtype=float)
            mean_col = np.mean(roi, axis=(0, 1))
            return float(np.linalg.norm(mean_col - c0))
            
        elif mode_idx == 1:  # projection
            if self.base_color is None or self.hit_color is None:
                c0 = np.array(self.base_color if self.base_color is not None else [100.0, 100.0, 100.0], dtype=float)
                mean_col = np.mean(roi, axis=(0, 1))
                return float(np.linalg.norm(mean_col - c0))
            c0 = np.array(self.base_color, dtype=float)
            c1 = np.array(self.hit_color, dtype=float)
            diff_vec = c1 - c0
            norm_sq = float(np.sum(diff_vec ** 2)) or 1.0
            mean_col = np.mean(roi, axis=(0, 1))
            return float(np.dot(mean_col - c0, diff_vec) / norm_sq) * 100.0
            
        elif mode_idx == 2:  # purple
            b = float(np.mean(roi[:, :, 0]))
            g = float(np.mean(roi[:, :, 1]))
            r = float(np.mean(roi[:, :, 2]))
            return max(0.0, (r + b) - 2.0 * g)
            
        elif mode_idx == 3:  # red
            b = float(np.mean(roi[:, :, 0]))
            g = float(np.mean(roi[:, :, 1]))
            r = float(np.mean(roi[:, :, 2]))
            return max(0.0, r * 2.0 - (g + b))
            
        elif mode_idx == 4:  # blue
            b = float(np.mean(roi[:, :, 0]))
            g = float(np.mean(roi[:, :, 1]))
            r = float(np.mean(roi[:, :, 2]))
            return max(0.0, b * 2.0 - (r + g))
            
        elif mode_idx == 5:  # green
            b = float(np.mean(roi[:, :, 0]))
            g = float(np.mean(roi[:, :, 1]))
            r = float(np.mean(roi[:, :, 2]))
            return max(0.0, g * 2.0 - (r + b))
            
        elif mode_idx == 6:  # brightness
            return float(np.mean(roi))
            
        return 0.0

    def update_live_metric(self):
        if self.current_frame is None:
            return
        rx = self.spin_rx.value()
        ry = self.spin_ry.value()
        rw = self.spin_rw.value()
        rh = self.spin_rh.value()
        roi_crop = self.current_frame[ry:ry+rh, rx:rx+rw]
        if roi_crop.size == 0:
            return
            
        val = self.compute_metric_for_roi(roi_crop)
        th = self.spin_th.value()
        is_hit = val >= th
        
        self.lbl_metric_info.setText(f"Metric at Frame: {val:.1f}  (Th: {th:.1f})")
        if is_hit:
            self.lbl_hit_status.setText("● HIT DETECTED!")
            self.lbl_hit_status.setStyleSheet("background: #2ECC40; color: #0c0c0e; font-weight: bold; border-radius: 4px; padding: 4px;")
        else:
            self.lbl_hit_status.setText("○ NO HIT")
            self.lbl_hit_status.setStyleSheet("background: #25252e; color: #888899; font-weight: bold; border-radius: 4px; padding: 4px;")

    def start_extraction(self):
        if not self.video_path or not os.path.exists(self.video_path):
            QMessageBox.warning(self, "No Video", "Please select a valid video file first.")
            return
            
        mode_map = [
            ("baseline_transition", "custom"),
            ("projection", "custom"),
            ("color_preset", "purple"),
            ("color_preset", "red"),
            ("color_preset", "blue"),
            ("color_preset", "green"),
            ("brightness", "white"),
        ]
        mode, color_name = mode_map[self.cb_mode.currentIndex()]
        
        rx = self.spin_rx.value()
        ry = self.spin_ry.value()
        rw = self.spin_rw.value()
        rh = self.spin_rh.value()
        roi_coords = (rx, ry, rw, rh)
        
        th = self.spin_th.value()
        min_gap = self.spin_min_gap.value()
        target_lane = self.cb_target_lane.currentData()
        deduplicate = self.chk_dedup.isChecked()
        lead_offset = self.spin_lead.value() / 1000.0
        
        self.btn_extract.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.slider_frame.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_progress_status.show()
        self.lbl_progress_status.setText("Starting video scan...")
        self.btn_dialog_cancel.setText("Cancel Scan")
        
        self.thread = VideoBeatParserThread(
            video_path=self.video_path,
            roi_coords=roi_coords,
            mode=mode,
            color_name=color_name,
            base_color=self.base_color,
            hit_color=self.hit_color,
            threshold=th,
            min_gap=min_gap,
            target_lane=target_lane,
            deduplicate=deduplicate,
            lead_offset=lead_offset
        )
        self.thread.progress.connect(self.on_thread_progress)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.error.connect(self.on_thread_error)
        self.thread.start()

    def on_thread_progress(self, f_idx, total_f, pct):
        self.progress_bar.setValue(pct)
        self.lbl_progress_status.setText(f"Processing frame {f_idx} / {total_f} ({pct}%)...")

    def on_thread_finished(self, beats):
        self.extracted_beats = beats
        self.selected_target_lane = self.cb_target_lane.currentData()
        self.clear_target_lane = self.chk_clear_lane.isChecked()
        self.cleanup_resources()
        self.accept()

    def on_thread_error(self, err_msg):
        self.reset_ui_after_thread()
        QMessageBox.critical(self, "Extraction Error", f"An error occurred while parsing video:\n{err_msg}")

    def reset_ui_after_thread(self):
        self.btn_extract.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.slider_frame.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_progress_status.hide()
        self.btn_dialog_cancel.setText("Cancel / Close")

    def on_cancel_clicked(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(600)
            self.reset_ui_after_thread()
            self.lbl_progress_status.setText("Canceled by user.")
        else:
            self.cleanup_resources()
            self.reject()

    def cleanup_resources(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(600)
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def closeEvent(self, event):
        self.cleanup_resources()
        event.accept()


class BeatbarSettingsDialog(QDialog):
    """Unified application settings dialog: keybindings, auto-difficulty parameters, and playback defaults."""
    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(480, 440)
        import copy
        self.app_config = copy.deepcopy(app_config)
        self.keybinds = self.app_config.get('keybinds', DEFAULT_KEYBINDS.copy())
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        header = QLabel(
            "<h3 style='margin:0; color:#00d2ff;'>Application Settings</h3>"
            "<span style='color:#a0a0b0; font-size:11px;'>Configure hotkeys, auto-difficulty burst detection, and playback defaults.</span>"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)
        
        # 1. Keybindings
        grp_keys = QGroupBox("Keybindings")
        form_keys = QFormLayout(grp_keys)
        form_keys.setSpacing(8)
        
        self.txt_beat_key = QLineEdit(self.keybinds.get('lane_4', '5'))
        self.txt_beat_key.setMaxLength(1)
        self.txt_beat_key.setToolTip("Key pressed during playback or editing to add a beat note at current playhead.")
        form_keys.addRow("Add Beat Key:", self.txt_beat_key)
        
        self.txt_beat_key_alt = QLineEdit(self.keybinds.get('lane_0', '1'))
        self.txt_beat_key_alt.setMaxLength(1)
        self.txt_beat_key_alt.setToolTip("Secondary shortcut key to add a beat note at current playhead.")
        form_keys.addRow("Add Beat (Alternate):", self.txt_beat_key_alt)
        
        self.txt_halve_key = QLineEdit(self.keybinds.get('halve', 'H'))
        self.txt_halve_key.setMaxLength(1)
        self.txt_halve_key.setToolTip("Key to thin out / halve selected notes.")
        form_keys.addRow("Halve Selected Key:", self.txt_halve_key)
        
        layout.addWidget(grp_keys)
        
        # 2. Auto-Difficulty & Rhythm Analysis
        grp_diff = QGroupBox("Auto-Difficulty & Burst Groups Analysis")
        form_diff = QFormLayout(grp_diff)
        form_diff.setSpacing(8)
        
        self.spin_close_gap = QDoubleSpinBox()
        self.spin_close_gap.setRange(0.10, 1.00)
        self.spin_close_gap.setSingleStep(0.05)
        self.spin_close_gap.setValue(float(self.app_config.get('close_gap_threshold', 0.35)))
        self.spin_close_gap.setSuffix(" s")
        self.spin_close_gap.setToolTip("Close notes spacing threshold (e.g. 0.35s detects groups of fast 1/8 and 1/16 burst notes).")
        form_diff.addRow("Close Note Gap Threshold:", self.spin_close_gap)
        
        self.spin_min_group = QSpinBox()
        self.spin_min_group.setRange(2, 10)
        self.spin_min_group.setValue(int(self.app_config.get('min_group_size', 3)))
        self.spin_min_group.setToolTip("Minimum consecutive close notes required to form a burst group (e.g. 3).")
        form_diff.addRow("Min Burst Group Size:", self.spin_min_group)
        
        self.chk_auto_recalc = QCheckBox("Auto-recalculate difficulty when beats change")
        self.chk_auto_recalc.setChecked(bool(self.app_config.get('auto_recalc_diff', True)))
        form_diff.addRow(self.chk_auto_recalc)
        
        layout.addWidget(grp_diff)
        
        # 3. Playback & Visuals
        grp_play = QGroupBox("Playback & Visuals")
        form_play = QFormLayout(grp_play)
        form_play.setSpacing(8)
        
        self.spin_vol = QSpinBox()
        self.spin_vol.setRange(0, 100)
        self.spin_vol.setValue(int(self.app_config.get('volume', 80)))
        self.spin_vol.setSuffix(" %")
        form_play.addRow("Default Volume:", self.spin_vol)
        
        self.chk_shake = QCheckBox("Enable screen shake on heavy beats in viewer")
        self.chk_shake.setChecked(bool(self.app_config.get('screen_shake', True)))
        form_play.addRow(self.chk_shake)
        
        layout.addWidget(grp_play)

        # 4. User Profile & Export Defaults
        grp_user = QGroupBox("User Profile & Export Defaults")
        form_user = QFormLayout(grp_user)
        form_user.setSpacing(8)
        self.txt_author = QLineEdit(self.app_config.get('default_author', 'User'))
        self.txt_author.setToolTip("Default author name embedded into .beat packs and beatmaps.")
        form_user.addRow("Default Username / Author:", self.txt_author)
        layout.addWidget(grp_user)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_reset = QPushButton("Reset Defaults")
        btn_reset.clicked.connect(self.reset_defaults)
        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_save = QPushButton("Save Settings")
        btn_save.setObjectName("generate_btn")
        btn_save.setStyleSheet("""
            QPushButton#generate_btn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00d2ff, stop:1 #0083b0);
                border: 1px solid #00d2ff;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton#generate_btn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #38ef7d, stop:1 #11998e);
                border-color: #38ef7d;
            }
        """)
        btn_save.clicked.connect(self.save_and_accept)
        btn_layout.addWidget(btn_save)
        
        layout.addLayout(btn_layout)

    def reset_defaults(self):
        self.txt_beat_key.setText('5')
        self.txt_beat_key_alt.setText('1')
        self.txt_halve_key.setText('H')
        self.spin_close_gap.setValue(0.35)
        self.spin_min_group.setValue(3)
        self.chk_auto_recalc.setChecked(True)
        self.spin_vol.setValue(80)
        self.chk_shake.setChecked(True)
        self.txt_author.setText('User')

    def save_and_accept(self):
        k_beat = self.txt_beat_key.text().strip().upper() or '5'
        k_alt = self.txt_beat_key_alt.text().strip().upper() or '1'
        k_halve = self.txt_halve_key.text().strip().upper() or 'H'
        
        self.keybinds['lane_4'] = k_beat
        self.keybinds['lane_0'] = k_alt
        self.keybinds['halve'] = k_halve
        self.app_config['keybinds'] = self.keybinds
        
        self.app_config['close_gap_threshold'] = self.spin_close_gap.value()
        self.app_config['min_group_size'] = self.spin_min_group.value()
        self.app_config['auto_recalc_diff'] = self.chk_auto_recalc.isChecked()
        self.app_config['volume'] = self.spin_vol.value()
        self.app_config['screen_shake'] = self.chk_shake.isChecked()
        self.app_config['default_author'] = self.txt_author.text().strip() or 'User'
        
        self.accept()


class ClickableSlider(QSlider):
    """QSlider that seeks immediately to the exact mouse click position anywhere along the slider bar."""
    seek_requested = pyqtSignal(float)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / float(max(1, self.width()))
            val = max(self.minimum(), min(self.maximum(), int(val)))
            self.setValue(val)
            self.seek_requested.emit(val / float(self.maximum()))
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / float(max(1, self.width()))
            val = max(self.minimum(), min(self.maximum(), int(val)))
            self.setValue(val)
            self.seek_requested.emit(val / float(self.maximum()))
            event.accept()
class ClearBeatsDialog(QDialog):
    """Dialog allowing user to choose which specific track to clear beats from, or clear all."""
    def __init__(self, parent=None, beats=None, tracks=None, visible_track_count=1):
        super().__init__(parent)
        self.setWindowTitle("Clear Beats")
        self.setFixedWidth(380)
        self.setStyleSheet("""
            QDialog {
                background-color: #121217;
                color: #e0e0e8;
            }
            QLabel {
                color: #e0e0e8;
            }
            QRadioButton {
                color: #e0e0e8;
                font-size: 12px;
                padding: 4px;
            }
            QRadioButton:hover {
                color: #ffffff;
            }
            QPushButton {
                padding: 7px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QLabel(
            "<h3 style='margin:0 0 4px 0; color:#ff6b62;'>Clear Beats</h3>"
            "<span style='color:#a0a0b0; font-size:12px;'>"
            "Select which track to clear beats from:</span>"
        )
        layout.addWidget(header)

        from collections import Counter
        track_counts = Counter()
        beats = beats or []
        for b in beats:
            lane = b.get('lane', 4)
            if lane in (4, 0):
                track_counts[0] += 1
            elif lane == 1:
                track_counts[1] += 1
            elif lane in (2, 3):
                track_counts[2] += 1

        self.btn_group = QButtonGroup(self)

        total_cnt = len(beats)
        self.rb_all = QRadioButton(f"All Tracks ({total_cnt} beats total)")
        self.rb_all.setChecked(True)
        self.btn_group.addButton(self.rb_all, -1)
        layout.addWidget(self.rb_all)

        tracks = tracks or []
        for i in range(max(1, visible_track_count)):
            tr_name = tracks[i]['name'] if i < len(tracks) else f"TRACK {i+1}"
            cnt = track_counts.get(i, 0)
            rb = QRadioButton(f"{tr_name} only ({cnt} beats)")
            self.btn_group.addButton(rb, i)
            layout.addWidget(rb)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background: #2b2b35; border: 1px solid #3b3b4a; color: #cccccc;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_clear = QPushButton("Clear Beats")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                border: 1px solid #e74c3c;
                color: white;
            }
            QPushButton:hover {
                background: #e74c3c;
            }
        """)
        self.btn_clear.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_clear)

        layout.addLayout(btn_box)

    @property
    def selected_track(self):
        """Returns -1 for all tracks, or 0, 1, 2 for specific track index."""
        return self.btn_group.checkedId()


class LoadBeatOptionsDialog(QDialog):
    """Dialog allowing user to choose how to import beats into a multi-track timeline."""
    def __init__(self, parent=None, beat_count=0, current_tracks=1):
        super().__init__(parent)
        self.setWindowTitle("Import Beats - Multi-Track Option")
        self.setFixedWidth(460)
        self.choice = "replace"
        
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        
        header = QLabel(
            f"<h3 style='margin:0 0 6px 0; color:#00E5FF;'>Load Beats File</h3>"
            f"<span style='color:#ccc; font-size:12px;'>"
            f"The project already contains active beats.<br>"
            f"Found <b>{beat_count}</b> beats in the selected file.<br>"
            f"Select how you want to import this beatmap:</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)
        
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)
        
        # 1. Replace all tracks
        self.btn_replace = QPushButton("Replace All Tracks (Standard)")
        self.btn_replace.setStyleSheet("""
            QPushButton {
                background: #c0392b; color: white; font-weight: bold;
                padding: 10px; border-radius: 4px; text-align: left; padding-left: 14px;
            }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.btn_replace.clicked.connect(lambda: self._choose("replace"))
        btn_box.addWidget(self.btn_replace)
        
        # 2. Load to Track 2 (Lane 1, Cyan)
        self.btn_track2 = QPushButton("Load onto Track 2 (Cyan Lane)")
        self.btn_track2.setStyleSheet("""
            QPushButton {
                background: #00838f; color: white; font-weight: bold;
                padding: 10px; border-radius: 4px; text-align: left; padding-left: 14px;
            }
            QPushButton:hover { background: #00acc1; }
        """)
        self.btn_track2.clicked.connect(lambda: self._choose("track2"))
        btn_box.addWidget(self.btn_track2)
        
        # 3. Load to Track 3 (Lane 2, Amber)
        self.btn_track3 = QPushButton("Load onto Track 3 (Amber Lane)")
        self.btn_track3.setStyleSheet("""
            QPushButton {
                background: #f57f17; color: white; font-weight: bold;
                padding: 10px; border-radius: 4px; text-align: left; padding-left: 14px;
            }
            QPushButton:hover { background: #fbc02d; }
        """)
        self.btn_track3.clicked.connect(lambda: self._choose("track3"))
        btn_box.addWidget(self.btn_track3)
        
        # 4. Merge onto Matching Tracks
        self.btn_merge = QPushButton("Merge onto Existing Tracks")
        self.btn_merge.setStyleSheet("""
            QPushButton {
                background: #2e7d32; color: white; font-weight: bold;
                padding: 10px; border-radius: 4px; text-align: left; padding-left: 14px;
            }
            QPushButton:hover { background: #388e3c; }
        """)
        self.btn_merge.clicked.connect(lambda: self._choose("merge"))
        btn_box.addWidget(self.btn_merge)
        
        layout.addLayout(btn_box)
        
        # Cancel button
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("padding: 6px 16px;")
        btn_cancel.clicked.connect(self.reject)
        cancel_layout.addWidget(btn_cancel)
        layout.addLayout(cancel_layout)
        
    def _choose(self, choice):
        self.choice = choice
        self.accept()
class PlaceLevelDialog(QDialog):
    """Dialog to create, edit, or place a Level & Difficulty chapter on the timeline."""
    def __init__(self, parent=None, chapter=None, current_time=0.0, duration=60.0):
        super().__init__(parent)
        self.setWindowTitle("Place Level & Difficulty Chapter")
        self.setFixedWidth(440)
        self.duration = max(1.0, float(duration))
        self.chapter = chapter or {}
        self.is_new = (chapter is None or not chapter)
        self.deleted = False
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        header = QLabel(
            "<h3 style='margin:0 0 4px 0; color:#c084fc;'>Place Level & Difficulty Chapter</h3>"
            "<span style='color:#a0a0b0; font-size:11px;'>"
            "Place named levels and difficulty segments on the video timeline (like YouTube chapters)."
            "</span>"
        )
        layout.addWidget(header)
        
        form = QFormLayout()
        form.setSpacing(10)
        
        # 1. Level Name (Editable with presets)
        self.cb_name = QComboBox()
        self.cb_name.setEditable(True)
        self.cb_name.addItems([
            "Level 1 - D.va", "Level 2 - Widow", "Level 3 - Mercy", "Level 4 - Tracer",
            "Level 1", "Level 2", "Level 3", "Level 4", "Level 5",
            "Level 6", "Level 7", "Level 8", "Level 9", "Level 10"
        ])
        init_name = self.chapter.get('name', "Level 1 - D.va" if current_time < self.duration * 0.4 else "Level 2 - Widow")
        self.cb_name.setCurrentText(init_name)
        form.addRow("Level Name:", self.cb_name)
        
        # 2. Difficulty (Expert and Master commented out to prevent beat spam)
        self.cb_difficulty = QComboBox()
        self.cb_difficulty.addItems(["Easy", "Normal", "Hard"])
        # self.cb_difficulty.addItems(["Easy", "Normal", "Hard", "Expert", "Master"])
        init_diff = self.chapter.get('difficulty', 'Normal')
        idx = self.cb_difficulty.findText(init_diff)
        if idx >= 0:
            self.cb_difficulty.setCurrentIndex(idx)
        form.addRow("Difficulty:", self.cb_difficulty)
        
        # 3. Start & End Times
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, self.duration)
        self.spin_start.setSingleStep(0.5)
        self.spin_start.setSuffix(" s")
        init_start = self.chapter.get('start_time', round(current_time, 2))
        self.spin_start.setValue(init_start)
        form.addRow("Start Time:", self.spin_start)
        
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.0, self.duration)
        self.spin_end.setSingleStep(0.5)
        self.spin_end.setSuffix(" s")
        init_end = self.chapter.get('end_time', round(min(self.duration, init_start + max(15.0, self.duration * 0.3)), 2))
        self.spin_end.setValue(init_end)
        form.addRow("End Time:", self.spin_end)
        
        layout.addLayout(form)
        
        # Buttons
        btn_box = QHBoxLayout()
        if not self.is_new:
            self.btn_delete = QPushButton("Delete Chapter")
            self.btn_delete.setStyleSheet("background: #c0392b; color: white; padding: 6px 12px; border-radius: 4px;")
            self.btn_delete.clicked.connect(self._on_delete)
            btn_box.addWidget(self.btn_delete)
        
        btn_box.addStretch()
        
        self.btn_open_zones = QPushButton("Zones & Levels Editor...")
        self.btn_open_zones.setIcon(get_feather_icon("video", "#38ef7d", 14))
        self.btn_open_zones.setToolTip("Open full visual timeline editor (Zones tab) to place, drag, and resize levels interactively.")
        self.btn_open_zones.setStyleSheet("""
            QPushButton {
                background: #0f172a;
                border: 1px solid #38ef7d;
                color: #38ef7d;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #134e4a;
                color: #ffffff;
            }
        """)
        self.btn_open_zones.clicked.connect(self._on_open_zones)
        btn_box.addWidget(self.btn_open_zones)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Save Chapter" if not self.is_new else "+ Place on Timeline")
        self.btn_save.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #6366f1); color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)
        
        layout.addLayout(btn_box)
        
    def _on_open_zones(self):
        self.reject()
        parent_win = self.parent()
        while parent_win and not hasattr(parent_win, 'open_video_zones_dialog'):
            parent_win = parent_win.parent()
        if parent_win and hasattr(parent_win, 'open_video_zones_dialog'):
            parent_win.open_video_zones_dialog()

    def _on_delete(self):
        self.deleted = True
        self.accept()
        
    def get_data(self):
        name = self.cb_name.currentText().strip() or "Level 1"
        digits = ''.join(filter(str.isdigit, name))
        lvl_num = int(digits) if digits else 1
        return {
            'id': self.chapter.get('id', str(uuid.uuid4())[:8]),
            'name': name,
            'level': lvl_num,
            'difficulty': self.cb_difficulty.currentText(),
            'start_time': round(self.spin_start.value(), 3),
            'end_time': round(max(self.spin_start.value() + 0.5, self.spin_end.value()), 3)
        }


class TimelineScrollArea(QScrollArea):
    """QScrollArea that forces full-viewport repainting on scroll to eliminate bit-blit ghosting artifacts."""
    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if self.widget():
            self.widget().update()


class TracksToggleButton(QPushButton):
    """
    Compact button displaying 'Tracks: 1' (or 2, 3).
    Clicking it cycles: 1 -> 2 -> 3 -> 1.
    Provides currentData(), currentIndex(), and setCurrentIndex() for backwards compatibility with cb_tracks.
    """
    def __init__(self, main_app, parent=None):
        super().__init__("Tracks: 1", parent)
        self.main_app = main_app
        self.track_count = 1
        self.setFixedHeight(32)
        self.setToolTip("Click to toggle visible tracks (1 -> 2 -> 3). Currently showing 1 track.")
        self.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
                border: 1px solid #3c3c44;
                border-radius: 6px;
                color: #e0e0f0;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
                border-color: #00d2ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #141417;
                border-color: #00ffff;
            }
        """)
        self.clicked.connect(self._cycle_tracks)

    def _cycle_tracks(self):
        next_count = (self.track_count % 3) + 1
        self.set_track_count(next_count)

    def set_track_count(self, count):
        self.track_count = max(1, min(3, int(count)))
        self.setText(f"Tracks: {self.track_count}")
        self.setToolTip(f"Click to toggle visible tracks (1 -> 2 -> 3). Currently showing {self.track_count} track{'s' if self.track_count > 1 else ''}.")
        if self.main_app:
            self.main_app.set_visible_track_count(self.track_count)

    def currentData(self):
        return self.track_count

    def currentIndex(self):
        return self.track_count - 1

    def setCurrentIndex(self, idx):
        self.set_track_count(idx + 1)


class BeatbarApp(QMainWindow):
    """The core desktop application container with control widgets, timeline integration, and player sync."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BeatBar Maker & Editor")
        try:
            from icon_utils import get_suite_icon
            m_ico = get_suite_icon("beatbar-maker", size=32)
            if m_ico and not m_ico.isNull():
                self.setWindowIcon(m_ico)
        except Exception:
            pass
        
        # Load user settings & keybinds from autosaving .config
        self.app_config = load_app_config()
        self.keybinds = self.app_config.get('keybinds', DEFAULT_KEYBINDS.copy())
        
        # Restore window geometry
        win_w = int(self.app_config.get('window_width', 1000))
        win_h = int(self.app_config.get('window_height', 600))
        self.resize(win_w, win_h)
        wx = self.app_config.get('window_x')
        wy = self.app_config.get('window_y')
        if wx is not None and wy is not None and int(wx) >= 0 and int(wy) >= 0:
            self.move(int(wx), int(wy))
        if self.app_config.get('is_maximized', False):
            self.showMaximized()
        
        self.audio_path = ""
        self.original_media_path = ""
        self.beats_path_base = ""
        self.ignore_time_slider_change = False
        
        # Difficulty & Level state
        self.current_level = int(self.app_config.get('level', 5))
        self.current_difficulty = self.app_config.get('difficulty', 'Normal')
        self.difficulty_stats = {}
        self.active_credits_end = None
        
        # Autosave debounced timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(400)
        self._autosave_timer.timeout.connect(self.autosave_settings)
        
        # Initialize Audio/Video Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Set App UI Styling
        self.setStyleSheet(self.get_stylesheet())
        
        self.setup_ui()
        self.setAcceptDrops(True)
        
        # Status / Setup Timer
        self.timer = QTimer(self)
        self.timer.setInterval(25)  # 40 FPS updates for smooth playhead motion
        self.timer.timeout.connect(self.update_playback_state)
        self.timer.start()

        # Connect media player events
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.player.playbackStateChanged.connect(self.on_player_state_changed)
        
    def get_stylesheet(self):
        return """
        QMainWindow {
            background-color: #0c0c0e;
        }
        QWidget {
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #d1d1d6;
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
            border: 1px solid #3c3c44;
            border-radius: 6px;
            padding: 7px 15px;
            font-weight: bold;
            font-size: 11px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
            border-color: #555562;
        }
        QPushButton:pressed {
            background: #141417;
            border-color: #00ffff;
        }
        QPushButton#generate_btn {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff007f, stop:1 #b30059);
            border: 1px solid #ff3399;
            color: #ffffff;
        }
        QPushButton#generate_btn:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff3399, stop:1 #d6006b);
            border-color: #ff66b3;
        }
        QPushButton#generate_btn:pressed {
            background: #99004d;
            border-color: #ff007f;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #12141a;
            border: 1px solid #222734;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0077b6, stop:1 #00f3ff);
            border-radius: 3px;
        }
        QSlider::add-page:horizontal {
            background: #141720;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.65 #00f3ff, stop:1.0 #0077b6);
            border: 2px solid #00f3ff;
            width: 16px;
            height: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }
        QSlider::handle:horizontal:hover {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.75 #ffffff, stop:1.0 #00f3ff);
            border: 2px solid #ffffff;
        }
        QSlider::handle:horizontal:pressed {
            background: #00f3ff;
            border: 2px solid #ffffff;
        }
        QComboBox {
            background-color: #1a1a1f;
            border: 1px solid #3c3c44;
            border-radius: 6px;
            padding: 5px 10px;
            min-width: 60px;
            font-weight: bold;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #1a1a1f;
            border: 1px solid #3c3c44;
            selection-background-color: #00ffff;
            selection-color: #0c0c0e;
        }
        #lane_labels {
            background-color: #16161a;
            border: 1px solid #2d2d35;
            border-right: 1px solid #2d2d35;
            border-top-left-radius: 8px;
            border-bottom-left-radius: 8px;
        }
        QScrollArea {
            border: 1px solid #2d2d35;
            border-left: none;
            background-color: #121214;
            border-top-right-radius: 8px;
            border-bottom-right-radius: 8px;
        }
        QCheckBox {
            font-size: 11px;
        }
        QLabel {
            font-size: 12px;
        }
        QDialog {
            background-color: #121215;
            border: 1px solid #2d2d35;
        }
        QSplitter::handle {
            background-color: #2d2d35;
            height: 4px;
        }
        QSplitter::handle:hover {
            background-color: #00ffff;
        }
        """

    def setup_ui(self):
        self.setMinimumSize(800, 480)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)
        
        # 1. Top Section - Unified compact top toolbar row
        top_toolbar_layout = QHBoxLayout()
        top_toolbar_layout.setSpacing(6)
        top_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        
        btn_icon_style = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
                border: 1px solid #3c3c44;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
                border-color: #00d2ff;
            }
            QPushButton:pressed {
                background: #141417;
                border-color: #00ffff;
            }
            QPushButton:disabled {
                background: #19191d;
                border-color: #2b2b32;
            }
        """
        
        # Settings button - First on the left
        self.btn_settings = QPushButton("SETTINGS")
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setIcon(get_feather_icon("settings", "#00d2ff", 14))
        self.btn_settings.setIconSize(QSize(14, 14))
        self.btn_settings.setToolTip("Configure keybindings, auto-difficulty thresholds, and playback defaults")
        self.btn_settings.setFixedHeight(32)
        self.btn_settings.setStyleSheet("""
            QPushButton#btn_settings {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
                border: 1px solid #3c3c44;
                border-radius: 6px;
                color: #00d2ff;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton#btn_settings:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
                border-color: #00d2ff;
                color: #ffffff;
            }
            QPushButton#btn_settings:pressed {
                background: #141417;
                border-color: #00ffff;
            }
        """)
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        self.btn_settings.setEnabled(True)
        top_toolbar_layout.addWidget(self.btn_settings)

        # File Operations
        self.btn_load_audio = QPushButton()
        self.btn_load_audio.setIcon(get_feather_icon("folder", "#00d2ff", 18))
        self.btn_load_audio.setIconSize(QSize(18, 18))
        self.btn_load_audio.setToolTip("Open Media or Beatmap Project File (*.mp4, *.mp3, *.beat, *.json)")
        self.btn_load_audio.setFixedSize(36, 32)
        self.btn_load_audio.setStyleSheet(btn_icon_style)
        self.btn_load_audio.clicked.connect(self.load_audio_file)
        top_toolbar_layout.addWidget(self.btn_load_audio)
        
        self.btn_load_beats = QPushButton()
        self.btn_load_beats.setIcon(get_feather_icon("file-text", "#00d2ff", 18))
        self.btn_load_beats.setIconSize(QSize(18, 18))
        self.btn_load_beats.setToolTip("Load Beatmap Project File (*.beat, *.json)")
        self.btn_load_beats.setFixedSize(36, 32)
        self.btn_load_beats.setStyleSheet(btn_icon_style)
        self.btn_load_beats.clicked.connect(self.load_beats_file)
        self.btn_load_beats.setEnabled(True)
        top_toolbar_layout.addWidget(self.btn_load_beats)
        
        self.btn_save_beats = QPushButton()
        self.btn_save_beats.setIcon(get_feather_icon("save", "#00d2ff", 18))
        self.btn_save_beats.setIconSize(QSize(18, 18))
        self.btn_save_beats.setToolTip("Save Beatmap Project (*.beat, *.json)")
        self.btn_save_beats.setFixedSize(36, 32)
        self.btn_save_beats.setStyleSheet(btn_icon_style)
        self.btn_save_beats.clicked.connect(self.save_beats_file)
        self.btn_save_beats.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_save_beats)

        self.btn_export_beat = QPushButton()
        self.btn_export_beat.setIcon(get_feather_icon("package", "#a855f7", 18))
        self.btn_export_beat.setIconSize(QSize(18, 18))
        self.btn_export_beat.setToolTip("Export Shareable .beat Archive (Package with Video)")
        self.btn_export_beat.setFixedSize(36, 32)
        self.btn_export_beat.setStyleSheet(btn_icon_style)
        self.btn_export_beat.clicked.connect(self.export_beat_package)
        self.btn_export_beat.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_export_beat)

        # Generator & Editing Tools
        # V2 Primary Button - Compact Icon + V2
        self.btn_auto_gen_v2 = QPushButton("V2")
        self.btn_auto_gen_v2.setObjectName("generate_btn_v2")
        self.btn_auto_gen_v2.setIcon(get_feather_icon("music", "#ffffff", 14))
        self.btn_auto_gen_v2.setFixedHeight(32)
        self.btn_auto_gen_v2.setStyleSheet("""
            QPushButton#generate_btn_v2 {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8a2be2, stop:1 #4a00e0);
                border: 1px solid #a855f7;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton#generate_btn_v2:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9d4edd, stop:1 #5a189a);
                border-color: #c084fc;
            }
            QPushButton#generate_btn_v2:pressed {
                background: #3c096c;
            }
            QPushButton#generate_btn_v2:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
                color: #666677;
            }
        """)
        self.btn_auto_gen_v2.setToolTip("V2 Engine: Generates musical beatbars aligned to BPM and dynamic song energy (Wicked PMV / Rhythm Game style).")
        self.btn_auto_gen_v2.clicked.connect(self.open_generate_v2_dialog)
        self.btn_auto_gen_v2.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_auto_gen_v2)
        
        # V3 Engine Button - Compact Icon + V3
        self.btn_auto_gen_v3 = QPushButton("V3")
        self.btn_auto_gen_v3.setObjectName("generate_btn_v3")
        self.btn_auto_gen_v3.setIcon(get_feather_icon("zap", "#ffffff", 14))
        self.btn_auto_gen_v3.setFixedHeight(32)
        self.btn_auto_gen_v3.setStyleSheet("""
            QPushButton#generate_btn_v3 {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff851b, stop:1 #ff4136);
                border: 1px solid #ffa07a;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton#generate_btn_v3:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff9933, stop:1 #e03224);
                border-color: #ffb380;
            }
            QPushButton#generate_btn_v3:pressed {
                background: #b32d00;
            }
            QPushButton#generate_btn_v3:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
                color: #666677;
            }
        """)
        self.btn_auto_gen_v3.setToolTip("V3 Engine: Zone-aware rhythm generator with anti-overlap protection and clean steady quarters.")
        self.btn_auto_gen_v3.clicked.connect(self.open_generate_v3_dialog)
        self.btn_auto_gen_v3.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_auto_gen_v3)
        
        # Video Beat Parser Button (Icon-only)
        self.btn_video_parser = QPushButton()
        self.btn_video_parser.setObjectName("btn_video_parser")
        self.btn_video_parser.setIcon(get_feather_icon("activity", "#ffffff", 14))
        self.btn_video_parser.setFixedSize(36, 32)
        self.btn_video_parser.setStyleSheet("""
            QPushButton#btn_video_parser {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b4db, stop:1 #0083b0);
                border: 1px solid #00d2ff;
                color: white;
                font-weight: bold;
                padding: 4px;
                border-radius: 4px;
            }
            QPushButton#btn_video_parser:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00c6ff, stop:1 #0072ff);
                border-color: #80dfff;
            }
            QPushButton#btn_video_parser:pressed {
                background: #005c8a;
            }
            QPushButton#btn_video_parser:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
                color: #666677;
            }
        """)
        self.btn_video_parser.setToolTip("Video Beat Parser [WIP]: Directly extracts ground-truth beats from target video by detecting color transitions. (Currently disabled / Work in progress)")
        self.btn_video_parser.clicked.connect(self.open_video_parser_dialog)
        self.btn_video_parser.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_video_parser)
        
        # Video & Rhythm Zones Window Button - Renamed to ZoneMaker
        self.btn_video_zones = QPushButton("ZoneMaker")
        self.btn_video_zones.setObjectName("btn_video_zones")
        self.btn_video_zones.setIcon(get_feather_icon("video", "#0c0c10", 14))
        self.btn_video_zones.setFixedHeight(32)
        self.btn_video_zones.setStyleSheet("""
            QPushButton#btn_video_zones {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #11998e, stop:1 #38ef7d);
                border: 1px solid #38ef7d;
                color: #0c0c10;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton#btn_video_zones:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #13b3a6, stop:1 #52f08e);
                border-color: #70f4a2;
                color: #000000;
            }
            QPushButton#btn_video_zones:pressed {
                background: #0a665e;
            }
            QPushButton#btn_video_zones:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
                color: #666677;
            }
        """)
        self.btn_video_zones.setToolTip("ZoneMaker: Synchronized video player and timeline to define playback zones (normal, speeding up, slowing, pause, climax, edging) and generate tailored rhythm beats.")
        self.btn_video_zones.clicked.connect(self.open_video_zones_dialog)
        self.btn_video_zones.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_video_zones)
        
        # Alias for backwards compatibility
        self.btn_auto_gen = self.btn_auto_gen_v3

        # Compact Tracks button (cycles 1 -> 2 -> 3 -> 1 on click)
        self.btn_tracks = TracksToggleButton(self)
        self.cb_tracks = self.btn_tracks  # Alias for backwards compatibility with DSP / load routines
        top_toolbar_layout.addWidget(self.btn_tracks)

        # Headless attributes
        self.cb_level = None
        self.cb_difficulty = None
        self.btn_place_level = None
        self.btn_auto_diff = None
        self.lbl_diff_badge = None

        top_toolbar_layout.addStretch(1)

        # Video Name on the same height as high buttons
        self.lbl_file_info = QLabel("No audio loaded.")
        self.lbl_file_info.setStyleSheet("color: #00d2ff; font-weight: bold; font-size: 11px; padding: 0 8px;")
        self.lbl_file_info.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        top_toolbar_layout.addWidget(self.lbl_file_info)

        # Halve Selected Beats button - Only visible when beats on timeline are selected
        self.btn_halve_beats = QPushButton()
        self.btn_halve_beats.setIcon(get_feather_icon("scissors", "#ffffff", 16))
        self.btn_halve_beats.setIconSize(QSize(16, 16))
        self.btn_halve_beats.setToolTip("Halve Selected Beats (Hotkey: H)")
        self.btn_halve_beats.setFixedSize(36, 32)
        self.btn_halve_beats.clicked.connect(self.halve_selected)
        self.btn_halve_beats.setEnabled(False)
        self.btn_halve_beats.hide()  # Hidden by default until beats are selected
        self.btn_halve_beats.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff8c00, stop:1 #e07b00);
                border: 1px solid #ff9d24;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffa500, stop:1 #e07b00);
                border-color: #ffb85c;
            }
            QPushButton:pressed {
                background: #b86500;
                border-color: #ffa500;
            }
            QPushButton:disabled {
                background: #2b2b36;
                border-color: #3b3b4a;
            }
        """)
        top_toolbar_layout.addWidget(self.btn_halve_beats)

        # Clear All Beats Button - Anchored in the far right corner
        self.btn_clear_beats = QPushButton()
        self.btn_clear_beats.setIcon(get_feather_icon("trash-2", "#ff6b62", 18))
        self.btn_clear_beats.setIconSize(QSize(18, 18))
        self.btn_clear_beats.setToolTip("Clear All Beats from Timeline")
        self.btn_clear_beats.setFixedSize(36, 32)
        self.btn_clear_beats.setStyleSheet(btn_icon_style)
        self.btn_clear_beats.clicked.connect(self.clear_all_beats)
        self.btn_clear_beats.setEnabled(False)
        top_toolbar_layout.addWidget(self.btn_clear_beats)

        main_layout.addLayout(top_toolbar_layout)

        # 2. Middle Section - Video Preview on TOP (fills available space), Timeline snugly at bottom
        self.splitter = None  # Eliminated dead open space and fixed layout directly
        
        # Video container (Expands vertically to make video preview area much bigger)
        self.video_container = QWidget()
        self.video_container.setMinimumHeight(140)
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_container.setStyleSheet("background-color: #0b0b10; border-radius: 6px; border: 1px solid #1a1a24;")
        video_layout = QHBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.player.setVideoOutput(self.video_widget)
        video_layout.addWidget(self.video_widget)
        
        # Floating Skip Credits Button (anime streaming site style)
        self.btn_skip_credits = QPushButton("Skip Credits ⏩", self.video_container)
        self.btn_skip_credits.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 27, 75, 0.90);
                border: 1.5px solid #818cf8;
                border-radius: 8px;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(49, 46, 129, 0.95);
                border-color: #a5b4fc;
                color: #c7d2fe;
            }
        """)
        self.btn_skip_credits.hide()
        self.btn_skip_credits.clicked.connect(self._skip_credits)
        
        # Video Info Overlay Capsule (Video name + Level name under it - NEVER collapses on inactivity)
        self.video_info_overlay = QFrame(self.video_container)
        self.video_info_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(14, 14, 20, 0.82);
                border: 1px solid #2d2d3e;
                border-radius: 8px;
            }
        """)
        vio_layout = QVBoxLayout(self.video_info_overlay)
        vio_layout.setContentsMargins(10, 5, 10, 5)
        vio_layout.setSpacing(2)
        
        self.lbl_overlay_video_title = QLabel("No Video Loaded", self.video_info_overlay)
        self.lbl_overlay_video_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        vio_layout.addWidget(self.lbl_overlay_video_title)
        
        self.lbl_overlay_level_name = QLabel("", self.video_info_overlay)
        self.lbl_overlay_level_name.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        vio_layout.addWidget(self.lbl_overlay_level_name)
        
        self.video_info_overlay.move(14, 14)
        self.video_info_overlay.show()
        
        # Grid/Timeline container (Moved down, perfectly sized to tracks with zero dead space)
        self.grid_container = QWidget()
        self.grid_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid_layout = QHBoxLayout(self.grid_container)
        grid_layout.setSpacing(0)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lane_labels = LaneLabelsWidget()
        grid_layout.addWidget(self.lane_labels, alignment=Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area = TimelineScrollArea()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(lambda _: self.timeline.update())
        
        self.timeline = TimelineWidget(self)
        self.timeline.time_seek_requested.connect(self.seek_audio)
        self.timeline.beats_changed.connect(self.mark_unsaved_changes)
        self.timeline.selection_changed.connect(self.update_selection_dependent_controls)
        self.scroll_area.setWidget(self.timeline)
        grid_layout.addWidget(self.scroll_area, alignment=Qt.AlignmentFlag.AlignTop)
        
        # Add directly to main layout: Video takes all remaining vertical space, tracks anchored below
        main_layout.addWidget(self.video_container, stretch=1)
        main_layout.addWidget(self.grid_container, stretch=0)
        
        # 3. Playback Seek Bar (Full song scrubber)
        scrub_layout = QHBoxLayout()
        
        self.txt_curr_time = QLineEdit("0:00.00")
        self.txt_curr_time.setFixedWidth(68)
        self.txt_curr_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_curr_time.setToolTip("Type precise timestamp (e.g. 0:45.00 or 85.5) and press Enter")
        self.txt_curr_time.setStyleSheet("""
            QLineEdit {
                background-color: #16161a;
                border: 1px solid #3c3c44;
                border-radius: 4px;
                color: #00ffff;
                font-weight: bold;
                font-size: 11px;
                padding: 2px;
            }
            QLineEdit:focus {
                border-color: #00ffff;
                background-color: #202028;
            }
        """)
        self.txt_curr_time.returnPressed.connect(self.on_time_text_entered)
        scrub_layout.addWidget(self.txt_curr_time)
        
        self.slider_progress = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setRange(0, 1000)
        self.slider_progress.seek_requested.connect(self.on_slider_seek_requested)
        self.slider_progress.sliderMoved.connect(self.on_scrub_moved)
        self.slider_progress.setEnabled(False)
        scrub_layout.addWidget(self.slider_progress)
        
        self.lbl_total_time = QLabel("0:00.00")
        self.lbl_total_time.setFixedWidth(55)
        scrub_layout.addWidget(self.lbl_total_time)
        
        main_layout.addLayout(scrub_layout)
        
        # 4. Bottom Controls Section (Playback speed on left, Play/Stop in center, Zoom & Vol on right)
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(4, 2, 4, 4)
        bottom_layout.setSpacing(8)
        
        # Left side: Compact Playback Speed
        lbl_speed = QLabel("Speed:")
        lbl_speed.setStyleSheet("color: #a0a0b8; font-weight: bold; font-size: 11px;")
        bottom_layout.addWidget(lbl_speed)

        self.cb_speed = QComboBox()
        self.cb_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        saved_speed = self.app_config.get('playback_speed', "1.0x")
        idx_spd = self.cb_speed.findText(saved_speed)
        if idx_spd >= 0:
            self.cb_speed.setCurrentIndex(idx_spd)
        else:
            self.cb_speed.setCurrentText("1.0x")
        self.cb_speed.setFixedWidth(68)
        self.cb_speed.setFixedHeight(28)
        self.cb_speed.setStyleSheet("""
            QComboBox {
                background: #1e1e24;
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                color: #e0e0f0;
                font-size: 11px;
                padding: 2px 6px;
            }
            QComboBox:hover {
                border-color: #00d2ff;
            }
        """)
        self.cb_speed.currentTextChanged.connect(self.change_speed)
        self.cb_speed.currentTextChanged.connect(lambda: self.queue_autosave())
        self.cb_speed.setEnabled(False)
        bottom_layout.addWidget(self.cb_speed)
        
        # Center balance stretch
        bottom_layout.addStretch(1)
        
        # Center: Play & Stop Buttons
        self.btn_play = QPushButton("PLAY")
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        self.btn_play.setFixedHeight(30)
        self.btn_play.setMinimumWidth(80)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a3a2a, stop:1 #0e2419);
                border: 1px solid #28a745;
                border-radius: 4px;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #224d37, stop:1 #143323);
                border-color: #4cd964;
            }
            QPushButton:pressed {
                background: #0a1b12;
            }
            QPushButton:disabled {
                background: #19191d;
                border-color: #2b2b32;
                color: #555566;
            }
        """)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setEnabled(False)
        bottom_layout.addWidget(self.btn_play)
        
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setIcon(get_feather_icon("square", "#ffffff", 14))
        self.btn_stop.setFixedHeight(30)
        self.btn_stop.setMinimumWidth(80)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
                border: 1px solid #3c3c44;
                border-radius: 4px;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
                border-color: #ff6b62;
                color: #ff6b62;
            }
            QPushButton:pressed {
                background: #141417;
            }
            QPushButton:disabled {
                background: #19191d;
                border-color: #2b2b32;
                color: #555566;
            }
        """)
        self.btn_stop.clicked.connect(self.stop_audio)
        self.btn_stop.setEnabled(False)
        bottom_layout.addWidget(self.btn_stop)
        
        # Center balance stretch
        bottom_layout.addStretch(1)
        
        # Right side: Compact Zoom & Volume
        lbl_zoom = QLabel("Zoom:")
        lbl_zoom.setStyleSheet("color: #a0a0b8; font-weight: bold; font-size: 11px;")
        bottom_layout.addWidget(lbl_zoom)

        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(30, 600)
        saved_zoom = int(self.app_config.get('zoom', 100))
        self.slider_zoom.setValue(saved_zoom)
        self.slider_zoom.setFixedWidth(75)  # Compacted from 120
        self.slider_zoom.valueChanged.connect(self.change_zoom)
        self.slider_zoom.valueChanged.connect(lambda: self.queue_autosave())
        self.slider_zoom.setEnabled(False)
        bottom_layout.addWidget(self.slider_zoom)
        
        bottom_layout.addSpacing(10)
        
        self.btn_mute = QPushButton()
        self.btn_mute.setFixedSize(28, 26)
        self.btn_mute.setIcon(get_feather_icon("volume-2", "#00ffff", 14))
        self.btn_mute.setToolTip("Mute / Unmute audio")
        self.btn_mute.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #3c3c44;
                border-radius: 4px;
                padding: 2px;
            }
            QPushButton:hover {
                border-color: #00ffff;
                background: #1e1e24;
            }
        """)
        self.btn_mute.clicked.connect(self.toggle_mute)
        bottom_layout.addWidget(self.btn_mute)
        
        lbl_vol = QLabel("Vol:")
        lbl_vol.setStyleSheet("color: #a0a0b8; font-weight: bold; font-size: 11px;")
        bottom_layout.addWidget(lbl_vol)

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        saved_vol = int(self.app_config.get('volume', 80))
        self.slider_vol.setValue(saved_vol)
        self.slider_vol.setFixedWidth(75)  # Compacted from 100
        self.slider_vol.valueChanged.connect(self.change_volume)
        self.slider_vol.valueChanged.connect(lambda: self.queue_autosave())
        bottom_layout.addWidget(self.slider_vol)
        
        # Initialize audio output volume and mute state
        self.audio_output.setVolume(saved_vol / 100.0)
        self.prev_volume = saved_vol if saved_vol > 0 else 80
        if self.app_config.get('is_muted', False):
            self.audio_output.setMuted(True)
            self.btn_mute.setIcon(get_feather_icon("volume-x", "#ff4136", 14))
        
        # Help label removed per user request for a cleaner bottom bar
        self.lbl_help = None
        
        main_layout.addLayout(bottom_layout)
        
        # Central widget setting
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Call initial height setup
        self.adjust_timeline_heights()

    def adjust_timeline_heights(self):
        """Resizes the track label side widget, scroll area, and grid container to fit visible tracks (1 to 3)."""
        th = self.timeline.header_height + self.timeline.visible_track_count * self.timeline.lane_height + 5
        self.timeline.setFixedHeight(th)
        self.lane_labels.setFixedHeight(th + 20)  # Add 20px matching scrollbar height allowance
        self.scroll_area.setFixedHeight(th + 20)
        if hasattr(self, 'grid_container') and self.grid_container:
            self.grid_container.setFixedHeight(th + 20)
        self.timeline.updateGeometry()
        self.timeline.update()
        self.lane_labels.update()

    def set_visible_track_count(self, count):
        count = max(1, min(3, int(count)))
        if hasattr(self, 'btn_tracks') and self.btn_tracks.track_count != count:
            self.btn_tracks.track_count = count
            self.btn_tracks.setText(f"Tracks: {count}")
            self.btn_tracks.setToolTip(f"Click to toggle visible tracks (1 -> 2 -> 3). Currently showing {count} track{'s' if count > 1 else ''}.")
        self.timeline.set_visible_track_count(count)
        self.lane_labels.set_visible_track_count(count)
        self.adjust_timeline_heights()

    def on_visible_tracks_changed(self, idx):
        count = self.btn_tracks.currentData() if hasattr(self, 'btn_tracks') else (idx + 1)
        self.set_visible_track_count(count)

    def normalize_loaded_beats(self, raw_beats):
        """
        Normalizes beats from any file format into Track 1 (Lane 4), Track 2 (Lane 1), and Track 3 (Lane 2).
        Returns (normalized_beats, max_track_idx).
        """
        if not raw_beats:
            return [], 0

        distinct_lanes = set()
        for b in raw_beats:
            l = b.get('lane', 4) if isinstance(b, dict) else 4
            distinct_lanes.add(l)

        if distinct_lanes == {4}:
            lane_map = {4: 4}
        elif distinct_lanes == {0}:
            lane_map = {0: 4}
        elif distinct_lanes == {0, 4}:
            lane_map = {4: 4, 0: 1}
        elif distinct_lanes.issubset({0, 1, 2, 3}):
            lane_map = {0: 4, 1: 1, 2: 2, 3: 2}
        else:
            lane_map = {4: 4, 0: 4, 1: 1, 2: 2, 3: 2}

        norm_beats = []
        max_track_idx = 0
        for b in raw_beats:
            t = float(b['time'] if isinstance(b, dict) else b)
            orig_lane = b.get('lane', 4) if isinstance(b, dict) else 4
            target_lane = lane_map.get(orig_lane, 4)
            tr_idx = 0 if target_lane == 4 else (1 if target_lane == 1 else 2)
            if tr_idx > max_track_idx:
                max_track_idx = tr_idx
            norm_beats.append({'time': round(t, 3), 'lane': target_lane})

        norm_beats.sort(key=lambda x: (x['time'], x['lane']))
        return norm_beats, max_track_idx

    def on_track_visibility_changed(self):
        self.adjust_timeline_heights()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_skip_credits_btn()

    def _reposition_skip_credits_btn(self):
        if hasattr(self, 'btn_skip_credits') and hasattr(self, 'video_container'):
            btn_w, btn_h = 140, 36
            vc = self.video_container
            x = vc.width() - btn_w - 20
            y = vc.height() - btn_h - 20
            self.btn_skip_credits.setGeometry(max(10, x), max(10, y), btn_w, btn_h)
            self.btn_skip_credits.raise_()
        if hasattr(self, 'video_info_overlay') and hasattr(self, 'video_container'):
            self.video_info_overlay.move(14, 14)
            self.video_info_overlay.adjustSize()
            self.video_info_overlay.raise_()

    def _skip_credits(self):
        if hasattr(self, 'active_credits_end') and self.active_credits_end is not None:
            self.seek_audio(self.active_credits_end)
            self.btn_skip_credits.hide()

    def _check_credits_zone(self, t):
        active_credits = None
        if hasattr(self, 'video_zones') and self.video_zones:
            zones = self.video_zones.zones if hasattr(self.video_zones, 'zones') else self.video_zones
            for z in zones:
                z_type = z.zone_type if hasattr(z, 'zone_type') else (z.get('type') if isinstance(z, dict) else None)
                z_start = z.start_time if hasattr(z, 'start_time') else (z.get('start_time', 0.0) if isinstance(z, dict) else 0.0)
                z_end = z.end_time if hasattr(z, 'end_time') else (z.get('end_time', 0.0) if isinstance(z, dict) else 0.0)
                if z_type == 'credits' and z_start <= t < z_end:
                    active_credits = (z_start, z_end)
                    break

        if active_credits is not None and hasattr(self, 'video_container') and self.video_container.isVisible():
            self.active_credits_end = active_credits[1]
            self.btn_skip_credits.show()
            self._reposition_skip_credits_btn()
            self.btn_skip_credits.raise_()
        elif hasattr(self, 'btn_skip_credits'):
            self.btn_skip_credits.hide()

    def on_place_level_clicked(self):
        self.timeline.open_place_level_dialog(self.timeline.playhead_time)

    def on_level_changed(self, text_or_idx):
        if not getattr(self, 'cb_level', None):
            return
        text = self.cb_level.currentText()
        ch = self.timeline.get_level_at(self.timeline.playhead_time)
        if ch:
            ch['name'] = text
            digits = ''.join(filter(str.isdigit, text))
            if digits:
                ch['level'] = int(digits)
            self.timeline.update()
        digits = ''.join(filter(str.isdigit, text))
        if digits:
            self.current_level = int(digits)
        self.update_difficulty_badge()
        self.sync_active_level_ui()
        self.mark_unsaved_changes()

    def on_difficulty_changed(self, diff_name):
        if diff_name:
            self.current_difficulty = diff_name
            ch = self.timeline.get_level_at(self.timeline.playhead_time)
            if ch:
                ch['difficulty'] = diff_name
                self.timeline.update()
            self.update_difficulty_badge()
            self.sync_active_level_ui()
            self.mark_unsaved_changes()

    def sync_active_level_ui(self, seconds=None):
        if seconds is None:
            seconds = getattr(self.timeline, 'playhead_time', 0.0)
        ch = self.timeline.get_level_at(seconds)
        if ch:
            ch_name = ch.get('name', f"Level {self.current_level}")
            ch_diff = ch.get('difficulty', self.current_difficulty)
            st = ch.get('start_time', 0.0)
            et = ch.get('end_time', self.timeline.duration)
            
            # Sync toolbar Level & Diff comboboxes without infinite recursion
            if getattr(self, 'cb_level', None) and not self.cb_level.hasFocus():
                self.cb_level.blockSignals(True)
                self.cb_level.setEditText(ch_name)
                self.cb_level.blockSignals(False)
            if getattr(self, 'cb_difficulty', None) and not self.cb_difficulty.hasFocus():
                self.cb_difficulty.blockSignals(True)
                self.cb_difficulty.setCurrentText(ch_diff)
                self.cb_difficulty.blockSignals(False)
                
            lvl_display = f"{ch_name} • {ch_diff} [{self.timeline.format_time_sec(st)} - {self.timeline.format_time_sec(et)}]"
        else:
            lvl_display = f"Lv.{self.current_level} • {self.current_difficulty}"
            
        if getattr(self, 'lbl_overlay_level_name', None):
            self.lbl_overlay_level_name.setText(lvl_display)
            if getattr(self, 'video_info_overlay', None):
                self.video_info_overlay.adjustSize()

    def update_difficulty_badge(self):
        if not getattr(self, 'lbl_diff_badge', None):
            return
        diff_colors = {
            "Easy": "#22c55e",
            "Normal": "#3b82f6",
            "Hard": "#f59e0b",
            "Expert": "#ef4444",
            "Master": "#a855f7"
        }
        col = diff_colors.get(getattr(self, 'current_difficulty', 'Normal'), "#6366f1")
        burst_count = self.difficulty_stats.get('burst_groups_count', 0) if hasattr(self, 'difficulty_stats') and self.difficulty_stats else 0
        total_beats = len(self.timeline.beats) if hasattr(self, 'timeline') else 0
        lvl = getattr(self, 'current_level', 5)
        diff = getattr(self, 'current_difficulty', 'Normal')
        self.lbl_diff_badge.setText(
            f"<span style='background-color: {col}; color: #ffffff; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;'>"
            f"{diff} • Lv.{lvl}</span> "
            f"<span style='color: #8a8a98; font-size: 11px;'>({total_beats} beats, {burst_count} bursts)</span>"
        )

    def auto_determine_difficulty(self, silent=False):
        duration = self.timeline.duration
        bpm = getattr(self, 'bpm', 120.0)
        if duration <= 0 and self.timeline.beats:
            duration = max([b['time'] for b in self.timeline.beats]) + 1.0
            
        if duration <= 0 or not self.timeline.beats:
            if not silent:
                QMessageBox.information(self, "Auto Difficulty", "No beats or audio loaded to evaluate difficulty.")
            return

        cfg_gap = float(self.app_config.get('close_gap_threshold', 0.35))
        cfg_size = int(self.app_config.get('min_group_size', 3))

        diff_info = calculate_beat_difficulty(
            self.timeline.beats,
            duration=duration,
            bpm=bpm,
            close_gap_threshold=cfg_gap,
            min_group_size=cfg_size
        )

        self.difficulty_stats = diff_info.get('stats', diff_info)

        if not silent:
            # User explicitly requested auto difficulty determination
            self.current_level = diff_info.get('level', 1)
            self.current_difficulty = diff_info.get('difficulty', 'Normal')

            if getattr(self, 'cb_level', None):
                self.cb_level.blockSignals(True)
                self.cb_level.setCurrentIndex(max(0, min(9, self.current_level - 1)))
                self.cb_level.blockSignals(False)

            if getattr(self, 'cb_difficulty', None):
                self.cb_difficulty.blockSignals(True)
                self.cb_difficulty.setCurrentText(self.current_difficulty)
                self.cb_difficulty.blockSignals(False)

            self.mark_unsaved_changes()

            stats = self.difficulty_stats
            msg = (
                f"Evaluated {stats.get('total_beats', len(self.timeline.beats))} beats:\n"
                f"• Level: {self.current_level} / 10\n"
                f"• Difficulty: {self.current_difficulty} (Score: {diff_info['score']}/10)\n"
                f"• Average Frequency: {stats.get('avg_freq_bpm', 0):.1f} beats/min\n"
                f"• Peak Burst Frequency: {stats.get('peak_freq_bpm', 0):.1f} beats/min\n"
                f"• Close-Note Groups (Bursts): {stats.get('burst_groups_count', 0)} groups\n"
                f"• Max Burst Run: {stats.get('burst_max_length', 0)} notes in a row"
            )
            QMessageBox.information(self, "Auto-Determined Difficulty", msg)

        self.update_difficulty_badge()

    def open_settings_dialog(self):
        dlg = BeatbarSettingsDialog(self.app_config, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.app_config = dlg.app_config
            self.keybinds = self.app_config.get('keybinds', DEFAULT_KEYBINDS.copy())
            save_app_config(self.app_config)
            
            # Apply immediate settings
            vol = int(self.app_config.get('volume', 80))
            self.slider_vol.setValue(vol)
            self.audio_output.setVolume(vol / 100.0)
            
            b_key = self.keybinds.get('lane_4', '5')
            h_key = self.keybinds.get('halve', 'H')
            if getattr(self, 'lbl_help', None):
                self.lbl_help.setText(
                    f"Hotkeys: [Space] Play/Pause | [{b_key}] Add Beat | [{h_key}] Halve Selected | [Click & Drag] Select | [Del] Delete"
                )
            
            if self.app_config.get('auto_recalc_diff', True) and self.timeline.beats:
                self.auto_determine_difficulty(silent=True)
                
            QMessageBox.information(self, "Settings Saved", "Application settings saved successfully!")

    def update_selection_dependent_controls(self):
        has_selection = len(self.timeline.selected_beats) > 0
        self.btn_halve_beats.setEnabled(has_selection)
        self.btn_halve_beats.setVisible(has_selection)

    def halve_selected(self):
        self.timeline.halve_selected_beats()

    def load_audio_file(self, file_path=None):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Open Media or Beatmap Project", "",
                "All Supported (*.beat *.json *.mp4 *.mkv *.avi *.mov *.flv *.webm *.mp3 *.wav);;"
                "Beatmap Projects (*.beat *_beats.json *.json);;"
                "Media Files (*.mp3 *.wav *.mp4 *.mkv *.avi *.mov *.flv *.webm);;"
                "All Files (*)"
            )
        if not file_path:
            return
            
        if file_path.lower().endswith(('.beat', '.json')):
            self.load_beats_file(file_path)
            return

        self.stop_audio()
        self.original_media_path = file_path
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Loading and preparing audio... (this takes a moment)", None, 0, 0, self)
        self.progress_dialog.setWindowTitle("Loading Media")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None) # disable cancel button
        self.progress_dialog.show()
        
        # Start background load thread
        self.load_thread = AudioLoadThread(file_path)
        self.load_thread.finished.connect(self.on_audio_loaded)
        self.load_thread.error.connect(self.on_audio_load_error)
        self.load_thread.start()

    def on_audio_loaded(self, envelope, duration, sr, final_audio_path):
        self.progress_dialog.close()
        self.audio_path = final_audio_path
        self.beats_path_base = os.path.splitext(self.audio_path)[0] + "_beats"
        
        # Load the original MP4 or MP3 into the player
        self.player.setSource(QUrl.fromLocalFile(self.original_media_path))
        
        # Show/hide video container based on file type
        ext = os.path.splitext(self.original_media_path)[1].lower()
        if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v']:
            self.video_container.show()
        else:
            # Check if there is a matching video file in the same directory
            base_no_ext = os.path.splitext(self.original_media_path)[0]
            matching_vid = None
            for vext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v']:
                candidate = base_no_ext + vext
                if os.path.exists(candidate):
                    matching_vid = candidate
                    break
            if matching_vid:
                self.player.setSource(QUrl.fromLocalFile(matching_vid))
                self.video_container.show()
            else:
                self.video_container.hide()
            
        # Update timeline widget
        self.timeline.set_audio_data(envelope, duration)
        self.adjust_timeline_heights()
        
        # Record last loaded audio file and autosave
        if self.original_media_path:
            self.app_config['last_audio_path'] = self.original_media_path
            self.queue_autosave()
        
        # Update labels & enable controls
        self.lbl_file_info.setText(os.path.basename(self.original_media_path))
        self.lbl_total_time.setText(self.format_time(duration))
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.cb_speed.setEnabled(True)
        self.slider_zoom.setEnabled(True)
        self.slider_progress.setEnabled(True)
        self.btn_load_beats.setEnabled(True)
        self.btn_save_beats.setEnabled(True)
        self.btn_export_beat.setEnabled(True)
        self.btn_auto_gen_v2.setEnabled(True)
        self.btn_auto_gen_v3.setEnabled(True)
        self.btn_auto_gen.setEnabled(True)
        self.btn_video_parser.setEnabled(False)  # Disabled: Video Parser is WIP
        self.btn_video_zones.setEnabled(True)
        self.btn_settings.setEnabled(True)
        self.btn_clear_beats.setEnabled(True)
        
        # Attempt to auto-load saved beats: check .beat archive first, then .json
        # Only if no beats are currently loaded into the timeline
        if not self.timeline.beats:
            matching_beat = self.beats_path_base + ".beat"
            matching_json = self.beats_path_base + ".json"
            target_file = matching_beat if os.path.exists(matching_beat) else (matching_json if os.path.exists(matching_json) else None)
            loaded_matching = False
            if target_file and os.path.exists(target_file):
                try:
                    res = load_beats(target_file)
                    norm_beats, max_tr = self.normalize_loaded_beats(res.beats)
                    self.timeline.beats = norm_beats
                    self.timeline.selected_beats = []
                    if max_tr > 0:
                        needed_tr = max_tr + 1
                        current_shown = self.cb_tracks.currentData() or 1
                        if needed_tr > current_shown:
                            self.cb_tracks.setCurrentIndex(needed_tr - 1)
                    if hasattr(res, 'zones') and res.zones:
                        self.video_zones = ZonesCollection.from_dict({'zones': res.zones})
                    if hasattr(res, 'level') and res.level:
                        self.current_level = int(res.level)
                        if self.cb_level:
                            self.cb_level.blockSignals(True)
                            self.cb_level.setEditText(f"Lv.{self.current_level}")
                            self.cb_level.blockSignals(False)
                    if hasattr(res, 'difficulty') and res.difficulty:
                        self.current_difficulty = res.difficulty
                        if self.cb_difficulty:
                            self.cb_difficulty.blockSignals(True)
                            self.cb_difficulty.setCurrentText(self.current_difficulty)
                            self.cb_difficulty.blockSignals(False)
                    if hasattr(res, 'difficulty_stats') and res.difficulty_stats:
                        self.difficulty_stats = res.difficulty_stats
                    
                    from beat_generator import infer_or_standardize_levels
                    raw_levels = getattr(res, 'levels', None)
                    loaded_levels = infer_or_standardize_levels(
                        duration=duration,
                        title=os.path.basename(target_file),
                        level=getattr(res, 'level', self.current_level),
                        levels=raw_levels
                    )
                    self.timeline.set_levels(loaded_levels)
                    if hasattr(res, 'level_mode') and res.level_mode:
                        self.level_mode = res.level_mode
                    
                    if (not hasattr(res, 'difficulty') or not res.difficulty) and self.timeline.beats:
                        self.auto_determine_difficulty(silent=True)
                    else:
                        self.update_difficulty_badge()
                    self.timeline.update()
                    loaded_matching = True
                    QMessageBox.information(self, "Load Project", f"Automatically loaded matching beats file:\n{os.path.basename(target_file)}")
                except Exception as e:
                    print("Failed to auto-load matching beats:", e)

            if not loaded_matching:
                # Per user request: Never auto-create initial levels unless loaded from file or placed by user
                self.timeline.set_levels([])
        else:
            # Beats were already present before loading media. Preserve them and re-sync timeline.
            if self.timeline.beats:
                self.auto_determine_difficulty(silent=True)
            self.timeline.update()

        if hasattr(self, 'lbl_overlay_video_title'):
            vname = os.path.basename(self.original_media_path) if self.original_media_path else "No Video"
            self.lbl_overlay_video_title.setText(vname)
        self.sync_active_level_ui()

    def on_audio_load_error(self, err_msg):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Audio Load Error", f"An error occurred while loading audio:\n{err_msg}")

    def load_beats_file(self, file_path=None):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Load Beatmap", "",
                "Beatmap Files (*.beat *_beats.json *.json);;Beat Archives (*.beat);;JSON Beatmap Files (*.json);;All Files (*)"
            )
        if not file_path:
            return
            
        try:
            res = load_beats(file_path)
            raw_beats = res[0]
            norm_beats, max_tr = self.normalize_loaded_beats(raw_beats)
            
            # If timeline already contains beats, ask user how to load
            if self.timeline.beats:
                dlg = LoadBeatOptionsDialog(self, beat_count=len(norm_beats), current_tracks=self.timeline.visible_track_count)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                choice = dlg.choice
                if choice == "track2":
                    for b in norm_beats:
                        b['lane'] = 1
                    self.timeline.beats = [b for b in self.timeline.beats if b.get('lane') != 1] + norm_beats
                    if (self.cb_tracks.currentData() or 1) < 2:
                        self.cb_tracks.setCurrentIndex(1)
                elif choice == "track3":
                    for b in norm_beats:
                        b['lane'] = 2
                    self.timeline.beats = [b for b in self.timeline.beats if b.get('lane') != 2] + norm_beats
                    if (self.cb_tracks.currentData() or 1) < 3:
                        self.cb_tracks.setCurrentIndex(2)
                elif choice == "merge":
                    self.timeline.beats.extend(norm_beats)
                    seen = set()
                    deduped = []
                    for b in self.timeline.beats:
                        k = (round(b['time'], 3), b.get('lane', 4))
                        if k not in seen:
                            seen.add(k)
                            deduped.append(b)
                    self.timeline.beats = deduped
                    needed_tr = max(1, max_tr + 1)
                    if (self.cb_tracks.currentData() or 1) < needed_tr:
                        self.cb_tracks.setCurrentIndex(needed_tr - 1)
                else: # "replace"
                    self.timeline.beats = norm_beats
                    needed_tr = max(1, max_tr + 1)
                    if (self.cb_tracks.currentData() or 1) < needed_tr:
                        self.cb_tracks.setCurrentIndex(needed_tr - 1)
            else:
                self.timeline.beats = norm_beats
                needed_tr = max(1, max_tr + 1)
                if (self.cb_tracks.currentData() or 1) < needed_tr:
                    self.cb_tracks.setCurrentIndex(needed_tr - 1)

            self.timeline.beats.sort(key=lambda b: (b['time'], b.get('lane', 4)))
            self.timeline.selected_beats = []
            if hasattr(res, 'zones') and res.zones:
                self.video_zones = ZonesCollection.from_dict({'zones': res.zones})

            if hasattr(res, 'level') and res.level:
                self.current_level = int(res.level)
                if self.cb_level:
                    self.cb_level.blockSignals(True)
                    self.cb_level.setEditText(f"Lv.{self.current_level}")
                    self.cb_level.blockSignals(False)
            if hasattr(res, 'difficulty') and res.difficulty:
                self.current_difficulty = res.difficulty
                if self.cb_difficulty:
                    self.cb_difficulty.blockSignals(True)
                    self.cb_difficulty.setCurrentText(self.current_difficulty)
                    self.cb_difficulty.blockSignals(False)
            if hasattr(res, 'difficulty_stats') and res.difficulty_stats:
                self.difficulty_stats = res.difficulty_stats

            # If no audio is currently loaded, ensure timeline duration and editor controls are properly set up
            if not self.audio_path:
                max_beat_time = max((b.get('time', 0.0) for b in self.timeline.beats), default=0.0)
                dur = max(60.0, max_beat_time + 5.0)
                self.timeline.set_audio_data(np.array([], dtype=np.float32), dur)
                self.adjust_timeline_heights()
                self.lbl_file_info.setText(f"[No Video] {os.path.basename(file_path)}")
                self.lbl_total_time.setText(self.format_time(dur))
                self.slider_zoom.setEnabled(True)
                self.slider_progress.setEnabled(True)
                self.btn_save_beats.setEnabled(True)
                self.btn_export_beat.setEnabled(True)
                self.btn_clear_beats.setEnabled(True)
                self.btn_auto_gen_v3.setEnabled(True)
                self.btn_video_zones.setEnabled(True)
                self.btn_settings.setEnabled(True)
                self.beats_path_base = os.path.splitext(file_path)[0]

            from beat_generator import infer_or_standardize_levels
            raw_levels = getattr(res, 'levels', None)
            loaded_levels = infer_or_standardize_levels(
                duration=self.timeline.duration or 60.0,
                title=os.path.basename(file_path),
                level=getattr(res, 'level', self.current_level),
                levels=raw_levels
            )
            self.timeline.set_levels(loaded_levels)
            if hasattr(res, 'level_mode') and res.level_mode:
                self.level_mode = res.level_mode

            if (not hasattr(res, 'difficulty') or not res.difficulty) and self.timeline.beats:
                self.auto_determine_difficulty(silent=True)
            else:
                self.update_difficulty_badge()

            self.sync_active_level_ui()
            self.timeline.update()
            zone_str = f" and {len(res.zones)} rhythm zones" if hasattr(res, 'zones') and res.zones else ""

            # Record last loaded beats file and autosave
            self.app_config['last_beats_path'] = file_path
            self.queue_autosave()

            # If no audio is currently loaded, search for or offer to load associated media
            if not self.audio_path:
                candidate_media = None
                
                # Check .beat embedded/referenced video
                if hasattr(res, 'beat_path') and res.beat_path:
                    try:
                        from beat_format import BeatFormat
                        with BeatFormat.open(res.beat_path) as bf:
                            vpath, _ = bf.resolve_video()
                            if vpath and os.path.exists(vpath):
                                candidate_media = vpath
                    except Exception as e:
                        print("Error resolving video from .beat:", e)
                
                # Check audio_file attribute
                if not candidate_media and hasattr(res, 'audio_file') and res.audio_file:
                    raw_af = str(res.audio_file).strip()
                    if raw_af:
                        if os.path.isabs(raw_af) and os.path.exists(raw_af):
                            candidate_media = raw_af
                        else:
                            rel_af = os.path.join(os.path.dirname(file_path), os.path.basename(raw_af))
                            if os.path.exists(rel_af):
                                candidate_media = rel_af

                # Check same directory for matching video filename
                if not candidate_media:
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    if base_name.endswith('_beats'):
                        base_name = base_name[:-6]
                    dir_name = os.path.dirname(file_path)
                    for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.mp3', '.wav']:
                        cand = os.path.join(dir_name, base_name + ext)
                        if os.path.exists(cand):
                            candidate_media = cand
                            break

                if candidate_media and os.path.exists(candidate_media):
                    reply = QMessageBox.question(
                        self, "Load Associated Video?",
                        f"Loaded {len(norm_beats)} beats{zone_str}.\n\nAssociated media found:\n{os.path.basename(candidate_media)}\n\nWould you like to load this video into the editor now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.load_audio_file(candidate_media)
                        return
                else:
                    reply = QMessageBox.question(
                        self, "Select Video/Audio Media?",
                        f"Loaded {len(norm_beats)} beats{zone_str}.\n\nNo associated video or audio was found in this folder.\nWould you like to select a media file for this beatmap now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        chosen_media, _ = QFileDialog.getOpenFileName(
                            self, "Select Video or Audio for Beatmap", os.path.dirname(file_path),
                            "Media Files (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.mp3 *.wav);;All Files (*)"
                        )
                        if chosen_media:
                            self.load_audio_file(chosen_media)
                            return

            QMessageBox.information(self, "Success", f"Loaded {len(norm_beats)} beats{zone_str} successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Beats", f"Failed to parse beats file:\n{str(e)}")

    def save_beats_file(self):
        if not self.audio_path and not self.timeline.beats:
            QMessageBox.warning(self, "No Project Loaded", "No beatmap or media is currently loaded.")
            return
            
        beats_to_export = [b for b in self.timeline.beats]
        
        default_dir = self.beats_path_base if self.beats_path_base else "beatmap_project"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Beatmap Project", default_dir,
            "JSON files (*.json);;Beat Archive (*.beat);;All files (*)"
        )
        if not file_path:
            return

        is_beat = file_path.lower().endswith('.beat') or "(*.beat)" in selected_filter
        if is_beat and not file_path.lower().endswith('.beat'):
            file_path += ".beat"
        elif not is_beat and not file_path.lower().endswith('.json'):
            file_path += ".json"
            
        zones_data = []
        if hasattr(self, 'video_zones') and self.video_zones:
            if hasattr(self.video_zones, 'zones'):
                zones_data = [z.to_dict() for z in self.video_zones.zones]
            elif isinstance(self.video_zones, list):
                zones_data = self.video_zones

        settings_data = {
            "bpm": getattr(self, 'bpm', 120.0),
            "lead_time": 1.5,
            "speed": 1.0,
            "screen_shake": bool(self.app_config.get('screen_shake', True))
        }

        embed_video = False
        video_src = self.original_media_path if (hasattr(self, 'original_media_path') and self.original_media_path and os.path.exists(self.original_media_path)) else self.audio_path
        if is_beat and video_src and os.path.exists(video_src):
            reply = QMessageBox.question(
                self, "Embed Video?",
                "Do you want to embed the full video binary inside the .beat archive?\n\n"
                "• Yes: Completely self-contained pack (can be copied to Android or shared).\n"
                "• No: Lightweight pack referencing the video by filename.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            embed_video = (reply == QMessageBox.StandardButton.Yes)

        try:
            audio_name = self.audio_path or (self.original_media_path if (hasattr(self, 'original_media_path') and self.original_media_path) else "") or ""
            save_beats(
                file_path, beats_to_export, audio_name,
                settings=settings_data, zones=zones_data,
                level=getattr(self, 'current_level', 5),
                levels=getattr(self.timeline, 'levels', []),
                level_mode=getattr(self, 'level_mode', 'ramp_within_level'),
                difficulty=getattr(self, 'current_difficulty', 'Normal'),
                difficulty_stats=getattr(self, 'difficulty_stats', {}),
                embed_video=embed_video, video_path=video_src
            )
            self.beats_path_base = os.path.splitext(file_path)[0]
            self.app_config['last_beats_path'] = file_path
            self.queue_autosave()
            self.setWindowTitle("BeatBar Maker & Editor")
            zone_msg = f" and {len(zones_data)} rhythm zones" if zones_data else ""
            fmt_name = ".beat archive" if is_beat else "JSON file"
            lvl = getattr(self, 'current_level', 5)
            diff = getattr(self, 'current_difficulty', 'Normal')
            QMessageBox.information(
                self, "Success", 
                f"Beatmap saved successfully!\nExported {len(beats_to_export)} beats on the BEATS track{zone_msg} into {fmt_name}.\n"
                f"Level: {lvl} | Difficulty: {diff}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Beats", f"Failed to save beatmap:\n{str(e)}")

    def export_beat_package(self):
        """Dedicated one-click export for .beat archives."""
        if not self.timeline.beats and not self.audio_path and not self.original_media_path:
            QMessageBox.warning(self, "No Project Loaded", "No beatmap or media is currently loaded.")
            return

        beats_to_export = [b for b in self.timeline.beats]
        default_name = (self.beats_path_base or "beatmap_project") + ".beat"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export .beat Archive", default_name,
            "Beat Archive (*.beat);;All Files (*)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".beat"):
            file_path += ".beat"

        video_src = self.original_media_path if (hasattr(self, 'original_media_path') and self.original_media_path and os.path.exists(self.original_media_path)) else self.audio_path

        embed_reply = QMessageBox.question(
            self, "Embed Video?",
            "Do you want to embed the full video binary directly into the .beat archive?\n\n"
            "• Yes: Completely self-contained pack (can be copied to Android or shared).\n"
            "• No: Lightweight pack referencing the video by filename.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        embed_video = (embed_reply == QMessageBox.StandardButton.Yes)

        zones_data = []
        if hasattr(self, 'video_zones') and self.video_zones:
            if hasattr(self.video_zones, 'zones'):
                zones_data = [z.to_dict() for z in self.video_zones.zones]
            elif isinstance(self.video_zones, list):
                zones_data = self.video_zones

        settings_data = {
            "bpm": getattr(self, 'bpm', 120.0),
            "lead_time": 1.5,
            "speed": 1.0,
            "screen_shake": bool(self.app_config.get('screen_shake', True))
        }

        try:
            from beat_format import BeatFormat
            title = os.path.splitext(os.path.basename(file_path))[0]
            default_author = self.app_config.get('default_author', 'User')
            from PyQt6.QtWidgets import QInputDialog
            author_val, ok = QInputDialog.getText(
                self, "Pack Author",
                f"Enter author name for '{title}':",
                QLineEdit.EchoMode.Normal,
                default_author
            )
            if not ok:
                return
            author_val = author_val.strip() or default_author
            self.app_config['default_author'] = author_val
            save_app_config(self.app_config)

            lvl = getattr(self, 'current_level', 5)
            diff = getattr(self, 'current_difficulty', 'Normal')
            stats = getattr(self, 'difficulty_stats', {})
            data = {
                "version": "2.0",
                "audio_file": os.path.basename(self.audio_path) if self.audio_path else os.path.basename(video_src),
                "video_file": os.path.basename(video_src),
                "author": author_val,
                "settings": settings_data,
                "zones": zones_data,
                "beats": beats_to_export,
                "level": lvl,
                "levels": getattr(self.timeline, 'levels', []),
                "level_mode": getattr(self, 'level_mode', 'ramp_within_level'),
                "difficulty": diff,
                "difficulty_stats": stats
            }
            out = BeatFormat.create(
                file_path,
                beatmap_source=data,
                title=title,
                author=author_val,
                video_path=video_src,
                embed_video=embed_video
            )
            size_mb = os.path.getsize(out) / (1024 * 1024)
            embed_msg = "with embedded video" if embed_video else "with video reference"
            QMessageBox.information(
                self, "Export Complete",
                f"Successfully exported .beat archive ({size_mb:.1f} MB, {embed_msg}):\n{out}\n\n"
                f"Beats: {len(beats_to_export)} | Zones: {len(zones_data)}\n"
                f"Level: {lvl} | Difficulty: {diff}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export .beat archive:\n{str(e)}")

    def open_generate_v2_dialog(self):
        if not self.audio_path:
            QMessageBox.warning(self, "Audio Required", "Please load an audio or video file first to analyze beats.")
            return
            
        dlg = GenerateSettingsDialogV2(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            preset = dlg.cb_preset.currentData()
            target_lane = dlg.cb_lane.currentData()
            bpm = None if dlg.chk_auto_bpm.isChecked() else dlg.spin_bpm.value()
            density_scale = dlg.spin_density.value()
            quantize_grid = dlg.cb_grid.currentData()
            min_gap = dlg.spin_min_gap.value()
            insert_rolls = dlg.chk_insert_rolls.isChecked()
            halve_non_intense = dlg.chk_halve_non_intense.isChecked()
            intro_cutoff = dlg.spin_intro_cutoff.value()
            clear_first = dlg.clear_existing.isChecked()
            
            # Ensure the targeted track is visible
            needed_tr = 1
            if target_lane == 1:
                needed_tr = 2
            elif target_lane == 2:
                needed_tr = 3
            if (self.cb_tracks.currentData() or 1) < needed_tr:
                self.cb_tracks.setCurrentIndex(needed_tr - 1)

            # Start background generation thread
            self.gen_progress = QProgressDialog("Auto-generating beat timeline (V2 Engine)...", "Cancel", 0, 100, self)
            self.gen_progress.setWindowTitle("Generating Beats (V2)")
            self.gen_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self.gen_progress.setValue(5)
            self.gen_progress.show()
            
            self.analyze_thread_v2 = AudioAnalyzeThreadV2(
                self.audio_path,
                target_lane=target_lane,
                preset=preset,
                bpm=bpm,
                density_scale=density_scale,
                quantize_grid=quantize_grid,
                min_gap=min_gap,
                insert_rolls=insert_rolls,
                halve_non_intense=halve_non_intense,
                intro_cutoff=intro_cutoff
            )
            self.analyze_thread_v2.progress.connect(
                lambda status, pct: (self.gen_progress.setLabelText(status), self.gen_progress.setValue(pct))
            )
            self.analyze_thread_v2.finished.connect(lambda beats: self.on_generation_finished(beats, clear_first))
            self.analyze_thread_v2.error.connect(self.on_generation_error)
            self.gen_progress.canceled.connect(self.analyze_thread_v2.terminate)
            self.analyze_thread_v2.start()

    def open_generate_v3_dialog(self):
        if not self.audio_path:
            QMessageBox.warning(self, "Audio Required", "Please load an audio or video file first to analyze beats.")
            return
            
        dlg = GenerateSettingsDialogV3(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            preset = dlg.cb_preset.currentData()
            target_lane = dlg.cb_lane.currentData()
            bpm = None if dlg.chk_auto_bpm.isChecked() else dlg.spin_bpm.value()
            density_scale = dlg.spin_density.value()
            quantize_grid = dlg.cb_grid.currentData()
            min_gap = dlg.spin_min_gap.value()
            insert_rolls = dlg.chk_insert_rolls.isChecked()
            halve_non_intense = dlg.chk_halve_non_intense.isChecked()
            intro_cutoff = dlg.spin_intro_cutoff.value()
            clear_first = dlg.clear_existing.isChecked()
            anti_overlap = dlg.chk_anti_overlap.isChecked()
            steady_section_cleanup = dlg.chk_steady_clean.isChecked()
            level = dlg.get_level()
            difficulty = dlg.get_difficulty()
            level_mode = dlg.get_level_mode()
            edging_style = dlg.get_edging_style()
            use_zones = dlg.chk_use_zones.isChecked()
            use_levels = dlg.chk_use_levels.isChecked()
            
            # Sync toolbar UI
            if level:
                self.current_level = level
                if self.cb_level:
                    self.cb_level.blockSignals(True)
                    self.cb_level.setCurrentIndex(max(0, min(9, level - 1)))
                    self.cb_level.blockSignals(False)
            if difficulty and difficulty != "Auto":
                self.current_difficulty = difficulty
                if self.cb_difficulty:
                    self.cb_difficulty.blockSignals(True)
                    self.cb_difficulty.setCurrentText(difficulty)
                    self.cb_difficulty.blockSignals(False)

            # Ensure the targeted track is visible
            needed_tr = 1
            if target_lane == 1:
                needed_tr = 2
            elif target_lane == 2:
                needed_tr = 3
            if (self.cb_tracks.currentData() or 1) < needed_tr:
                self.cb_tracks.setCurrentIndex(needed_tr - 1)
            
            # Start background generation thread
            self.gen_progress = QProgressDialog("Auto-generating beat timeline (V3 Engine)...", "Cancel", 0, 100, self)
            self.gen_progress.setWindowTitle("Generating Beats (V3)")
            self.gen_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self.gen_progress.setValue(5)
            self.gen_progress.show()
            
            self.analyze_thread_v3 = AudioAnalyzeThreadV3(
                self.audio_path,
                target_lane=target_lane,
                preset=preset,
                bpm=bpm,
                density_scale=density_scale,
                quantize_grid=quantize_grid,
                min_gap=min_gap,
                insert_rolls=insert_rolls,
                halve_non_intense=halve_non_intense,
                intro_cutoff=intro_cutoff,
                zones=getattr(self, 'video_zones', None),
                anti_overlap=anti_overlap,
                steady_section_cleanup=steady_section_cleanup,
                level=level,
                difficulty=difficulty,
                level_mode=level_mode,
                use_zones=use_zones,
                use_levels=use_levels,
                levels=getattr(self.timeline, 'levels', []),
                edging_style=edging_style
            )
            self.analyze_thread_v3.progress.connect(
                lambda status, pct: (self.gen_progress.setLabelText(status), self.gen_progress.setValue(pct))
            )
            self.analyze_thread_v3.finished.connect(lambda beats: self.on_generation_finished(beats, clear_first))
            self.analyze_thread_v3.error.connect(self.on_generation_error)
            self.gen_progress.canceled.connect(self.analyze_thread_v3.terminate)
            self.analyze_thread_v3.start()

    def open_generate_dialog(self):
        # Default alias points to V3
        self.open_generate_v3_dialog()

    def open_video_parser_dialog(self):
        QMessageBox.information(
            self,
            "Video Parser (WIP)",
            "The Video Beat Parser engine is currently under maintenance / work-in-progress and has been temporarily disabled."
        )
        return

    def open_video_zones_dialog(self):
        if not self.audio_path:
            QMessageBox.warning(self, "Audio/Video Required", "Please load an audio or video file first to edit video & rhythm zones.")
            return

        # Pause playback if running
        self.stop_audio()

        media_path = None
        if hasattr(self, 'original_media_path') and self.original_media_path and os.path.exists(self.original_media_path):
            media_path = self.original_media_path
        else:
            media_path = self.audio_path

        duration = self.timeline.duration
        envelope = self.timeline.waveform_envelope
        tr1_beats = [b['time'] for b in self.timeline.beats if b.get('lane', 4) == 4]
        tr2_beats = [b['time'] for b in self.timeline.beats if b.get('lane', 4) == 1]
        tr3_beats = [b['time'] for b in self.timeline.beats if b.get('lane', 4) == 2]

        # Estimate BPM & phase
        bpm = 125.0
        phase = 0.0
        try:
            import librosa
            from beat_generator import estimate_tempo_and_grid
            y_sub, sr_sub = librosa.load(self.audio_path, sr=22050, duration=min(duration, 50.0))
            hop = int(sr_sub * 0.02)
            g_info = estimate_tempo_and_grid(y_sub, sr_sub, hop)
            bpm = float(g_info['bpm'])
            phase = float(g_info['phase'])
        except Exception as e:
            print("Video zones BPM estimation fallback:", e)

        dlg = VideoZonesEditorDialog(
            media_path=media_path,
            duration=duration,
            bpm=bpm,
            phase=phase,
            waveform_envelope=envelope,
            existing_beats=tr1_beats,
            video_parser_beats=getattr(self, 'last_video_parser_beats', None),
            initial_level=getattr(self, 'current_level', 5),
            initial_difficulty=getattr(self, 'current_difficulty', 'Normal'),
            parent=self,
            initial_levels=getattr(self.timeline, 'levels', []),
            initial_level_mode=getattr(self, 'level_mode', 'ramp_within_level'),
            initial_zones=getattr(self, 'video_zones', None),
            tr1_beats=tr1_beats,
            tr2_beats=tr2_beats,
            tr3_beats=tr3_beats,
            audio_path=getattr(self, 'audio_path', None)
        )

        try:
            ret = dlg.exec()

            # Always synchronize zones, levels, and difficulty from dialog back to main app
            if hasattr(dlg, 'zones_collection') and dlg.zones_collection:
                self.video_zones = dlg.zones_collection
            if hasattr(dlg, 'resulting_levels') and dlg.resulting_levels:
                self.timeline.set_levels(dlg.resulting_levels)
            if hasattr(dlg, 'resulting_level_mode') and dlg.resulting_level_mode:
                self.level_mode = dlg.resulting_level_mode

            # Sync level and difficulty from zones editor if available
            if hasattr(dlg, 'resulting_level') and dlg.resulting_level is not None:
                lvl_str = str(dlg.resulting_level)
                digits = ''.join(filter(str.isdigit, lvl_str))
                if digits:
                    self.current_level = int(digits)
                if self.cb_level:
                    self.cb_level.blockSignals(True)
                    self.cb_level.setCurrentIndex(max(0, min(9, self.current_level - 1)))
                    self.cb_level.blockSignals(False)
            if hasattr(dlg, 'resulting_difficulty') and dlg.resulting_difficulty:
                self.current_difficulty = str(dlg.resulting_difficulty)
                if self.cb_difficulty:
                    idx = self.cb_difficulty.findText(self.current_difficulty)
                    if idx >= 0:
                        self.cb_difficulty.blockSignals(True)
                        self.cb_difficulty.setCurrentIndex(idx)
                        self.cb_difficulty.blockSignals(False)
            if hasattr(dlg, 'difficulty_stats') and dlg.difficulty_stats:
                self.difficulty_stats = dict(dlg.difficulty_stats)
            self.update_difficulty_badge()
            self.sync_active_level_ui()
            self.mark_unsaved_changes()
            self.timeline.update()
            if hasattr(self, 'queue_autosave'):
                self.queue_autosave()

            if ret == QDialog.DialogCode.Accepted:
                new_beats = dlg.generated_beats
                if new_beats:
                    try:
                        if hasattr(self, 'save_history'):
                            self.save_history()
                        target_lane = getattr(dlg, 'target_lane', 4)
                        needed_tr = 1
                        if target_lane == 1:
                            needed_tr = 2
                        elif target_lane == 2:
                            needed_tr = 3
                        if (self.cb_tracks.currentData() or 1) < needed_tr:
                            self.cb_tracks.setCurrentIndex(needed_tr - 1)

                        # Clear target lane existing beats and apply zone beats
                        self.timeline.beats = [b for b in self.timeline.beats if b.get('lane', 4) != target_lane]
                        for bt in new_beats:
                            self.timeline.beats.append({'time': float(bt), 'lane': target_lane})
                        self.timeline.beats.sort(key=lambda b: (b['time'], b['lane']))
                        self.timeline.selected_beats = []
                        self.timeline.update()
                        self.mark_unsaved_changes()
                        self.auto_determine_difficulty(silent=True)
                        lane_name = {4: "Track 1", 1: "Track 2", 2: "Track 3"}.get(target_lane, f"Track {target_lane}")
                        QMessageBox.information(
                            self, "Rhythm Zone Beats Applied",
                            f"Successfully applied {len(new_beats)} rhythm-zone beats to {lane_name}!"
                        )
                    except Exception as e:
                        print("Error applying rhythm zone beats:", e)
        finally:
            if hasattr(dlg, '_cleanup_player'):
                dlg._cleanup_player()


    def on_generation_finished(self, beats, clear_first):
        self.gen_progress.close()
        
        # Check target lanes and ensure tracks are visible
        lanes_in_gen = {b.get('lane', 4) for b in beats}
        needed_tracks = 1
        if 2 in lanes_in_gen or 3 in lanes_in_gen:
            needed_tracks = 3
        elif 1 in lanes_in_gen:
            needed_tracks = max(needed_tracks, 2)
        if (self.cb_tracks.currentData() or 1) < needed_tracks:
            self.cb_tracks.setCurrentIndex(needed_tracks - 1)

        if clear_first:
            if lanes_in_gen:
                self.timeline.beats = [b for b in self.timeline.beats if b.get('lane', 4) not in lanes_in_gen]
                self.timeline.beats.extend(beats)
            else:
                self.timeline.beats = beats
        else:
            # Merge beats
            self.timeline.beats.extend(beats)

        # Deduplicate by rounding and sorting
        seen = set()
        deduped = []
        for b in self.timeline.beats:
            key = (round(b['time'], 3), b.get('lane', 4))
            if key not in seen:
                seen.add(key)
                deduped.append(b)
        self.timeline.beats = deduped
        self.timeline.beats.sort(key=lambda x: (x['time'], x.get('lane', 4)))
            
        self.timeline.selected_beats = []
        self.timeline.update()
        self.mark_unsaved_changes()
        self.auto_determine_difficulty(silent=True)
        
        QMessageBox.information(self, "Success", f"Auto-generation finished! Placed {len(beats)} beats on the tracks.")

    def on_generation_error(self, err_msg):
        self.gen_progress.close()
        QMessageBox.critical(self, "Generation Error", f"An error occurred while generating beats:\n{err_msg}")

    def clear_all_beats(self):
        if not self.timeline.beats:
            return

        dlg = ClearBeatsDialog(
            self,
            beats=self.timeline.beats,
            tracks=self.timeline.tracks,
            visible_track_count=self.timeline.visible_track_count
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        sel_track = dlg.selected_track
        if sel_track == -1:
            # Clear all tracks
            self.timeline.beats = []
            self.timeline.selected_beats = []
        else:
            # Clear chosen track index (0: Track 1, 1: Track 2, 2: Track 3)
            kept_beats = []
            for b in self.timeline.beats:
                tr_idx = self.timeline.lane_to_track_idx(b.get('lane', 4))
                if tr_idx != sel_track:
                    kept_beats.append(b)
            self.timeline.beats = kept_beats
            self.timeline.selected_beats = [
                b for b in self.timeline.selected_beats
                if self.timeline.lane_to_track_idx(b.get('lane', 4)) != sel_track
            ]

        self.timeline.update()
        self.mark_unsaved_changes()
        self.auto_determine_difficulty(silent=True)

    def mark_unsaved_changes(self):
        # Add an asterisk to the title to show unsaved changes
        title = self.windowTitle()
        if not title.endswith("*"):
            self.setWindowTitle(title + " *")

    def format_time(self, seconds):
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds - int(seconds)) * 100)
        return f"{minutes}:{secs:02d}.{centiseconds:02d}"

    def update_curr_time_display(self, seconds):
        if not self.txt_curr_time.hasFocus():
            self.txt_curr_time.setText(self.format_time(seconds))
        self.sync_active_level_ui(seconds)

    def on_time_text_entered(self):
        text = self.txt_curr_time.text().strip()
        parsed_sec = self.parse_time_string(text)
        if parsed_sec is not None and self.timeline.duration > 0:
            target_t = max(0.0, min(parsed_sec, self.timeline.duration))
            self.seek_audio(target_t)
            self.txt_curr_time.clearFocus()
        else:
            self.update_curr_time_display(self.timeline.playhead_time)

    def parse_time_string(self, text):
        if not text:
            return None
        try:
            if ":" in text:
                parts = text.split(":")
                if len(parts) == 2:
                    mins = float(parts[0])
                    secs = float(parts[1])
                    return mins * 60.0 + secs
                elif len(parts) == 3:
                    hrs = float(parts[0])
                    mins = float(parts[1])
                    secs = float(parts[2])
                    return hrs * 3600.0 + mins * 60.0 + secs
            else:
                return float(text)
        except ValueError:
            pass
        return None

    def on_slider_seek_requested(self, pct):
        if self.timeline.duration > 0:
            t = pct * self.timeline.duration
            self.seek_audio(t)

    def update_playback_state(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos_sec = self.player.position() / 1000.0
            self.timeline.set_playhead_time(pos_sec)
            
            # Smoothly scroll scrollarea to center the playhead
            self.scroll_to_time(pos_sec)
            
            # Update scrub bar and time label
            self.ignore_time_slider_change = True
            if self.timeline.duration > 0:
                self.slider_progress.setValue(int(pos_sec / self.timeline.duration * 1000.0))
            self.update_curr_time_display(pos_sec)
            self.ignore_time_slider_change = False
            self._check_credits_zone(pos_sec)

    def scroll_to_time(self, t):
        px = int(t * self.timeline.pixels_per_second)
        viewport_w = self.scroll_area.viewport().width()
        # Center playhead in screen
        scroll_bar = self.scroll_area.horizontalScrollBar()
        target_val = px - viewport_w // 2
        scroll_bar.setValue(target_val)

    def on_player_position_changed(self, pos):
        # Back-up position updates (if timer isn't running)
        if not self.timer.isActive() or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            pos_sec = pos / 1000.0
            self.timeline.set_playhead_time(pos_sec)
            self.update_curr_time_display(pos_sec)
            
            self.ignore_time_slider_change = True
            if self.timeline.duration > 0:
                self.slider_progress.setValue(int(pos_sec / self.timeline.duration * 1000.0))
            self.ignore_time_slider_change = False
            self._check_credits_zone(pos_sec)

    def on_player_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("PAUSE")
            self.btn_play.setIcon(get_feather_icon("pause", "#ffffff", 14))
        else:
            self.btn_play.setText("PLAY")
            self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop_audio(self):
        self.player.stop()
        self.player.setPosition(0)
        self.btn_play.setText("PLAY")
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        self.timeline.set_playhead_time(0.0)
        self.slider_progress.setValue(0)
        self.update_curr_time_display(0.0)
        self.scroll_area.horizontalScrollBar().setValue(0)
        self._check_credits_zone(0.0)

    def seek_audio(self, t):
        self.player.setPosition(int(t * 1000.0))
        self.timeline.set_playhead_time(t)
        self.update_curr_time_display(t)
        
        self.ignore_time_slider_change = True
        if self.timeline.duration > 0:
            self.slider_progress.setValue(int(t / self.timeline.duration * 1000.0))
        self.ignore_time_slider_change = False
        self._check_credits_zone(t)

    def on_scrub_moved(self, val):
        if self.ignore_time_slider_change or self.timeline.duration <= 0:
            return
        t = (val / 1000.0) * self.timeline.duration
        self.seek_audio(t)

    def change_speed(self, speed_text):
        rate = float(speed_text.replace("x", ""))
        self.player.setPlaybackRate(rate)

    def change_zoom(self, val):
        self.timeline.set_pixels_per_second(float(val))

    def toggle_mute(self):
        curr_vol = self.slider_vol.value()
        if curr_vol > 0:
            self.prev_volume = curr_vol
            self.slider_vol.setValue(0)
            self.audio_output.setVolume(0.0)
            self.btn_mute.setIcon(get_feather_icon("volume-x", "#ff6b62", 14))
        else:
            restore_vol = getattr(self, 'prev_volume', 80) or 80
            self.slider_vol.setValue(restore_vol)
            self.audio_output.setVolume(restore_vol / 100.0)
            self.btn_mute.setIcon(get_feather_icon("volume-2", "#00ffff", 14))

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)
        if val == 0:
            self.btn_mute.setIcon(get_feather_icon("volume-x", "#ff6b62", 14))
        else:
            self.btn_mute.setIcon(get_feather_icon("volume-2", "#00ffff", 14))

    def queue_autosave(self):
        """Debounced autosave trigger."""
        if hasattr(self, '_autosave_timer'):
            self._autosave_timer.start()

    def autosave_settings(self):
        """Flushes user settings to .config immediately."""
        try:
            if not self.isFullScreen() and not self.isMaximized():
                self.app_config['window_width'] = self.width()
                self.app_config['window_height'] = self.height()
                self.app_config['window_x'] = self.pos().x()
                self.app_config['window_y'] = self.pos().y()
            self.app_config['is_maximized'] = self.isMaximized()
            if hasattr(self, 'slider_zoom'):
                self.app_config['zoom'] = self.slider_zoom.value()
            if hasattr(self, 'slider_vol'):
                self.app_config['volume'] = self.slider_vol.value()
            if hasattr(self, 'audio_output'):
                self.app_config['is_muted'] = self.audio_output.isMuted()
            if hasattr(self, 'cb_speed'):
                self.app_config['playback_speed'] = self.cb_speed.currentText()
            self.app_config['level'] = getattr(self, 'current_level', 5)
            self.app_config['difficulty'] = getattr(self, 'current_difficulty', 'Normal')
            if getattr(self, 'splitter', None):
                self.app_config['splitter_sizes'] = self.splitter.sizes()
            if self.original_media_path:
                self.app_config['last_audio_path'] = self.original_media_path
            if self.beats_path_base:
                self.app_config['last_beats_path'] = self.beats_path_base
            save_app_config(self.app_config)
        except Exception as e:
            print("[BeatbarApp] Error autosaving settings:", e)

    def closeEvent(self, event):
        self.autosave_settings()
        if hasattr(self, 'player') and self.player:
            self.player.stop()
        super().closeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                fpath = urls[0].toLocalFile()
                if fpath:
                    ext = os.path.splitext(fpath)[1].lower()
                    if ext in ['.beat', '.json']:
                        self.load_beats_file(fpath)
                    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v', '.mp3', '.wav']:
                        self.load_audio_file(fpath)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                super().keyPressEvent(event)
                return
            if hasattr(self, 'timeline'):
                if self.timeline.selected_beats:
                    self.timeline.delete_selected_beats()
                elif getattr(self.timeline, 'selected_chapter', None):
                    self.timeline.delete_level_chapter(self.timeline.selected_chapter)
                elif getattr(self.timeline, 'hovered_chapter', None):
                    self.timeline.delete_level_chapter(self.timeline.hovered_chapter)
        else:
            super().keyPressEvent(event)


def main():
    if "--web" in sys.argv:
        from web.run_web import main as run_web_main
        sys.argv.remove("--web")
        run_web_main()
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setApplicationName("BeatBar Maker")
    try:
        from icon_utils import get_suite_icon
        m_ico = get_suite_icon("beatbar-maker", size=32)
        if m_ico and not m_ico.isNull():
            app.setWindowIcon(m_ico)
    except Exception:
        pass
    window = BeatbarApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
