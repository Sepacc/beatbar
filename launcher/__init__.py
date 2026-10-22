"""
Beatbar Suite Launcher package.
"""

from .version_manager import PROGRAM_REGISTRY, compare_program_version
from .process_manager import process_manager

__all__ = ["PROGRAM_REGISTRY", "compare_program_version", "process_manager"]
