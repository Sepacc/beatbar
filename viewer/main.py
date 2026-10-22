"""
main.py - Entry point for the Beatbar Video Viewer Application.

Run directly via:
    python viewer/main.py
    python viewer/main.py path/to/video.mp4 [path/to/beatbar.json]
"""

import sys
import os

# Ensure current and parent directories are in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
MAIN_DIR = os.path.join(PARENT_DIR, "main")
for p in [CURRENT_DIR, PARENT_DIR, MAIN_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, qInstallMessageHandler
from PyQt6.QtGui import QFont, QIcon
try:
    from .viewer import BeatBarViewerWindow
except (ImportError, ValueError):
    from viewer import BeatBarViewerWindow


def silence_ffmpeg():
    """Silences low-level FFmpeg C-library console logging (stderr)."""
    try:
        import ctypes
        import PyQt6
        pyqt_dir = os.path.dirname(PyQt6.__file__)
        for root, _, files in os.walk(pyqt_dir):
            for f in files:
                if f.lower().startswith("avutil") and f.lower().endswith(".dll"):
                    dll_path = os.path.join(root, f)
                    try:
                        av = ctypes.CDLL(dll_path)
                        LOG_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
                        def _dummy(avcl, level, fmt, vl):
                            pass
                        _cb = LOG_CALLBACK(_dummy)
                        setattr(silence_ffmpeg, "_cb", _cb)
                        if hasattr(av, "av_log_set_callback"):
                            av.av_log_set_callback(_cb)
                        if hasattr(av, "av_log_set_level"):
                            av.av_log_set_level(-8)
                    except Exception:
                        pass
    except Exception:
        pass


def _qt_message_handler(msg_type, context, message):
    # Suppress Qt internal FFmpeg teardown / wildcard disconnect warnings
    if any(k in message for k in ["QFFmpeg", "wildcard call disconnects", "corrupted CTTS", "error reading header"]):
        return
    sys.stderr.write(f"{message}\n")


def main():
    # Suppress Qt Multimedia & FFmpeg C-level logging spam
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
    silence_ffmpeg()

    # Install message filter for clean console output
    qInstallMessageHandler(_qt_message_handler)

    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("BeatBar Viewer")
    try:
        from icon_utils import get_suite_icon
        v_ico = get_suite_icon("beatbar-viewer", size=32)
        if v_ico and not v_ico.isNull():
            app.setWindowIcon(v_ico)
    except Exception:
        pass
    app.setStyle("Fusion")

    # Set default UI font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Check for web viewer flag
    if "--web" in sys.argv:
        from web.run_web import main as run_web_main
        sys.argv.remove("--web")
        run_web_main()
        sys.exit(0)

    # Parse arguments
    video_path = None
    beats_path = None

    if len(sys.argv) > 1:
        video_path = sys.argv[1]
    if len(sys.argv) > 2:
        beats_path = sys.argv[2]

    # Create and display viewer window
    viewer = BeatBarViewerWindow(initial_video=video_path, initial_beats=beats_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
