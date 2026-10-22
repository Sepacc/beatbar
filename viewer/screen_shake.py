"""
screen_shake.py - Screen Shake & Beat Hit Flash Controller for Video Viewer.

Implements the camera punch / screen shake & flash effects:
- Camera punch / zoom in-n-out centered on the video every time a beat hits.
- Screen Border Color Flash on beat hit (glowing neon border around video perimeter).
- Picture Color Flash on beat hit (translucent color wash over video picture).
- Triggers specifically in intense & speedy zones, or when there is a group of 5+ beats in a row.
- Smooth spring-decay interpolation ensuring crisp visual feedback without jitter.
"""

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QColor

try:
    from .skin_manager import SkinManager
except (ImportError, ValueError):
    from skin_manager import SkinManager


class ScreenShakeController(QObject):
    """
    Manages camera punch / zoom and screen border/picture flashes on the video canvas.
    """
    def __init__(self, video_canvas, parent=None):
        super().__init__(parent)
        self.video_canvas = video_canvas
        self.skin_mgr = SkinManager()

        self.current_zoom = 1.0
        self.current_flash_alpha = 0.0
        self.decay_rate = 0.88  # per 16ms tick (~320ms smooth bloom decay)
        self.is_active = False

        self.shake_timer = QTimer(self)
        self.shake_timer.setInterval(16)
        self.shake_timer.timeout.connect(self._on_tick)

    def on_beat_hit(self, beat, is_intense_or_burst):
        """
        Called when a beat lands on the beatbar target.
        Evaluates trigger criteria and initiates the camera punch / flash.
        """
        mode = self.skin_mgr.config.get("screen_shake_mode", "intense_and_bursts")

        if mode == "off":
            return

        should_shake = False
        if mode == "always":
            should_shake = True
        elif mode == "intense_and_bursts":
            should_shake = (
                is_intense_or_burst or
                beat.get('is_burst', False) or
                beat.get('in_intense_zone', False) or
                beat.get('in_speedy_zone', False)
            )

        if should_shake:
            self.trigger_shake()

    def trigger_shake(self, custom_strength=None):
        """Punches the zoom scale and/or triggers border/picture flash immediately."""
        strength = custom_strength or float(self.skin_mgr.config.get("screen_shake_strength", 0.045))
        # Effect type: "border_flash", "picture_flash", "shake", "both", "all"
        effect_type = self.skin_mgr.config.get("beat_hit_effect_type", "border_flash")

        # Color for border/picture flash (derived from skin or neon magenta)
        flash_col = QColor(self.skin_mgr.config.get("flash_color", "#e056fd"))

        if effect_type in ["shake", "both", "all"]:
            self.current_zoom = 1.0 + strength
            if self.video_canvas:
                self.video_canvas.set_zoom(self.current_zoom)

        if effect_type in ["border_flash", "picture_flash", "both", "all"]:
            self.current_flash_alpha = 1.0
            if self.video_canvas:
                self.video_canvas.set_flash(self.current_flash_alpha, flash_col, mode=effect_type)

        if not self.is_active:
            self.is_active = True
            self.shake_timer.start()

    def reset_geometry(self):
        """Restores video canvas zoom to 1.0x and resets flash alpha."""
        self.current_zoom = 1.0
        self.current_flash_alpha = 0.0
        if self.video_canvas:
            self.video_canvas.set_zoom(1.0)
            self.video_canvas.set_flash(0.0)
        self.is_active = False
        self.shake_timer.stop()

    def _on_tick(self):
        """Updates zoom level and flash alpha with smooth ease-out spring decay."""
        has_active_effect = False

        # Zoom decay
        delta = self.current_zoom - 1.0
        if delta > 0.001:
            self.current_zoom = 1.0 + delta * self.decay_rate
            if self.video_canvas:
                self.video_canvas.set_zoom(self.current_zoom)
            has_active_effect = True
        else:
            self.current_zoom = 1.0
            if self.video_canvas:
                self.video_canvas.set_zoom(1.0)

        # Flash alpha decay
        if self.current_flash_alpha > 0.01:
            self.current_flash_alpha *= self.decay_rate
            if self.video_canvas:
                self.video_canvas.set_flash(self.current_flash_alpha)
            has_active_effect = True
        else:
            self.current_flash_alpha = 0.0
            if self.video_canvas:
                self.video_canvas.set_flash(0.0)

        if not has_active_effect:
            self.reset_geometry()
