"""
run_web.py - Convenience launcher for Beatbar Web Viewer.

Usage:
    python run_web.py
    python run_web.py --port 8080 --open
    python run_web.py --folder "C:\\HDD\\code\\gemini antigrav\\beatmake\\videos"
"""

import os
import sys
import argparse
import webbrowser
import threading
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from web.app import run_server, DEFAULT_VIDEOS_DIR


def open_browser(port):
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser(description="Launch BeatBar Web Viewer (for Android & Desktop)")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default 8080)")
    parser.add_argument("--folder", default=DEFAULT_VIDEOS_DIR, help="Video directory folder")
    parser.add_argument("--open", action="store_true", help="Open default web browser automatically")
    parser.add_argument("--debug", action="store_true", help="Run with Flask debug mode")

    args = parser.parse_args()

    if args.open:
        threading.Thread(target=open_browser, args=(args.port,), daemon=True).start()

    run_server(host=args.host, port=args.port, folder=args.folder, debug=args.debug)


if __name__ == "__main__":
    main()
