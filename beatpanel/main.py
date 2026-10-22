"""
main.py - Entry point for BeatPanel Skin Maker and Previewer.

Run directly via:
    python beatpanel/main.py
    python -m beatpanel
"""

import sys
import os

# Ensure project root, main, and beatpanel package are in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
MAIN_DIR = os.path.join(PARENT_DIR, "main")
for p in [CURRENT_DIR, PARENT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from beatpanel.skin_maker_window import SkinMakerWindow


def main():
    # Enable high-DPI scaling
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("BeatBar Skin Maker")
    try:
        from icon_utils import get_suite_icon
        s_ico = get_suite_icon("beatbar-skins", size=32)
        if s_ico and not s_ico.isNull():
            app.setWindowIcon(s_ico)
    except Exception:
        pass
    app.setFont(QFont("Segoe UI", 10))

    window = SkinMakerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
