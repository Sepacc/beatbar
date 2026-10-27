"""
version_manager.py - Version tracking and comparison for Beatbar Suite programs.

Handles reading .version files, detecting versions in compiled Windows PE executables,
companion metadata files, and evaluating synchronization status.
"""

import os
import re
import sys
import json
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LAUNCHER_DIR)
COMPILED_DIR = os.path.join(LAUNCHER_DIR, "compiled")


@dataclass
class ProgramConfig:
    id: str
    name: str
    subtitle: str
    description: str
    icon_name: str
    source_version_path: str
    entry_script: str
    target_exe_name: Optional[str]
    can_compile: bool
    is_web: bool = False
    working_dir: Optional[str] = None
    theme_color: str = "#00f3ff"
    accent_color: str = "#0098ff"
    exe_pattern: Optional[str] = None
    icon_svg: Optional[str] = None


PROGRAM_REGISTRY: Dict[str, ProgramConfig] = {
    "launcher": ProgramConfig(
        id="launcher",
        name="BeatBar Suite Launcher",
        subtitle="Central Studio Hub & Compiler",
        description="Desktop command center for launching and compiling BeatBar Suite applications.",
        icon_name="grid",
        icon_svg="beatbar-main",
        source_version_path=os.path.join(ROOT_DIR, "launcher", ".version"),
        entry_script=os.path.join(ROOT_DIR, "launcher", "launcher.py"),
        target_exe_name="BeatbarLauncher.exe",
        can_compile=True,
        working_dir=ROOT_DIR,
        theme_color="#58a6ff",
        accent_color="#1f6feb",
        exe_pattern=r"^BeatbarLauncher.*\.exe$",
    ),
    "beatbar_maker": ProgramConfig(
        id="beatbar_maker",
        name="BeatBar Maker",
        subtitle="Audio DSP & Beat Tracking Studio",
        description="Comprehensive rhythm editor: audio transient detection, tempo estimation, zones timeline, and video beat mapping.",
        icon_name="sliders",
        icon_svg="beatbar-maker",
        source_version_path=os.path.join(ROOT_DIR, "main", ".version"),
        entry_script=os.path.join(ROOT_DIR, "main", "main.py"),
        target_exe_name="BeatbarMaker.exe",
        can_compile=True,
        working_dir=ROOT_DIR,
        theme_color="#39bfed",
        accent_color="#00a8ff",
        exe_pattern=r"^BeatbarMaker.*\.exe$",
    ),
    "beatbar_viewer": ProgramConfig(
        id="beatbar_viewer",
        name="BeatBar Viewer",
        subtitle="Synchronized Video & Rhythm Player",
        description="High-performance desktop video player with animated vector beatbars, target shockwaves, and dynamic camera punch screen shake.",
        icon_name="play-circle",
        icon_svg="beatbar-viewer",
        source_version_path=os.path.join(ROOT_DIR, "viewer", ".version"),
        entry_script=os.path.join(ROOT_DIR, "viewer", "main.py"),
        target_exe_name="BeatbarViewer.exe",
        can_compile=True,
        theme_color="#39ed4e",
        accent_color="#2ed573",
        exe_pattern=r"^BeatbarViewer.*\.exe$",
    ),
    "beatbar_skins": ProgramConfig(
        id="beatbar_skins",
        name="BeatBar Skin Maker",
        subtitle="Vector Skin Designer & SVG Studio",
        description="Dedicated vector suite: live animated beatbar simulation, color swatch harmonizer, wing mirroring, and 1-click viewer export.",
        icon_name="feather",
        icon_svg="beatbar-skins",
        source_version_path=os.path.join(ROOT_DIR, "beatpanel", ".version"),
        entry_script=os.path.join(ROOT_DIR, "beatpanel", "main.py"),
        target_exe_name="BeatbarSkinMaker.exe",
        can_compile=True,
        theme_color="#ed8139",
        accent_color="#ff793f",
        exe_pattern=r"^BeatbarSkin.*\.exe$",
    ),
    "beatbar_web": ProgramConfig(
        id="beatbar_web",
        name="BeatBar Web Viewer",
        subtitle="Browser & Mobile Rhythm Streamer",
        description="Local web streaming server with HTML5/Canvas responsive beatbar HUD for desktop and Android mobile devices.",
        icon_name="globe",
        icon_svg="beatbar-web",
        source_version_path=os.path.join(ROOT_DIR, "web", ".version"),
        entry_script=os.path.join(ROOT_DIR, "web", "run_web.py"),
        target_exe_name=None,
        can_compile=False,
        is_web=True,
        working_dir=ROOT_DIR,
        theme_color="#3f39ed",
        accent_color="#8139ed",
        exe_pattern=None,
    ),
}


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def parse_semver(ver_str: Optional[str]) -> Tuple[int, ...]:
    """Parse version string like '1.2.3' or 'v1.2' into integer tuple for comparison."""
    if not ver_str:
        return (0, 0, 0)
    # Strip any leading 'v' or non-digit chars
    cleaned = re.sub(r"^[^\d]*", "", ver_str.strip())
    # Extract digit groups
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0, 0, 0)
    return tuple(int(p) for p in parts)


def normalize_version_str(ver_str: Optional[str]) -> str:
    """Standardizes version string like '1.0.0.0' or '1.0' into clean '1.0.0'."""
    if not ver_str:
        return "1.0.0"
    v = ver_str.strip().lstrip("vV")
    parts = [p for p in re.split(r"[._-]", v) if p.isdigit()]
    if not parts:
        return ver_str.strip()
    while len(parts) > 3 and parts[-1] == "0":
        parts.pop()
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def read_source_version(prog: ProgramConfig) -> str:
    """Reads the source .version file for a given program."""
    path = prog.source_version_path
    if not os.path.exists(path):
        return "1.0.0"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("{"):
                data = json.loads(content)
                return normalize_version_str(str(data.get("version", "1.0.0")))
            return normalize_version_str(content)
    except Exception:
        return "1.0.0"


def get_pe_file_version(filepath: str) -> Optional[str]:
    """Reads Windows PE version information directly from .exe binary via version.dll."""
    if not sys.platform.startswith("win") or not os.path.exists(filepath):
        return None
    try:
        ver_dll = ctypes.windll.version
        size = ver_dll.GetFileVersionInfoSizeW(filepath, None)
        if not size:
            return None
        res = ctypes.create_string_buffer(size)
        if not ver_dll.GetFileVersionInfoW(filepath, 0, size, res):
            return None
        p_info = ctypes.c_void_p()
        u_len = wintypes.UINT()
        if not ver_dll.VerQueryValueW(res, r"\\", ctypes.byref(p_info), ctypes.byref(u_len)):
            return None
        info = VS_FIXEDFILEINFO.from_address(p_info.value)
        ms = info.dwFileVersionMS
        ls = info.dwFileVersionLS
        v_parts = [(ms >> 16) & 0xFFFF, ms & 0xFFFF, (ls >> 16) & 0xFFFF, ls & 0xFFFF]
        # Trim trailing zeroes to form standard 3-part or 4-part version
        while len(v_parts) > 3 and v_parts[-1] == 0:
            v_parts.pop()
        raw_ver = ".".join(str(p) for p in v_parts)
        if raw_ver and raw_ver != "0.0.0":
            return normalize_version_str(raw_ver)
    except Exception:
        pass
    return None


def find_compiled_files(prog: ProgramConfig) -> List[str]:
    """Finds all compiled executable and metadata files for this program in launcher/compiled/."""
    if not os.path.exists(COMPILED_DIR) or not prog.can_compile:
        return []
    
    found = []
    pattern = re.compile(prog.exe_pattern or "", re.IGNORECASE)
    for fname in os.listdir(COMPILED_DIR):
        if pattern.match(fname):
            found.append(os.path.join(COMPILED_DIR, fname))
    return found


def find_primary_compiled_exe(prog: ProgramConfig) -> Optional[str]:
    """Finds the primary compiled executable for a program across candidate locations."""
    if not prog.can_compile:
        return None

    candidate_dirs = [
        COMPILED_DIR,
        ROOT_DIR,
        os.path.dirname(sys.executable)
    ]

    # Check exact expected name first
    if prog.target_exe_name:
        for cdir in candidate_dirs:
            if not os.path.exists(cdir):
                continue
            exact_path = os.path.join(cdir, prog.target_exe_name)
            if os.path.isfile(exact_path):
                return exact_path

    # Check pattern matches in COMPILED_DIR
    files = find_compiled_files(prog)
    if files:
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files[0]

    return None


def read_compiled_version(prog: ProgramConfig) -> Optional[str]:
    """
    Detects compiled version through multiple resilient layers:
    1. Companion <name>.version or <id>.version in compiled/
    2. Embedded Windows PE version in .exe
    3. Filename version tag
    """
    if not prog.can_compile:
        return None

    exe_path = find_primary_compiled_exe(prog)
    if not exe_path:
        return None

    # Layer 1: Check companion .version file
    base_no_ext = os.path.splitext(exe_path)[0]
    companion_paths = [
        f"{base_no_ext}.version",
        os.path.join(COMPILED_DIR, f"{prog.id}.version"),
    ]
    for c_path in companion_paths:
        if os.path.exists(c_path):
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return normalize_version_str(v)
            except Exception:
                pass

    # Layer 2: Read Windows PE version info
    pe_ver = get_pe_file_version(exe_path)
    if pe_ver and pe_ver != "0.0.0":
        return pe_ver

    # Layer 3: Check filename pattern (e.g. BeatbarMaker_v1.0.0.exe)
    fname = os.path.basename(exe_path)
    match = re.search(r"[vV]?(\d+\.\d+(?:\.\d+)?)", fname)
    if match:
        return normalize_version_str(match.group(1))

    return "1.0.0"


@dataclass
class VersionComparison:
    prog_id: str
    source_version: str
    compiled_version: Optional[str]
    has_compiled: bool
    status_code: str  # "UP_TO_DATE", "OUTDATED", "NOT_COMPILED", "WEB_NATIVE"
    status_label: str
    status_color: str
    details: str
    primary_exe_path: Optional[str]


def compare_program_version(prog: ProgramConfig) -> VersionComparison:
    """Compares the program's source .version file with any compiled binary."""
    source_ver = read_source_version(prog)

    if prog.is_web or not prog.can_compile:
        return VersionComparison(
            prog_id=prog.id,
            source_version=source_ver,
            compiled_version=None,
            has_compiled=False,
            status_code="WEB_NATIVE",
            status_label="Web Service",
            status_color="#2ed573",
            details="Runs natively via Python Flask server (No compilation needed)",
            primary_exe_path=None,
        )

    exe_path = find_primary_compiled_exe(prog)
    compiled_ver = read_compiled_version(prog) if exe_path else None

    if not exe_path or not compiled_ver:
        return VersionComparison(
            prog_id=prog.id,
            source_version=source_ver,
            compiled_version=None,
            has_compiled=False,
            status_code="NOT_COMPILED",
            status_label="Not Compiled",
            status_color="#747d8c",
            details=f"Source is v{source_ver}. No compiled executable in launcher/compiled/",
            primary_exe_path=None,
        )

    s_tuple = parse_semver(source_ver)
    c_tuple = parse_semver(compiled_ver)

    if s_tuple == c_tuple:
        return VersionComparison(
            prog_id=prog.id,
            source_version=source_ver,
            compiled_version=compiled_ver,
            has_compiled=True,
            status_code="UP_TO_DATE",
            status_label="Up to Date",
            status_color="#10b981",
            details=f"Executable matches source version (v{compiled_ver})",
            primary_exe_path=exe_path,
        )
    elif s_tuple > c_tuple:
        return VersionComparison(
            prog_id=prog.id,
            source_version=source_ver,
            compiled_version=compiled_ver,
            has_compiled=True,
            status_code="OUTDATED",
            status_label="Update Available",
            status_color="#f59e0b",
            details=f"Source is v{source_ver}, but compiled executable is v{compiled_ver}",
            primary_exe_path=exe_path,
        )
    else:
        return VersionComparison(
            prog_id=prog.id,
            source_version=source_ver,
            compiled_version=compiled_ver,
            has_compiled=True,
            status_code="OUTDATED",
            status_label="Version Mismatch",
            status_color="#e67e22",
            details=f"Compiled executable is v{compiled_ver} (Source is v{source_ver})",
            primary_exe_path=exe_path,
        )


def clean_old_compiled_versions(prog: ProgramConfig) -> List[str]:
    """
    Removes old compiled executables and companion files for this program in launcher/compiled/.
    Ensures that fresh compilation starts clean with no obsolete versions lingering.
    """
    removed = []
    if not os.path.exists(COMPILED_DIR) or not prog.can_compile:
        return removed

    # Match executables
    pattern = re.compile(prog.exe_pattern or "", re.IGNORECASE)
    for fname in os.listdir(COMPILED_DIR):
        full_path = os.path.join(COMPILED_DIR, fname)
        if not os.path.isfile(full_path):
            continue

        base_name, ext = os.path.splitext(fname)
        is_target_exe = pattern.match(fname)
        is_companion = (
            fname.startswith(prog.id) or
            (prog.target_exe_name and fname.startswith(os.path.splitext(prog.target_exe_name)[0]))
        )

        if is_target_exe or (is_companion and ext in [".version", ".manifest", ".json", ".pdb", ".spec"]):
            try:
                os.remove(full_path)
                removed.append(full_path)
            except Exception as e:
                print(f"[VersionManager] Could not remove old file {fname}: {e}")

    return removed


def check_program_dirty(prog: ProgramConfig) -> Tuple[bool, str]:
    """
    Checks whether a program is dirty and requires recompilation:
    1. Returns (False, "Web native service") if prog is not compilable.
    2. Returns (True, "No compiled binary found") if no binary exists in compiled/.
    3. Returns (True, f"Version mismatch: source v{s} vs binary v{c}") if versions mismatch.
    4. Compares source code modification times with primary executable timestamp.
       If any source file in the program package was modified after the binary, returns (True, "Source files modified after build").
    5. Returns (False, "Binary is up-to-date") otherwise.
    """
    if prog.is_web or not prog.can_compile:
        return False, "Web service (native execution)"

    comp = compare_program_version(prog)
    if not comp.has_compiled or not comp.primary_exe_path:
        return True, "No compiled binary found"

    if comp.status_code == "OUTDATED":
        return True, f"Version mismatch: source v{comp.source_version} vs binary v{comp.compiled_version}"

    exe_mtime = os.path.getmtime(comp.primary_exe_path)

    # Determine directories to check for source modification
    source_dirs = []
    if prog.id == "launcher":
        source_dirs = [os.path.join(ROOT_DIR, "launcher")]
    elif prog.id == "beatbar_maker":
        source_dirs = [os.path.join(ROOT_DIR, "main")]
    elif prog.id == "beatbar_viewer":
        source_dirs = [os.path.join(ROOT_DIR, "viewer"), os.path.join(ROOT_DIR, "web")]
    elif prog.id == "beatbar_skins":
        source_dirs = [os.path.join(ROOT_DIR, "beatpanel"), os.path.join(ROOT_DIR, "viewer")]

    max_source_mtime = 0.0
    latest_file = ""

    for s_dir in source_dirs:
        if not os.path.isdir(s_dir):
            continue
        for root, dirs, files in os.walk(s_dir):
            if any(skip in root for skip in ["__pycache__", "compiled", "build", "dist", ".git"]):
                continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in [".py", ".json", ".svg", ".version", ".html", ".js", ".css"]:
                    fpath = os.path.join(root, f)
                    try:
                        fmtime = os.path.getmtime(fpath)
                        if fmtime > max_source_mtime:
                            max_source_mtime = fmtime
                            latest_file = f
                    except OSError:
                        pass

    if max_source_mtime > exe_mtime:
        return True, f"Source modified after build ({latest_file})"

    return False, "Up to date"
