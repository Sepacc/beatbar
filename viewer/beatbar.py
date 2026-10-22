"""
beatbar.py - Interactive Stylized Beatbar Widget for Beatbar Viewer.

Faithfully implements the Beatbar UI from the reference designs:
- Fancy customizable angled panel with wing sigils, metallic border, and themes.
- Moving space where beats scroll towards the central target.
- Central target with hit animations (shockwaves, particles, scale pop).
- Triangular hit indicator arrow (▲).
- Customizable beat skins (purple demonic crests, neon gems, colored bars, orbs).
- Secondary timeline in the bottom notch that progressively fills as video plays.
"""

import math
import random
import os
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath,
    QPolygonF, QRadialGradient, QFont
)
try:
    from .skin_manager import SkinManager
except (ImportError, ValueError):
    from skin_manager import SkinManager


class HitParticle:
    """Represents a sparkling particle emitted upon a beat hit."""
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(40, 160)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(10, 40)
        self.life = 1.0  # 1.0 down to 0.0
        self.decay = random.uniform(2.5, 4.5)
        self.size = random.uniform(2.5, 5.5)
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 60 * dt  # subtle gravity
        self.life = max(0.0, self.life - self.decay * dt)
        return self.life > 0.0


class Shockwave:
    """Expanding glowing ring emitted upon a beat hit."""
    def __init__(self, x, y, max_radius, color):
        self.x = x
        self.y = y
        self.radius = 8.0
        self.max_radius = max_radius
        self.life = 1.0
        self.decay = 3.2
        self.color = color

    def update(self, dt):
        self.life = max(0.0, self.life - self.decay * dt)
        progress = 1.0 - self.life
        self.radius = 8.0 + (self.max_radius - 8.0) * math.sqrt(progress)
        return self.life > 0.0


class BeatBarWidget(QWidget):
    """
    The centerpiece Beatbar:
    - Renders the custom angled trapezoid panel based on beatmake-bar.svg & beatmake-2.jpg.
    - Features approaching beats, central target, hit animations, and secondary timeline.
    """
    beat_hit = pyqtSignal(dict, bool)  # beat, is_intense_or_burst
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.skin_mgr = SkinManager()
        
        # State
        self.current_time = 0.0
        self.duration = 1.0
        self.beats = []
        self.zones = []
        self.is_playing = False
        
        # Beat processing state
        self._last_processed_time = -1.0
        self._hit_beats_set = set()
        
        # Animations
        self.target_pop_scale = 1.0
        self.shockwaves = []
        self.particles = []
        
        # Animation loop timer (60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._on_anim_frame)
        self.anim_timer.start()

        # Mouse interaction for small timeline
        self._dragging_small_timeline = False

        # Panel geometry and padding/headroom for wings & effects
        self.bar_w = 0.0
        self.bar_h = 0.0
        self.pad_top = 0.0
        self.pad_bottom = 0.0
        self.pad_left = 0.0
        self.pad_right = 0.0
        self._last_bar_rect = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setMouseTracking(True)

    def set_bar_geometry(self, bar_x, bar_y, bar_w, bar_h):
        """
        Positions the visual beatbar panel at (bar_x, bar_y) with dimensions (bar_w, bar_h)
        while sizing the underlying QWidget with sufficient headroom and side padding so that
        elements sticking outside the panel (e.g. wings, shockwaves, particles) are never clipped.
        """
        self._last_bar_rect = (bar_x, bar_y, bar_w, bar_h)
        self._recompute_geometry()

    def _recompute_geometry(self):
        if not self._last_bar_rect:
            return
        bar_x, bar_y, bar_w, bar_h = self._last_bar_rect
        self.bar_w = float(bar_w)
        self.bar_h = float(bar_h)

        off_y_l = float(self.skin_mgr.config.get("wing_left_offset_y", 0.0))
        off_y_r = float(self.skin_mgr.config.get("wing_right_offset_y", 0.0))
        min_wing_y = min(0.0, (0.12 + min(off_y_l, off_y_r) / 100.0) * bar_h)

        off_x_l = float(self.skin_mgr.config.get("wing_left_offset_x", 0.0))
        off_x_r = float(self.skin_mgr.config.get("wing_right_offset_x", 0.0))
        scale_r = float(self.skin_mgr.config.get("wing_right_scale", 1.0))
        min_wing_x = min(0.0, (0.045 + off_x_l / 1000.0) * bar_w)
        max_wing_x = max(bar_w, (0.955 + off_x_r / 1000.0) * bar_w + bar_h * 0.65 * (scale_r - 1.0))

        pad_top = max(80, int(bar_h * 1.25), int(abs(min_wing_y) + 30))
        pad_bottom = max(24, int(bar_h * 0.35))
        pad_left = max(60, int(bar_w * 0.08), int(abs(min_wing_x) + 30))
        pad_right = max(60, int(bar_w * 0.08), int(max(0, max_wing_x - bar_w) + 30))

        # Clamp padding so widget doesn't extend beyond parent window bounds
        pad_left = min(pad_left, max(0, bar_x))
        pad_top = min(pad_top, max(0, bar_y))

        self.pad_top = float(pad_top)
        self.pad_bottom = float(pad_bottom)
        self.pad_left = float(pad_left)
        self.pad_right = float(pad_right)

        wx = int(bar_x - pad_left)
        wy = int(bar_y - pad_top)
        ww = int(bar_w + pad_left + pad_right)
        wh = int(bar_h + pad_top + pad_bottom)

        self.setGeometry(wx, wy, ww, wh)

    def set_duration(self, duration_sec):
        self.duration = max(0.1, float(duration_sec))
        self.update()

    def set_current_time(self, time_sec):
        old_time = self.current_time
        self.current_time = max(0.0, float(time_sec))

        # If seeking backward or major jump, reset hit tracking
        if abs(self.current_time - old_time) > 0.5:
            self._hit_beats_set.clear()

        # Check for beat hits
        self._check_beat_hits(old_time, self.current_time)
        self.update()

    def set_beats_and_zones(self, beats, zones=None):
        """Sets beats and zones, pre-calculating 5+ beat bursts and zone associations."""
        self.beats = sorted(beats or [], key=lambda b: b.get('time', 0.0))
        self.zones = zones or []
        self._hit_beats_set.clear()

        # Tag beats with burst and zone info
        self._tag_beat_bursts_and_zones()
        self.update()

    def _tag_beat_bursts_and_zones(self):
        """Identifies rapid streaks of 5+ beats and checks intense/speedy zones."""
        n = len(self.beats)
        for b in self.beats:
            b['is_burst'] = False
            b['in_intense_zone'] = False
            b['in_speedy_zone'] = False

        # 1. Detect 5+ beats in a row (gap <= 0.35s between consecutive beats)
        i = 0
        while i < n:
            run_end = i
            while run_end + 1 < n and (self.beats[run_end + 1]['time'] - self.beats[run_end]['time']) <= 0.36:
                run_end += 1
            
            run_length = run_end - i + 1
            if run_length >= 5:
                for k in range(i, run_end + 1):
                    self.beats[k]['is_burst'] = True
            i = run_end + 1

        # 2. Check zones
        for b in self.beats:
            bt = b.get('time', 0.0)
            for z in self.zones:
                st = z.get('start_time', z.get('start', 0.0))
                et = z.get('end_time', z.get('end', 0.0))
                ztype = z.get('type', z.get('zone_type', 'normal')).lower()
                if st <= bt <= et:
                    if ztype in ['climax', 'edging', 'intense']:
                        b['in_intense_zone'] = True
                    elif ztype in ['speeding_up', 'speedy', 'fast']:
                        b['in_speedy_zone'] = True

    def _check_beat_hits(self, t_prev, t_curr):
        """Detects if any beat crossed the hit point between t_prev and t_curr."""
        if not self.beats or t_curr < t_prev:
            return

        # Hit window around current time
        window = max(0.04, t_curr - t_prev)
        for b in self.beats:
            bt = b.get('time', 0.0)
            if bt not in self._hit_beats_set and (t_prev - 0.01 <= bt <= t_curr + 0.02):
                self._hit_beats_set.add(bt)
                is_intense_or_burst = b.get('in_intense_zone', False) or b.get('in_speedy_zone', False) or b.get('is_burst', False)
                self._trigger_hit(b, is_intense_or_burst)

    def _trigger_hit(self, beat, is_intense_or_burst):
        """Triggers visual target animations and emits hit signal for screen shake."""
        palette = self.skin_mgr.get_palette()
        hit_anim = self.skin_mgr.config.get("hit_animation", "shockwave")

        # Target scale pop & hit duration from config
        pop_mult = float(self.skin_mgr.config.get("trigger_hit_pop_scale", 1.35))
        self.target_pop_scale = pop_mult if is_intense_or_burst else (1.0 + (pop_mult - 1.0) * 0.7)
        dur_ms = float(self.skin_mgr.config.get("trigger_hit_duration_ms", 180))
        self.hit_state_time_left = max(0.06, dur_ms / 1000.0)

        bar_w = float(self.bar_w if self.bar_w > 0 else self.width())
        bar_h = float(self.bar_h if self.bar_h > 0 else self.height())
        center_x = bar_w / 2.0
        center_y = bar_h * 0.42

        hit_color = QColor(palette["glow"])

        # Shockwave
        if hit_anim in ["shockwave", "ripple", "all"]:
            self.shockwaves.append(Shockwave(center_x, center_y, max_radius=bar_h * 0.9, color=hit_color))

        # Particles
        if hit_anim in ["burst", "all"] or is_intense_or_burst:
            count = 14 if is_intense_or_burst else 7
            for _ in range(count):
                self.particles.append(HitParticle(center_x, center_y, hit_color))

        # Emit signal for camera punch / screen shake
        self.beat_hit.emit(beat, is_intense_or_burst)

    def _on_anim_frame(self):
        """60 FPS physics and particle update loop."""
        dt = 0.016
        needs_redraw = False

        # Target scale spring decay
        if self.target_pop_scale > 1.0:
            self.target_pop_scale = max(1.0, self.target_pop_scale - (self.target_pop_scale - 1.0) * 12.0 * dt)
            needs_redraw = True

        # Target hit 2nd state duration timer
        if hasattr(self, "hit_state_time_left") and self.hit_state_time_left > 0:
            self.hit_state_time_left -= dt
            needs_redraw = True

        # Update shockwaves
        if self.shockwaves:
            self.shockwaves = [sw for sw in self.shockwaves if sw.update(dt)]
            needs_redraw = True

        # Update particles
        if self.particles:
            self.particles = [p for p in self.particles if p.update(dt)]
            needs_redraw = True

        if needs_redraw:
            self.update()

    # ==========================================================================
    # PAINTING
    # ==========================================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        bar_w = float(self.bar_w if self.bar_w > 0 else self.width())
        bar_h = float(self.bar_h if self.bar_h > 0 else self.height())
        pad_left = float(self.pad_left)
        pad_top = float(self.pad_top)

        painter.save()
        painter.translate(pad_left, pad_top)

        palette = self.skin_mgr.get_palette()

        # 1. Draw Fancy Outer Angled Panel
        self._paint_panel(painter, bar_w, bar_h, palette)

        # 2. Draw End Wing Sigils
        self._paint_wing_sigils(painter, bar_w, bar_h, palette)

        # 3. Draw Moving Beats
        self._paint_beats(painter, bar_w, bar_h, palette)

        # 4. Draw Central Target & Triangular Indicator
        self._paint_target_and_indicator(painter, bar_w, bar_h, palette)

        # 5. Draw Hit Shockwaves & Particles
        self._paint_hit_effects(painter, palette)

        # 6. Draw Small Bottom Timeline (Fill that progresses with video)
        self._paint_small_timeline(painter, bar_w, bar_h, palette)

        painter.restore()
        painter.end()

    def _get_panel_path(self, W, H):
        """Constructs vector path for the angled panel matching beatmake-bar.svg & beatmake-2.jpg."""
        path = QPainterPath()
        # Relative coordinates mapped to current widget size
        # Top-left wing
        x_left_wing_tip = W * 0.015
        y_top_wing = H * 0.10
        x_left_top = W * 0.045
        
        # Center tab
        x_tab_l1 = W * 0.43
        x_tab_l2 = W * 0.445
        y_tab_top = H * 0.03
        x_tab_r2 = W * 0.555
        x_tab_r1 = W * 0.57
        
        # Right wing
        x_right_top = W * 0.955
        x_right_wing_tip = W * 0.985
        
        # Main bar bottom
        y_bar_bottom = H * 0.76
        
        # Bottom notch cutout for secondary timeline
        x_notch_r1 = W * 0.71
        x_notch_r2 = W * 0.70
        y_notch_bottom = H * 0.96
        x_notch_l2 = W * 0.30
        x_notch_l1 = W * 0.29

        path.moveTo(x_left_wing_tip, y_top_wing + H * 0.04)
        path.lineTo(x_left_top, y_top_wing)
        path.lineTo(x_tab_l1, y_top_wing)
        path.lineTo(x_tab_l2, y_tab_top)
        path.lineTo(x_tab_r2, y_tab_top)
        path.lineTo(x_tab_r1, y_top_wing)
        path.lineTo(x_right_top, y_top_wing)
        path.lineTo(x_right_wing_tip, y_top_wing + H * 0.04)
        path.lineTo(x_right_top, y_bar_bottom)
        path.lineTo(x_notch_r1, y_bar_bottom)
        path.lineTo(x_notch_r2, y_notch_bottom)
        path.lineTo(x_notch_l2, y_notch_bottom)
        path.lineTo(x_notch_l1, y_bar_bottom)
        path.lineTo(x_left_top, y_bar_bottom)
        path.closeSubpath()
        return path

    def _get_clean_panel_path(self, W, H):
        """Constructs vector path for the Clean Template matching beatmake-bar.svg exactly."""
        path = QPainterPath()
        sx = W / 3497.0
        sy = H / 174.0

        p1_x = 5.342 * sx
        p1_y = 8.772 * sy
        p2_x = 3436.940 * sx
        p2_y = 8.772 * sy
        p3_x = 3436.940 * sx
        p3_y = 15.201 * sy
        p4_x = 3367.097 * sx
        p4_y = 131.875 * sy
        p5_x = 2480.068 * sx
        p5_y = 131.875 * sy
        p6_x = 2449.305 * sx
        p6_y = 164.945 * sy
        p7_x = 993.617 * sx
        p7_y = 164.945 * sy
        p8_x = 962.854 * sx
        p8_y = 131.875 * sy
        p9_x = 75.847 * sx
        p9_y = 131.875 * sy
        p10_x = 5.342 * sx
        p10_y = 15.201 * sy

        path.moveTo(p1_x, p1_y)
        path.lineTo(p2_x, p2_y)
        path.lineTo(p3_x, p3_y)
        path.lineTo(p4_x, p4_y)
        path.lineTo(p5_x, p5_y)
        path.lineTo(p6_x, p6_y)
        path.lineTo(p7_x, p7_y)
        path.lineTo(p8_x, p8_y)
        path.lineTo(p9_x, p9_y)
        path.lineTo(p10_x, p10_y)
        path.closeSubpath()
        return path

    def _paint_panel(self, painter, W, H, palette):
        """Paints the main trapezoidal panel with metallic sheen and stylish borders."""
        skin = self.skin_mgr.config.get("panel_skin", "cyber_wings")
        is_clean = skin in ("classic_svg", "clean_template")

        if is_clean:
            panel_path = self._get_clean_panel_path(W, H)
        else:
            panel_path = self._get_panel_path(W, H)

        # Gradient fill (dark metallic cyberpunk charcoal)
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor("#282830"))
        grad.setColorAt(0.2, QColor("#18181e"))
        grad.setColorAt(0.7, QColor("#0d0d12"))
        grad.setColorAt(1.0, QColor("#1c1c24"))

        # Border gradient
        border_grad = QLinearGradient(0, 0, W, 0)
        border_color = QColor(palette["panel_border"])
        border_grad.setColorAt(0.0, QColor("#666670"))
        border_grad.setColorAt(0.18, border_color)
        border_grad.setColorAt(0.5, QColor(palette["glow"]))
        border_grad.setColorAt(0.82, border_color)
        border_grad.setColorAt(1.0, QColor("#666670"))

        painter.save()
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QBrush(border_grad), 2.2))
        painter.drawPath(panel_path)

        # Inner Top Rim Highlight
        rim_pen = QPen(QColor(255, 255, 255, 60), 1.2)
        painter.setPen(rim_pen)
        if is_clean:
            top_y = H * (8.772 / 174.0) + 1.2
            painter.drawLine(QPointF(W * 0.02, top_y), QPointF(W * 0.98, top_y))
        else:
            painter.drawLine(QPointF(W * 0.05, H * 0.12), QPointF(W * 0.43, H * 0.12))
            painter.drawLine(QPointF(W * 0.445, H * 0.05), QPointF(W * 0.555, H * 0.05))
            painter.drawLine(QPointF(W * 0.57, H * 0.12), QPointF(W * 0.95, H * 0.12))

        # Check if custom SVG/image skin applies
        if skin == "custom" or str(skin).startswith("bundle_"):
            svg_path = self.skin_mgr.get_panel_svg_path()
            if svg_path:
                renderer = self.skin_mgr.get_svg_renderer(svg_path)
                if renderer:
                    renderer.render(painter, QRectF(0, 0, W, H))

        painter.restore()

    def _paint_wing_sigils(self, painter, W, H, palette):
        """Draws the stylized metallic wing emblems at left and right ends with customizable offset & scale."""
        skin = self.skin_mgr.config.get("panel_skin", "cyber_wings")
        has_custom_wings = bool(self.skin_mgr.config.get("custom_wing_left_path") or self.skin_mgr.config.get("custom_wing_right_path"))
        if skin in ("classic_svg", "clean_template") and not has_custom_wings:
            return  # Clean template without custom wings does not show wings

        left_svg, right_svg = self.skin_mgr.get_wing_sigil_paths()
        r_left = self.skin_mgr.get_svg_renderer(left_svg)
        r_right = self.skin_mgr.get_svg_renderer(right_svg)

        scale_l = float(self.skin_mgr.config.get("wing_left_scale", 1.0))
        off_x_l = float(self.skin_mgr.config.get("wing_left_offset_x", 0.0)) * (W / 1000.0)
        off_y_l = float(self.skin_mgr.config.get("wing_left_offset_y", 0.0)) * (H / 100.0)

        scale_r = float(self.skin_mgr.config.get("wing_right_scale", 1.0))
        off_x_r = float(self.skin_mgr.config.get("wing_right_offset_x", 0.0)) * (W / 1000.0)
        off_y_r = float(self.skin_mgr.config.get("wing_right_offset_y", 0.0)) * (H / 100.0)

        base_w = H * 0.65
        base_h = H * 0.60
        base_y = H * 0.12

        if r_left:
            wl = base_w * scale_l
            hl = base_h * scale_l
            target_left = QRectF(W * 0.045 + off_x_l, base_y + off_y_l, wl, hl)
            r_left.render(painter, target_left)
        if r_right:
            wr = base_w * scale_r
            hr = base_h * scale_r
            target_right = QRectF(W * 0.955 - wr + off_x_r, base_y + off_y_r, wr, hr)
            r_right.render(painter, target_right)

    def get_beat_direction(self, b):
        """
        Determines the scroll direction for a given beat:
        - Checks individual zone direction overrides
        - Checks intense zones setting ('ltr', 'both', 'rtl')
        - Falls back to default scroll direction
        """
        bt = b.get('time', 0.0)
        zone_overrides = self.skin_mgr.config.get("zone_direction_overrides", {})
        zone_type_dirs = self.skin_mgr.config.get("zone_type_directions", {
            "climax": "ltr",
            "edging": "ltr",
            "intense": "ltr",
            "speeding_up": "both",
            "fast": "both",
            "normal": "rtl",
            "pause": "rtl"
        })

        # Check if beat falls in any zone with override or type setting
        for z in self.zones:
            st = z.get('start_time', z.get('start', 0.0))
            et = z.get('end_time', z.get('end', 0.0))
            if st <= bt <= et:
                zid = str(z.get('id', ''))
                zname = str(z.get('name', ''))
                # Extended mode individual override takes highest priority if not "default"
                if zid in zone_overrides and zone_overrides[zid] != "default":
                    return zone_overrides[zid]
                if zname in zone_overrides and zone_overrides[zname] != "default":
                    return zone_overrides[zname]

                # Simple mode zone type direction
                ztype = str(z.get('type', z.get('zone_type', 'normal'))).lower()
                if ztype in zone_type_dirs:
                    return zone_type_dirs[ztype]

                if ztype in ['climax', 'edging', 'intense', 'speeding_up', 'speedy', 'fast']:
                    return self.skin_mgr.config.get("intense_zones_direction", "ltr")
                elif ztype in ['pause', 'slow', 'normal']:
                    return "rtl"

        # Fallback if tagged by burst or intense
        if b.get('in_intense_zone') or b.get('is_burst') or b.get('in_speedy_zone'):
            return self.skin_mgr.config.get("intense_zones_direction", "ltr")

        return self.skin_mgr.config.get("scroll_direction", "rtl")

    def _draw_single_beat(self, painter, bx, center_y, bw, bh, lane_height, beat_skin, b, alpha, renderer, palette, flip_h=False):
        """Renders one visual instance of a beat at position bx, optionally flipped horizontally."""
        if beat_skin == "lane_bar":
            bar_w = max(8.0, bw * 0.60)
            bar_h = lane_height
            lane_idx = b.get('lane', 4)
            colors = ["#ff4757", "#2ed573", "#1e90ff", "#ffa502", "#be2edd"]
            col = QColor(colors[lane_idx % len(colors)])
            col.setAlpha(alpha)
            painter.setBrush(QBrush(col))
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.5))
            painter.drawRoundedRect(QRectF(bx - bar_w / 2, center_y - bar_h / 2, bar_w, bar_h), 4, 4)
        else:
            painter.save()
            painter.setOpacity(alpha / 255.0)
            if flip_h:
                painter.translate(bx, center_y)
                painter.scale(-1.0, 1.0)
                draw_rect = QRectF(-bw / 2.0, -bh / 2.0, bw, bh)
            else:
                painter.translate(bx, center_y)
                draw_rect = QRectF(-bw / 2.0, -bh / 2.0, bw, bh)

            if renderer:
                renderer.render(painter, draw_rect)
            else:
                col = QColor(palette["primary"])
                col.setAlpha(alpha)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.5))
                poly = QPolygonF([
                    QPointF(0, -bh / 2.0),
                    QPointF(bw / 2.0, 0),
                    QPointF(0, bh / 2.0),
                    QPointF(-bw / 2.0, 0)
                ])
                painter.drawPolygon(poly)
            painter.restore()

    def _paint_beats(self, painter, W, H, palette):
        """Renders approaching beats traveling horizontally towards the central target."""
        if not self.beats:
            return

        lead_time = float(self.skin_mgr.config.get("lead_time", 1.5))
        beat_scale = float(self.skin_mgr.config.get("beat_scale", 1.0))
        anti_overlap = bool(self.skin_mgr.config.get("anti_overlap_beats", True))
        beat_skin = self.skin_mgr.config.get("beats_skin", "crest")
        renderer = self.skin_mgr.get_svg_renderer(self.skin_mgr.get_beat_svg_path())

        flip_l = bool(self.skin_mgr.config.get("flip_left_beats", False))
        flip_r = bool(self.skin_mgr.config.get("flip_right_beats", False))

        center_x = W / 2.0
        center_y = H * 0.42
        lane_height = H * 0.46
        travel_distance = W * 0.43

        base_bw = H * 0.44 * beat_scale
        base_bh = H * 0.42 * beat_scale

        painter.save()

        # Visible time window: beats that will arrive in the next `lead_time` seconds,
        # or beats that arrived within the last 0.08s (for smooth hit transition)
        t_now = self.current_time

        # 1. Collect visible beats
        visible_entries = []
        for b in self.beats:
            bt = b.get('time', 0.0)
            time_diff = bt - t_now
            if -0.08 <= time_diff <= lead_time:
                visible_entries.append((b, time_diff))

        # 2. Smart anti-overlap scaling for rapid bursts (e.g. 2 or 3 consecutive beats)
        overlap_scales = {}
        if anti_overlap and len(visible_entries) > 1:
            right_stream = [b for (b, td) in visible_entries if self.get_beat_direction(b) in ("rtl", "both")]
            left_stream = [b for (b, td) in visible_entries if self.get_beat_direction(b) in ("ltr", "both")]

            def _calc_scales(stream):
                res = {}
                n = len(stream)
                for i in range(n):
                    cur_t = stream[i].get('time', 0.0)
                    dt_p = (cur_t - stream[i - 1].get('time', 0.0)) if i > 0 else 999.0
                    dt_n = (stream[i + 1].get('time', 0.0) - cur_t) if i + 1 < n else 999.0
                    min_dt = min(dt_p, dt_n)
                    px_dist = (min_dt / lead_time) * travel_distance
                    if px_dist < base_bw:
                        res[id(stream[i])] = max(0.55, min(1.0, px_dist / (base_bw * 0.92)))
                    else:
                        res[id(stream[i])] = 1.0
                return res

            sc_r = _calc_scales(right_stream)
            sc_l = _calc_scales(left_stream)

            for b, _ in visible_entries:
                bid = id(b)
                overlap_scales[bid] = min(sc_r.get(bid, 1.0), sc_l.get(bid, 1.0))

        # 3. Draw approaching beats
        for b, time_diff in visible_entries:
            norm_pos = time_diff / lead_time  # 1.0 (spawn) down to 0.0 (hit point)

            alpha = 255
            if time_diff < 0:
                alpha = max(0, int(255 * (1.0 + time_diff / 0.08)))

            scale_mult = overlap_scales.get(id(b), 1.0)
            bw = base_bw * scale_mult
            bh = base_bh * scale_mult

            dir_mode = self.get_beat_direction(b)

            if dir_mode == "ltr":
                bx = center_x - norm_pos * travel_distance
                should_flip = flip_l if bx < center_x else flip_r
                self._draw_single_beat(painter, bx, center_y, bw, bh, lane_height, beat_skin, b, alpha, renderer, palette, flip_h=should_flip)
            elif dir_mode == "both":
                bx_right = center_x + norm_pos * travel_distance
                bx_left = center_x - norm_pos * travel_distance
                self._draw_single_beat(painter, bx_right, center_y, bw, bh, lane_height, beat_skin, b, alpha, renderer, palette, flip_h=flip_r)
                self._draw_single_beat(painter, bx_left, center_y, bw, bh, lane_height, beat_skin, b, alpha, renderer, palette, flip_h=flip_l)
            else:  # rtl (default)
                bx = center_x + norm_pos * travel_distance
                should_flip = flip_r if bx > center_x else flip_l
                self._draw_single_beat(painter, bx, center_y, bw, bh, lane_height, beat_skin, b, alpha, renderer, palette, flip_h=should_flip)

        painter.restore()

    def _paint_target_and_indicator(self, painter, W, H, palette):
        """Renders the central target entity (with 2nd state hit SVG), and customizable hit indicator."""
        center_x = W / 2.0
        center_y = H * 0.40

        scale_t = float(self.skin_mgr.config.get("target_scale", 1.0))
        off_x_t = float(self.skin_mgr.config.get("target_offset_x", 0.0)) * (W / 1000.0)
        off_y_t = float(self.skin_mgr.config.get("target_offset_y", 0.0)) * (H / 100.0)

        painter.save()

        # 1. Central Target (scaled by hit pop & target_scale)
        tw = H * 0.85 * self.target_pop_scale * scale_t
        th = H * 0.52 * self.target_pop_scale * scale_t
        target_rect = QRectF(center_x + off_x_t - tw / 2.0, center_y + off_y_t - th / 2.0, tw, th)

        is_hit = getattr(self, "hit_state_time_left", 0.0) > 0.0 or getattr(self, "target_pop_scale", 1.0) > 1.05
        hit_svg_path = self.skin_mgr.get_target_hit_svg_path()

        if is_hit and hit_svg_path:
            renderer = self.skin_mgr.get_svg_renderer(hit_svg_path)
        else:
            renderer = self.skin_mgr.get_svg_renderer(self.skin_mgr.get_target_svg_path())

        if renderer:
            renderer.render(painter, target_rect)
        else:
            # Fallback procedural crest/reticle
            painter.setPen(QPen(QColor(palette["glow"]), 2.0))
            painter.setBrush(QBrush(QColor(palette["target"])))
            painter.drawRoundedRect(target_rect, 6, 6)

        # 2. Customizable Hit Indicator beneath target
        ind_style = self.skin_mgr.config.get("trigger_hit_indicator_style", "triangle")
        if ind_style not in ("hidden", "off"):
            ind_color = QColor(self.skin_mgr.config.get("trigger_hit_indicator_color", "#ffffff"))
            arrow_y = H * 0.76 + off_y_t
            arrow_h = H * 0.12 * scale_t
            arrow_w = arrow_h * 1.3
            ind_x = center_x + off_x_t

            if ind_style == "diamond":
                dh = arrow_h * 1.08
                dw = dh * 0.76
                poly = QPolygonF([
                    QPointF(ind_x, arrow_y - dh),
                    QPointF(ind_x + dw / 2.0, arrow_y - dh / 2.0),
                    QPointF(ind_x, arrow_y),
                    QPointF(ind_x - dw / 2.0, arrow_y - dh / 2.0)
                ])
                painter.setBrush(QBrush(ind_color))
                painter.setPen(QPen(QColor(palette["panel_border"]), 1.2))
                painter.drawPolygon(poly)
            elif ind_style == "glow_bar":
                bw = arrow_h * 2.2
                bh = arrow_h * 0.4
                r = QRectF(ind_x - bw / 2.0, arrow_y - bh, bw, bh)
                painter.setBrush(QBrush(ind_color))
                painter.setPen(QPen(QColor(palette["glow"]), 1.5))
                painter.drawRoundedRect(r, 2, 2)
            else:  # "triangle"
                arrow_poly = QPolygonF([
                    QPointF(ind_x, arrow_y - arrow_h),
                    QPointF(ind_x + arrow_w / 2.0, arrow_y),
                    QPointF(ind_x - arrow_w / 2.0, arrow_y)
                ])
                painter.setBrush(QBrush(ind_color))
                painter.setPen(QPen(QColor(palette["panel_border"]), 1.2))
                painter.drawPolygon(arrow_poly)

        painter.restore()

    def _paint_hit_effects(self, painter, palette):
        """Draws glowing expanding shockwaves and sparkling burst particles."""
        painter.save()

        # Shockwaves
        for sw in self.shockwaves:
            col = QColor(sw.color)
            col.setAlpha(int(255 * sw.life))
            painter.setPen(QPen(col, 2.5 * sw.life + 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(sw.x, sw.y), sw.radius, sw.radius * 0.6)

        # Particles
        for p in self.particles:
            col = QColor(p.color)
            col.setAlpha(int(255 * p.life))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(col))
            painter.drawEllipse(QPointF(p.x, p.y), p.size * p.life, p.size * p.life)

        painter.restore()

    def _paint_small_timeline(self, painter, W, H, palette):
        """
        Renders the secondary progress timeline in the bottom notch of the panel.
        Styled faithfully after the polished cyberpunk web viewer:
        - Sleek recessed dark track groove with subtle border
        - Semi-transparent rhythm zone roadmap segments inside track (when zones loaded)
        - Vibrant primary -> accent -> white glowing gradient
        - Glassy top-edge reflection sheen for a glossy OLED look
        - Luminous white tip line with glowing accent aura
        - Clean rounded clipping to prevent edge spill
        - Full support for customizable fill modes (center_out, reverse, etc.)
        """
        notch_l = W * 0.30
        notch_r = W * 0.70
        notch_w = notch_r - notch_l
        notch_y = H * 0.80
        notch_h = H * 0.14

        track_rect = QRectF(notch_l, notch_y, notch_w, notch_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Track background (sleek recessed dark groove with subtle border)
        track_grad = QLinearGradient(notch_l, notch_y, notch_l, notch_y + notch_h)
        track_grad.setColorAt(0.0, QColor("#09090d"))
        track_grad.setColorAt(0.5, QColor("#121218"))
        track_grad.setColorAt(1.0, QColor("#181822"))
        painter.setBrush(QBrush(track_grad))
        painter.setPen(QPen(QColor("#2a2a36"), 1.0))
        painter.drawRoundedRect(track_rect, 2.5, 2.5)

        # 2. Semi-translucent rhythm zone roadmap segments inside track
        show_zones = self.skin_mgr.config.get("show_timeline_zones", True)
        if show_zones and self.zones and self.duration > 0:
            def _get_notch_zone_color(ztype):
                zt = str(ztype).lower()
                if zt in ['climax', 'intense']:
                    return QColor(255, 71, 87, 50)
                elif zt in ['edging']:
                    return QColor(190, 46, 221, 50)
                elif zt in ['speeding_up', 'speedy', 'fast']:
                    return QColor(255, 165, 2, 50)
                elif zt in ['pause', 'slow']:
                    return QColor(55, 66, 250, 50)
                elif zt in ['credits', 'outro']:
                    return QColor(99, 102, 241, 50)
                else:
                    return QColor(46, 213, 115, 50)

            for z in self.zones:
                st = max(0.0, min(self.duration, float(z.get('start_time', z.get('start', 0.0)))))
                et = max(0.0, min(self.duration, float(z.get('end_time', z.get('end', 0.0)))))
                if et <= st:
                    continue
                zx1 = notch_l + notch_w * (st / self.duration)
                zx2 = notch_l + notch_w * (et / self.duration)
                zw = max(1.0, zx2 - zx1)
                painter.fillRect(QRectF(zx1, notch_y + 1.0, zw, notch_h - 2.0), _get_notch_zone_color(z.get('type', z.get('zone_type', 'normal'))))

        # 3. Calculate progress
        mode = self.skin_mgr.config.get("timeline_fill_mode", "left_to_right")
        fill_per_zone = self.skin_mgr.config.get("fill_timeline_per_zone", False)
        active_zone = None
        if fill_per_zone and self.zones:
            for z in self.zones:
                st = float(z.get('start_time', z.get('start', 0.0)))
                et = float(z.get('end_time', z.get('end', 0.0)))
                if st <= self.current_time <= et:
                    active_zone = z
                    break

        if active_zone:
            z_st = float(active_zone.get('start_time', active_zone.get('start', 0.0)))
            z_et = float(active_zone.get('end_time', active_zone.get('end', 0.0)))
            progress = max(0.0, min(1.0, (self.current_time - z_st) / max(0.1, z_et - z_st)))
        else:
            progress = max(0.0, min(1.0, self.current_time / max(0.1, self.duration)))

        # Palette colors (matches web version's primary -> accent -> white glowing gradient)
        col_primary = QColor(palette.get("primary", "#be2edd"))
        col_accent = QColor(palette.get("accent", "#e056fd"))
        col_glow = QColor(palette.get("glow", col_accent.name()))

        # Clip fill inside the track rounded rect
        clip_path = QPainterPath()
        clip_path.addRoundedRect(track_rect, 2.5, 2.5)
        painter.setClipPath(clip_path)

        def draw_bar_segment(rx, rw, reversed_grad=False):
            if rw <= 0.8:
                return
            fill_rect = QRectF(rx, notch_y, rw, notch_h)
            fill_grad = QLinearGradient(rx, notch_y, rx + rw, notch_y)
            if not reversed_grad:
                fill_grad.setColorAt(0.0, col_primary)
                fill_grad.setColorAt(0.70, col_accent)
                fill_grad.setColorAt(0.92, col_accent.lighter(130))
                fill_grad.setColorAt(1.0, QColor("#ffffff"))
            else:
                fill_grad.setColorAt(0.0, QColor("#ffffff"))
                fill_grad.setColorAt(0.08, col_accent.lighter(130))
                fill_grad.setColorAt(0.30, col_accent)
                fill_grad.setColorAt(1.0, col_primary)

            painter.setBrush(QBrush(fill_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 2.5, 2.5)

            # Polished top glossy glass reflection
            gloss_h = notch_h * 0.42
            gloss_grad = QLinearGradient(rx, notch_y, rx, notch_y + gloss_h)
            gloss_grad.setColorAt(0.0, QColor(255, 255, 255, 70))
            gloss_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(gloss_grad))
            painter.drawRect(QRectF(rx, notch_y, rw, gloss_h))

        def draw_tip(tx):
            # Soft glowing halo
            glow_pen = QPen(col_glow, 3.5)
            col_soft = QColor(col_glow)
            col_soft.setAlpha(130)
            glow_pen.setColor(col_soft)
            painter.setPen(glow_pen)
            painter.drawLine(QPointF(tx, notch_y), QPointF(tx, notch_y + notch_h))

            # Sharp white core tip line (matching web viewer 1.8px)
            painter.setPen(QPen(QColor("#ffffff"), 1.8))
            painter.drawLine(QPointF(tx, notch_y), QPointF(tx, notch_y + notch_h))

        cx = notch_l + notch_w / 2.0

        if mode == "center_out":
            half_w = (notch_w / 2.0) * progress
            if half_w > 0.5:
                draw_bar_segment(cx - half_w, half_w, reversed_grad=True)
                draw_bar_segment(cx, half_w, reversed_grad=False)
                draw_tip(cx - half_w)
                draw_tip(cx + half_w)

        elif mode == "reverse_left":
            gap = notch_w * progress
            remaining_w = notch_w - gap
            if remaining_w > 1.0:
                draw_bar_segment(notch_l + gap, remaining_w, reversed_grad=True)
                draw_tip(notch_l + gap)

        elif mode == "reverse_center_out":
            half_gap = (notch_w / 2.0) * progress
            left_w = max(0.0, (notch_w / 2.0) - half_gap)
            if left_w > 0.5:
                draw_bar_segment(notch_l, left_w, reversed_grad=False)
                draw_tip(notch_l + left_w)
                draw_bar_segment(cx + half_gap, left_w, reversed_grad=True)
                draw_tip(cx + half_gap)

        elif mode == "reverse_center_in":
            half_w = (notch_w / 2.0) * (1.0 - progress)
            if half_w > 0.5:
                draw_bar_segment(cx - half_w, half_w, reversed_grad=True)
                draw_bar_segment(cx, half_w, reversed_grad=False)
                draw_tip(cx - half_w)
                draw_tip(cx + half_w)

        else:  # left_to_right (default)
            fill_w = notch_w * progress
            if fill_w > 1.0:
                draw_bar_segment(notch_l, fill_w, reversed_grad=False)
                draw_tip(notch_l + fill_w)

        # 4. Re-stroke outer track border cleanly on top of clipped contents
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#33333e"), 1.0))
        painter.drawRoundedRect(track_rect, 2.5, 2.5)

        painter.restore()

    # ==========================================================================
    # INTERACTION
    # ==========================================================================

    def mousePressEvent(self, event):
        bar_w = float(self.bar_w if self.bar_w > 0 else self.width())
        bar_h = float(self.bar_h if self.bar_h > 0 else self.height())
        pad_left = float(self.pad_left)
        pad_top = float(self.pad_top)

        notch_l = bar_w * 0.30
        notch_r = bar_w * 0.70
        notch_y = bar_h * 0.78
        notch_h = bar_h * 0.22

        pos = event.position()
        mx = pos.x() - pad_left
        my = pos.y() - pad_top

        # If user clicks within the small timeline notch
        if notch_l <= mx <= notch_r and notch_y <= my <= notch_y + notch_h:
            self._dragging_small_timeline = True
            self._seek_from_notch_x(mx, notch_l, notch_r)
            event.accept()
        else:
            # Click is on video area outside the timeline notch -> forward to player video click
            p = self.window()
            if hasattr(p, "_on_video_canvas_clicked"):
                p._on_video_canvas_clicked()
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._dragging_small_timeline:
            bar_w = float(self.bar_w if self.bar_w > 0 else self.width())
            pad_left = float(self.pad_left)
            notch_l = bar_w * 0.30
            notch_r = bar_w * 0.70
            mx = event.position().x() - pad_left
            self._seek_from_notch_x(mx, notch_l, notch_r)
            event.accept()
        else:
            p = self.window()
            if hasattr(p, "inactivity_mgr"):
                p.inactivity_mgr.notify_activity()
            event.ignore()

    def mouseReleaseEvent(self, event):
        if self._dragging_small_timeline:
            self._dragging_small_timeline = False
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        p = self.window()
        if hasattr(p, "toggle_fullscreen"):
            p.toggle_fullscreen()
        else:
            super().mouseDoubleClickEvent(event)

    def _seek_from_notch_x(self, mouse_x, notch_l, notch_r):
        progress = max(0.0, min(1.0, (mouse_x - notch_l) / (notch_r - notch_l)))
        fill_per_zone = self.skin_mgr.config.get("fill_timeline_per_zone", False)
        active_zone = None
        if fill_per_zone and self.zones:
            for z in self.zones:
                st = float(z.get('start_time', z.get('start', 0.0)))
                et = float(z.get('end_time', z.get('end', 0.0)))
                if st <= self.current_time <= et:
                    active_zone = z
                    break

        if active_zone:
            z_st = float(active_zone.get('start_time', active_zone.get('start', 0.0)))
            z_et = float(active_zone.get('end_time', active_zone.get('end', 0.0)))
            target_time = z_st + progress * (z_et - z_st)
        else:
            target_time = progress * self.duration
        self.seek_requested.emit(target_time)
