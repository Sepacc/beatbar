"""
zones_editor.py - Interactive Video & Rhythm Zones Editor for Beatmaker Pro.

Allows users to define, view, and edit musical/choreographic zones on top of the
video player and beatbar timeline:
- Types: Normal, Speeding Up, Slowing, Pause, Climax, Edging.
- Synchronized video playback with scrubbing, frame-stepping, and speed control.
- Live beats timeline displaying existing project beats alongside human reference charts.
- Direct integration with the V3 auto-generation engine.
"""

import os
import json
import uuid
import numpy as np

from PyQt6.QtCore import (
    Qt, QUrl, QTimer, QSize, QRect, QRectF, QPoint, QPointF, pyqtSignal
)
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QDoubleSpinBox, QCheckBox, QComboBox, QFileDialog, QMessageBox,
    QScrollBar, QToolBar, QFrame, QSizePolicy, QToolTip, QSplitter,
    QLineEdit, QMenu, QGroupBox, QSpinBox, QScrollArea
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPainterPath,
    QPolygonF, QCursor, QKeySequence, QAction
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from icon_utils import get_feather_icon, draw_feather_icon


# ==============================================================================
# 1. ZONE DEFINITIONS & DATA MODEL
# ==============================================================================

ZONE_TYPES = {
    "normal": {
        "id": "normal",
        "name": "Normal Groove",
        "desc": "Standard musical groove (steady quarter notes, musical phrasing, 1x rate)",
        "color": "#2ECC40",       # Emerald Green
        "bg_color": "#113817",
        "border_color": "#44e057",
        "feather_icon": "music"
    },
    "speeding_up": {
        "id": "speeding_up",
        "name": "Speeding Up",
        "desc": "Accelerando / Rising tension (progressively accelerates from half-notes to 8ths)",
        "color": "#FF851B",       # Vibrant Orange
        "bg_color": "#3f2105",
        "border_color": "#ffa047",
        "feather_icon": "fast-forward"
    },
    "slowing": {
        "id": "slowing",
        "name": "Slowing Down",
        "desc": "Ritardando / Cooldown (decreases density from quarters to half notes)",
        "color": "#39CCCC",       # Cyan / Teal
        "bg_color": "#0d3131",
        "border_color": "#5cebeb",
        "feather_icon": "rewind"
    },
    "pause": {
        "id": "pause",
        "name": "Pause / Rest",
        "desc": "Sparse ambient section (1----3----1----1----1, major downbeats only or complete rests)",
        "color": "#0074D9",       # Deep Blue
        "bg_color": "#0a243e",
        "border_color": "#3399ff",
        "feather_icon": "pause"
    },
    "climax": {
        "id": "climax",
        "name": "Climax Burst",
        "desc": "Peak energy / dense rhythm (6-1-3-6-1-3-6, driving 8ths and burst rolls)",
        "color": "#FF4136",       # Crimson Red
        "bg_color": "#401311",
        "border_color": "#ff6b62",
        "feather_icon": "zap"
    },
    "edging": {
        "id": "edging",
        "name": "Edging Tension",
        "desc": "High tension syncopation / stutter pulses followed by sudden dramatic pauses",
        "color": "#B10DC9",       # Purple / Magenta
        "bg_color": "#33083b",
        "border_color": "#d434ef",
        "feather_icon": "activity"
    },
    "credits": {
        "id": "credits",
        "name": "Credits",
        "desc": "Skippable credits/outro zone with no beats (skippable like anime streaming intro/credits)",
        "color": "#6366F1",       # Indigo / Slate Iris
        "bg_color": "#1e1b4b",
        "border_color": "#818cf8",
        "feather_icon": "skip-forward"
    }
}


class VideoZone:
    """Represents a single timed choreographic/rhythm zone on the video timeline."""
    def __init__(self, start_time, end_time, zone_type="normal", label=""):
        self.id = str(uuid.uuid4())[:8]
        self.start_time = max(0.0, round(float(start_time), 3))
        self.end_time = max(self.start_time + 0.1, round(float(end_time), 3))
        self.zone_type = zone_type if zone_type in ZONE_TYPES else "normal"
        self.label = label or ZONE_TYPES[self.zone_type]["name"]

    @property
    def duration(self):
        return max(0.0, self.end_time - self.start_time)

    def contains(self, t):
        return self.start_time <= t <= self.end_time

    def to_dict(self):
        return {
            'id': self.id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'type': self.zone_type,
            'label': self.label
        }

    @classmethod
    def from_dict(cls, data):
        zone = cls(
            start_time=data.get('start_time', data.get('start', 0.0)),
            end_time=data.get('end_time', data.get('end', 1.0)),
            zone_type=data.get('type', data.get('zone_type', 'normal')),
            label=data.get('label', '')
        )
        if 'id' in data:
            zone.id = str(data['id'])
        return zone


class ZonesCollection:
    """Ordered collection of video zones."""
    def __init__(self):
        self.zones = []  # List of VideoZone

    def __len__(self):
        return len(self.zones)

    def __iter__(self):
        return iter(self.zones)

    def __getitem__(self, idx):
        return self.zones[idx]

    def sanitize_no_overlaps(self):
        """Ensures that no zones overlap in time. Trims adjacent boundaries to guarantee strict non-overlap."""
        if len(self.zones) <= 1:
            return
        self.sort_zones()
        sanitized = [self.zones[0]]
        for z in self.zones[1:]:
            prev = sanitized[-1]
            if z.start_time < prev.end_time:
                # Collision detected: clamp boundary
                if z.end_time <= prev.end_time:
                    # z is enveloped inside prev -> skip
                    continue
                else:
                    z.start_time = prev.end_time
            if z.duration >= 0.1:
                sanitized.append(z)
        self.zones = sanitized

    def add_zone(self, start_time, end_time, zone_type="normal", label=""):
        st = max(0.0, round(float(start_time), 3))
        et = max(st + 0.1, round(float(end_time), 3))
        new_zone = VideoZone(st, et, zone_type, label)
        
        # Cleanly insert without overlapping: slice or trim any intersecting existing zones
        updated = []
        for z in self.zones:
            if z.end_time <= new_zone.start_time:
                updated.append(z)
            elif z.start_time >= new_zone.end_time:
                updated.append(z)
            else:
                # Overlaps new_zone
                if z.start_time < new_zone.start_time and z.end_time > new_zone.end_time:
                    left_p = VideoZone(z.start_time, new_zone.start_time, z.zone_type, z.label)
                    right_p = VideoZone(new_zone.end_time, z.end_time, z.zone_type, z.label)
                    updated.append(left_p)
                    updated.append(right_p)
                elif z.start_time < new_zone.start_time:
                    z.end_time = new_zone.start_time
                    if z.duration >= 0.1:
                        updated.append(z)
                elif z.end_time > new_zone.end_time:
                    z.start_time = new_zone.end_time
                    if z.duration >= 0.1:
                        updated.append(z)
        updated.append(new_zone)
        updated.sort(key=lambda x: x.start_time)
        self.zones = updated
        self.sanitize_no_overlaps()
        return new_zone

    def remove_zone(self, zone_id):
        self.zones = [z for z in self.zones if z.id != zone_id]

    def clear(self):
        self.zones.clear()

    def sort_zones(self):
        self.zones.sort(key=lambda z: z.start_time)

    def get_zone_at(self, t):
        for z in self.zones:
            if z.contains(t):
                return z
        return None

    def to_dict(self):
        return {
            'version': '1.0',
            'zones': [z.to_dict() for z in self.zones]
        }

    @classmethod
    def from_dict(cls, data):
        col = cls()
        if isinstance(data, dict) and 'zones' in data:
            raw_zones = data['zones']
        elif isinstance(data, list):
            raw_zones = data
        else:
            raw_zones = []
        for d in raw_zones:
            if isinstance(d, dict):
                col.zones.append(VideoZone.from_dict(d))
        col.sort_zones()
        return col

    def save_to_file(self, file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


# ==============================================================================
# 1B. LEVEL CHAPTERS DATA MODEL (FOR TIMELINE PLACEMENT LIKE ZONES)
# ==============================================================================

DIFFICULTY_COLORS = {
    "Easy": {"color": "#10b981", "bg_color": "#064e3b", "icon": "smile"},
    "Normal": {"color": "#06b6d4", "bg_color": "#0e7490", "icon": "music"},
    "Hard": {"color": "#f59e0b", "bg_color": "#78350f", "icon": "zap"},
    "Expert": {"color": "#f43f5e", "bg_color": "#881337", "icon": "target"},
    "Master": {"color": "#a855f7", "bg_color": "#581c87", "icon": "award"},
}

class LevelChapter:
    """Represents a timed level segment on the timeline with custom name, level number, and difficulty."""
    def __init__(self, start_time, end_time, name="Level 1", level=1, difficulty="Normal"):
        self.id = str(uuid.uuid4())[:8]
        self.start_time = max(0.0, round(float(start_time), 3))
        self.end_time = max(self.start_time + 0.5, round(float(end_time), 3))
        self.name = str(name).strip() or f"Level {level}"
        self.level = int(level) if str(level).isdigit() else 1
        self.difficulty = str(difficulty) if difficulty in DIFFICULTY_COLORS else "Normal"

    @property
    def duration(self):
        return max(0.0, self.end_time - self.start_time)

    def contains(self, t):
        return self.start_time <= t <= self.end_time

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'level': self.level,
            'difficulty': self.difficulty,
            'start_time': self.start_time,
            'end_time': self.end_time
        }

    @classmethod
    def from_dict(cls, data):
        c = cls(
            start_time=data.get('start_time', data.get('start', 0.0)),
            end_time=data.get('end_time', data.get('end', 10.0)),
            name=data.get('name', 'Level 1'),
            level=data.get('level', 1),
            difficulty=data.get('difficulty', 'Normal')
        )
        if 'id' in data:
            c.id = str(data['id'])
        return c


class LevelsCollection:
    """Ordered collection of level chapters for the timeline."""
    def __init__(self):
        self.levels = []  # List of LevelChapter

    def __len__(self):
        return len(self.levels)

    def __iter__(self):
        return iter(self.levels)

    def __getitem__(self, idx):
        return self.levels[idx]

    def sort_levels(self):
        self.levels.sort(key=lambda c: c.start_time)

    def add_level(self, start_time, end_time, name="Level 1", level=1, difficulty="Normal"):
        st = max(0.0, round(float(start_time), 3))
        et = max(st + 0.5, round(float(end_time), 3))
        new_ch = LevelChapter(st, et, name, level, difficulty)
        updated = []
        for ch in self.levels:
            if ch.end_time <= new_ch.start_time:
                updated.append(ch)
            elif ch.start_time >= new_ch.end_time:
                updated.append(ch)
            else:
                if ch.start_time < new_ch.start_time and ch.end_time > new_ch.end_time:
                    left_p = LevelChapter(ch.start_time, new_ch.start_time, ch.name, ch.level, ch.difficulty)
                    right_p = LevelChapter(new_ch.end_time, ch.end_time, ch.name, ch.level, ch.difficulty)
                    updated.append(left_p)
                    updated.append(right_p)
                elif ch.start_time < new_ch.start_time:
                    ch.end_time = new_ch.start_time
                    if ch.duration >= 0.2:
                        updated.append(ch)
                elif ch.end_time > new_ch.end_time:
                    ch.start_time = new_ch.end_time
                    if ch.duration >= 0.2:
                        updated.append(ch)
        updated.append(new_ch)
        updated.sort(key=lambda x: x.start_time)
        self.levels = updated
        return new_ch

    def remove_level(self, ch_or_id):
        if isinstance(ch_or_id, LevelChapter):
            self.levels = [c for c in self.levels if c.id != ch_or_id.id]
        else:
            self.levels = [c for c in self.levels if c.id != str(ch_or_id)]

    def get_level_at(self, t):
        for c in self.levels:
            if c.contains(t):
                return c
        return None

    def to_list(self):
        return [c.to_dict() for c in self.levels]

    @classmethod
    def from_list(cls, data_list):
        col = cls()
        if isinstance(data_list, list):
            for d in data_list:
                if isinstance(d, dict):
                    col.levels.append(LevelChapter.from_dict(d))
        col.sort_levels()
        return col


# ==============================================================================
# 2. INTERACTIVE TIMELINE WIDGET (ZONES + LEVELS + BEATS)
# ==============================================================================

class ZonesTimelineWidget(QWidget):
    """
    Timeline painting:
    1. Timecode Ruler & Musical Bars (BPM-aligned).
    2. Beats Track (existing project beats & human reference beats).
    3. Video Zones Track (editable colored ribbons with resize & move handles).
    4. Playhead Needle (cyan tracking line synchronized with video player).
    """
    position_changed = pyqtSignal(float)      # Emits time in seconds on click/scrub
    zone_selected = pyqtSignal(object)        # Emits selected VideoZone or None
    zones_modified = pyqtSignal()             # Emits whenever zones are moved, resized, or created
    level_selected = pyqtSignal(object)      # Emits selected LevelChapter or None
    levels_modified = pyqtSignal()           # Emits whenever levels are moved, resized, or created
    track_visibility_changed = pyqtSignal(str, bool) # Emits (track_key, visible)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Core Data
        self.zones_collection = ZonesCollection()
        self.levels_collection = LevelsCollection()
        self.duration = 100.0
        self.bpm = 125.0
        self.phase = 0.105
        self.tr1_beats = []           # list of float (seconds, Track 1 / Lane 4 beats)
        self.tr2_beats = []           # list of float (seconds, Track 2 / Lane 1 beats)
        self.tr3_beats = []           # list of float (seconds, Track 3 / Lane 2 beats)
        self.video_parser_beats = [] # list of float (seconds, video beat parser)

        # Track Visibility Toggles (Track 1 only shown by default, Vid Parser hidden by default)
        self.show_tr1 = True
        self.show_tr2 = False
        self.show_tr3 = False
        self.show_vid = False
        self.show_zones = True
        self.show_levels = True

        # View Parameters
        self.zoom = 70.0           # Pixels per second
        self.scroll_x = 0          # Horizontal pixel offset
        self.current_time = 0.0    # Current playhead in seconds

        # Dynamic Layout Dimensions (recalculated based on active tracks)
        self.ruler_height = 28
        self.beats_track_y = 28
        self.beats_track_height = 128
        self.zones_track_y = 160
        self.zones_track_height = 68
        self.levels_track_y = 232
        self.levels_track_height = 64
        self.total_content_height = 304
        self.lane_info = {}

        # Compute initial layout
        self.recalculate_layout()

        # Interaction States for Zones
        self.selected_zone = None
        self.hovered_zone = None
        self.drag_mode = None      # None, 'create', 'move', 'resize_left', 'resize_right', 'scrub', 'level_create', 'level_move', 'level_resize_left', 'level_resize_right'
        self.drag_start_x = 0
        self.drag_start_time = 0.0
        self.drag_orig_zone_start = 0.0
        self.drag_orig_zone_end = 0.0
        self.create_start_time = 0.0
        self.current_create_time = 0.0
        self.drag_limit_min = 0.0
        self.drag_limit_max = 100.0

        # Interaction States for Levels
        self.selected_level = None
        self.hovered_level = None
        self.drag_orig_level_start = 0.0
        self.drag_orig_level_end = 0.0

    @property
    def project_beats(self):
        return self.tr1_beats

    @project_beats.setter
    def project_beats(self, val):
        self.tr1_beats = sorted(val or [])

    @property
    def v3_beats(self):
        return self.tr1_beats

    @property
    def v2_beats(self):
        return self.tr2_beats

    @v2_beats.setter
    def v2_beats(self, val):
        self.tr2_beats = sorted(val or [])

    @property
    def reference_beats(self):
        return []

    @reference_beats.setter
    def reference_beats(self, val):
        pass

    @property
    def show_v3(self):
        return self.show_tr1

    @show_v3.setter
    def show_v3(self, val):
        self.show_tr1 = val

    @property
    def show_v2(self):
        return self.show_tr2

    @show_v2.setter
    def show_v2(self, val):
        self.show_tr2 = val

    @property
    def show_ref(self):
        return False

    @show_ref.setter
    def show_ref(self, val):
        pass

    # -------------------------------------------------------------------------
    # Dynamic Layout Calculation
    # -------------------------------------------------------------------------
    def recalculate_layout(self):
        """Dynamically computes Y coordinates and heights for active tracks."""
        self.ruler_height = 28
        curr_y = self.ruler_height
        self.lane_info = {}
        lane_h = 32

        # 1. Beat Lanes (ordered: Track 1, Track 2, Track 3, Vid Parser)
        if self.show_tr1:
            self.lane_info['tr1'] = {'y_mid': curr_y + lane_h / 2.0, 'y_top': curr_y, 'height': lane_h}
            curr_y += lane_h
        if self.show_tr2:
            self.lane_info['tr2'] = {'y_mid': curr_y + lane_h / 2.0, 'y_top': curr_y, 'height': lane_h}
            curr_y += lane_h
        if self.show_tr3:
            self.lane_info['tr3'] = {'y_mid': curr_y + lane_h / 2.0, 'y_top': curr_y, 'height': lane_h}
            curr_y += lane_h
        if self.show_vid:
            self.lane_info['vid'] = {'y_mid': curr_y + lane_h / 2.0, 'y_top': curr_y, 'height': lane_h}
            curr_y += lane_h

        self.beats_track_y = self.ruler_height
        self.beats_track_height = curr_y - self.ruler_height

        # 2. Zones Track Ribbon
        if self.show_zones:
            self.zones_track_y = curr_y + 4
            self.zones_track_height = 68
            curr_y = self.zones_track_y + self.zones_track_height + 4
        else:
            self.zones_track_y = curr_y
            self.zones_track_height = 0
            curr_y += 4

        # 3. Levels Track Ribbon (Levels & Difficulty chapters)
        if self.show_levels:
            self.levels_track_y = curr_y + 4
            self.levels_track_height = 64
            curr_y = self.levels_track_y + self.levels_track_height + 8
        else:
            self.levels_track_y = curr_y
            self.levels_track_height = 0
            curr_y += 8

        self.total_content_height = max(220, int(curr_y))
        self.setMinimumHeight(self.total_content_height)
        self.update()

    def set_track_visible(self, track_name, visible: bool):
        attr_map = {
            'tr1': 'show_tr1',
            'tr2': 'show_tr2',
            'tr3': 'show_tr3',
            'v3': 'show_tr1',
            'v2': 'show_tr2',
            'vid': 'show_vid',
            'zones': 'show_zones',
            'levels': 'show_levels'
        }
        attr = attr_map.get(track_name)
        if attr and getattr(self, attr) != visible:
            setattr(self, attr, visible)
            self.recalculate_layout()
            self.track_visibility_changed.emit(track_name, visible)

    # -------------------------------------------------------------------------
    # Coordinate Transforms
    # -------------------------------------------------------------------------
    def time_to_x(self, t):
        return int(t * self.zoom) - self.scroll_x

    def x_to_time(self, x):
        t = (x + self.scroll_x) / max(1.0, self.zoom)
        return max(0.0, min(self.duration, t))

    def snap_to_beat(self, t):
        """Snaps time to the nearest musical subdivision (quarter note or eighth note)."""
        spb = 60.0 / self.bpm
        step = spb / 2.0  # Snap to eighths
        snapped = self.phase + round((t - self.phase) / step) * step
        return max(0.0, min(self.duration, round(snapped, 3)))

    # -------------------------------------------------------------------------
    # Setters
    # -------------------------------------------------------------------------
    def set_duration(self, duration):
        self.duration = max(1.0, float(duration))
        self.update()

    def set_bpm_phase(self, bpm, phase=0.0):
        self.bpm = max(30.0, float(bpm))
        self.phase = float(phase)
        self.update()

    def set_beats(self, tr1_beats=None, tr2_beats=None, tr3_beats=None, video_parser_beats=None,
                  project_beats=None, reference_beats=None, v2_beats=None):
        primary = tr1_beats if tr1_beats is not None else project_beats
        if primary is not None:
            if primary and isinstance(primary[0], dict):
                self.tr1_beats = sorted([float(b['time']) for b in primary if b.get('lane', 4) == 4])
                if tr2_beats is None and v2_beats is None:
                    self.tr2_beats = sorted([float(b['time']) for b in primary if b.get('lane', 4) == 1])
                if tr3_beats is None:
                    self.tr3_beats = sorted([float(b['time']) for b in primary if b.get('lane', 4) == 2])
            else:
                self.tr1_beats = sorted([float(b['time'] if isinstance(b, dict) else b) for b in primary])

        secondary = tr2_beats if tr2_beats is not None else v2_beats
        if secondary is not None:
            self.tr2_beats = sorted([float(b['time'] if isinstance(b, dict) else b) for b in secondary])

        if tr3_beats is not None:
            self.tr3_beats = sorted([float(b['time'] if isinstance(b, dict) else b) for b in tr3_beats])

        if video_parser_beats is not None:
            self.video_parser_beats = sorted([float(b['time'] if isinstance(b, dict) else b) for b in video_parser_beats])
        self.update()

    def set_current_time(self, t):
        self.current_time = max(0.0, min(self.duration, float(t)))
        self.update()

    def set_zoom(self, zoom):
        self.zoom = max(15.0, min(300.0, float(zoom)))
        self.update()

    def set_scroll_x(self, x):
        self.scroll_x = max(0, int(x))
        self.update()

    def select_zone(self, zone):
        self.selected_zone = zone
        if zone:
            self.selected_level = None
            self.level_selected.emit(None)
        self.zone_selected.emit(zone)
        self.update()

    def set_zones(self, zones_data):
        if isinstance(zones_data, ZonesCollection):
            self.zones_collection = zones_data
        elif zones_data:
            self.zones_collection = ZonesCollection.from_dict(zones_data)
        else:
            self.zones_collection = ZonesCollection()
        self.select_zone(None)
        self.zones_modified.emit()
        self.update()

    def get_zones(self):
        return [z.to_dict() for z in self.zones_collection.zones]

    def set_levels(self, levels_list):
        if not levels_list:
            self.levels_collection = LevelsCollection()
        else:
            self.levels_collection = LevelsCollection.from_list(levels_list)
        self.select_level(None)
        self.levels_modified.emit()
        self.update()

    def get_levels(self):
        return self.levels_collection.to_list()

    def select_level(self, level):
        self.selected_level = level
        if level:
            self.selected_zone = None
            self.zone_selected.emit(None)
        self.level_selected.emit(level)
        self.update()

    def hit_test_level(self, x, y):
        """Returns (level_chapter, edge_str) where edge_str is 'left', 'right', 'body', or None."""
        if not self.show_levels or self.levels_track_height <= 0:
            return None, None
        ly = self.levels_track_y
        lh = self.levels_track_height
        if not (ly <= y <= ly + lh):
            return None, None
        for ch in reversed(self.levels_collection.levels):
            cx0 = self.time_to_x(ch.start_time)
            cx1 = self.time_to_x(ch.end_time)
            if cx0 - 8 <= x <= cx1 + 8:
                if abs(x - cx0) <= 8:
                    return ch, 'left'
                elif abs(x - cx1) <= 8:
                    return ch, 'right'
                elif cx0 <= x <= cx1:
                    return ch, 'body'
        return None, None

    # -------------------------------------------------------------------------
    # Paint Event
    # -------------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Background
        painter.fillRect(0, 0, w, h, QColor("#121216"))

        # Time range visible
        t_start = max(0.0, self.x_to_time(0))
        t_end = min(self.duration, self.x_to_time(w) + 1.0)

        # 2. Musical Grid & Ruler
        self.paint_ruler_and_grid(painter, w, h, t_start, t_end)

        # 3. Beats Track
        self.paint_beats_track(painter, w, t_start, t_end)

        # 4. Zones Track
        self.paint_zones_track(painter, w, t_start, t_end)

        # 4b. Levels Track
        self.paint_levels_track(painter, w, t_start, t_end)

        # 5. Active Creation Preview (if dragging on empty space)
        if self.drag_mode == 'create':
            t0 = min(self.create_start_time, self.current_create_time)
            t1 = max(self.create_start_time, self.current_create_time)
            x0 = self.time_to_x(t0)
            x1 = self.time_to_x(t1)
            rect = QRectF(x0, self.zones_track_y, max(4.0, x1 - x0), self.zones_track_height)
            painter.setPen(QPen(QColor("#00d2ff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(0, 210, 255, 60)))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"+ New Zone: {t1 - t0:.2f}s")
        elif self.drag_mode == 'level_create':
            t0 = min(self.create_start_time, self.current_create_time)
            t1 = max(self.create_start_time, self.current_create_time)
            x0 = self.time_to_x(t0)
            x1 = self.time_to_x(t1)
            rect = QRectF(x0, self.levels_track_y + 20, max(4.0, x1 - x0), self.levels_track_height - 24)
            painter.setPen(QPen(QColor("#c084fc"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(192, 132, 252, 60)))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor("#ffffff"))
            font_preview = QFont("Segoe UI", 9)
            font_preview.setBold(True)
            painter.setFont(font_preview)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"+ New Level: {t1 - t0:.2f}s")

        # 6. Playhead Needle
        self.paint_playhead(painter, h)

    def paint_ruler_and_grid(self, painter, w, h, t_start, t_end):
        # Ruler background
        painter.fillRect(0, 0, w, self.ruler_height, QColor("#181820"))
        painter.setPen(QPen(QColor("#2d2d38"), 1))
        painter.drawLine(0, self.ruler_height, w, self.ruler_height)

        # Musical measures (Bars)
        spb = 60.0 / self.bpm
        bar_len = spb * 4.0  # 4/4 measure

        k_start = int(max(0, (t_start - self.phase) // spb))
        k_end = int((t_end - self.phase) // spb) + 2

        font_ruler = QFont("Segoe UI", 8)
        font_ruler.setBold(True)
        painter.setFont(font_ruler)

        for k in range(k_start, k_end):
            t_beat = self.phase + k * spb
            if t_beat < 0 or t_beat > self.duration:
                continue

            x = self.time_to_x(t_beat)
            is_downbeat = (k % 4 == 0)

            if is_downbeat:
                # Major Bar Line
                painter.setPen(QPen(QColor("#3a3a4c"), 1))
                painter.drawLine(x, 0, x, h)

                # Bar Number & Time Label
                bar_num = (k // 4) + 1
                painter.setPen(QColor("#00ffff"))
                painter.drawText(x + 4, 13, f"B{bar_num}")
                painter.setPen(QColor("#808098"))
                painter.drawText(x + 4, 23, f"{int(t_beat//60):02d}:{t_beat%60:04.1f}")
            else:
                # Minor Beat Line
                painter.setPen(QPen(QColor("#20202a"), 1))
                painter.drawLine(x, self.ruler_height, x, h)
                painter.drawLine(x, self.ruler_height - 6, x, self.ruler_height)

    def paint_beats_track(self, painter, w, t_start, t_end):
        if self.beats_track_height <= 0:
            return

        y0 = self.beats_track_y
        h0 = self.beats_track_height

        # Track background
        painter.fillRect(0, y0, w, h0, QColor("#14141a"))
        painter.setPen(QPen(QColor("#262632"), 1))
        painter.drawLine(0, y0 + h0, w, y0 + h0)

        # Draw each visible beat track sub-lane divider and baseline
        for key, lane in self.lane_info.items():
            y_top = int(lane['y_top'])
            y_mid = lane['y_mid']

            # Divider line between sub-lanes
            painter.setPen(QPen(QColor("#1e1e28"), 1))
            painter.drawLine(0, y_top, w, y_top)

            # Subtle sub-lane baseline guide line
            painter.setPen(QPen(QColor("#181822"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(0, int(y_mid), w, int(y_mid))

        # 1. Paint Track 1 Beats (Purple circles with white outline)
        if self.show_tr1 and 'tr1' in self.lane_info and self.tr1_beats:
            y_mid = self.lane_info['tr1']['y_mid']
            painter.setPen(QPen(QColor("#ffffff"), 1.4))
            painter.setBrush(QBrush(QColor("#b10dc9")))
            for bt in self.tr1_beats:
                if bt < t_start or bt > t_end:
                    continue
                bx = self.time_to_x(bt)
                painter.drawEllipse(QPointF(bx, y_mid), 6.5, 6.5)

        # 2. Paint Track 2 Beats (Cyan diamonds)
        if self.show_tr2 and 'tr2' in self.lane_info and self.tr2_beats:
            y_mid = self.lane_info['tr2']['y_mid']
            painter.setPen(QPen(QColor("#80f0ff"), 1.2))
            painter.setBrush(QBrush(QColor(0, 229, 255, 220)))
            for bt in self.tr2_beats:
                if bt < t_start or bt > t_end:
                    continue
                bx = self.time_to_x(bt)
                poly = QPolygonF([
                    QPointF(bx, y_mid - 6), QPointF(bx + 6, y_mid),
                    QPointF(bx, y_mid + 6), QPointF(bx - 6, y_mid)
                ])
                painter.drawPolygon(poly)

        # 3. Paint Track 3 Beats (Amber upward triangles)
        if self.show_tr3 and 'tr3' in self.lane_info and self.tr3_beats:
            y_mid = self.lane_info['tr3']['y_mid']
            painter.setPen(QPen(QColor("#ffd000"), 1.2))
            painter.setBrush(QBrush(QColor(255, 179, 0, 220)))
            for bt in self.tr3_beats:
                if bt < t_start or bt > t_end:
                    continue
                bx = self.time_to_x(bt)
                poly = QPolygonF([
                    QPointF(bx, y_mid - 6.5),
                    QPointF(bx + 6, y_mid + 5.5),
                    QPointF(bx - 6, y_mid + 5.5)
                ])
                painter.drawPolygon(poly)

        # 4. Paint Video Parser Beats (Gold/Amber rounded squares)
        if self.show_vid and 'vid' in self.lane_info and self.video_parser_beats:
            y_mid = self.lane_info['vid']['y_mid']
            painter.setPen(QPen(QColor("#ffea00"), 1.2))
            painter.setBrush(QBrush(QColor(255, 208, 0, 220)))
            for vt in self.video_parser_beats:
                if vt < t_start or vt > t_end:
                    continue
                vx = self.time_to_x(vt)
                painter.drawRoundedRect(QRectF(vx - 5, y_mid - 5, 10, 10), 2.5, 2.5)

        # 5. Pinned Left Header Labels (Frozen on the left so they never scroll off)
        badge_w = 142
        painter.fillRect(0, y0, badge_w, h0, QColor(18, 18, 24, 242))
        painter.setPen(QPen(QColor("#2d2d3c"), 1))
        painter.drawLine(badge_w, y0, badge_w, y0 + h0)

        font_label = QFont("Segoe UI", 8)
        font_label.setBold(True)
        painter.setFont(font_label)

        track_defs = [
            ('tr1', 'zap', '#d488ff', 'Track 1', len(self.tr1_beats)),
            ('tr2', 'music', '#00e5ff', 'Track 2', len(self.tr2_beats)),
            ('tr3', 'activity', '#ffb300', 'Track 3', len(self.tr3_beats)),
            ('vid', 'video', '#ffd000', 'Vid Parser', len(self.video_parser_beats)),
        ]

        for key, icon_name, color_hex, label_title, count in track_defs:
            if key not in self.lane_info:
                continue
            lane = self.lane_info[key]
            y_top = int(lane['y_top'])
            y_mid = lane['y_mid']

            # Divider line
            painter.setPen(QPen(QColor("#2d2d3c"), 1))
            painter.drawLine(0, y_top, badge_w, y_top)

            # Left Feather Icon
            draw_feather_icon(painter, icon_name, QRectF(8, y_mid - 7, 14, 14), color_hex)

            # Label text
            painter.setPen(QColor(color_hex))
            count_str = f" ({count})" if count > 0 else " (0)"
            painter.drawText(
                QRectF(26, y_mid - 10, 88, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{label_title}{count_str}"
            )

            # Right eye toggle icon
            draw_feather_icon(painter, "eye", QRectF(120, y_mid - 7, 14, 14), color_hex)

    def paint_zones_track(self, painter, w, t_start, t_end):
        if not self.show_zones or self.zones_track_height <= 0:
            return

        y0 = self.zones_track_y
        h0 = self.zones_track_height

        # Track background
        painter.fillRect(0, y0, w, h0, QColor("#111116"))
        painter.setPen(QPen(QColor("#2a2a38"), 1))
        painter.drawLine(0, y0 + h0, w, y0 + h0)

        # Track header with Feather icon
        draw_feather_icon(painter, "layers", QRectF(8, y0 + 3, 14, 14), "#707085")
        painter.setPen(QColor("#707085"))
        font_header = QFont("Segoe UI", 8)
        font_header.setBold(True)
        painter.setFont(font_header)
        painter.drawText(26, y0 + 15, "VIDEO & RHYTHM ZONES (CLICK & DRAG TO CREATE)")

        # Render Zones
        for zone in self.zones_collection.zones:
            if zone.end_time < t_start or zone.start_time > t_end:
                continue

            zx0 = self.time_to_x(zone.start_time)
            zx1 = self.time_to_x(zone.end_time)
            zw = max(8.0, zx1 - zx0)
            zy = y0 + 22
            zh = h0 - 28

            rect = QRectF(zx0, zy, zw, zh)
            zinfo = ZONE_TYPES.get(zone.zone_type, ZONE_TYPES["normal"])
            base_color = QColor(zinfo["color"])
            bg_color = QColor(zinfo["bg_color"])

            is_sel = (zone == self.selected_zone)
            is_hov = (zone == self.hovered_zone)

            # Zone Body Gradient
            grad = QLinearGradient(zx0, zy, zx0, zy + zh)
            if is_sel:
                grad.setColorAt(0, base_color.lighter(130))
                grad.setColorAt(1, bg_color.lighter(150))
            else:
                grad.setColorAt(0, base_color.darker(110))
                grad.setColorAt(1, bg_color)

            painter.setBrush(QBrush(grad))
            pen_border = QPen(base_color if not is_sel else QColor("#ffffff"), 2 if is_sel else 1.2)
            painter.setPen(pen_border)
            painter.drawRoundedRect(rect, 6, 6)

            # Left & Right Resize Handles if selected or hovered
            if is_sel or is_hov:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
                # Left handle bar
                painter.drawRoundedRect(QRectF(zx0 + 2, zy + 6, 3, zh - 12), 1.5, 1.5)
                # Right handle bar
                painter.drawRoundedRect(QRectF(zx0 + zw - 5, zy + 6, 3, zh - 12), 1.5, 1.5)

            # Zone Feather Icon
            feather_name = zinfo.get("feather_icon", "music")
            draw_feather_icon(painter, feather_name, QRectF(zx0 + 8, zy + (zh - 14) / 2.0, 14, 14), "#ffffff")

            # Zone Label & Duration
            painter.setPen(QColor("#ffffff"))
            font_zone = QFont("Segoe UI", 9)
            font_zone.setBold(True)
            painter.setFont(font_zone)

            label_text = f"{zone.label} ({zone.duration:.2f}s)"
            text_rect = QRectF(zx0 + 26, zy, max(10.0, zw - 32), zh)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label_text)

    def paint_levels_track(self, painter, w, t_start, t_end):
        if not self.show_levels or self.levels_track_height <= 0:
            return

        y0 = self.levels_track_y
        h0 = self.levels_track_height

        # Track background
        painter.fillRect(0, y0, w, h0, QColor("#141118"))
        painter.setPen(QPen(QColor("#382a44"), 1))
        painter.drawLine(0, y0 + h0, w, y0 + h0)

        # Track header with Feather icon
        draw_feather_icon(painter, "award", QRectF(8, y0 + 3, 14, 14), "#c084fc")
        painter.setPen(QColor("#c084fc"))
        font_header = QFont("Segoe UI", 8)
        font_header.setBold(True)
        painter.setFont(font_header)
        painter.drawText(26, y0 + 15, "SECTIONS & DIFFICULTY (CLICK & DRAG TO CREATE)")

        # Render Level Chapters
        for ch in self.levels_collection.levels:
            if ch.end_time < t_start or ch.start_time > t_end:
                continue

            cx0 = self.time_to_x(ch.start_time)
            cx1 = self.time_to_x(ch.end_time)
            cw = max(8.0, cx1 - cx0)
            cy = y0 + 20
            ch_h = h0 - 24

            rect = QRectF(cx0, cy, cw, ch_h)
            dinfo = DIFFICULTY_COLORS.get(ch.difficulty, DIFFICULTY_COLORS["Normal"])
            base_color = QColor(dinfo["color"])
            bg_color = QColor(dinfo["bg_color"])

            is_sel = (ch == self.selected_level)
            is_hov = (ch == self.hovered_level)

            # Gradient
            grad = QLinearGradient(cx0, cy, cx0, cy + ch_h)
            if is_sel:
                grad.setColorAt(0, base_color.lighter(130))
                grad.setColorAt(1, bg_color.lighter(140))
            else:
                grad.setColorAt(0, base_color.darker(110))
                grad.setColorAt(1, bg_color)

            painter.setBrush(QBrush(grad))
            pen_border = QPen(QColor("#ffffff") if is_sel else base_color, 2 if is_sel else 1.2)
            painter.setPen(pen_border)
            painter.drawRoundedRect(rect, 6, 6)

            # Left & Right Resize Handles if selected or hovered
            if is_sel or is_hov:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
                painter.drawRoundedRect(QRectF(cx0 + 2, cy + 5, 3, ch_h - 10), 1.5, 1.5)
                painter.drawRoundedRect(QRectF(cx0 + cw - 5, cy + 5, 3, ch_h - 10), 1.5, 1.5)

            # Icon
            feather_name = dinfo.get("icon", "award")
            draw_feather_icon(painter, feather_name, QRectF(cx0 + 8, cy + (ch_h - 14) / 2.0, 14, 14), "#ffffff")

            # Label text
            painter.setPen(QColor("#ffffff"))
            font_lvl = QFont("Segoe UI", 9)
            font_lvl.setBold(True)
            painter.setFont(font_lvl)
            label_text = f"{ch.name} • {ch.difficulty} ({ch.duration:.2f}s)"
            text_rect = QRectF(cx0 + 26, cy, max(10.0, cw - 32), ch_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label_text)

    def paint_playhead(self, painter, h):
        px = self.time_to_x(self.current_time)
        if -5 <= px <= self.width() + 5:
            # Playhead needle line
            painter.setPen(QPen(QColor("#00ffff"), 2))
            painter.drawLine(px, 0, px, h)

            # Triangular cursor head on ruler
            poly = QPolygonF([
                QPointF(px - 6, 0),
                QPointF(px + 6, 0),
                QPointF(px, 12)
            ])
            painter.setBrush(QBrush(QColor("#00ffff")))
            painter.drawPolygon(poly)

    # -------------------------------------------------------------------------
    # Mouse Interaction
    # -------------------------------------------------------------------------
    def hit_test_badge_eye(self, x, y):
        """Returns track_key if click falls on the eye icon in the pinned badge (x in [112, 140])."""
        if x < 112 or x > 140:
            return None
        for key, lane in self.lane_info.items():
            if lane['y_top'] <= y <= lane['y_top'] + lane['height']:
                return key
        return None

    def mousePressEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        t = self.x_to_time(x)

        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked on badge eye icon to hide track
            eye_track = self.hit_test_badge_eye(x, y)
            if eye_track:
                self.set_track_visible(eye_track, False)
                return

            min_y = min(
                self.zones_track_y if self.show_zones else 9999,
                self.levels_track_y if self.show_levels else 9999
            )
            # Check if clicked on ruler or beats track -> Seek Playhead
            if y < min_y:
                self.drag_mode = 'scrub'
                self.position_changed.emit(t)
                return

            # Check if clicked on Zones track
            if self.show_zones and self.zones_track_y <= y < self.zones_track_y + self.zones_track_height:
                hit_zone, edge = self.hit_test_zone(x, y)
                if hit_zone:
                    self.select_zone(hit_zone)
                    self.drag_start_x = x
                    self.drag_start_time = t
                    self.drag_orig_zone_start = hit_zone.start_time
                    self.drag_orig_zone_end = hit_zone.end_time

                    # Compute neighbor clamping bounds so zone never collides or overlaps with adjacent zones
                    other_zones = [z for z in self.zones_collection.zones if z.id != hit_zone.id]
                    left_bounds = [z.end_time for z in other_zones if z.end_time <= hit_zone.start_time + 0.05]
                    self.drag_limit_min = max(0.0, max(left_bounds)) if left_bounds else 0.0
                    right_bounds = [z.start_time for z in other_zones if z.start_time >= hit_zone.end_time - 0.05]
                    self.drag_limit_max = min(self.duration, min(right_bounds)) if right_bounds else self.duration

                    if edge == 'left':
                        self.drag_mode = 'resize_left'
                    elif edge == 'right':
                        self.drag_mode = 'resize_right'
                    else:
                        self.drag_mode = 'move'
                else:
                    # Clicked on empty zones track -> Start creating new zone!
                    self.select_zone(None)
                    self.drag_mode = 'create'
                    self.create_start_time = self.snap_to_beat(t)
                    self.current_create_time = self.create_start_time
                return

            # Check if clicked on Levels track
            if self.show_levels and self.levels_track_y <= y < self.levels_track_y + self.levels_track_height:
                hit_level, edge = self.hit_test_level(x, y)
                if hit_level:
                    self.select_level(hit_level)
                    self.drag_start_x = x
                    self.drag_start_time = t
                    self.drag_orig_level_start = hit_level.start_time
                    self.drag_orig_level_end = hit_level.end_time

                    other_lvls = [c for c in self.levels_collection.levels if c.id != hit_level.id]
                    left_b = [c.end_time for c in other_lvls if c.end_time <= hit_level.start_time + 0.05]
                    self.drag_limit_min = max(0.0, max(left_b)) if left_b else 0.0
                    right_b = [c.start_time for c in other_lvls if c.start_time >= hit_level.end_time - 0.05]
                    self.drag_limit_max = min(self.duration, min(right_b)) if right_b else self.duration

                    if edge == 'left':
                        self.drag_mode = 'level_resize_left'
                    elif edge == 'right':
                        self.drag_mode = 'level_resize_right'
                    else:
                        self.drag_mode = 'level_move'
                else:
                    self.select_level(None)
                    self.drag_mode = 'level_create'
                    self.create_start_time = self.snap_to_beat(t)
                    self.current_create_time = self.create_start_time
                return

        elif event.button() == Qt.MouseButton.RightButton:
            # Right-click context menu
            hit_zone, _ = self.hit_test_zone(x, y)
            if hit_zone:
                self.select_zone(hit_zone)
                self.show_zone_context_menu(hit_zone, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        t = self.x_to_time(x)

        if self.drag_mode == 'scrub':
            self.position_changed.emit(t)

        elif self.drag_mode == 'create':
            self.current_create_time = self.snap_to_beat(t)
            self.update()

        elif self.drag_mode == 'move' and self.selected_zone:
            dt = t - self.drag_start_time
            dur = self.drag_orig_zone_end - self.drag_orig_zone_start
            raw_start = self.drag_orig_zone_start + dt
            new_start = self.snap_to_beat(raw_start)
            min_s = getattr(self, 'drag_limit_min', 0.0)
            max_s = max(min_s, getattr(self, 'drag_limit_max', self.duration) - dur)
            clamped_start = max(min_s, min(max_s, new_start))
            self.selected_zone.start_time = round(clamped_start, 3)
            self.selected_zone.end_time = round(clamped_start + dur, 3)
            self.zones_collection.sort_zones()
            self.zones_modified.emit()
            self.update()

        elif self.drag_mode == 'resize_left' and self.selected_zone:
            new_start = self.snap_to_beat(t)
            min_s = getattr(self, 'drag_limit_min', 0.0)
            max_s = self.drag_orig_zone_end - 0.25
            clamped_start = max(min_s, min(max_s, new_start))
            self.selected_zone.start_time = round(clamped_start, 3)
            self.zones_collection.sort_zones()
            self.zones_modified.emit()
            self.update()

        elif self.drag_mode == 'resize_right' and self.selected_zone:
            new_end = self.snap_to_beat(t)
            min_e = self.drag_orig_zone_start + 0.25
            max_e = getattr(self, 'drag_limit_max', self.duration)
            clamped_end = max(min_e, min(max_e, new_end))
            self.selected_zone.end_time = round(clamped_end, 3)
            self.zones_collection.sort_zones()
            self.zones_modified.emit()
            self.update()

        elif self.drag_mode == 'level_create':
            self.current_create_time = self.snap_to_beat(t)
            self.update()

        elif self.drag_mode == 'level_move' and self.selected_level:
            dt = t - self.drag_start_time
            dur = self.drag_orig_level_end - self.drag_orig_level_start
            raw_start = self.drag_orig_level_start + dt
            new_start = self.snap_to_beat(raw_start)
            min_s = getattr(self, 'drag_limit_min', 0.0)
            max_s = max(min_s, getattr(self, 'drag_limit_max', self.duration) - dur)
            clamped_start = max(min_s, min(max_s, new_start))
            self.selected_level.start_time = round(clamped_start, 3)
            self.selected_level.end_time = round(clamped_start + dur, 3)
            self.levels_collection.sort_levels()
            self.levels_modified.emit()
            self.update()

        elif self.drag_mode == 'level_resize_left' and self.selected_level:
            new_start = self.snap_to_beat(t)
            min_s = getattr(self, 'drag_limit_min', 0.0)
            max_s = self.drag_orig_level_end - 0.5
            clamped_start = max(min_s, min(max_s, new_start))
            self.selected_level.start_time = round(clamped_start, 3)
            self.levels_collection.sort_levels()
            self.levels_modified.emit()
            self.update()

        elif self.drag_mode == 'level_resize_right' and self.selected_level:
            new_end = self.snap_to_beat(t)
            min_e = self.drag_orig_level_start + 0.5
            max_e = getattr(self, 'drag_limit_max', self.duration)
            clamped_end = max(min_e, min(max_e, new_end))
            self.selected_level.end_time = round(clamped_end, 3)
            self.levels_collection.sort_levels()
            self.levels_modified.emit()
            self.update()

        else:
            # Hover detection & Cursor updating
            eye_track = self.hit_test_badge_eye(x, y)
            if eye_track:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                self.update()
                return

            hit_zone, edge_z = self.hit_test_zone(x, y)
            hit_level, edge_l = self.hit_test_level(x, y)
            self.hovered_zone = hit_zone
            self.hovered_level = hit_level

            if edge_z in ('left', 'right') or edge_l in ('left', 'right'):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif hit_zone or hit_level:
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            elif (self.show_zones and self.zones_track_y <= y < self.zones_track_y + self.zones_track_height) or \
                 (self.show_levels and self.levels_track_y <= y < self.levels_track_y + self.levels_track_height):
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_mode == 'create':
            t0 = min(self.create_start_time, self.current_create_time)
            t1 = max(self.create_start_time, self.current_create_time)
            if t1 - t0 >= 0.25:
                new_zone = self.zones_collection.add_zone(t0, t1, zone_type="normal")
                self.select_zone(new_zone)
                self.zones_modified.emit()
        elif self.drag_mode in ('move', 'resize_left', 'resize_right'):
            self.zones_collection.sanitize_no_overlaps()
            self.zones_modified.emit()
        elif self.drag_mode == 'level_create':
            t0 = min(self.create_start_time, self.current_create_time)
            t1 = max(self.create_start_time, self.current_create_time)
            if t1 - t0 >= 0.25:
                curr_count = len(self.levels_collection)
                next_lvl = curr_count + 1
                default_name = f"Section {next_lvl}"
                new_ch = self.levels_collection.add_level(t0, t1, default_name, next_lvl, "Normal")
                self.select_level(new_ch)
                self.levels_modified.emit()
            else:
                if not self.selected_level and len(self.levels_collection) > 0:
                    closest = min(self.levels_collection.levels, key=lambda c: min(abs(t0 - c.start_time), abs(t0 - c.end_time)))
                    self.select_level(closest)
        elif self.drag_mode in ('level_move', 'level_resize_left', 'level_resize_right'):
            self.levels_collection.sort_levels()
            self.levels_modified.emit()
        self.drag_mode = None
        self.update()

    def hit_test_zone(self, x, y):
        """Returns (zone, edge_str) where edge_str is 'left', 'right', 'body', or None."""
        if not self.show_zones or self.zones_track_height <= 0:
            return None, None
        zy = self.zones_track_y + 22
        zh = self.zones_track_height - 28
        if not (zy <= y <= zy + zh):
            return None, None

        for zone in reversed(self.zones_collection.zones):
            zx0 = self.time_to_x(zone.start_time)
            zx1 = self.time_to_x(zone.end_time)
            if zx0 - 6 <= x <= zx1 + 6:
                if abs(x - zx0) <= 6:
                    return zone, 'left'
                elif abs(x - zx1) <= 6:
                    return zone, 'right'
                elif zx0 < x < zx1:
                    return zone, 'body'
        return None, None

    def show_zone_context_menu(self, zone, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e26;
                color: #e0e0e0;
                border: 1px solid #3c3c4e;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #8a2be2;
                color: #ffffff;
            }
        """)

        # Change Type Submenu
        sub_type = menu.addMenu("Set Zone Type")
        for key, info in ZONE_TYPES.items():
            feather_name = info.get("feather_icon", "music")
            act = sub_type.addAction(get_feather_icon(feather_name, info["color"], 14), info["name"])
            act.triggered.connect(lambda checked, z=zone, k=key: self.set_zone_type(z, k))

        menu.addSeparator()

        # Split Zone at Playhead
        if zone.start_time < self.current_time < zone.end_time:
            act_split = menu.addAction(get_feather_icon("scissors", "#00ffff", 14), "Split Zone at Playhead")
            act_split.triggered.connect(lambda: self.split_zone_at(zone, self.current_time))

        # Delete Zone
        act_del = menu.addAction(get_feather_icon("trash-2", "#ff6b62", 14), "Delete Zone")
        act_del.triggered.connect(lambda: self.delete_zone(zone))

        menu.exec(global_pos)

    def set_zone_type(self, zone, new_type):
        if zone and new_type in ZONE_TYPES:
            zone.zone_type = new_type
            zone.label = ZONE_TYPES[new_type]["name"]
            self.zones_modified.emit()
            self.update()

    def split_zone_at(self, zone, t):
        if zone.start_time + 0.1 < t < zone.end_time - 0.1:
            orig_end = zone.end_time
            zone.end_time = round(t, 3)
            new_z = self.zones_collection.add_zone(round(t, 3), orig_end, zone.zone_type)
            self.select_zone(new_z)
            self.zones_modified.emit()
            self.update()

    def delete_zone(self, zone):
        if zone:
            self.zones_collection.remove_zone(zone.id)
            if self.selected_zone == zone:
                self.selected_zone = None
                self.zone_selected.emit(None)
            self.zones_modified.emit()
            self.update()

    def delete_level(self, level):
        if not level:
            return
        self.levels_collection.remove_level(level)
        self.select_level(None)
        self.levels_modified.emit()
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_zone:
                self.delete_zone(self.selected_zone)
                return
            elif self.selected_level:
                self.delete_level(self.selected_level)
                return
        elif key == Qt.Key.Key_Space:
            # Parent dialog handles space for video play/pause
            event.ignore()
        elif key == Qt.Key.Key_1 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "normal")
        elif key == Qt.Key.Key_2 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "speeding_up")
        elif key == Qt.Key.Key_3 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "slowing")
        elif key == Qt.Key.Key_4 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "pause")
        elif key == Qt.Key.Key_5 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "climax")
        elif key == Qt.Key.Key_6 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "edging")
        elif key == Qt.Key.Key_7 and self.selected_zone:
            self.set_zone_type(self.selected_zone, "credits")
        else:
            super().keyPressEvent(event)


# ==============================================================================
# 3. MAIN VIDEO & RHYTHM ZONES DIALOG
# ==============================================================================

class VideoZonesEditorDialog(QDialog):
    """
    Dedicated Window for Video Previewing, Zone Management, and V3 Rhythm Generation.
    """
    def __init__(self, media_path, duration=100.0, bpm=125.0, phase=0.0, initial_beats=None,
                 waveform_envelope=None, existing_beats=None, video_parser_beats=None,
                 initial_level=1, initial_difficulty="Normal", parent=None,
                 initial_levels=None, initial_level_mode="ramp_within_level",
                 initial_zones=None, tr1_beats=None, tr2_beats=None, tr3_beats=None,
                 audio_path=None):
        super().__init__(parent)
        self.setWindowTitle("Video & Rhythm Zones Editor - Beatmaker Pro")
        self.setWindowIcon(get_feather_icon("video", "#00ffff", 24))
        self.resize(1260, 780)
        self.setMinimumSize(950, 620)

        self.media_path = media_path
        self.audio_path = audio_path
        if not self.audio_path and self.media_path:
            ext = os.path.splitext(self.media_path)[1].lower()
            if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v']:
                base = os.path.splitext(self.media_path)[0]
                for aext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a']:
                    candidate = base + aext
                    if os.path.exists(candidate) and os.path.getsize(candidate) > 1024:
                        self.audio_path = candidate
                        break
        if not self.audio_path:
            self.audio_path = self.media_path

        self.duration = max(1.0, float(duration))
        self.bpm = max(30.0, float(bpm))
        self.phase = float(phase)

        # Multi-Track Project Beats initialization
        if tr1_beats is not None:
            self.tr1_beats = list(tr1_beats)
        elif initial_beats is not None or existing_beats is not None:
            raw_b = initial_beats if initial_beats is not None else existing_beats
            if raw_b and isinstance(raw_b[0], dict):
                self.tr1_beats = [float(b['time']) for b in raw_b if b.get('lane', 4) == 4]
            else:
                self.tr1_beats = [float(b['time'] if isinstance(b, dict) else b) for b in raw_b]
        elif parent and hasattr(parent, 'timeline') and hasattr(parent.timeline, 'beats'):
            self.tr1_beats = [float(b['time']) for b in parent.timeline.beats if b.get('lane', 4) == 4]
        else:
            self.tr1_beats = []

        if tr2_beats is not None:
            self.tr2_beats = list(tr2_beats)
        elif parent and hasattr(parent, 'timeline') and hasattr(parent.timeline, 'beats'):
            self.tr2_beats = [float(b['time']) for b in parent.timeline.beats if b.get('lane', 4) == 1]
        else:
            self.tr2_beats = []

        if tr3_beats is not None:
            self.tr3_beats = list(tr3_beats)
        elif parent and hasattr(parent, 'timeline') and hasattr(parent.timeline, 'beats'):
            self.tr3_beats = [float(b['time']) for b in parent.timeline.beats if b.get('lane', 4) == 2]
        else:
            self.tr3_beats = []

        self.resulting_beats = list(self.tr1_beats)
        self.generated_beats = list(self.tr1_beats)
        self._backup_v3_beats = list(self.tr1_beats)
        self.video_parser_beats = list(video_parser_beats or [])
        self.waveform_envelope = waveform_envelope
        self.initial_level = initial_level or 1
        self.initial_difficulty = initial_difficulty or "Normal"
        self.initial_levels = initial_levels
        self.initial_level_mode = initial_level_mode or "ramp_within_level"
        self.initial_zones = initial_zones
        self.resulting_level = self.initial_level
        self.resulting_difficulty = self.initial_difficulty
        self.resulting_levels = list(initial_levels) if initial_levels else []
        self.resulting_level_mode = self.initial_level_mode
        self.difficulty_stats = {}
        self._is_closing = False

        self.setup_styling()
        self.setup_ui()
        self.setup_media_player()

        # Sync beats to timeline
        self.timeline_widget.set_beats(
            tr1_beats=self.tr1_beats,
            tr2_beats=self.tr2_beats,
            tr3_beats=self.tr3_beats,
            video_parser_beats=self.video_parser_beats
        )
        self.update_inspector_stats()

    def setup_styling(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #121216;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: #202028;
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                color: #e0e0e8;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2d2d3a;
                border-color: #00d2ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #16161e;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #1a1a22;
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                color: #00ffff;
                padding: 4px 6px;
                font-weight: bold;
            }
            QComboBox {
                background-color: #1a1a22;
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #1a1a22;
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
            }
            QLabel {
                font-size: 11px;
                color: #a0a0b0;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #14141c;
                border: 1px solid #282836;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0077b6, stop:1 #00f3ff);
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: #181822;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.65 #00f3ff, stop:1.0 #0077b6);
                border: 2px solid #00f3ff;
                width: 15px;
                height: 15px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.75 #ffffff, stop:1.0 #00f3ff);
                border: 2px solid #ffffff;
            }
            QSlider::handle:horizontal:pressed {
                background: #00f3ff;
                border: 2px solid #ffffff;
            }
            QScrollBar:horizontal {
                background: #141418;
                height: 12px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #323240;
                min-width: 25px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #00d2ff;
            }
        """)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # ---------------------------------------------------------------------
        # Top Splitter: Video Player (Left) + Zone Inspector / Controls (Right)
        # ---------------------------------------------------------------------
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Video Player Panel (occupies min 25-30% height on top)
        video_container = QWidget()
        v_layout = QVBoxLayout(video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(6)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(440, 240)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v_layout.addWidget(self.video_widget)

        # Transport Bar with Feather Icons, Speed & Volume Controls
        transport_bar = QHBoxLayout()
        transport_bar.setSpacing(6)

        self.btn_play = QPushButton("Play")
        self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self.toggle_play)
        transport_bar.addWidget(self.btn_play)

        btn_step_back = QPushButton("-1s")
        btn_step_back.setIcon(get_feather_icon("rewind", "#ffffff", 14))
        btn_step_back.clicked.connect(lambda: self.seek_relative(-1.0))
        transport_bar.addWidget(btn_step_back)

        btn_step_fwd = QPushButton("+1s")
        btn_step_fwd.setIcon(get_feather_icon("fast-forward", "#ffffff", 14))
        btn_step_fwd.clicked.connect(lambda: self.seek_relative(1.0))
        transport_bar.addWidget(btn_step_fwd)

        self.cb_speed = QComboBox()
        self.cb_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x (Normal)", "1.25x", "1.5x", "2.0x"])
        self.cb_speed.setCurrentIndex(3)
        self.cb_speed.currentIndexChanged.connect(self.on_speed_changed)
        transport_bar.addWidget(self.cb_speed)

        # Volume control (Mute button + slider)
        self.btn_mute = QPushButton()
        self.btn_mute.setFixedSize(30, 26)
        self.btn_mute.setIcon(get_feather_icon("volume-2", "#00ffff", 15))
        self.btn_mute.setToolTip("Mute / Unmute audio")
        self.btn_mute.clicked.connect(self.toggle_mute)
        transport_bar.addWidget(self.btn_mute)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(80)
        self.slider_volume.setFixedWidth(80)
        self.slider_volume.setToolTip("Playback Volume")
        self.slider_volume.valueChanged.connect(self.on_volume_changed)
        transport_bar.addWidget(self.slider_volume)

        transport_bar.addStretch()

        self.lbl_timecode = QLabel("00:00.000 / 00:00.000")
        self.lbl_timecode.setStyleSheet("color: #00ffff; font-family: monospace; font-size: 12px; font-weight: bold;")
        transport_bar.addWidget(self.lbl_timecode)

        v_layout.addLayout(transport_bar)
        top_splitter.addWidget(video_container)

        # 2. Zone Inspector & Settings Panel
        inspector_container = QWidget()
        insp_layout = QVBoxLayout(inspector_container)
        insp_layout.setContentsMargins(8, 0, 0, 0)
        insp_layout.setSpacing(8)

        # Header Info
        lbl_insp_title = QLabel("<b>ZONE INSPECTOR & ACTIONS</b>")
        lbl_insp_title.setStyleSheet("color: #ffffff; font-size: 12px;")
        insp_layout.addWidget(lbl_insp_title)

        # Zone Type Selection with Feather SVG Icons
        zone_type_box = QHBoxLayout()
        zone_type_box.addWidget(QLabel("Zone Type:"))
        self.cb_zone_type = QComboBox()
        for k, info in ZONE_TYPES.items():
            feather_name = info.get("feather_icon", "music")
            self.cb_zone_type.addItem(get_feather_icon(feather_name, info["color"], 14), info["name"], k)
        self.cb_zone_type.currentIndexChanged.connect(self.on_zone_type_combo_changed)
        zone_type_box.addWidget(self.cb_zone_type)
        insp_layout.addLayout(zone_type_box)

        # Zone Description Label
        self.lbl_zone_desc = QLabel("Select or create a zone on the timeline to inspect.")
        self.lbl_zone_desc.setStyleSheet("color: #888899; font-size: 10px;")
        self.lbl_zone_desc.setWordWrap(True)
        insp_layout.addWidget(self.lbl_zone_desc)

        # Timing inputs
        timing_box = QHBoxLayout()
        timing_box.addWidget(QLabel("Start:"))
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, 9999.0)
        self.spin_start.setSingleStep(0.24)
        self.spin_start.setSuffix(" s")
        self.spin_start.valueChanged.connect(self.on_timing_inputs_changed)
        timing_box.addWidget(self.spin_start)

        timing_box.addWidget(QLabel("End:"))
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.0, 9999.0)
        self.spin_end.setSingleStep(0.24)
        self.spin_end.setSuffix(" s")
        self.spin_end.valueChanged.connect(self.on_timing_inputs_changed)
        timing_box.addWidget(self.spin_end)
        insp_layout.addLayout(timing_box)

        # Zone Label / Custom Name
        label_box = QHBoxLayout()
        label_box.addWidget(QLabel("Label:"))
        self.txt_zone_label = QLineEdit()
        self.txt_zone_label.setPlaceholderText("Optional zone note...")
        self.txt_zone_label.textChanged.connect(self.on_zone_label_changed)
        label_box.addWidget(self.txt_zone_label)
        insp_layout.addLayout(label_box)

        # Action Buttons with Feather Icons
        btn_grid_1 = QHBoxLayout()
        self.btn_add_zone = QPushButton("Add Zone at Playhead")
        self.btn_add_zone.setIcon(get_feather_icon("plus", "#ffffff", 14))
        self.btn_add_zone.clicked.connect(self.action_add_zone_at_playhead)
        btn_grid_1.addWidget(self.btn_add_zone)

        self.btn_delete_zone = QPushButton("Delete Selected")
        self.btn_delete_zone.setIcon(get_feather_icon("trash-2", "#ff6b62", 14))
        self.btn_delete_zone.clicked.connect(self.action_delete_selected_zone)
        btn_grid_1.addWidget(self.btn_delete_zone)
        insp_layout.addLayout(btn_grid_1)

        btn_grid_2 = QHBoxLayout()
        self.btn_auto_zones = QPushButton("Auto-Detect Zones")
        self.btn_auto_zones.setIcon(get_feather_icon("zap", "#ffd000", 14))
        self.btn_auto_zones.setToolTip("Analyzes audio energy and automatically lays out initial zones.")
        self.btn_auto_zones.clicked.connect(self.auto_detect_initial_zones)
        btn_grid_2.addWidget(self.btn_auto_zones)

        self.btn_clear_all = QPushButton("Clear All Zones")
        self.btn_clear_all.setIcon(get_feather_icon("trash", "#ff6b62", 14))
        self.btn_clear_all.clicked.connect(self.action_clear_all_zones)
        btn_grid_2.addWidget(self.btn_clear_all)
        insp_layout.addLayout(btn_grid_2)

        # File I/O for Zones JSON
        io_box = QHBoxLayout()
        self.btn_save_zones = QPushButton("Save Zones JSON")
        self.btn_save_zones.setIcon(get_feather_icon("save", "#ffffff", 14))
        self.btn_save_zones.clicked.connect(self.action_save_zones)
        io_box.addWidget(self.btn_save_zones)

        self.btn_load_zones = QPushButton("Load Zones JSON")
        self.btn_load_zones.setIcon(get_feather_icon("folder", "#ffffff", 14))
        self.btn_load_zones.clicked.connect(self.action_load_zones)
        io_box.addWidget(self.btn_load_zones)
        insp_layout.addLayout(io_box)

        # Section & Difficulty Inspector Section
        level_group = QGroupBox("SECTION & DIFFICULTY INSPECTOR")
        level_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #4a3c5a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
                font-weight: bold;
                font-size: 11px;
                color: #c084fc;
            }
        """)
        level_layout = QVBoxLayout(level_group)
        level_layout.setSpacing(6)

        # 1. Section Name (Editable combobox with presets, custom naming in ALL modes!)
        name_box = QHBoxLayout()
        name_box.addWidget(QLabel("Section Name:"))
        self.cb_level_name = QComboBox()
        self.cb_level_name.setEditable(True)
        self.cb_level_name.addItems([
            "Section 1", "Section 2", "Section 3", "Section 4", "Section 5",
            "Level 1", "Level 2", "Level 3", "Level 4", "Level 5",
            "Intro", "Verse 1", "Verse 2", "Chorus", "Drop", "Climax", "Outro"
        ])
        self.cb_level_name.setToolTip("Custom section or level chapter name (e.g. Intro, Verse 1, Drop, Section 1).")
        self.cb_level_name.currentTextChanged.connect(self.on_level_name_changed)
        name_box.addWidget(self.cb_level_name)
        level_layout.addLayout(name_box)

        # 2. Difficulty Rating number & Difficulty & Auto
        row_ld = QHBoxLayout()
        row_ld.addWidget(QLabel("Rating (1-10):"))
        self.spin_level_num = QSpinBox()
        self.spin_level_num.setRange(1, 20)
        self.spin_level_num.setValue(self.initial_level)
        self.spin_level_num.valueChanged.connect(self.on_level_num_changed)
        row_ld.addWidget(self.spin_level_num)

        row_ld.addWidget(QLabel("Difficulty:"))
        self.cb_difficulty = QComboBox()
        # Expert and Master commented out to prevent beat spam
        self.cb_difficulty.addItems(["Easy", "Normal", "Hard"])
        # self.cb_difficulty.addItems(["Easy", "Normal", "Hard", "Expert", "Master"])
        init_diff = str(self.initial_difficulty)
        if init_diff in ("Expert", "Master"):
            init_diff = "Hard"
        idx_diff = self.cb_difficulty.findText(init_diff)
        if idx_diff >= 0:
            self.cb_difficulty.setCurrentIndex(idx_diff)
        self.cb_difficulty.currentIndexChanged.connect(self.on_level_difficulty_changed)
        row_ld.addWidget(self.cb_difficulty)

        self.btn_auto_diff = QPushButton("Auto")
        self.btn_auto_diff.setIcon(get_feather_icon("zap", "#00ffff", 14))
        self.btn_auto_diff.setToolTip("Auto-calculates difficulty rating and density based on beats within this section.")
        self.btn_auto_diff.clicked.connect(self.auto_determine_difficulty)
        row_ld.addWidget(self.btn_auto_diff)
        level_layout.addLayout(row_ld)

        # 3. Start & End times for Section
        timing_lvl = QHBoxLayout()
        timing_lvl.addWidget(QLabel("Start:"))
        self.spin_level_start = QDoubleSpinBox()
        self.spin_level_start.setRange(0.0, 9999.0)
        self.spin_level_start.setSingleStep(0.24)
        self.spin_level_start.setSuffix(" s")
        self.spin_level_start.valueChanged.connect(self.on_level_timing_inputs_changed)
        timing_lvl.addWidget(self.spin_level_start)

        timing_lvl.addWidget(QLabel("End:"))
        self.spin_level_end = QDoubleSpinBox()
        self.spin_level_end.setRange(0.0, 9999.0)
        self.spin_level_end.setSingleStep(0.24)
        self.spin_level_end.setSuffix(" s")
        self.spin_level_end.valueChanged.connect(self.on_level_timing_inputs_changed)
        timing_lvl.addWidget(self.spin_level_end)
        level_layout.addLayout(timing_lvl)

        # 4. Action Buttons (+ Add Section at Playhead, Delete Selected Section)
        btn_lvl_box = QHBoxLayout()
        self.btn_add_level = QPushButton("+ Add Section at Playhead")
        self.btn_add_level.setIcon(get_feather_icon("plus", "#ffffff", 14))
        self.btn_add_level.setToolTip("Places a new section chapter on the timeline at the playhead position.")
        self.btn_add_level.clicked.connect(self.action_add_level_at_playhead)
        btn_lvl_box.addWidget(self.btn_add_level)

        self.btn_delete_level = QPushButton("Delete Selected")
        self.btn_delete_level.setIcon(get_feather_icon("trash-2", "#ff6b62", 14))
        self.btn_delete_level.clicked.connect(self.action_delete_selected_level)
        btn_lvl_box.addWidget(self.btn_delete_level)
        level_layout.addLayout(btn_lvl_box)

        # 5. Progression Mode selector with clear descriptions
        row_lm = QHBoxLayout()
        row_lm.addWidget(QLabel("Progression Mode:"))
        self.cb_level_mode = QComboBox()
        self.cb_level_mode.addItem("Ramping (Easy to Hard inside section)", "ramp_within_level")
        self.cb_level_mode.addItem("Progressive (Each section gets harder)", "rise_with_level")
        self.cb_level_mode.addItem("Fixed (Manual difficulty per section)", "named_levels")
        self.cb_level_mode.setToolTip("Controls how beat generation adjusts difficulty across sections.")
        init_mode_idx = self.cb_level_mode.findData(self.initial_level_mode)
        if init_mode_idx >= 0:
            self.cb_level_mode.setCurrentIndex(init_mode_idx)
        self.cb_level_mode.currentIndexChanged.connect(self.on_level_mode_changed)
        row_lm.addWidget(self.cb_level_mode)
        level_layout.addLayout(row_lm)

        self.lbl_level_mode_hint = QLabel()
        self.lbl_level_mode_hint.setStyleSheet("color: #a0a0b8; font-size: 10px; font-style: italic; padding-bottom: 2px;")
        self.lbl_level_mode_hint.setWordWrap(True)
        level_layout.addWidget(self.lbl_level_mode_hint)
        self.on_level_mode_changed(self.cb_level_mode.currentIndex())

        self.lbl_difficulty_display = QLabel("No beats to evaluate")
        self.lbl_difficulty_display.setStyleSheet("color: #00ffff; font-size: 11px; font-weight: bold; background: #161622; padding: 6px 10px; border-radius: 4px; border: 1px solid #2d2d3d;")
        self.lbl_difficulty_display.setWordWrap(True)
        level_layout.addWidget(self.lbl_difficulty_display)

        insp_layout.addWidget(level_group)

        # Stats readout
        self.lbl_stats = QLabel("Levels: 0  |  Zones: 0  |  V3: 0  |  V2: 0  |  Ref: 0  |  Vid: 0")
        self.lbl_stats.setStyleSheet("color: #a0a0b8; font-size: 11px; font-weight: bold;")
        insp_layout.addWidget(self.lbl_stats)

        # Video Beat Parser Section
        parser_group = QGroupBox("VIDEO BEAT PARSER TRACK")
        parser_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3c3c4a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
                font-weight: bold;
                font-size: 11px;
                color: #ffd000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        parser_layout = QVBoxLayout(parser_group)
        parser_layout.setSpacing(6)

        p_row1 = QHBoxLayout()
        self.btn_run_parser = QPushButton("Scan Video Beats... (WIP)")
        self.btn_run_parser.setIcon(get_feather_icon("video", "#777788", 14))
        self.btn_run_parser.setToolTip("Scan Video Beats [WIP - Currently Disabled]: Video beat parsing engine is under maintenance / work-in-progress.")
        self.btn_run_parser.setEnabled(False)
        self.btn_run_parser.clicked.connect(self.action_run_video_parser)
        p_row1.addWidget(self.btn_run_parser)

        self.btn_load_parser_beats = QPushButton("Load Parser JSON")
        self.btn_load_parser_beats.setIcon(get_feather_icon("folder", "#ffd000", 14))
        self.btn_load_parser_beats.setToolTip("Loads previously extracted video parser beats from a JSON file.")
        self.btn_load_parser_beats.clicked.connect(self.action_load_parser_beats)
        p_row1.addWidget(self.btn_load_parser_beats)
        parser_layout.addLayout(p_row1)

        self.chk_use_parser = QCheckBox("Use Parser Beats as Project Beats")
        self.chk_use_parser.setStyleSheet("""
            QCheckBox {
                color: #ffd000;
                font-weight: bold;
                font-size: 11px;
            }
            QCheckBox::indicator:checked {
                background: #ffd000;
                border: 1px solid #ffffff;
            }
        """)
        self.chk_use_parser.toggled.connect(self.on_toggle_use_parser_beats)
        parser_layout.addWidget(self.chk_use_parser)

        insp_layout.addWidget(parser_group)

        insp_layout.addStretch()

        insp_scroll = QScrollArea()
        insp_scroll.setWidgetResizable(True)
        insp_scroll.setWidget(inspector_container)
        insp_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        top_splitter.addWidget(insp_scroll)
        top_splitter.setSizes([750, 450])
        main_layout.addWidget(top_splitter, stretch=3)

        # ---------------------------------------------------------------------
        # Middle: Timeline Tracks Toggle Bar & Zoom Slider
        # ---------------------------------------------------------------------
        tracks_bar = QHBoxLayout()
        tracks_bar.setSpacing(14)
        lbl_tracks = QLabel("<b>TIMELINE TRACKS:</b>")
        lbl_tracks.setStyleSheet("color: #a0a0b8; font-size: 11px;")
        tracks_bar.addWidget(lbl_tracks)

        self.chk_tr1 = QCheckBox("Track 1")
        self.chk_tr1.setChecked(True)
        self.chk_tr1.setStyleSheet("QCheckBox { color: #d488ff; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #d488ff; border: 1px solid #ffffff; }")
        self.chk_tr1.toggled.connect(lambda c: self.timeline_widget.set_track_visible('tr1', c))
        tracks_bar.addWidget(self.chk_tr1)

        self.chk_tr2 = QCheckBox("Track 2")
        self.chk_tr2.setChecked(False)
        self.chk_tr2.setStyleSheet("QCheckBox { color: #00e5ff; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #00e5ff; border: 1px solid #ffffff; }")
        self.chk_tr2.toggled.connect(lambda c: self.timeline_widget.set_track_visible('tr2', c))
        tracks_bar.addWidget(self.chk_tr2)

        self.chk_tr3 = QCheckBox("Track 3")
        self.chk_tr3.setChecked(False)
        self.chk_tr3.setStyleSheet("QCheckBox { color: #ffb300; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #ffb300; border: 1px solid #ffffff; }")
        self.chk_tr3.toggled.connect(lambda c: self.timeline_widget.set_track_visible('tr3', c))
        tracks_bar.addWidget(self.chk_tr3)

        self.chk_vid = QCheckBox("Vid Parser")
        self.chk_vid.setChecked(False)  # Hidden by default per user request
        self.chk_vid.setStyleSheet("QCheckBox { color: #ffd000; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #ffd000; border: 1px solid #ffffff; }")
        self.chk_vid.toggled.connect(lambda c: self.timeline_widget.set_track_visible('vid', c))
        tracks_bar.addWidget(self.chk_vid)

        # Aliases for backwards compatibility
        self.chk_v3 = self.chk_tr1
        self.chk_v2 = self.chk_tr2
        self.chk_ref = None

        self.chk_zones = QCheckBox("Zones Track")
        self.chk_zones.setChecked(True)
        self.chk_zones.setStyleSheet("QCheckBox { color: #34d399; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #34d399; border: 1px solid #ffffff; }")
        self.chk_zones.toggled.connect(lambda c: self.timeline_widget.set_track_visible('zones', c))
        tracks_bar.addWidget(self.chk_zones)

        self.chk_levels = QCheckBox("Levels Track")
        self.chk_levels.setChecked(True)
        self.chk_levels.setStyleSheet("QCheckBox { color: #c084fc; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #c084fc; border: 1px solid #ffffff; }")
        self.chk_levels.toggled.connect(lambda c: self.timeline_widget.set_track_visible('levels', c))
        tracks_bar.addWidget(self.chk_levels)

        tracks_bar.addStretch()

        lbl_zoom = QLabel("Zoom:")
        lbl_zoom.setStyleSheet("color: #a0a0b8; font-size: 11px;")
        tracks_bar.addWidget(lbl_zoom)

        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(20, 200)
        self.slider_zoom.setValue(70)
        self.slider_zoom.setFixedWidth(140)
        self.slider_zoom.valueChanged.connect(self.on_zoom_changed)
        tracks_bar.addWidget(self.slider_zoom)
        main_layout.addLayout(tracks_bar)

        # ---------------------------------------------------------------------
        # Timeline Widget + Scrollbar
        # ---------------------------------------------------------------------
        self.timeline_widget = ZonesTimelineWidget(self)
        self.timeline_widget.set_duration(self.duration)
        self.timeline_widget.set_bpm_phase(self.bpm, self.phase)
        self.timeline_widget.set_beats(
            tr1_beats=self.tr1_beats,
            tr2_beats=self.tr2_beats,
            tr3_beats=self.tr3_beats,
            video_parser_beats=self.video_parser_beats
        )
        self.timeline_widget.set_levels(self.initial_levels)
        if self.initial_zones:
            self.timeline_widget.set_zones(self.initial_zones)
        self.timeline_widget.position_changed.connect(self.seek_to_time)
        self.timeline_widget.zone_selected.connect(self.on_zone_selected)
        self.timeline_widget.zones_modified.connect(self.update_inspector_stats)
        self.timeline_widget.level_selected.connect(self.on_level_selected)
        self.timeline_widget.levels_modified.connect(self.on_levels_modified_sync)
        self.timeline_widget.track_visibility_changed.connect(self.on_track_visibility_changed_from_timeline)
        main_layout.addWidget(self.timeline_widget, stretch=2)

        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.scrollbar.valueChanged.connect(self.timeline_widget.set_scroll_x)
        main_layout.addWidget(self.scrollbar)

        # ---------------------------------------------------------------------
        # Bottom: Generator & Apply Actions with Feather Icons
        # ---------------------------------------------------------------------
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        lbl_help = QLabel("<b>Tips:</b> Drag on Zones track to create  |  Drag edges to resize  |  Space to Play/Pause  |  Keys 1-6 set type")
        lbl_help.setStyleSheet("color: #606075; font-size: 10px;")
        bottom_bar.addWidget(lbl_help)
        bottom_bar.addStretch()

        # Target Track Combo for Generated Beats
        lbl_target = QLabel("Target Track:")
        lbl_target.setStyleSheet("color: #c0c0d0; font-weight: bold; font-size: 11px;")
        bottom_bar.addWidget(lbl_target)

        self.cb_target_track = QComboBox()
        self.cb_target_track.addItem("Track 1", 4)
        self.cb_target_track.addItem("Track 2", 1)
        self.cb_target_track.addItem("Track 3", 2)
        self.cb_target_track.setStyleSheet("""
            QComboBox {
                background: #252535;
                color: #ffffff;
                border: 1px solid #4a4a60;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1e1e2d;
                color: #ffffff;
                selection-background-color: #8a2be2;
            }
        """)
        bottom_bar.addWidget(self.cb_target_track)

        # V3 Generation Toggles
        self.chk_v3_use_zones = QCheckBox("Use Zones")
        self.chk_v3_use_zones.setChecked(True)
        self.chk_v3_use_zones.setStyleSheet("QCheckBox { color: #34d399; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #34d399; border: 1px solid #ffffff; }")
        bottom_bar.addWidget(self.chk_v3_use_zones)

        self.chk_v3_use_levels = QCheckBox("Use Levels")
        self.chk_v3_use_levels.setChecked(True)
        self.chk_v3_use_levels.setStyleSheet("QCheckBox { color: #c084fc; font-weight: bold; font-size: 11px; } QCheckBox::indicator:checked { background: #c084fc; border: 1px solid #ffffff; }")
        bottom_bar.addWidget(self.chk_v3_use_levels)

        # GENERATE V2 BEATS BUTTON
        self.btn_gen_v2 = QPushButton("GENERATE V2 BEATS...")
        self.btn_gen_v2.setIcon(get_feather_icon("music", "#ffffff", 14))
        self.btn_gen_v2.setToolTip("Configure options (preset, tempo, density, grid) and generate V2 beats")
        self.btn_gen_v2.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b4db, stop:1 #0083b0);
                border: 1px solid #00d2ff;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00c6ff, stop:1 #0072ff);
                border-color: #80dfff;
            }
        """)
        self.btn_gen_v2.clicked.connect(self.generate_v2_beats)
        bottom_bar.addWidget(self.btn_gen_v2)

        # GENERATE V3 BEATS BUTTON
        self.btn_regen = QPushButton("GENERATE V3 BEATS...")
        self.btn_regen.setIcon(get_feather_icon("zap", "#ffffff", 14))
        self.btn_regen.setToolTip("Configure options (zones, sections, density, grid) and generate V3 beats")
        self.btn_regen.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8a2be2, stop:1 #4a00e0);
                border: 1px solid #a855f7;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9d4edd, stop:1 #5a189a);
                border-color: #c084fc;
            }
        """)
        self.btn_regen.clicked.connect(self.generate_v3_beats_from_zones)
        bottom_bar.addWidget(self.btn_regen)

        # APPLY AND CLOSE BUTTON
        self.btn_apply = QPushButton("APPLY TO PROJECT CLOSE")
        self.btn_apply.setIcon(get_feather_icon("check", "#ffffff", 14))
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #047857);
                border: 1px solid #34d399;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #059669);
            }
        """)
        self.btn_apply.clicked.connect(self.apply_and_close)
        bottom_bar.addWidget(self.btn_apply)

        main_layout.addLayout(bottom_bar)
        self.update_scrollbar()

    # -------------------------------------------------------------------------
    # Media Player Setup & Sync
    # -------------------------------------------------------------------------
    def setup_media_player(self):
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(0.8)

        if self.media_path and os.path.exists(self.media_path):
            self.player.setSource(QUrl.fromLocalFile(self.media_path))

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(25)  # 40 fps tracking
        self.play_timer.timeout.connect(self.sync_playback)

    def toggle_play(self):
        if not hasattr(self, 'player') or not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_timer.stop()
            self.btn_play.setText("Play")
            self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        else:
            self.player.play()
            self.play_timer.start()
            self.btn_play.setText("Pause")
            self.btn_play.setIcon(get_feather_icon("pause", "#ffffff", 14))

    def stop_playback(self):
        try:
            if hasattr(self, 'play_timer') and self.play_timer:
                self.play_timer.stop()
            if hasattr(self, 'player') and self.player:
                self.player.stop()
            if hasattr(self, 'btn_play') and self.btn_play:
                self.btn_play.setText("Play")
                self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        except Exception as e:
            print("Error stopping playback:", e)

    def toggle_mute(self):
        if not hasattr(self, 'audio_output') or not self.audio_output:
            return
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        if not is_muted:
            self.btn_mute.setIcon(get_feather_icon("volume-x", "#ff6b62", 15))
        else:
            vol = self.slider_volume.value() if hasattr(self, 'slider_volume') else 80
            icon_name = "volume-2" if vol >= 50 else ("volume-1" if vol > 0 else "volume-x")
            self.btn_mute.setIcon(get_feather_icon(icon_name, "#00ffff", 15))

    def on_volume_changed(self, val):
        if hasattr(self, 'audio_output') and self.audio_output:
            self.audio_output.setVolume(val / 100.0)
            if self.audio_output.isMuted():
                self.audio_output.setMuted(False)
        if val == 0:
            self.btn_mute.setIcon(get_feather_icon("volume-x", "#888899", 15))
        elif val < 50:
            self.btn_mute.setIcon(get_feather_icon("volume-1", "#00ffff", 15))
        else:
            self.btn_mute.setIcon(get_feather_icon("volume-2", "#00ffff", 15))

    def sync_playback(self):
        if not hasattr(self, 'player') or not self.player:
            return
        pos_ms = self.player.position()
        t = pos_ms / 1000.0
        self.timeline_widget.set_current_time(t)
        self.lbl_timecode.setText(f"{int(t//60):02d}:{t%60:06.3f} / {int(self.duration//60):02d}:{self.duration%60:06.3f}")

    def seek_to_time(self, t):
        if not hasattr(self, 'player') or not self.player:
            return
        t = max(0.0, min(self.duration, float(t)))
        self.player.setPosition(int(t * 1000))
        self.timeline_widget.set_current_time(t)
        self.lbl_timecode.setText(f"{int(t//60):02d}:{t%60:06.3f} / {int(self.duration//60):02d}:{self.duration%60:06.3f}")

    def seek_relative(self, dt):
        if not hasattr(self, 'player') or not self.player:
            return
        cur_t = self.player.position() / 1000.0
        self.seek_to_time(cur_t + dt)

    def on_speed_changed(self, idx):
        if not hasattr(self, 'player') or not self.player:
            return
        speeds = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        sp = speeds[idx] if idx < len(speeds) else 1.0
        self.player.setPlaybackRate(sp)

    def on_toggle_use_parser_beats(self, checked):
        if checked:
            if not getattr(self, 'video_parser_beats', []):
                QMessageBox.warning(self, "No Parser Beats", "Please scan or load video parser beats first.")
                self.chk_use_parser.blockSignals(True)
                self.chk_use_parser.setChecked(False)
                self.chk_use_parser.blockSignals(False)
                return
            self._backup_v3_beats = list(self.resulting_beats)
            self.resulting_beats = list(self.video_parser_beats)
            self.generated_beats = list(self.video_parser_beats)
            self.timeline_widget.set_beats(
                tr1_beats=self.resulting_beats,
                tr2_beats=self.tr2_beats,
                tr3_beats=self.tr3_beats,
                video_parser_beats=self.video_parser_beats
            )
            self.update_inspector_stats()
        else:
            if hasattr(self, '_backup_v3_beats') and self._backup_v3_beats:
                self.resulting_beats = list(self._backup_v3_beats)
                self.generated_beats = list(self._backup_v3_beats)
                self.timeline_widget.set_beats(
                    tr1_beats=self.resulting_beats,
                    tr2_beats=self.tr2_beats,
                    tr3_beats=self.tr3_beats,
                    video_parser_beats=self.video_parser_beats
                )
                self.update_inspector_stats()

    def on_track_visibility_changed_from_timeline(self, track_name, visible):
        cb_map = {
            'tr1': self.chk_tr1,
            'tr2': self.chk_tr2,
            'tr3': self.chk_tr3,
            'v3': self.chk_tr1,
            'v2': self.chk_tr2,
            'vid': self.chk_vid,
            'zones': self.chk_zones,
            'levels': self.chk_levels
        }
        chk = cb_map.get(track_name)
        if chk and chk.isChecked() != visible:
            chk.blockSignals(True)
            chk.setChecked(visible)
            chk.blockSignals(False)

    # -------------------------------------------------------------------------
    # Zone Inspector & Editing Events
    # -------------------------------------------------------------------------
    def on_zone_selected(self, zone):
        if not zone:
            self.btn_delete_zone.setEnabled(False)
            self.lbl_zone_desc.setText("Click anywhere on the Zones track to select or drag to create.")
            return

        self.btn_delete_zone.setEnabled(True)
        # Block signals temporarily to prevent recursive loops
        self.cb_zone_type.blockSignals(True)
        self.spin_start.blockSignals(True)
        self.spin_end.blockSignals(True)
        self.txt_zone_label.blockSignals(True)

        idx = self.cb_zone_type.findData(zone.zone_type)
        if idx >= 0:
            self.cb_zone_type.setCurrentIndex(idx)
        self.spin_start.setValue(zone.start_time)
        self.spin_end.setValue(zone.end_time)
        self.txt_zone_label.setText(zone.label)

        zinfo = ZONE_TYPES.get(zone.zone_type, ZONE_TYPES["normal"])
        self.lbl_zone_desc.setText(f"<b>{zinfo['name']}:</b> {zinfo['desc']}")

        self.cb_zone_type.blockSignals(False)
        self.spin_start.blockSignals(False)
        self.spin_end.blockSignals(False)
        self.txt_zone_label.blockSignals(False)

    def on_zone_type_combo_changed(self, idx):
        z = self.timeline_widget.selected_zone
        if z:
            new_type = self.cb_zone_type.currentData()
            self.timeline_widget.set_zone_type(z, new_type)
            zinfo = ZONE_TYPES.get(new_type, ZONE_TYPES["normal"])
            self.lbl_zone_desc.setText(f"<b>{zinfo['name']}:</b> {zinfo['desc']}")
            self.txt_zone_label.setText(z.label)

    def on_timing_inputs_changed(self):
        z = self.timeline_widget.selected_zone
        if z:
            s = self.spin_start.value()
            e = self.spin_end.value()
            if e > s + 0.1:
                z.start_time = round(s, 3)
                z.end_time = round(e, 3)
                self.timeline_widget.zones_collection.sanitize_no_overlaps()
                self.timeline_widget.zones_collection.sort_zones()
                self.timeline_widget.update()
                self.update_inspector_stats()

    def on_zone_label_changed(self, text):
        z = self.timeline_widget.selected_zone
        if z:
            z.label = text.strip() or ZONE_TYPES[z.zone_type]["name"]
            self.timeline_widget.update()

    def action_add_zone_at_playhead(self):
        t0 = self.timeline_widget.current_time
        # Default zone length = 4 measures (e.g. ~7.68s at 125 BPM)
        spb = 60.0 / self.bpm
        dur = spb * 4.0 * 2.0  # 8 beats / 2 bars
        t1 = min(self.duration, t0 + dur)
        z = self.timeline_widget.zones_collection.add_zone(t0, t1, zone_type="normal")
        self.timeline_widget.select_zone(z)
        self.update_inspector_stats()

    def action_delete_selected_zone(self):
        z = self.timeline_widget.selected_zone
        if z:
            self.timeline_widget.delete_zone(z)
            self.update_inspector_stats()

    def action_clear_all_zones(self):
        ans = QMessageBox.question(
            self, "Clear All Zones",
            "Are you sure you want to remove all video zones?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.timeline_widget.zones_collection.clear()
            self.timeline_widget.select_zone(None)
            self.timeline_widget.update()
            self.update_inspector_stats()

    # -------------------------------------------------------------------------
    # Level Inspector & Editing Events (Placed like zones in the Zones Tab!)
    # -------------------------------------------------------------------------
    def on_level_selected(self, level):
        if not level:
            self.btn_delete_level.setEnabled(False)
            self.cb_level_name.setEnabled(False)
            self.spin_level_num.setEnabled(False)
            self.cb_difficulty.setEnabled(False)
            self.spin_level_start.setEnabled(False)
            self.spin_level_end.setEnabled(False)
            self.update_difficulty_display()
            return

        self.btn_delete_level.setEnabled(True)
        self.cb_level_name.setEnabled(True)
        self.spin_level_num.setEnabled(True)
        self.cb_difficulty.setEnabled(True)
        self.spin_level_start.setEnabled(True)
        self.spin_level_end.setEnabled(True)

        self.cb_level_name.blockSignals(True)
        self.spin_level_num.blockSignals(True)
        self.cb_difficulty.blockSignals(True)
        self.spin_level_start.blockSignals(True)
        self.spin_level_end.blockSignals(True)

        self.cb_level_name.setCurrentText(level.name)
        self.spin_level_num.setValue(level.level)
        idx_diff = self.cb_difficulty.findText(level.difficulty)
        if idx_diff >= 0:
            self.cb_difficulty.setCurrentIndex(idx_diff)
        self.spin_level_start.setValue(level.start_time)
        self.spin_level_end.setValue(level.end_time)

        self.cb_level_name.blockSignals(False)
        self.spin_level_num.blockSignals(False)
        self.cb_difficulty.blockSignals(False)
        self.spin_level_start.blockSignals(False)
        self.spin_level_end.blockSignals(False)

        self.update_difficulty_display()

    def on_levels_modified_sync(self):
        """Called whenever levels on timeline are moved, resized, or created."""
        lvl = getattr(self.timeline_widget, 'selected_level', None)
        if lvl:
            self.spin_level_start.blockSignals(True)
            self.spin_level_end.blockSignals(True)
            self.spin_level_start.setValue(lvl.start_time)
            self.spin_level_end.setValue(lvl.end_time)
            self.spin_level_start.blockSignals(False)
            self.spin_level_end.blockSignals(False)
        self.update_inspector_stats()

    def on_level_mode_changed(self, idx):
        mode_data = self.cb_level_mode.currentData()
        hints = {
            "ramp_within_level": "(i) Ramping: Beats start calm at the beginning of each section and ramp up towards the end.",
            "rise_with_level": "(i) Progressive: Earlier sections have a lower base difficulty; later sections get progressively harder.",
            "named_levels": "(i) Fixed: Each section strictly follows its own assigned Difficulty and Rating."
        }
        if hasattr(self, 'lbl_level_mode_hint'):
            self.lbl_level_mode_hint.setText(hints.get(mode_data, ""))

    def on_level_name_changed(self, text):
        lvl = getattr(self.timeline_widget, 'selected_level', None)
        if not lvl and len(self.timeline_widget.levels_collection) > 0:
            lvl = self.timeline_widget.levels_collection[0]
            self.timeline_widget.select_level(lvl)
        if lvl:
            lvl.name = text.strip() or f"Section {lvl.level}"
            self.timeline_widget.update()
            self.update_difficulty_display()

    def on_level_num_changed(self, val):
        lvl = getattr(self.timeline_widget, 'selected_level', None)
        if not lvl and len(self.timeline_widget.levels_collection) > 0:
            lvl = self.timeline_widget.levels_collection[0]
            self.timeline_widget.select_level(lvl)
        if lvl:
            lvl.level = int(val)
            self.timeline_widget.update()
            self.update_difficulty_display()

    def on_level_difficulty_changed(self, idx):
        lvl = getattr(self.timeline_widget, 'selected_level', None)
        if not lvl and len(self.timeline_widget.levels_collection) > 0:
            lvl = self.timeline_widget.levels_collection[0]
            self.timeline_widget.select_level(lvl)
        if lvl:
            lvl.difficulty = self.cb_difficulty.currentText()
            self.timeline_widget.update()
            self.update_difficulty_display()

    def on_level_timing_inputs_changed(self):
        lvl = getattr(self.timeline_widget, 'selected_level', None)
        if not lvl and len(self.timeline_widget.levels_collection) > 0:
            lvl = self.timeline_widget.levels_collection[0]
            self.timeline_widget.select_level(lvl)
        if lvl:
            st = round(self.spin_level_start.value(), 3)
            et = round(self.spin_level_end.value(), 3)
            if et > st + 0.1:
                lvl.start_time = st
                lvl.end_time = et
                self.timeline_widget.levels_collection.sort_levels()
                self.timeline_widget.update()
                self.update_difficulty_display()

    def action_add_level_at_playhead(self):
        t = round(self.timeline_widget.current_time, 2)
        curr_count = len(self.timeline_widget.levels_collection)
        next_lvl = curr_count + 1
        default_name = f"Section {next_lvl}"
        diff = self.cb_difficulty.currentText() if hasattr(self, 'cb_difficulty') else "Normal"
        dur = min(self.duration, t + 30.0)
        new_ch = self.timeline_widget.levels_collection.add_level(t, dur, default_name, next_lvl, diff)
        self.timeline_widget.select_level(new_ch)
        self.timeline_widget.levels_modified.emit()
        self.timeline_widget.update()

    def action_delete_selected_level(self):
        if self.timeline_widget.selected_level:
            self.timeline_widget.levels_collection.remove_level(self.timeline_widget.selected_level)
            next_sel = self.timeline_widget.levels_collection[0] if len(self.timeline_widget.levels_collection) > 0 else None
            self.timeline_widget.select_level(next_sel)
            self.timeline_widget.levels_modified.emit()
            self.timeline_widget.update()

    # -------------------------------------------------------------------------
    # Auto-Detection & File I/O
    # -------------------------------------------------------------------------
    def auto_detect_initial_zones(self):
        """
        Uses acoustic multi-band energy to automatically detect intro, verses,
        buildups, drops, and climaxes as starting zones.
        """
        if not self.media_path or not os.path.exists(self.media_path):
            return

        try:
            from beat_generator import auto_detect_zones
            detected_zones = auto_detect_zones(
                getattr(self, 'audio_path', self.media_path),
                duration=self.duration,
                bpm=self.bpm,
                phase=self.phase
            )
            if detected_zones:
                self.timeline_widget.zones_collection.zones = detected_zones
                self.timeline_widget.zones_collection.sort_zones()
                self.timeline_widget.update()
                self.update_inspector_stats()
                print(f"Auto-detected {len(detected_zones)} zones from audio features.")
        except Exception as e:
            print("Auto zone detection fallback:", e)

    def auto_load_reference_beats(self):
        # Disabled per user request (do not auto-load files or human ref from disk)
        pass

    def action_save_zones(self):
        default_name = f"{os.path.splitext(self.media_path)[0]}_zones.json" if self.media_path else "video_zones.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save Video Zones JSON", default_name, "JSON Files (*.json)")
        if path:
            try:
                self.timeline_widget.zones_collection.save_to_file(path)
                parent_win = self.parent()
                if parent_win and hasattr(parent_win, 'video_zones'):
                    parent_win.video_zones = self.timeline_widget.zones_collection
                    if hasattr(parent_win, 'mark_unsaved_changes'):
                        parent_win.mark_unsaved_changes()
                QMessageBox.information(self, "Saved", f"Saved {len(self.timeline_widget.zones_collection.zones)} zones to:\n{os.path.basename(path)}")
            except Exception as e:
                QMessageBox.warning(self, "Save Error", str(e))

    def action_load_zones(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Video Zones JSON", "", "JSON Files (*.json)")
        if path and os.path.exists(path):
            try:
                col = ZonesCollection.load_from_file(path)
                self.timeline_widget.zones_collection = col
                self.timeline_widget.select_zone(None)
                self.timeline_widget.update()
                self.update_inspector_stats()
                parent_win = self.parent()
                if parent_win and hasattr(parent_win, 'video_zones'):
                    parent_win.video_zones = self.timeline_widget.zones_collection
                    if hasattr(parent_win, 'mark_unsaved_changes'):
                        parent_win.mark_unsaved_changes()
                QMessageBox.information(self, "Loaded", f"Loaded {len(col.zones)} zones from:\n{os.path.basename(path)}")
            except Exception as e:
                QMessageBox.warning(self, "Load Error", str(e))

    # -------------------------------------------------------------------------
    # Video Beat Parser Actions
    # -------------------------------------------------------------------------
    def action_run_video_parser(self):
        """Launches the Video Beat Parser dialog to scan beats visually from video (Currently WIP)."""
        QMessageBox.information(
            self,
            "Video Parser (WIP)",
            "The Video Beat Parser engine is currently under maintenance / work-in-progress and has been temporarily disabled."
        )
        return

    def action_load_parser_beats(self):
        """Loads video parser beats from a previously saved JSON file."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Video Parser Beats JSON", "", "JSON Files (*.json);;All Files (*)")
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                raw_beats = data.get('beats', data) if isinstance(data, dict) else data
                times = []
                for b in raw_beats:
                    if isinstance(b, dict):
                        times.append(float(b.get('time', 0.0)))
                    elif isinstance(b, (int, float)):
                        times.append(float(b))
                if times:
                    self.video_parser_beats = sorted(times)
                    self.timeline_widget.set_beats(
                        tr1_beats=self.resulting_beats,
                        tr2_beats=self.tr2_beats,
                        tr3_beats=self.tr3_beats,
                        video_parser_beats=self.video_parser_beats
                    )
                    self.update_inspector_stats()
                    QMessageBox.information(
                        self, "Parser Beats Loaded",
                        f"Loaded {len(times)} video parser beats.\n"
                        f"Displayed on Line 4 (VID PARSER)."
                    )
                else:
                    QMessageBox.warning(self, "No Beats", "No beat timestamps found in file.")
            except Exception as e:
                QMessageBox.warning(self, "Load Error", str(e))

    def action_copy_parser_beats_to_project(self):
        """Copies video parser beats into the project beats."""
        if not getattr(self, 'video_parser_beats', []):
            QMessageBox.warning(self, "No Parser Beats", "Please scan or load video parser beats first.")
            return

        ans = QMessageBox.question(
            self, "Use Parser Beats",
            f"Replace current Project Beats with {len(self.video_parser_beats)} Video Parser beats?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._backup_v3_beats = list(self.resulting_beats)
            self.resulting_beats = list(self.video_parser_beats)
            self.generated_beats = list(self.video_parser_beats)
            self.timeline_widget.set_beats(
                tr1_beats=self.resulting_beats,
                tr2_beats=self.tr2_beats,
                tr3_beats=self.tr3_beats,
                video_parser_beats=self.video_parser_beats
            )
            self.update_inspector_stats()
            QMessageBox.information(
                self, "Beats Replaced",
                f"Successfully set {len(self.resulting_beats)} video parser beats as Project Beats!"
            )

    def auto_determine_difficulty(self):
        """Called when user explicitly clicks the '⚡ Auto' button to calculate and apply recommended level/difficulty."""
        try:
            from beat_generator import calculate_beat_difficulty
            all_beats = self.resulting_beats if self.resulting_beats else self.timeline_widget.project_beats
            sel_lvl = getattr(self.timeline_widget, 'selected_level', None)
            if not sel_lvl:
                if len(self.timeline_widget.levels_collection) > 0:
                    sel_lvl = self.timeline_widget.levels_collection[0]
                    self.timeline_widget.select_level(sel_lvl)
                else:
                    QMessageBox.information(self, "Auto Difficulty", "Please select or create a section first.")
                    return

            if sel_lvl and all_beats:
                eval_dur = max(1.0, sel_lvl.duration)
                beats_to_eval = [b for b in all_beats if sel_lvl.start_time <= b <= sel_lvl.end_time]
            else:
                eval_dur = self.duration
                beats_to_eval = all_beats

            diff_info = calculate_beat_difficulty(beats_to_eval, duration=eval_dur, bpm=self.bpm)
            self.difficulty_stats = diff_info
            self.resulting_level = diff_info["level"]
            self.resulting_difficulty = diff_info["difficulty"]

            if sel_lvl:
                sel_lvl.level = diff_info["level"]
                sel_lvl.difficulty = diff_info["difficulty"]
                self.timeline_widget.update()

            if hasattr(self, 'spin_level_num'):
                self.spin_level_num.blockSignals(True)
                self.spin_level_num.setValue(diff_info["level"])
                self.spin_level_num.blockSignals(False)

            if hasattr(self, 'cb_difficulty'):
                target_diff = diff_info["difficulty"]
                if target_diff in ("Expert", "Master"):
                    target_diff = "Hard"  # Capped while Expert/Master are disabled
                idx_diff = self.cb_difficulty.findText(target_diff)
                if idx_diff >= 0:
                    self.cb_difficulty.blockSignals(True)
                    self.cb_difficulty.setCurrentIndex(idx_diff)
                    self.cb_difficulty.blockSignals(False)

            if hasattr(self, 'lbl_difficulty_display'):
                self.update_difficulty_display()
        except Exception as e:
            print("Auto difficulty error:", e)

    def update_difficulty_display(self):
        """Updates the informational display label with difficulty metrics without altering user settings."""
        try:
            from beat_generator import calculate_beat_difficulty
            all_beats = self.resulting_beats if self.resulting_beats else self.timeline_widget.project_beats
            sel_lvl = getattr(self.timeline_widget, 'selected_level', None)
            if sel_lvl and all_beats:
                eval_dur = max(1.0, sel_lvl.duration)
                beats_to_eval = [b for b in all_beats if sel_lvl.start_time <= b <= sel_lvl.end_time]
                diff_info = calculate_beat_difficulty(beats_to_eval, duration=eval_dur, bpm=self.bpm)
                self.difficulty_stats = diff_info
                if hasattr(self, 'lbl_difficulty_display'):
                    name_text = sel_lvl.name
                    diff_text = sel_lvl.difficulty if getattr(sel_lvl, 'difficulty', None) else diff_info["difficulty"]
                    rate_text = sel_lvl.level if getattr(sel_lvl, 'level', None) else diff_info["level"]
                    count_text = len(beats_to_eval)
                    density_text = f"{diff_info['avg_frequency']:.1f}"
                    self.lbl_difficulty_display.setText(
                        f"Section: \"{name_text}\"  •  Difficulty: {diff_text} (Rating {rate_text}/10)  •  "
                        f"{count_text} notes  •  Density: {density_text} notes/sec"
                    )
            elif sel_lvl:
                if hasattr(self, 'lbl_difficulty_display'):
                    self.lbl_difficulty_display.setText(
                        f"Section: \"{sel_lvl.name}\"  •  Difficulty: {sel_lvl.difficulty} (Rating {sel_lvl.level}/10)  •  0 notes"
                    )
            else:
                # Before clicking on any section, do NOT compute track-wide Level 10/Master
                if hasattr(self, 'lbl_difficulty_display'):
                    self.lbl_difficulty_display.setText(
                        "Click a section or create one above to view and edit its level and difficulty."
                    )
        except Exception as e:
            pass

    def update_inspector_stats(self):
        n_levels = len(getattr(self.timeline_widget, 'levels_collection', []))
        n_zones = len(self.timeline_widget.zones_collection.zones)
        n_tr1 = len(getattr(self.timeline_widget, 'tr1_beats', []))
        n_tr2 = len(getattr(self.timeline_widget, 'tr2_beats', []))
        n_tr3 = len(getattr(self.timeline_widget, 'tr3_beats', []))
        n_vid = len(getattr(self.timeline_widget, 'video_parser_beats', []))
        self.lbl_stats.setText(
            f"Levels: {n_levels}  |  Zones: {n_zones}  |  Track 1: {n_tr1}  |  Track 2: {n_tr2}  |  Track 3: {n_tr3}  |  Vid: {n_vid}"
        )
        self.update_difficulty_display()
        self.update_scrollbar()

    # -------------------------------------------------------------------------
    # Zoom & Scroll
    # -------------------------------------------------------------------------
    def on_zoom_changed(self, val):
        self.timeline_widget.set_zoom(val)
        self.update_scrollbar()

    def update_scrollbar(self):
        total_w = int(self.duration * self.timeline_widget.zoom)
        vis_w = self.timeline_widget.width()
        max_scroll = max(0, total_w - vis_w)
        self.scrollbar.setMaximum(max_scroll)
        self.scrollbar.setPageStep(vis_w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_scrollbar()

    # -------------------------------------------------------------------------
    # V2 & V3 Generation & Apply
    # -------------------------------------------------------------------------
    def generate_v2_beats(self):
        """
        Generates V2 rhythm beats directly from the Zones Editor with full option choosing dialog.
        """
        if not self.media_path or not os.path.exists(self.media_path):
            QMessageBox.warning(self, "File Required", "Audio or video file is required to generate beats.")
            return

        try:
            from main.main import GenerateSettingsDialogV2
        except ImportError:
            from main import GenerateSettingsDialogV2
        dlg = GenerateSettingsDialogV2(self, default_bpm=self.bpm)
        if hasattr(dlg, 'btn_video_zones'):
            dlg.btn_video_zones.setVisible(False)

        # Pre-select target lane
        target_lane = self.cb_target_track.currentData() if hasattr(self, 'cb_target_track') else 4
        idx_lane = dlg.cb_lane.findData(target_lane)
        if idx_lane >= 0:
            dlg.cb_lane.setCurrentIndex(idx_lane)

        # Restore cached V2 settings if previously configured
        if hasattr(self, '_cached_v2_settings') and self._cached_v2_settings:
            s = self._cached_v2_settings
            if 'preset' in s:
                p_idx = dlg.cb_preset.findData(s['preset'])
                if p_idx >= 0:
                    dlg.cb_preset.setCurrentIndex(p_idx)
            if 'density' in s:
                dlg.spin_density.setValue(s['density'])
            if 'grid' in s:
                g_idx = dlg.cb_grid.findData(s['grid'])
                if g_idx >= 0:
                    dlg.cb_grid.setCurrentIndex(g_idx)
            if 'min_gap' in s:
                dlg.spin_min_gap.setValue(s['min_gap'])
            if 'intro_cutoff' in s:
                dlg.spin_intro_cutoff.setValue(s['intro_cutoff'])
            if 'insert_rolls' in s:
                dlg.chk_insert_rolls.setChecked(s['insert_rolls'])
            if 'halve_non_intense' in s:
                dlg.chk_halve_non_intense.setChecked(s['halve_non_intense'])

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

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

        self._cached_v2_settings = {
            'preset': preset,
            'density': density_scale,
            'grid': quantize_grid,
            'min_gap': min_gap,
            'intro_cutoff': intro_cutoff,
            'insert_rolls': insert_rolls,
            'halve_non_intense': halve_non_intense
        }

        from beat_generator import analyze_audio_v2
        self.target_lane = target_lane
        if hasattr(self, 'cb_target_track'):
            idx_tt = self.cb_target_track.findData(target_lane)
            if idx_tt >= 0:
                self.cb_target_track.blockSignals(True)
                self.cb_target_track.setCurrentIndex(idx_tt)
                self.cb_target_track.blockSignals(False)

        try:
            beats = analyze_audio_v2(
                getattr(self, 'audio_path', self.media_path),
                target_lane=target_lane,
                preset=preset,
                bpm=bpm if bpm else self.bpm,
                density_scale=density_scale,
                quantize_grid=quantize_grid,
                min_gap=min_gap,
                insert_rolls=insert_rolls,
                halve_non_intense=halve_non_intense,
                intro_cutoff=intro_cutoff
            )
            lane_beats = [b['time'] for b in beats if b.get('lane', target_lane) == target_lane]
            self.resulting_beats = lane_beats
            self.generated_beats = list(lane_beats)

            if target_lane == 4:
                self.tr1_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr1_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr1', True)
            elif target_lane == 1:
                self.tr2_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr2_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr2', True)
            elif target_lane == 2:
                self.tr3_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr3_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr3', True)

            self.timeline_widget.set_beats(
                tr1_beats=self.tr1_beats,
                tr2_beats=self.tr2_beats,
                tr3_beats=self.tr3_beats,
                video_parser_beats=self.video_parser_beats
            )
            self.update_inspector_stats()

            tr_name = {4: "Track 1", 1: "Track 2", 2: "Track 3"}.get(target_lane, f"Track {target_lane}")
            QMessageBox.information(
                self, "V2 Beats Generated",
                f"Generated {len(self.resulting_beats)} beats on {tr_name} using V2 engine!\n"
                f"Settings: Preset={preset}, Density={density_scale:.2f}, Grid={quantize_grid}\n"
                f"Beats are displayed on the timeline track above."
            )
        except Exception as e:
            QMessageBox.critical(self, "Generation Error", f"Failed to generate V2 beats:\n{e}")

    def generate_v3_beats_from_zones(self):
        """
        Executes the V3 beat generator engine with full option choosing dialog using
        user-defined zones and level chapters.
        """
        if not self.media_path or not os.path.exists(self.media_path):
            QMessageBox.warning(self, "File Required", "Audio or video file is required to generate beats.")
            return

        try:
            from main.main import GenerateSettingsDialogV3
        except ImportError:
            from main import GenerateSettingsDialogV3
        self.current_level = self.spin_level_num.value() if hasattr(self, 'spin_level_num') else 5
        self.current_difficulty = self.cb_difficulty.currentText() if hasattr(self, 'cb_difficulty') else "Normal"
        self.level_mode = self.cb_level_mode.currentData() if hasattr(self, 'cb_level_mode') else "ramp_within_level"

        dlg = GenerateSettingsDialogV3(self, default_bpm=self.bpm)
        if hasattr(dlg, 'btn_video_zones'):
            dlg.btn_video_zones.setVisible(False)

        target_lane = self.cb_target_track.currentData() if hasattr(self, 'cb_target_track') else 4
        idx_lane = dlg.cb_lane.findData(target_lane)
        if idx_lane >= 0:
            dlg.cb_lane.setCurrentIndex(idx_lane)

        if hasattr(self, 'chk_v3_use_zones'):
            dlg.chk_use_zones.setChecked(self.chk_v3_use_zones.isChecked())
        if hasattr(self, 'chk_v3_use_levels'):
            dlg.chk_use_levels.setChecked(self.chk_v3_use_levels.isChecked())

        # Restore cached V3 settings if previously configured
        if hasattr(self, '_cached_v3_settings') and self._cached_v3_settings:
            s = self._cached_v3_settings
            if 'preset' in s:
                p_idx = dlg.cb_preset.findData(s['preset'])
                if p_idx >= 0: dlg.cb_preset.setCurrentIndex(p_idx)
            if 'density' in s:
                dlg.spin_density.setValue(s['density'])
            if 'grid' in s:
                g_idx = dlg.cb_grid.findData(s['grid'])
                if g_idx >= 0: dlg.cb_grid.setCurrentIndex(g_idx)
            if 'min_gap' in s:
                dlg.spin_min_gap.setValue(s['min_gap'])
            if 'intro_cutoff' in s:
                dlg.spin_intro_cutoff.setValue(s['intro_cutoff'])
            if 'insert_rolls' in s:
                dlg.chk_insert_rolls.setChecked(s['insert_rolls'])
            if 'anti_overlap' in s:
                dlg.chk_anti_overlap.setChecked(s['anti_overlap'])
            if 'steady_clean' in s:
                dlg.chk_steady_clean.setChecked(s['steady_clean'])
            if 'edging_style' in s and hasattr(dlg, 'cb_edging_style'):
                e_idx = dlg.cb_edging_style.findData(s['edging_style'])
                if e_idx >= 0: dlg.cb_edging_style.setCurrentIndex(e_idx)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        preset = dlg.cb_preset.currentData()
        target_lane = dlg.cb_lane.currentData()
        bpm = None if dlg.chk_auto_bpm.isChecked() else dlg.spin_bpm.value()
        density_scale = dlg.spin_density.value()
        quantize_grid = dlg.cb_grid.currentData()
        min_gap = dlg.spin_min_gap.value()
        insert_rolls = dlg.chk_insert_rolls.isChecked()
        halve_non_intense = dlg.chk_halve_non_intense.isChecked()
        intro_cutoff = dlg.spin_intro_cutoff.value()
        anti_overlap = dlg.chk_anti_overlap.isChecked()
        steady_section_cleanup = dlg.chk_steady_clean.isChecked()
        level = dlg.get_level()
        difficulty = dlg.get_difficulty()
        level_mode = dlg.get_level_mode()
        edging_style = dlg.get_edging_style() if hasattr(dlg, 'get_edging_style') else "rhythmic_tension"
        use_zones = dlg.chk_use_zones.isChecked()
        use_levels = dlg.chk_use_levels.isChecked()
        clear_first = dlg.clear_existing.isChecked()

        # Sync bottom bar checkboxes with dialog choices
        if hasattr(self, 'chk_v3_use_zones'):
            self.chk_v3_use_zones.blockSignals(True)
            self.chk_v3_use_zones.setChecked(use_zones)
            self.chk_v3_use_zones.blockSignals(False)
        if hasattr(self, 'chk_v3_use_levels'):
            self.chk_v3_use_levels.blockSignals(True)
            self.chk_v3_use_levels.setChecked(use_levels)
            self.chk_v3_use_levels.blockSignals(False)

        self._cached_v3_settings = {
            'preset': preset,
            'density': density_scale,
            'grid': quantize_grid,
            'min_gap': min_gap,
            'intro_cutoff': intro_cutoff,
            'insert_rolls': insert_rolls,
            'anti_overlap': anti_overlap,
            'steady_clean': steady_section_cleanup,
            'edging_style': edging_style
        }

        from beat_generator import analyze_audio_v3
        zones_data = [z.to_dict() for z in self.timeline_widget.zones_collection.zones]
        levels_data = self.timeline_widget.get_levels()

        self.target_lane = target_lane
        if hasattr(self, 'cb_target_track'):
            idx_tt = self.cb_target_track.findData(target_lane)
            if idx_tt >= 0:
                self.cb_target_track.blockSignals(True)
                self.cb_target_track.setCurrentIndex(idx_tt)
                self.cb_target_track.blockSignals(False)

        try:
            beats = analyze_audio_v3(
                getattr(self, 'audio_path', self.media_path),
                target_lane=target_lane,
                preset=preset,
                bpm=bpm if bpm else self.bpm,
                density_scale=density_scale,
                quantize_grid=quantize_grid,
                min_gap=min_gap,
                anti_overlap=anti_overlap,
                zones=zones_data,
                intro_cutoff=intro_cutoff,
                insert_rolls=insert_rolls,
                halve_non_intense=halve_non_intense,
                steady_section_cleanup=steady_section_cleanup,
                level=level,
                difficulty=difficulty,
                level_mode=level_mode,
                levels=levels_data,
                use_zones=use_zones,
                use_levels=use_levels,
                edging_style=edging_style
            )
            lane_beats = [b['time'] for b in beats if b.get('lane', target_lane) == target_lane]
            self.resulting_beats = lane_beats
            self.generated_beats = list(lane_beats)

            if target_lane == 4:
                self.tr1_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr1_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr1', True)
            elif target_lane == 1:
                self.tr2_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr2_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr2', True)
            elif target_lane == 2:
                self.tr3_beats = list(lane_beats) if clear_first else sorted(list(set(self.tr3_beats + lane_beats)))
                self.timeline_widget.set_track_visible('tr3', True)

            self.timeline_widget.set_beats(
                tr1_beats=self.tr1_beats,
                tr2_beats=self.tr2_beats,
                tr3_beats=self.tr3_beats,
                video_parser_beats=self.video_parser_beats
            )
            self.update_inspector_stats()

            tr_name = {4: "Track 1", 1: "Track 2", 2: "Track 3"}.get(target_lane, f"Track {target_lane}")
            QMessageBox.information(
                self, "V3 Beats Generated",
                f"Generated {len(self.resulting_beats)} beats on {tr_name} based on {len(zones_data)} video zones and {len(levels_data)} sections!\n"
                f"Settings: Preset={preset}, Density={density_scale:.2f}, Grid={quantize_grid}\n"
                f"Beats are displayed on the timeline track above."
            )
        except Exception as e:
            QMessageBox.critical(self, "Generation Error", f"Failed to generate V3 beats:\n{e}")

    @property
    def zones_collection(self):
        return self.timeline_widget.zones_collection

    def _cleanup_player(self):
        # Safely stop playback without detaching sinks (which causes WMF thread deadlocks)
        try:
            if hasattr(self, 'play_timer') and self.play_timer:
                self.play_timer.stop()
            if hasattr(self, 'player') and self.player:
                self.player.stop()
            if hasattr(self, 'btn_play') and self.btn_play:
                self.btn_play.setText("Play")
                self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))
        except Exception as e:
            print("Safe player cleanup error in _cleanup_player:", e)

    def _sync_zones_and_levels(self):
        # Always sync current zones and levels state back
        try:
            if hasattr(self, 'timeline_widget') and self.timeline_widget:
                self.resulting_levels = self.timeline_widget.get_levels()
                sel_lvl = getattr(self.timeline_widget, 'selected_level', None)
                if sel_lvl:
                    self.resulting_level = sel_lvl.level
                    self.resulting_difficulty = sel_lvl.difficulty
                elif self.resulting_levels and len(self.resulting_levels) > 0:
                    first_lvl = self.resulting_levels[0]
                    if isinstance(first_lvl, dict):
                        self.resulting_level = first_lvl.get("level", self.initial_level)
                        self.resulting_difficulty = first_lvl.get("difficulty", self.initial_difficulty)
                    else:
                        self.resulting_level = getattr(first_lvl, "level", self.initial_level)
                        self.resulting_difficulty = getattr(first_lvl, "difficulty", self.initial_difficulty)
                else:
                    self.resulting_level = self.initial_level
                    self.resulting_difficulty = self.initial_difficulty

            if hasattr(self, 'cb_level_mode') and self.cb_level_mode:
                self.resulting_level_mode = self.cb_level_mode.currentData()
            else:
                self.resulting_level_mode = "ramp_within_level"

            parent_win = self.parent()
            if parent_win and hasattr(self, 'timeline_widget') and self.timeline_widget:
                if hasattr(parent_win, 'video_zones'):
                    parent_win.video_zones = self.timeline_widget.zones_collection
                if hasattr(parent_win, 'timeline') and hasattr(parent_win.timeline, 'set_levels'):
                    parent_win.timeline.set_levels(self.resulting_levels)
                if hasattr(parent_win, 'mark_unsaved_changes'):
                    parent_win.mark_unsaved_changes()
        except Exception as e:
            print("Sync zones and levels error:", e)

    def _prepare_to_close(self):
        """Idempotent teardown: stops media player and synchronizes zones back exactly once."""
        if getattr(self, '_is_closing', False):
            return
        self._is_closing = True
        self._cleanup_player()
        self._sync_zones_and_levels()

    def apply_and_close(self):
        if not self.resulting_beats:
            self.generate_v3_beats_from_zones()
        self.target_lane = self.cb_target_track.currentData() if hasattr(self, 'cb_target_track') else 4
        self.generated_beats = list(self.resulting_beats)

        if not getattr(self, 'difficulty_stats', None) and self.resulting_beats:
            from beat_generator import calculate_beat_difficulty
            self.difficulty_stats = calculate_beat_difficulty(self.resulting_beats, duration=self.duration, bpm=self.bpm)
        
        self._prepare_to_close()
        self.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
            return
        elif key == Qt.Key.Key_Escape:
            self._prepare_to_close()
            self.reject()
            event.accept()
            return
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                super().keyPressEvent(event)
                return
            if hasattr(self, 'timeline_widget'):
                if self.timeline_widget.selected_zone:
                    self.action_delete_selected_zone()
                    event.accept()
                    return
                elif self.timeline_widget.selected_level:
                    self.action_delete_selected_level()
                    event.accept()
                    return
        super().keyPressEvent(event)

    def reject(self):
        self._prepare_to_close()
        super().reject()

    def accept(self):
        self._prepare_to_close()
        super().accept()

    def done(self, r):
        self._prepare_to_close()
        super().done(r)

    def closeEvent(self, event):
        self._prepare_to_close()
        super().closeEvent(event)
