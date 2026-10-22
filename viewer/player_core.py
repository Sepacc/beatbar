"""
player_core.py - Media Player Engine and Playlist / Beatbar Matcher for Viewer.

Manages:
- Synchronized video/audio playback via QMediaPlayer & QAudioOutput.
- Automatic discovery of video files in folder and playlist cycling (Next Video).
- Intelligent auto-matching of video files to beatbar JSON files.
- High-frequency 60 FPS time synchronization with the Beatbar widget.
"""

import os
import json
import glob
from PyQt6.QtCore import QObject, QUrl, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# Add parent and main directories for beat_format
import sys
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_DIR = os.path.join(PARENT_DIR, "main")
for p in [PARENT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from beat_format import BeatFormat, load_beats, calculate_beat_difficulty, infer_zones_from_beats
try:
    from .skin_manager import SkinManager
except (ImportError, ValueError):
    from skin_manager import SkinManager

import time
import tempfile

VIDEO_EXTS = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.m4v']


class PlayerCore(QObject):
    """
    Video/Audio playback engine with playlist discovery and beatbar matching.
    Features high-precision clock interpolation to ensure buttery-smooth 60/120 FPS beat movement.
    """
    position_changed = pyqtSignal(float)
    duration_changed = pyqtSignal(float)
    playing_state_changed = pyqtSignal(bool)
    media_loaded = pyqtSignal(str, str, list, list)  # video_path, beat_path, beats, zones
    volume_changed = pyqtSignal(float, bool)  # volume, is_muted
    skin_updated = pyqtSignal(dict)  # skin_config dict from .beat archive
    playback_ended = pyqtSignal()

    def __init__(self, video_output, parent=None):
        super().__init__(parent)
        self.video_output = video_output
        
        # Qt Multimedia setup
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        
        if hasattr(self.video_output, 'sink'):
            self.player.setVideoSink(self.video_output.sink)
        elif hasattr(self.video_output, 'videoFrameChanged'):
            self.player.setVideoSink(self.video_output)
        else:
            self.player.setVideoOutput(self.video_output)
        
        # State
        self.video_path = ""
        self.beatbar_path = ""
        self.beats = []
        self.zones = []
        self.levels = []
        self.level_mode = "ramp_within_level"
        self.level = 1
        self.difficulty = "Normal"
        self.difficulty_stats = {}
        self.title = ""
        self.playlist = []
        self.playlist_idx = 0
        self.loop_enabled = True
        self.volume = 0.2
        self.playback_rate = 1.0
        self.duration = 1.0
        
        # High precision interpolation clock state
        self._smoothed_pos = 0.0
        self._last_perf_time = time.perf_counter()
        
        # 120 FPS High Precision Tracking Timer for silky smooth beatbar animation
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(8)
        self.track_timer.timeout.connect(self._on_track_tick)

        # QMediaPlayer signals
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        self.player.positionChanged.connect(self._on_player_position_sync)
        self.player.mediaStatusChanged.connect(self._on_player_media_status)

        self.audio_output.setVolume(self.volume)
        self.player.setLoops(QMediaPlayer.Loops.Infinite if self.loop_enabled else QMediaPlayer.Loops.Once)

    def load_video(self, video_path, beatbar_path=None):
        """Loads video file or .beat archive and automatically finds or loads matching beatbar."""
        if not video_path:
            return False

        # Support opening .beat file directly as the media source
        if video_path.lower().endswith(".beat"):
            return self.load_beat_pack(video_path)

        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            return False

        self.video_path = os.path.abspath(video_path)
        try:
            SkinManager().config["last_video_path"] = self.video_path
            SkinManager().save_config()
        except Exception:
            pass
        self._build_playlist(os.path.dirname(self.video_path))

        # Auto-match beatbar if not explicitly provided
        matched_new_beatbar = False
        if beatbar_path is None:
            beatbar_path = self.find_matching_beatbar(self.video_path)

        if beatbar_path and os.path.abspath(beatbar_path) != self.beatbar_path:
            matched_new_beatbar = True
            self.load_beatbar(beatbar_path)
        elif not beatbar_path and self.beatbar_path:
            matched_new_beatbar = True
            self.load_beatbar("")

        # Set media source
        self.player.setLoops(QMediaPlayer.Loops.Infinite if self.loop_enabled else QMediaPlayer.Loops.Once)
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.player.setPlaybackRate(self.playback_rate)

        # If load_beatbar was not invoked, emit media_loaded directly so UI updates!
        if not matched_new_beatbar:
            self.media_loaded.emit(self.video_path, self.beatbar_path, self.beats, self.zones)

        return True

    def load_beat_pack(self, beat_path):
        """
        Loads a .beat archive directly as the primary media container:
        1. Resolves video (extracts embedded video or searches for referenced video).
        2. Loads beats and rhythm zones.
        3. Extracts custom skin assets if included.
        4. Initializes video and emits media_loaded.
        """
        if not os.path.exists(beat_path):
            print(f".beat file not found: {beat_path}")
            return False

        vid_path = None
        is_embedded = False
        try:
            with BeatFormat.open(beat_path) as bf:
                bm = bf.get_beatmap()
                self.beats = bm.get("beats", [])
                self.zones = bm.get("zones", [])
                self.levels = bm.get("levels", [])
                self.level_mode = bm.get("level_mode", "ramp_within_level")
                self.beatbar_path = os.path.abspath(beat_path)
                self.title = bf.get_title() or bm.get("title", "") or os.path.splitext(os.path.basename(beat_path))[0]

                # Resolve video with expansive fallback directories
                search_dirs = [
                    os.path.dirname(os.path.abspath(beat_path)),
                    PARENT_DIR,
                    os.path.join(PARENT_DIR, "videos"),
                    os.path.join(PARENT_DIR, "1"),
                    os.path.expanduser("~/Downloads"),
                    os.path.expanduser("~/Videos"),
                    os.path.expanduser("~/Desktop"),
                ]
                try:
                    last_vid = SkinManager().config.get("last_video_path")
                    if last_vid and os.path.exists(last_vid):
                        search_dirs.append(os.path.dirname(last_vid))
                except Exception:
                    pass

                vid_path, is_embedded = bf.resolve_video(search_dirs=search_dirs)

                # Calculate difficulty stats from beats if not present
                diff_stats = bm.get("difficulty_stats")
                if not diff_stats and self.beats:
                    try:
                        from beat_format import calculate_beat_difficulty
                        diff_stats = calculate_beat_difficulty(self.beats)
                    except Exception:
                        diff_stats = {}
                self.difficulty_stats = diff_stats or {}

                # Determine Level: prioritize filename cues (e.g. 'level-1', 'no-09')
                import re
                raw_level = bm.get("level")
                m = re.search(r'(?:level|lv|no)[-_ ]*0*(\d+)', f"{self.title} {os.path.basename(beat_path)}", re.IGNORECASE)
                if m:
                    self.level = int(m.group(1))
                elif raw_level is not None:
                    self.level = raw_level
                elif self.difficulty_stats and "level" in self.difficulty_stats:
                    self.level = int(self.difficulty_stats["level"])
                else:
                    self.level = 1

                # Determine Difficulty
                raw_diff = bm.get("difficulty")
                if not raw_diff or raw_diff == "Normal":
                    if self.difficulty_stats and "difficulty" in self.difficulty_stats:
                        self.difficulty = self.difficulty_stats["difficulty"]
                    else:
                        self.difficulty = raw_diff or "Normal"
                else:
                    self.difficulty = raw_diff

                # Auto-generate rhythm zones if missing and beats exist
                if not self.zones and self.beats:
                    try:
                        from beat_format import infer_zones_from_beats
                        self.zones = infer_zones_from_beats(self.beats)
                    except Exception:
                        pass

                # Extract bundled skins if present and apply corresponding components
                skins = bf.list_skins()
                if skins:
                    pack_name = os.path.splitext(os.path.basename(beat_path))[0]
                    cache_dir = os.path.join(tempfile.gettempdir(), "beatmake_skins", pack_name)
                    skins_dir = bf.extract_skins(cache_dir)
                    skin_cfg = bf.get_skin_config()
                    if skin_cfg:
                        SkinManager().apply_skin_bundle(skins_dir, skin_cfg)
                        self.skin_updated.emit(skin_cfg)
        except Exception as e:
            print(f"Failed to read .beat archive {beat_path}:", e)
            return False

        try:
            SkinManager().config["last_beatbar_path"] = self.beatbar_path
            SkinManager().save_config()
        except Exception:
            pass

        if vid_path and os.path.exists(vid_path):
            self.video_path = os.path.abspath(vid_path)
            try:
                SkinManager().config["last_video_path"] = self.video_path
                SkinManager().save_config()
            except Exception:
                pass
            self._build_playlist(os.path.dirname(self.video_path))
            self.player.setLoops(QMediaPlayer.Loops.Infinite if self.loop_enabled else QMediaPlayer.Loops.Once)
            self.player.setSource(QUrl.fromLocalFile(self.video_path))
            self.player.setPlaybackRate(self.playback_rate)
            self.media_loaded.emit(self.video_path, self.beatbar_path, self.beats, self.zones)
            print(f"Loaded .beat pack: {len(self.beats)} beats, {len(self.zones)} zones, Level {self.level} ({self.difficulty}), video: {os.path.basename(self.video_path)} (embedded={is_embedded})")
            return True
        else:
            print(f"Loaded .beat pack without video: {len(self.beats)} beats, {len(self.zones)} zones from {beat_path}")
            self.video_path = ""
            self.media_loaded.emit("", self.beatbar_path, self.beats, self.zones)
            return False

    def load_beatbar(self, beatbar_path):
        """Loads beatbar JSON or .beat file, parsing beats, settings, and zones."""
        if not beatbar_path or not os.path.exists(beatbar_path):
            self.beatbar_path = ""
            self.beats = []
            self.zones = []
            self.media_loaded.emit(self.video_path, self.beatbar_path, self.beats, self.zones)
            return

        # If .beat file, load as complete pack with bundled/referenced video
        if beatbar_path.lower().endswith(".beat"):
            return self.load_beat_pack(beatbar_path)

        try:
            res = load_beats(beatbar_path)
            self.beatbar_path = os.path.abspath(beatbar_path)
            try:
                SkinManager().config["last_beatbar_path"] = self.beatbar_path
                SkinManager().save_config()
            except Exception:
                pass
            self.beats = res.beats
            self.zones = res.zones
            self.levels = getattr(res, 'levels', [])
            self.level_mode = getattr(res, 'level_mode', 'ramp_within_level')
            self.level = getattr(res, 'level', 1)
            self.difficulty = getattr(res, 'difficulty', 'Normal')
            self.difficulty_stats = getattr(res, 'difficulty_stats', {})
            self.title = getattr(res, 'title', os.path.splitext(os.path.basename(beatbar_path))[0])
            print(f"Loaded beatbar: {len(self.beats)} beats, {len(self.zones)} zones, Level {self.level} ({self.difficulty}) from {beatbar_path}")

            # Auto-infer zones if missing and beats exist
            if not self.zones and self.beats:
                try:
                    from beat_format import infer_zones_from_beats
                    self.zones = infer_zones_from_beats(self.beats)
                except Exception:
                    pass

            # Auto-load matching video if current video does not match
            if res.audio_file:
                cand = None
                dirs_to_check = [
                    os.path.dirname(self.beatbar_path),
                    PARENT_DIR,
                    os.path.join(PARENT_DIR, "videos"),
                    os.path.join(PARENT_DIR, "1"),
                    os.path.expanduser("~/Downloads"),
                    os.path.expanduser("~/Videos"),
                    os.path.expanduser("~/Desktop"),
                ]
                try:
                    last_v = SkinManager().config.get("last_video_path")
                    if last_v and os.path.exists(last_v):
                        dirs_to_check.append(os.path.dirname(last_v))
                except Exception:
                    pass

                for d in dirs_to_check:
                    c = os.path.join(d, res.audio_file)
                    if os.path.exists(c):
                        cand = c
                        break
                    if os.path.isdir(d):
                        base_stem = os.path.splitext(res.audio_file)[0].lower()
                        for vf in os.listdir(d):
                            if os.path.splitext(vf)[1].lower() in VIDEO_EXTS:
                                if os.path.splitext(vf)[0].lower() == base_stem:
                                    cand = os.path.join(d, vf)
                                    break
                    if cand:
                        break

                if cand and os.path.exists(cand) and (not self.video_path or not os.path.exists(self.video_path) or os.path.basename(self.video_path).lower() != os.path.basename(cand).lower()):
                    self.load_video(cand, self.beatbar_path)
                    return
        except Exception as e:
            print(f"Failed to load beatbar {beatbar_path}:", e)
            self.beats = []
            self.zones = []

        self.media_loaded.emit(self.video_path, self.beatbar_path, self.beats, self.zones)

    def find_matching_beatbar(self, video_path):
        """Discovers matching beatbar (.beat or .json) for a given video."""
        base = os.path.splitext(os.path.basename(video_path))[0]
        base_clean = base.lower().replace("_720p", "").replace("_1080p", "").replace("_480p", "").replace("-720p", "").replace("-1080p", "").replace("-480p", "")

        # Folders to inspect in priority order
        folders = [
            os.path.dirname(video_path),
            os.path.join(PARENT_DIR, "1"),
            os.path.join(PARENT_DIR, "videos"),
            PARENT_DIR,
        ]
        try:
            last_b = SkinManager().config.get("last_beatbar_path", "")
            if last_b and os.path.exists(last_b):
                folders.append(os.path.dirname(last_b))
        except Exception:
            pass

        # Check explicit priority candidates in all folders (.beat files first!)
        for folder in folders:
            if not folder or not os.path.isdir(folder):
                continue
            candidates = [
                os.path.join(folder, f"{base}.beat"),
                os.path.join(folder, f"{base}_beats.beat"),
                os.path.join(folder, f"{base_clean}.beat"),
                os.path.join(folder, f"{base_clean}_beats.beat"),
                os.path.join(folder, f"{base}.json"),
                os.path.join(folder, f"{base}_beats.json"),
                os.path.join(folder, f"{base}_V2.json"),
                os.path.join(folder, f"{base}_v2.json"),
                os.path.join(folder, f"{base}_video_beats.json"),
                os.path.join(folder, f"{base}_generated.json"),
                os.path.join(folder, f"{base}_v2_new.json"),
                os.path.join(folder, f"{base_clean}_beats.json"),
                os.path.join(folder, f"{base_clean}.json"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    return os.path.abspath(c)

        # Scan for any .beat or .json in those folders whose stem contains base_clean
        for folder in folders:
            if not folder or not os.path.isdir(folder):
                continue
            all_files = glob.glob(os.path.join(folder, "*.beat")) + glob.glob(os.path.join(folder, "*.json"))
            for j in all_files:
                j_base = os.path.splitext(os.path.basename(j))[0].lower()
                if base_clean and base_clean in j_base:
                    return os.path.abspath(j)
        return ""

    def _build_playlist(self, folder):
        """Finds all video files in the directory for seamless 'Next Video' browsing."""
        self.playlist = []
        for file in sorted(os.listdir(folder)):
            ext = os.path.splitext(file)[1].lower()
            if ext in VIDEO_EXTS:
                self.playlist.append(os.path.join(folder, file))

        if self.video_path in self.playlist:
            self.playlist_idx = self.playlist.index(self.video_path)
        else:
            self.playlist_idx = 0

    def play_next_video(self):
        """Switches to the next video in the playlist."""
        if not self.playlist:
            return
        self.playlist_idx = (self.playlist_idx + 1) % len(self.playlist)
        next_vid = self.playlist[self.playlist_idx]
        self.load_video(next_vid)
        self.play()

    def play(self):
        self._smoothed_pos = max(0.0, self.player.position() / 1000.0)
        self._last_perf_time = time.perf_counter()
        self.player.play()
        self.track_timer.start()

    def pause(self):
        self._smoothed_pos = max(0.0, self.player.position() / 1000.0)
        self.player.pause()
        self.track_timer.stop()

    def toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def seek(self, seconds):
        seconds = max(0.0, min(self.duration, float(seconds)))
        ms = int(seconds * 1000)
        self._smoothed_pos = seconds
        self._last_perf_time = time.perf_counter()
        self.player.setPosition(ms)
        self.position_changed.emit(seconds)

    def set_volume(self, vol):
        self.volume = max(0.0, min(1.0, float(vol)))
        self.audio_output.setVolume(self.volume)
        self.volume_changed.emit(self.volume, self.audio_output.isMuted())
        try:
            SkinManager().config["volume"] = self.volume
            SkinManager().save_config()
        except Exception:
            pass

    def toggle_mute(self):
        muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(muted)
        self.volume_changed.emit(self.volume, muted)
        try:
            SkinManager().config["is_muted"] = muted
            SkinManager().save_config()
        except Exception:
            pass

    def set_playback_rate(self, rate):
        self.playback_rate = max(0.2, min(4.0, float(rate)))
        self.player.setPlaybackRate(self.playback_rate)
        try:
            SkinManager().config["speed"] = self.playback_rate
            SkinManager().save_config()
        except Exception:
            pass

    def set_loop(self, enabled):
        self.loop_enabled = enabled
        self.player.setLoops(QMediaPlayer.Loops.Infinite if enabled else QMediaPlayer.Loops.Once)
        try:
            SkinManager().config["loop_enabled"] = self.loop_enabled
            SkinManager().save_config()
        except Exception:
            pass

    def _on_player_duration_changed(self, dur_ms):
        self.duration = max(0.1, dur_ms / 1000.0)
        self.duration_changed.emit(self.duration)

    def _on_player_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.playing_state_changed.emit(is_playing)
        if is_playing:
            self._smoothed_pos = max(0.0, self.player.position() / 1000.0)
            self._last_perf_time = time.perf_counter()
            self.track_timer.start()
        else:
            self.track_timer.stop()
            # If reached end and stopped, but loop is enabled (fallback if driver stopped):
            if state == QMediaPlayer.PlaybackState.StoppedState and self.loop_enabled:
                self.seek(0.0)
                self.play()

    def _on_player_position_sync(self, pos_ms):
        """Called whenever QMediaPlayer reports a raw position."""
        raw_sec = max(0.0, pos_ms / 1000.0)
        now = time.perf_counter()
        # If difference is larger than 0.12s, snap to raw (user seeked or video skipped)
        if abs(raw_sec - self._smoothed_pos) > 0.12:
            self._smoothed_pos = raw_sec
        else:
            # Soft low-pass filter to keep clocks gently locked without jitter
            self._smoothed_pos = self._smoothed_pos * 0.65 + raw_sec * 0.35
        self._last_perf_time = now

    def _on_track_tick(self):
        """High-precision time broadcast using clock interpolation for silky-smooth 60/120 FPS beat movement."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            now = time.perf_counter()
            dt = (now - self._last_perf_time) * self.playback_rate
            self._smoothed_pos += dt
            self._last_perf_time = now
            self._smoothed_pos = min(self.duration, max(0.0, self._smoothed_pos))
        else:
            self._smoothed_pos = max(0.0, self.player.position() / 1000.0)
            self._last_perf_time = time.perf_counter()

        self.position_changed.emit(self._smoothed_pos)

    def _on_player_media_status(self, status):
        """Emits playback_ended when video playback finishes naturally."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.playback_ended.emit()
