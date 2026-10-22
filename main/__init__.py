"""
Beatbar Maker Package
Comprehensive rhythm editor: audio DSP transient detection, tempo estimation,
zones timeline, and video beat mapping.
"""

from .main import main, BeatbarApp, GenerateSettingsDialogV2, GenerateSettingsDialogV3, VideoBeatParserDialog

__all__ = ["main", "BeatbarApp", "GenerateSettingsDialogV2", "GenerateSettingsDialogV3", "VideoBeatParserDialog"]

