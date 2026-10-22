"""
video_canvas.py - High-Performance Video Canvas with Aspect Ratio and Zoom.

Renders video frames directly onto a standard QWidget via QVideoSink.
This avoids native Direct3D HWND occlusion issues on Windows, allowing
overlays (Beatbar, Top Bar, Bottom Bar, and popups) to render seamlessly on top.
Also provides smooth hardware-accelerated zoom scaling for screen shakes.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtMultimedia import QVideoSink
from PyQt6.QtGui import QPainter, QColor, QImage, QPen, QLinearGradient
from PyQt6.QtCore import Qt, QRectF, pyqtSignal


class VideoCanvasWidget(QWidget):
    """
    Renders video frames received from QVideoSink with aspect ratio fitting
    and zoom punch scaling for the beat-hit screen shake effect.
    """
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_video_frame)
        self.current_frame = None
        self.zoom_scale = 1.0
        self.flash_alpha = 0.0
        self.flash_color = QColor("#e056fd")
        self.flash_mode = "shake"  # "shake", "border_flash", "picture_flash", "both", "all"
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def _on_video_frame(self, frame):
        if frame.isValid():
            self.current_frame = frame.toImage()
            self.update()

    def set_zoom(self, zoom):
        self.zoom_scale = max(1.0, float(zoom))
        self.update()

    def set_flash(self, alpha: float, color: QColor = None, mode: str = "border_flash"):
        """Sets flash intensity (0.0 to 1.0), color, and effect mode."""
        self.flash_alpha = max(0.0, min(1.0, float(alpha)))
        if color is not None:
            self.flash_color = color
        if mode:
            self.flash_mode = mode
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        W, H = self.width(), self.height()

        # Background fill
        painter.fillRect(0, 0, W, H, QColor("#000000"))

        if self.current_frame and not self.current_frame.isNull():
            vw = self.current_frame.width()
            vh = self.current_frame.height()
            if vw > 0 and vh > 0:
                # Maintain aspect ratio with zoom scaling
                scale = min(W / vw, H / vh) * self.zoom_scale
                dw = vw * scale
                dh = vh * scale
                dx = (W - dw) / 2.0
                dy = (H - dh) / 2.0
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(QRectF(dx, dy, dw, dh), self.current_frame)
            else:
                dx, dy, dw, dh = 0, 0, W, H
        else:
            dx, dy, dw, dh = 0, 0, W, H

        # Render Beat-Hit Flash Effects (Screen Border Color Flash / Picture Flash)
        if self.flash_alpha > 0.01:
            alpha_val = int(255 * self.flash_alpha)
            col = self.flash_color or QColor("#e056fd")

            # 1. Full Screen Picture Color Flash / Strobe Wash
            if self.flash_mode in ["picture_flash", "all"]:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                pic_alpha = int(140 * self.flash_alpha)
                wash_col = QColor(col.red(), col.green(), col.blue(), pic_alpha)
                painter.fillRect(QRectF(dx, dy, dw, dh), wash_col)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 2. Screen Border Color Flash (Feathered glowing vignette bloom - seamless edge falloff)
            if self.flash_mode in ["border_flash", "both", "all"]:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                glow_depth = max(42.0, min(W, H) * 0.085)

                c_outer = QColor(col.red(), col.green(), col.blue(), int(230 * self.flash_alpha))
                c_mid1 = QColor(col.red(), col.green(), col.blue(), int(140 * self.flash_alpha))
                c_mid2 = QColor(col.red(), col.green(), col.blue(), int(50 * self.flash_alpha))
                c_fade = QColor(col.red(), col.green(), col.blue(), 0)

                painter.setPen(Qt.PenStyle.NoPen)

                # Edge 1: Top linear gradient (Full width from x=0 to W)
                g_top = QLinearGradient(0, 0, 0, glow_depth)
                g_top.setColorAt(0.0, c_outer)
                g_top.setColorAt(0.25, c_mid1)
                g_top.setColorAt(0.65, c_mid2)
                g_top.setColorAt(1.0, c_fade)
                painter.fillRect(QRectF(0, 0, W, glow_depth), g_top)

                # Edge 2: Bottom linear gradient (Full width from x=0 to W)
                g_bot = QLinearGradient(0, H, 0, H - glow_depth)
                g_bot.setColorAt(0.0, c_outer)
                g_bot.setColorAt(0.25, c_mid1)
                g_bot.setColorAt(0.65, c_mid2)
                g_bot.setColorAt(1.0, c_fade)
                painter.fillRect(QRectF(0, H - glow_depth, W, glow_depth), g_bot)

                # Edge 3: Left linear gradient (Full height from y=0 to H)
                g_left = QLinearGradient(0, 0, glow_depth, 0)
                g_left.setColorAt(0.0, c_outer)
                g_left.setColorAt(0.25, c_mid1)
                g_left.setColorAt(0.65, c_mid2)
                g_left.setColorAt(1.0, c_fade)
                painter.fillRect(QRectF(0, 0, glow_depth, H), g_left)

                # Edge 4: Right linear gradient (Full height from y=0 to H)
                g_right = QLinearGradient(W, 0, W - glow_depth, 0)
                g_right.setColorAt(0.0, c_outer)
                g_right.setColorAt(0.25, c_mid1)
                g_right.setColorAt(0.65, c_mid2)
                g_right.setColorAt(1.0, c_fade)
                painter.fillRect(QRectF(W - glow_depth, 0, glow_depth, H), g_right)

                # Subtle luminous neon edge rim
                rim_pen = QPen(QColor(col.red(), col.green(), col.blue(), int(255 * self.flash_alpha)), 2.0)
                painter.setPen(rim_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(1.0, 1.0, W - 2.0, H - 2.0))

                white_rim = QPen(QColor(255, 255, 255, int(160 * self.flash_alpha)), 1.0)
                painter.setPen(white_rim)
                painter.drawRect(QRectF(0.5, 0.5, W - 1.0, H - 1.0))

        painter.end()
