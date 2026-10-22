"""
web/__main__.py - Entry point for running web module: python -m web
"""

import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from web.run_web import main

if __name__ == "__main__":
    main()
