"""
component_preview.py - Isolated High-Resolution Component Preview Box.

Renders an individual component (Panel, Left Wing, Right Wing, Target, Beat)
with transparent checkerboard background, zoom controls, and alignment guides.
"""

from PyQt6.QtCore import Qt, QRectF, QByteArray, QPointF
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QFrame
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtSvg import QSvgRenderer

from beatpanel.svg_utils import get_svg_dimensions


class IsolatedComponentCanvas(QWidget):
    """Isolated canvas for rendering a single SVG component."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.svg_content = ""
        self.renderer = None
        self.zoom = 1.0
        self.show_guides = True
        self.setMinimumSize(120, 90)

    def set_svg_content(self, svg_content: str):
        self.svg_content = svg_content
        if svg_content:
            try:
                r = QSvgRenderer(QByteArray(svg_content.encode("utf-8")))
                self.renderer = r if r.isValid() else None
            except Exception:
                self.renderer = None
        else:
            self.renderer = None
        self.update()

    def set_zoom(self, zoom: float):
        self.zoom = max(0.2, min(5.0, zoom))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W = float(self.width())
        H = float(self.height())

        # 1. Checkerboard Background
        painter.fillRect(QRectF(0, 0, W, H), QColor("#181822"))
        sz = 14
        c2 = QColor("#222230")
        for y in range(0, int(H), sz):
            for x in range(0, int(W), sz):
                if ((x // sz) + (y // sz)) % 2 == 1:
                    painter.fillRect(QRectF(x, y, sz, sz), c2)

        # 2. Render SVG
        if self.renderer and self.renderer.isValid():
            orig_w, orig_h = get_svg_dimensions(self.svg_content)
            aspect = orig_w / max(1.0, orig_h)

            # Fit in canvas with padding and zoom
            max_w = (W - 32) * self.zoom
            max_h = (H - 32) * self.zoom

            if max_w / max(1.0, aspect) <= max_h:
                draw_w = max_w
                draw_h = max_w / aspect
            else:
                draw_h = max_h
                draw_w = max_h * aspect

            x = (W - draw_w) / 2.0
            y = (H - draw_h) / 2.0
            rect = QRectF(x, y, draw_w, draw_h)

            self.renderer.render(painter, rect)

            # 3. Alignment Guides & Bounding Box
            if self.show_guides:
                # Bounding box
                painter.setPen(QPen(QColor(155, 81, 224, 120), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)

                # Center crosshair
                cx = W / 2.0
                cy = H / 2.0
                painter.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DotLine))
                painter.drawLine(QPointF(cx, y - 8), QPointF(cx, y + draw_h + 8))
                painter.drawLine(QPointF(x - 8, cy), QPointF(x + draw_w + 8, cy))
        else:
            # Fallback placeholder text
            painter.setPen(QColor("#707085"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, "No Valid SVG")

        painter.end()


class ComponentPreviewWidget(QWidget):
    """Container with canvas, zoom slider, and dimension stats."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Frame
        frame = QFrame(self)
        frame.setStyleSheet("""
            QFrame {
                background: #15151e;
                border: 1px solid #2a2a38;
                border-radius: 8px;
            }
        """)
        f_layout = QVBoxLayout(frame)
        f_layout.setContentsMargins(6, 6, 6, 6)
        self.canvas = IsolatedComponentCanvas(self)
        f_layout.addWidget(self.canvas)

        # Toolbar
        tb_layout = QHBoxLayout()
        tb_layout.setContentsMargins(4, 2, 4, 2)
        
        self.lbl_dims = QLabel("Dim: --")
        self.lbl_dims.setStyleSheet("color: #8888a0; font-size: 11px;")
        tb_layout.addWidget(self.lbl_dims)

        tb_layout.addStretch(1)

        tb_layout.addWidget(QLabel("Zoom:"))
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(20, 250)
        self.slider_zoom.setValue(100)
        self.slider_zoom.setFixedWidth(90)
        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        tb_layout.addWidget(self.slider_zoom)

        f_layout.addLayout(tb_layout)
        layout.addWidget(frame)

    def _on_zoom_changed(self, val):
        self.canvas.set_zoom(val / 100.0)

    def set_svg_content(self, svg_content: str):
        self.canvas.set_svg_content(svg_content)
        w, h = get_svg_dimensions(svg_content)
        self.lbl_dims.setText(f"Size: {int(w)} × {int(h)} px")
