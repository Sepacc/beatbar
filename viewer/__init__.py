"""
__init__.py for viewer package.
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from .viewer import BeatBarViewerWindow

__all__ = ["BeatBarViewerWindow"]
