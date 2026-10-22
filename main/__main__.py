"""
main/__main__.py - Entry point for running Beatbar Maker: python -m main
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from main.main import main

if __name__ == "__main__":
    main()
