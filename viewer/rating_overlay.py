"""
rating_overlay.py - Post-Watch 1-5 Star Rating Overlay for Desktop Viewer.

Renders an interactive rating HUD after video playback completes:
- 1-5 Interactive Star Rating buttons using Feather SVG icons
- Synchronizes with ratings_manager (cache/user_ratings.json & .beat manifest)
- Auto-advances to next queue item upon rating or dismissal
- Zero emojis: Clean Feather SVG icons throughout
"""

import os
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtGui import QCursor

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from icon_utils import get_feather_icon
from ratings_manager import set_rating, get_rating


class PostWatchRatingOverlay(QWidget):
    """
    Floating post-watch banner prompting user to rate the completed track 1-5 stars.
    """
    rated = pyqtSignal(str, int)  # filepath, rating
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(54)

        self.current_filepath = ""
        self.current_rating = 0
        self.star_buttons = []

        self._init_ui()

    def _init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Glass capsule container
        self.capsule = QFrame(self)
        self.capsule.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 15, 28, 0.94);
                border: 1.5px solid #e056fd;
                border-radius: 26px;
            }
        """)
        c_layout = QHBoxLayout(self.capsule)
        c_layout.setContentsMargins(16, 6, 12, 6)
        c_layout.setSpacing(10)

        # Prompt Title
        self.lbl_title = QLabel("Rate this track:")
        self.lbl_title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; border: none; background: transparent;")
        c_layout.addWidget(self.lbl_title)

        # 5 Star Buttons
        stars_container = QWidget()
        stars_container.setStyleSheet("border: none; background: transparent;")
        s_layout = QHBoxLayout(stars_container)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(4)

        for s in range(1, 6):
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setIcon(get_feather_icon("star", "#4b4b58", 20))
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 14px;
                }
                QPushButton:hover {
                    background: rgba(255, 202, 40, 0.15);
                }
            """)
            btn.clicked.connect(lambda checked, val=s: self._on_star_clicked(val))
            s_layout.addWidget(btn)
            self.star_buttons.append(btn)

        c_layout.addWidget(stars_container)

        # Dismiss / Close button
        self.btn_close = QPushButton()
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setIcon(get_feather_icon("x", "#a0a0b2", 14))
        self.btn_close.setToolTip("Dismiss")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover {
                background: rgba(231, 76, 60, 0.3);
                border: 1px solid #e74c3c;
            }
        """)
        self.btn_close.clicked.connect(self._on_dismiss)
        c_layout.addWidget(self.btn_close)

        root_layout.addWidget(self.capsule)

    def show_rating_for(self, filepath: str):
        """Displays rating banner for completed track."""
        if not filepath:
            return
        self.current_filepath = filepath
        self.current_rating = get_rating(filepath)
        self._update_star_visuals(self.current_rating)
        self.adjustSize()
        self.show()
        self.raise_()

    def _update_star_visuals(self, rating: int):
        for idx, btn in enumerate(self.star_buttons):
            s = idx + 1
            is_filled = s <= rating
            col = "#ffca28" if is_filled else "#4b4b58"
            fill_col = "#ffca28" if is_filled else "none"
            btn.setIcon(get_feather_icon("star", col, 20, fill=fill_col))

    def _on_star_clicked(self, rating: int):
        if not self.current_filepath:
            return
        self.current_rating = rating
        set_rating(self.current_filepath, rating)
        self._update_star_visuals(rating)
        self.rated.emit(self.current_filepath, rating)
        # Briefly show feedback then close
        QTimer.singleShot(900, self.hide)

    def _on_dismiss(self):
        self.hide()
        self.dismissed.emit()
