"""
beatbar_preview.py - Live Beatbar Preview Widget for Skin Maker.

Faithfully implements the Beatbar UI and animations from viewer/beatbar.py:
- Main panel rendering (SVG or stylized vector geometry)
- Left and right wing sigils in panel corners
- Center target with scale pop on hit
- Approaching beats traveling towards center target
- Hit indicator (▲)
- Shockwaves, glowing particles, and secondary progress timeline
- Interactive playback simulation, scrub slider, and hit triggers.
"""

import math
import random
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, QByteArray
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel,
    QCheckBox, QComboBox, QFrame, QSizePolicy
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath,
    QPolygonF, QFont
)
from PyQt6.QtSvg import QSvgRenderer

from beatpanel.skin_data import BeatbarSkin
try:
    from icon_utils import get_feather_icon
except (ImportError, ValueError):
    import os, sys
    _p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _d in [_p, os.path.join(_p, "main")]:
        if _d not in sys.path:
            sys.path.insert(0, _d)
    from icon_utils import get_feather_icon


class HitParticle:
    """Sparkling particle emitted on beat hit."""
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(40, 160)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(10, 40)
        self.life = 1.0
        self.decay = random.uniform(2.5, 4.5)
        self.size = random.uniform(2.5, 5.5)
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 60 * dt
        self.life = max(0.0, self.life - self.decay * dt)
        return self.life > 0.0


class Shockwave:
    """Expanding glowing ring emitted on beat hit."""
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


class BeatBarCanvas(QWidget):
    """
    Renders the live beatbar graphics matching the viewer application.
    """
    beat_hit = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.skin: BeatbarSkin = BeatbarSkin()
        
        # Renderers cache
        self._renderers = {}

        # Component visibility flags
        self.show_panel = True
        self.show_wings = True
        self.show_target = True
        self.show_beats = True
        self.show_indicator = True
        self.show_effects = True
        self.show_timeline = True

        # Backdrop mode: 'studio', 'checker', 'cyber', 'black'
        self.backdrop_mode = "studio"

        # Beat simulation state
        self.current_time = 0.0
        self.duration = 60.0
        self.is_playing = True
        self.lead_time = 1.5
        self.scroll_direction = "rtl"  # "rtl", "ltr", "both"
        self.bpm = 128.0

        # Simulated beat sequence
        self.beats = []
        self._generate_test_beats()
        self._hit_beats_set = set()

        # Hit animation states
        self.target_pop_scale = 1.0
        self.shockwaves = []
        self.particles = []

        # Physics / Animation Timer (60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._on_anim_frame)
        self.anim_timer.start()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(85)

    def _get_bar_geometry(self, W: float, H: float):
        """Calculates beatbar container dimensions with the exact aspect ratio of Viewer."""
        ratio = (174.0 / 3497.0) * 1.35
        bar_w = min(W * 0.94, 1640.0)
        bar_h = bar_w * ratio
        max_h = H * 0.75
        if bar_h > max_h:
            bar_h = max_h
            bar_w = bar_h / ratio
        bar_h = max(42.0, bar_h)
        bar_x = (W - bar_w) / 2.0
        bar_y = (H - bar_h) / 2.0
        return bar_w, bar_h, bar_x, bar_y

    def _generate_test_beats(self):
        """Generates regular rhythmic test beats for preview."""
        beat_interval = 60.0 / self.bpm
        self.beats = [round(i * beat_interval, 3) for i in range(1, int(self.duration / beat_interval))]

    def set_skin(self, skin: BeatbarSkin):
        """Updates active skin and invalidates cached SVG renderers."""
        self.skin = skin
        self._invalidate_renderers()
        self.update()

    def _invalidate_renderers(self):
        self._renderers.clear()

    def get_renderer(self, key: str) -> QSvgRenderer:
        """Retrieves or creates a QSvgRenderer for a skin component."""
        if key in self._renderers:
            return self._renderers[key]
        svg_content = self.skin.get_component(key)
        if svg_content:
            try:
                r = QSvgRenderer(QByteArray(svg_content.encode("utf-8")))
                if r.isValid():
                    self._renderers[key] = r
                    return r
            except Exception:
                pass
        return None

    def trigger_hit(self):
        """Manual test hit trigger centered directly on target."""
        trig = getattr(self.skin, "trigger_hit", {})
        pop_cfg = float(trig.get("pop_scale", 1.35))
        self.target_pop_scale = pop_cfg
        dur_ms = float(trig.get("duration_ms", 180))
        self.hit_state_time_left = max(0.06, dur_ms / 1000.0)

        W = float(self.width())
        H = float(self.height())
        bar_w, bar_h, _, _ = self._get_bar_geometry(W, H)

        lay = getattr(self.skin, "layout", {})
        t_cfg = lay.get("target", {})
        off_x_t = float(t_cfg.get("offset_x", 0.0)) * (bar_w / 1000.0)
        off_y_t = float(t_cfg.get("offset_y", 0.0)) * (bar_h / 100.0)

        center_x = bar_w / 2.0 + off_x_t
        center_y = bar_h * 0.40 + off_y_t
        glow_col = QColor(self.skin.palette.get("glow", "#f368e0"))

        if self.show_effects:
            self.shockwaves.append(Shockwave(center_x, center_y, bar_h * 0.9, glow_col))
            for _ in range(12):
                self.particles.append(HitParticle(center_x, center_y, glow_col))

        self.beat_hit.emit()
        self.update()

    def _on_anim_frame(self):
        dt = 0.016
        needs_redraw = False

        if self.is_playing:
            old_time = self.current_time
            self.current_time += dt
            if self.current_time >= self.duration:
                self.current_time = 0.0
                self._hit_beats_set.clear()

            # Check hits
            for bt in self.beats:
                if bt not in self._hit_beats_set and (old_time - 0.02 <= bt <= self.current_time + 0.02):
                    self._hit_beats_set.add(bt)
                    self.trigger_hit()

            needs_redraw = True

        # Target spring decay
        if self.target_pop_scale > 1.0:
            self.target_pop_scale = max(1.0, self.target_pop_scale - (self.target_pop_scale - 1.0) * 12.0 * dt)
            needs_redraw = True

        # Target hit 2nd state timer
        if hasattr(self, "hit_state_time_left") and self.hit_state_time_left > 0:
            self.hit_state_time_left -= dt
            needs_redraw = True

        # Shockwaves update
        if self.shockwaves:
            self.shockwaves = [sw for sw in self.shockwaves if sw.update(dt)]
            needs_redraw = True

        # Particles update
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

        W = float(self.width())
        H = float(self.height())
        pal = self.skin.palette

        # 1. Background
        self._paint_backdrop(painter, W, H)

        # Calculate Beatbar container bounds (centered with proper aspect ratio)
        bar_w, bar_h, bar_x, bar_y = self._get_bar_geometry(W, H)

        painter.save()
        painter.translate(bar_x, bar_y)

        # 2. Main Panel
        if self.show_panel:
            self._paint_panel(painter, bar_w, bar_h, pal)

        # 3. Left and Right Wing Sigils
        if self.show_wings:
            self._paint_wings(painter, bar_w, bar_h)

        # 4. Approaching Beats
        if self.show_beats:
            self._paint_beats(painter, bar_w, bar_h, pal)

        # 5. Center Target & Hit Indicator
        if self.show_target or self.show_indicator:
            self._paint_target_and_indicator(painter, bar_w, bar_h, pal)

        # 6. Hit Effects (Shockwaves & Particles)
        if self.show_effects:
            self._paint_effects(painter, bar_w, bar_h)

        # 7. Bottom Notch Timeline
        if self.show_timeline:
            self._paint_timeline(painter, bar_w, bar_h, pal)

        painter.restore()
        painter.end()

    def _paint_backdrop(self, painter, W, H):
        """Paints canvas background based on active backdrop mode."""
        if self.backdrop_mode == "black":
            painter.fillRect(QRectF(0, 0, W, H), QColor("#09090c"))

        elif self.backdrop_mode == "checker":
            # Transparent alpha checkerboard
            painter.fillRect(QRectF(0, 0, W, H), QColor("#1c1c24"))
            sz = 16
            c2 = QColor("#282834")
            for y in range(0, int(H), sz):
                for x in range(0, int(W), sz):
                    if ((x // sz) + (y // sz)) % 2 == 1:
                        painter.fillRect(QRectF(x, y, sz, sz), c2)

        elif self.backdrop_mode == "cyber":
            # Cyberpunk stage backdrop
            grad = QLinearGradient(0, 0, W, H)
            grad.setColorAt(0.0, QColor("#0d0b18"))
            grad.setColorAt(0.5, QColor("#1b122c"))
            grad.setColorAt(1.0, QColor("#080c16"))
            painter.fillRect(QRectF(0, 0, W, H), grad)
            # Subtle grid lines
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
            for x in range(0, int(W), 40):
                painter.drawLine(x, 0, x, int(H))
            for y in range(0, int(H), 40):
                painter.drawLine(0, y, int(W), y)

        else:  # Studio (default)
            grad = QLinearGradient(0, 0, 0, H)
            grad.setColorAt(0.0, QColor("#14141a"))
            grad.setColorAt(0.5, QColor("#101015"))
            grad.setColorAt(1.0, QColor("#0c0c10"))
            painter.fillRect(QRectF(0, 0, W, H), grad)

            # Center glow spotlight
            spot = QLinearGradient(W / 2.0, 0, W / 2.0, H)
            spot_col = QColor(self.skin.palette.get("glow", "#9b51e0"))
            spot_col.setAlpha(20)
            spot.setColorAt(0.0, spot_col)
            spot.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(0, 0, W, H), spot)

    def _get_panel_path(self, W, H):
        """Constructs vector path for the angled panel matching viewer/beatbar.py."""
        path = QPainterPath()
        path.moveTo(W * 0.015, H * 0.14)
        path.lineTo(W * 0.045, H * 0.10)
        path.lineTo(W * 0.43, H * 0.10)
        path.lineTo(W * 0.445, H * 0.03)
        path.lineTo(W * 0.555, H * 0.03)
        path.lineTo(W * 0.57, H * 0.10)
        path.lineTo(W * 0.955, H * 0.10)
        path.lineTo(W * 0.985, H * 0.14)
        path.lineTo(W * 0.955, H * 0.76)
        path.lineTo(W * 0.71, H * 0.76)
        path.lineTo(W * 0.70, H * 0.96)
        path.lineTo(W * 0.30, H * 0.96)
        path.lineTo(W * 0.29, H * 0.76)
        path.lineTo(W * 0.045, H * 0.76)
        path.closeSubpath()
        return path

    def _paint_panel(self, painter, W, H, pal):
        """Paints main trapezoidal panel matching viewer/beatbar.py exactly."""
        path = self._get_panel_path(W, H)

        # Metallic charcoal gradient fill
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor("#282830"))
        grad.setColorAt(0.2, QColor("#18181e"))
        grad.setColorAt(0.7, QColor("#0d0d12"))
        grad.setColorAt(1.0, QColor("#1c1c24"))

        # Border gradient with glow center
        border_grad = QLinearGradient(0, 0, W, 0)
        border_color = QColor(pal.get("panel_border", "#d434ef"))
        glow_color = QColor(pal.get("glow", "#f368e0"))
        border_grad.setColorAt(0.0, QColor("#666670"))
        border_grad.setColorAt(0.18, border_color)
        border_grad.setColorAt(0.5, glow_color)
        border_grad.setColorAt(0.82, border_color)
        border_grad.setColorAt(1.0, QColor("#666670"))

        painter.save()
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QBrush(border_grad), 2.2))
        painter.drawPath(path)

        # Inner Top Rim Highlight
        rim_pen = QPen(QColor(255, 255, 255, 60), 1.2)
        painter.setPen(rim_pen)
        painter.drawLine(QPointF(W * 0.05, H * 0.12), QPointF(W * 0.43, H * 0.12))
        painter.drawLine(QPointF(W * 0.445, H * 0.05), QPointF(W * 0.555, H * 0.05))
        painter.drawLine(QPointF(W * 0.57, H * 0.12), QPointF(W * 0.95, H * 0.12))

        # Overlay SVG skin renderer if present
        r_panel = self.get_renderer("panel")
        if r_panel:
            r_panel.render(painter, QRectF(0, 0, W, H))

        painter.restore()

    def _paint_wings(self, painter, W, H):
        """Paints left and right wing sigils in panel corners matching viewer/beatbar.py exactly."""
        r_left = self.get_renderer("wing_left")
        r_right = self.get_renderer("wing_right")

        lay = getattr(self.skin, "layout", {})
        wl_cfg = lay.get("wing_left", {})
        wr_cfg = lay.get("wing_right", {})

        wl_scale = float(wl_cfg.get("scale", 1.0))
        wr_scale = float(wr_cfg.get("scale", 1.0))
        wl_off_x = float(wl_cfg.get("offset_x", 0.0)) * (W / 1000.0)
        wl_off_y = float(wl_cfg.get("offset_y", 0.0)) * (H / 100.0)
        wr_off_x = float(wr_cfg.get("offset_x", 0.0)) * (W / 1000.0)
        wr_off_y = float(wr_cfg.get("offset_y", 0.0)) * (H / 100.0)

        base_w = H * 0.65
        base_h = H * 0.60
        base_y = H * 0.12

        if r_left:
            wl = base_w * wl_scale
            hl = base_h * wl_scale
            target_left = QRectF(W * 0.045 + wl_off_x, base_y + wl_off_y, wl, hl)
            r_left.render(painter, target_left)
        if r_right:
            wr = base_w * wr_scale
            hr = base_h * wr_scale
            target_right = QRectF(W * 0.955 - wr + wr_off_x, base_y + wr_off_y, wr, hr)
            r_right.render(painter, target_right)

    def _draw_single_beat(self, painter, r_beat, bx, center_y, bw, bh, pal, flip_h=False):
        """Draws an individual beat icon, flipped horizontally around center if requested."""
        painter.save()
        painter.translate(bx, center_y)
        if flip_h:
            painter.scale(-1.0, 1.0)
        draw_rect = QRectF(-bw / 2.0, -bh / 2.0, bw, bh)
        if r_beat:
            r_beat.render(painter, draw_rect)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(pal.get("primary", "#be2edd"))))
            painter.drawRoundedRect(draw_rect, 4, 4)
        painter.restore()

    def _paint_beats(self, painter, W, H, pal):
        """Paints approaching beats with configurable directional flipping."""
        r_beat = self.get_renderer("beat")
        center_x = W / 2.0
        center_y = H * 0.42
        bw = H * 0.44
        bh = H * 0.42
        travel_distance = W * 0.43
        t_now = self.current_time

        lay = getattr(self.skin, "layout", {})
        flip_left = bool(lay.get("flip_left_beats", False))
        flip_right = bool(lay.get("flip_right_beats", False))

        for bt in self.beats:
            time_diff = bt - t_now
            if -0.08 <= time_diff <= self.lead_time:
                norm_pos = time_diff / self.lead_time
                alpha = 255
                if time_diff < 0:
                    alpha = max(0, int(255 * (1.0 + time_diff / 0.08)))

                painter.save()
                painter.setOpacity(alpha / 255.0)

                if self.scroll_direction == "ltr":
                    bx = center_x - norm_pos * travel_distance
                    flip_h = flip_left if bx < center_x else flip_right
                    self._draw_single_beat(painter, r_beat, bx, center_y, bw, bh, pal, flip_h)
                elif self.scroll_direction == "both":
                    bx_r = center_x + norm_pos * travel_distance
                    bx_l = center_x - norm_pos * travel_distance
                    self._draw_single_beat(painter, r_beat, bx_r, center_y, bw, bh, pal, flip_right)
                    self._draw_single_beat(painter, r_beat, bx_l, center_y, bw, bh, pal, flip_left)
                else:  # rtl (default)
                    bx = center_x + norm_pos * travel_distance
                    flip_h = flip_left if bx < center_x else flip_right
                    self._draw_single_beat(painter, r_beat, bx, center_y, bw, bh, pal, flip_h)

                painter.restore()

    def _paint_target_and_indicator(self, painter, W, H, pal):
        """Paints central target (idle or hit 2nd state) and customizable hit indicator matching viewer/beatbar.py."""
        lay = getattr(self.skin, "layout", {})
        t_cfg = lay.get("target", {})
        scale_t = float(t_cfg.get("scale", 1.0))
        off_x_t = float(t_cfg.get("offset_x", 0.0)) * (W / 1000.0)
        off_y_t = float(t_cfg.get("offset_y", 0.0)) * (H / 100.0)

        center_x = W / 2.0
        center_y = H * 0.40

        painter.save()

        # 1. Central Target (scaled by hit pop & target_scale)
        if self.show_target:
            tw = H * 0.85 * self.target_pop_scale * scale_t
            th = H * 0.52 * self.target_pop_scale * scale_t
            target_rect = QRectF(center_x + off_x_t - tw / 2.0, center_y + off_y_t - th / 2.0, tw, th)

            is_hit = (getattr(self, "hit_state_time_left", 0.0) > 0.0 
                      or getattr(self, "preview_hit_state", False) 
                      or self.target_pop_scale > 1.05)
            r_target_hit = self.get_renderer("target_hit") if is_hit else None
            renderer = r_target_hit if r_target_hit else self.get_renderer("target")

            if renderer:
                renderer.render(painter, target_rect)
            else:
                painter.setPen(QPen(QColor(pal.get("glow", "#f368e0")), 2.0))
                painter.setBrush(QBrush(QColor(pal.get("target", "#9b51e0"))))
                painter.drawRoundedRect(target_rect, 6, 6)

        # 2. Customizable Hit Indicator beneath target
        if self.show_indicator:
            trig = getattr(self.skin, "trigger_hit", {})
            ind_style = trig.get("indicator_style", "triangle")
            if ind_style not in ("hidden", "off"):
                ind_color = QColor(trig.get("indicator_color", "#ffffff"))
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
                    painter.setPen(QPen(QColor(pal.get("panel_border", "#d434ef")), 1.2))
                    painter.drawPolygon(poly)
                elif ind_style == "glow_bar":
                    bw = arrow_h * 2.2
                    bh = arrow_h * 0.4
                    r = QRectF(ind_x - bw / 2.0, arrow_y - bh, bw, bh)
                    painter.setBrush(QBrush(ind_color))
                    painter.setPen(QPen(QColor(pal.get("glow", "#f368e0")), 1.5))
                    painter.drawRoundedRect(r, 2, 2)
                else:  # "triangle"
                    arrow_poly = QPolygonF([
                        QPointF(ind_x, arrow_y - arrow_h),
                        QPointF(ind_x + arrow_w / 2.0, arrow_y),
                        QPointF(ind_x - arrow_w / 2.0, arrow_y)
                    ])
                    painter.setBrush(QBrush(ind_color))
                    painter.setPen(QPen(QColor(pal.get("panel_border", "#d434ef")), 1.2))
                    painter.drawPolygon(arrow_poly)

        painter.restore()

    def _paint_effects(self, painter, W, H):
        """Paints shockwaves and particles."""
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

    def _paint_timeline(self, painter, W, H, pal):
        """Paints bottom notch progress timeline matching viewer/beatbar.py exactly."""
        notch_l = W * 0.30
        notch_r = W * 0.70
        notch_w = notch_r - notch_l
        notch_y = H * 0.80
        notch_h = H * 0.14

        track_rect = QRectF(notch_l, notch_y, notch_w, notch_h)

        painter.save()

        # Track background
        painter.setBrush(QBrush(QColor("#101014")))
        painter.setPen(QPen(QColor("#333338"), 1.0))
        painter.drawRoundedRect(track_rect, 3, 3)

        lay = getattr(self.skin, "layout", {})
        mode = lay.get("timeline_fill_mode", getattr(self, "timeline_fill_mode", "left_to_right"))
        progress = max(0.0, min(1.0, (self.current_time % 10.0) / 10.0))
        fill_color = QColor(pal.get("timeline_fill", "#ffffff"))

        def draw_bar_segment(rx, rw):
            if rw <= 0.8:
                return
            fill_rect = QRectF(rx, notch_y, rw, notch_h)
            fill_grad = QLinearGradient(rx, notch_y, rx + rw, notch_y)
            fill_grad.setColorAt(0.0, fill_color.lighter(110))
            fill_grad.setColorAt(0.85, fill_color)
            fill_grad.setColorAt(1.0, QColor("#ffffff"))
            painter.setBrush(QBrush(fill_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(fill_rect, 3, 3)

        def draw_tip(tx):
            painter.setPen(QPen(QColor("#ffffff"), 2.0))
            painter.drawLine(QPointF(tx, notch_y), QPointF(tx, notch_y + notch_h))

        cx = notch_l + notch_w / 2.0

        if mode == "center_out":
            half_w = (notch_w / 2.0) * progress
            if half_w > 0.5:
                draw_bar_segment(cx - half_w, half_w * 2.0)
                draw_tip(cx - half_w)
                draw_tip(cx + half_w)

        elif mode == "reverse_left":
            gap = notch_w * progress
            remaining_w = notch_w - gap
            if remaining_w > 1.0:
                draw_bar_segment(notch_l + gap, remaining_w)
                draw_tip(notch_l + gap)

        elif mode == "reverse_center_out":
            half_gap = (notch_w / 2.0) * progress
            left_w = max(0.0, (notch_w / 2.0) - half_gap)
            if left_w > 0.5:
                draw_bar_segment(notch_l, left_w)
                draw_bar_segment(cx + half_gap, left_w)
                draw_tip(cx - half_gap)
                draw_tip(cx + half_gap)

        elif mode == "reverse_center_in":
            half_w = (notch_w / 2.0) * (1.0 - progress)
            if half_w > 0.5:
                draw_bar_segment(cx - half_w, half_w * 2.0)
                draw_tip(cx - half_w)
                draw_tip(cx + half_w)

        else:  # left_to_right
            fill_w = notch_w * progress
            if fill_w > 1.0:
                draw_bar_segment(notch_l, fill_w)
                draw_tip(notch_l + fill_w)

        painter.restore()


class BeatBarPreviewWidget(QWidget):
    """
    Combined container widget with canvas and interactive control toolbar.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = BeatBarCanvas(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Preview Canvas Container Frame
        canvas_frame = QFrame(self)
        canvas_frame.setStyleSheet("""
            QFrame {
                background: #101016;
                border: 1px solid #282834;
                border-radius: 10px;
            }
        """)
        c_layout = QVBoxLayout(canvas_frame)
        c_layout.setContentsMargins(4, 4, 4, 4)
        c_layout.addWidget(self.canvas)
        layout.addWidget(canvas_frame, stretch=1)

        # Bottom Interactive Control Bar
        control_bar = QFrame(self)
        control_bar.setStyleSheet("""
            QFrame {
                background: #181822;
                border: 1px solid #2c2c3c;
                border-radius: 8px;
                padding: 2px;
            }
            QPushButton {
                background: #242432;
                border: 1px solid #3c3c50;
                border-radius: 6px;
                color: #ffffff;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #343448;
                border-color: #9b51e0;
            }
            QCheckBox {
                color: #c0c0d0;
                font-size: 11px;
            }
            QComboBox {
                background: #242432;
                border: 1px solid #3c3c50;
                border-radius: 6px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLabel {
                color: #9090a8;
                font-size: 11px;
            }
        """)
        cb_layout = QHBoxLayout(control_bar)
        cb_layout.setContentsMargins(10, 6, 10, 6)
        cb_layout.setSpacing(10)

        # Play / Pause
        self.btn_play = QPushButton(" Pause")
        self.btn_play.setIcon(get_feather_icon("pause", "#ffffff", 14))
        self.btn_play.clicked.connect(self._toggle_playback)
        cb_layout.addWidget(self.btn_play)

        self.btn_hit = QPushButton(" Trigger Hit")
        self.btn_hit.setIcon(get_feather_icon("zap", "#00f3ff", 14))
        self.btn_hit.setToolTip("Test hit animations (Shockwave, Particles, Pop)")
        self.btn_hit.clicked.connect(self.canvas.trigger_hit)
        cb_layout.addWidget(self.btn_hit)

        self.chk_hold_hit = QCheckBox("Hold Hit")
        self.chk_hold_hit.setToolTip("Keep target hit (2nd state) visible in preview for styling")
        self.chk_hold_hit.toggled.connect(lambda v: setattr(self.canvas, "preview_hit_state", v) or self.canvas.update())
        cb_layout.addWidget(self.chk_hold_hit)

        # Direction Mode
        cb_layout.addWidget(QLabel("Flow:"))
        self.combo_dir = QComboBox()
        self.combo_dir.addItem("Right to Left (RTL)", "rtl")
        self.combo_dir.addItem("Left to Right (LTR)", "ltr")
        self.combo_dir.addItem("Both Sides", "both")
        self.combo_dir.currentIndexChanged.connect(self._on_dir_changed)
        cb_layout.addWidget(self.combo_dir)

        # Backdrop Switcher
        cb_layout.addWidget(QLabel("Backdrop:"))
        self.combo_backdrop = QComboBox()
        self.combo_backdrop.addItem("Studio Glow", "studio")
        self.combo_backdrop.addItem("Transparent Grid", "checker")
        self.combo_backdrop.addItem("Cyber Stage", "cyber")
        self.combo_backdrop.addItem("Pitch Black", "black")
        self.combo_backdrop.currentIndexChanged.connect(self._on_backdrop_changed)
        cb_layout.addWidget(self.combo_backdrop)

        cb_layout.addStretch(1)

        # Component Toggles
        self.chk_panel = QCheckBox("Panel")
        self.chk_panel.setChecked(True)
        self.chk_panel.toggled.connect(lambda v: setattr(self.canvas, "show_panel", v) or self.canvas.update())
        cb_layout.addWidget(self.chk_panel)

        self.chk_wings = QCheckBox("Wings")
        self.chk_wings.setChecked(True)
        self.chk_wings.toggled.connect(lambda v: setattr(self.canvas, "show_wings", v) or self.canvas.update())
        cb_layout.addWidget(self.chk_wings)

        self.chk_target = QCheckBox("Target")
        self.chk_target.setChecked(True)
        self.chk_target.toggled.connect(lambda v: setattr(self.canvas, "show_target", v) or self.canvas.update())
        cb_layout.addWidget(self.chk_target)

        self.chk_beats = QCheckBox("Beats")
        self.chk_beats.setChecked(True)
        self.chk_beats.toggled.connect(lambda v: setattr(self.canvas, "show_beats", v) or self.canvas.update())
        cb_layout.addWidget(self.chk_beats)

        # Quick Flip toggles
        self.chk_flip_l = QCheckBox("Flip L")
        self.chk_flip_l.setToolTip("Flip beats approaching from left")
        self.chk_flip_l.toggled.connect(self._on_flip_l_toggled)
        cb_layout.addWidget(self.chk_flip_l)

        self.chk_flip_r = QCheckBox("Flip R")
        self.chk_flip_r.setToolTip("Flip beats approaching from right")
        self.chk_flip_r.toggled.connect(self._on_flip_r_toggled)
        cb_layout.addWidget(self.chk_flip_r)

        layout.addWidget(control_bar)

    def _toggle_playback(self):
        self.canvas.is_playing = not self.canvas.is_playing
        if self.canvas.is_playing:
            self.btn_play.setText(" Pause")
            self.btn_play.setIcon(get_feather_icon("pause", "#ffffff", 14))
        else:
            self.btn_play.setText(" Play")
            self.btn_play.setIcon(get_feather_icon("play", "#ffffff", 14))

    def _on_flip_l_toggled(self, checked: bool):
        if not hasattr(self.canvas.skin, "layout"):
            self.canvas.skin.layout = {}
        self.canvas.skin.layout["flip_left_beats"] = checked
        self.canvas.update()

    def _on_flip_r_toggled(self, checked: bool):
        if not hasattr(self.canvas.skin, "layout"):
            self.canvas.skin.layout = {}
        self.canvas.skin.layout["flip_right_beats"] = checked
        self.canvas.update()

    def _on_dir_changed(self):
        self.canvas.scroll_direction = self.combo_dir.currentData()
        self.canvas.update()

    def _on_backdrop_changed(self):
        self.canvas.backdrop_mode = self.combo_backdrop.currentData()
        self.canvas.update()

    def set_skin(self, skin: BeatbarSkin):
        self.canvas.set_skin(skin)
        lay = getattr(skin, "layout", {})
        self.chk_flip_l.blockSignals(True)
        self.chk_flip_r.blockSignals(True)
        self.chk_flip_l.setChecked(bool(lay.get("flip_left_beats", False)))
        self.chk_flip_r.setChecked(bool(lay.get("flip_right_beats", False)))
        self.chk_flip_l.blockSignals(False)
        self.chk_flip_r.blockSignals(False)
