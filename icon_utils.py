"""
icon_utils.py - Root proxy for main/icon_utils.py.
Ensures universal import across Launcher, Viewer, Skin Maker, and Main Editor.
"""

import sys
import os
import importlib.util

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_MAIN_ICON_UTILS = os.path.join(_ROOT_DIR, "main", "icon_utils.py")

_spec = importlib.util.spec_from_file_location("_main_icon_utils", _MAIN_ICON_UTILS)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Export all attributes from main/icon_utils.py
for _k, _v in _mod.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v
