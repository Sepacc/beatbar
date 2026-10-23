"""
package_release.py - Automated Release Packaging Utility for Beatbar Suite.

Packages compiled executables, assets, guides, and web service into:
1. release/BeatbarSuite-v<VERSION>-Windows.zip (All-in-One complete release)
2. Standalone executables copied to release/ for individual downloads
3. release/RELEASE_NOTES_TEMPLATE.md with ready-to-use release notes for GitHub
"""

import os
import sys
import shutil
import zipfile
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
COMPILED_DIR = os.path.join(ROOT_DIR, "launcher", "compiled")
RELEASE_DIR = os.path.join(ROOT_DIR, "release")


def get_suite_version() -> str:
    v_path = os.path.join(ROOT_DIR, "launcher", ".version")
    if os.path.exists(v_path):
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    return "1.0.0"


def package_release(auto_compile_missing: bool = False):
    print("=" * 70)
    print("          BEATBAR SUITE - RELEASE PACKAGING UTILITY")
    print("=" * 70)
    
    version = get_suite_version()
    print(f"[INFO] Suite Version: v{version}")
    print(f"[INFO] Root Directory: {ROOT_DIR}")
    print(f"[INFO] Output Directory: {RELEASE_DIR}")
    print()

    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(COMPILED_DIR, exist_ok=True)

    # 1. Identify compiled executables
    expected_exes = [
        ("BeatbarLauncher.exe", "BeatBar Suite Launcher"),
        ("BeatbarMaker.exe", "BeatBar Maker"),
        ("BeatbarViewer.exe", "BeatBar Viewer"),
        ("BeatbarSkinMaker.exe", "BeatBar Skin Maker"),
    ]

    found_exes = []
    missing_exes = []

    for exe_name, label in expected_exes:
        p = os.path.join(COMPILED_DIR, exe_name)
        if os.path.exists(p):
            sz_mb = os.path.getsize(p) / (1024 * 1024)
            found_exes.append((exe_name, p, sz_mb))
            print(f"  [FOUND] {label} -> {exe_name} ({sz_mb:.1f} MB)")
        else:
            missing_exes.append((exe_name, label))
            print(f"  [MISSING] {label} -> {exe_name}")

    if missing_exes and not auto_compile_missing:
        print()
        print(f"[NOTICE] {len(missing_exes)} executables are not compiled yet.")
        print("You can compile them via the Launcher (Compiler Tab) or with PyInstaller.")
        print("Packaging will continue with available binaries and scripts.")
    print()

    # 2. Build All-in-One ZIP package
    zip_filename = f"BeatbarSuite-v{version}-Windows.zip"
    zip_dest = os.path.join(RELEASE_DIR, zip_filename)
    print(f"[INFO] Creating all-in-one archive: {zip_filename}...")

    prefix = "BeatbarSuite"

    # Folders to bundle
    dirs_to_copy = [
        ("assets", ["*.svg", "*.ico", "*.beat"]),
        ("Guide", ["*.txt", "*.md", "*.bat"]),
        ("web", ["app.py", "run_web.py", "video_scanner.py", "beat_parser.py", "skin_manager.py"]),
    ]

    files_to_copy = [
        "README.md",
        "LICENSE",
        "requirements.txt",
        "ratings_manager.py",
        "icon_utils.py",
        "run_launcher.bat",
        "run_launcher.vbs",
    ]

    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        # Include compiled executables at the root of the suite zip
        for exe_name, exe_path, _ in found_exes:
            arc_name = f"{prefix}/{exe_name}"
            z.write(exe_path, arc_name)
            # Also copy to release/ for standalone upload
            shutil.copy2(exe_path, os.path.join(RELEASE_DIR, exe_name))

        # Root files
        for f in files_to_copy:
            p = os.path.join(ROOT_DIR, f)
            if os.path.exists(p):
                z.write(p, f"{prefix}/{f}")

        # assets/ folder
        for root, _, files in os.walk(os.path.join(ROOT_DIR, "assets")):
            for f in files:
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, ROOT_DIR)
                z.write(full_p, f"{prefix}/{rel_p.replace(os.sep, '/')}")

        # Guide/ folder
        for root, _, files in os.walk(os.path.join(ROOT_DIR, "Guide")):
            for f in files:
                if f.endswith((".txt", ".md", ".bat")):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, ROOT_DIR)
                    z.write(full_p, f"{prefix}/{rel_p.replace(os.sep, '/')}")

        # web/ folder (templates, static, skins, python scripts)
        for root, _, files in os.walk(os.path.join(ROOT_DIR, "web")):
            # Skip previews and thumbnails
            if any(x in root for x in ["previews", "thumbnails", "__pycache__"]):
                continue
            for f in files:
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, ROOT_DIR)
                z.write(full_p, f"{prefix}/{rel_p.replace(os.sep, '/')}")

        # Empty videos folder with .gitkeep
        z.writestr(f"{prefix}/videos/.gitkeep", "")

    total_zip_mb = os.path.getsize(zip_dest) / (1024 * 1024)
    print(f"[SUCCESS] Created {zip_dest} ({total_zip_mb:.1f} MB)")
    print()

    # 3. Create ready-to-copy GitHub Release Notes Template
    notes_file = os.path.join(RELEASE_DIR, "RELEASE_NOTES_TEMPLATE.md")
    notes_content = f"""# Beatbar Suite v{version} Release Notes

Released on {datetime.now().strftime('%Y-%m-%d')}

## Overview
Beatbar Suite is a desktop rhythm production, vector skin styling, synchronized video playback, and mobile network streaming workstation.

## What's Included in This Release

### Desktop Applications (.exe)
* **BeatBar Suite Launcher** (`BeatbarLauncher.exe`): Central studio dashboard and binary manager.
* **BeatBar Maker** (`BeatbarMaker.exe`): Multi-band audio DSP transient analysis (v2 & v3), tempo estimation, snapping grid, and rhythm zones editor.
* **BeatBar Viewer** (`BeatbarViewer.exe`): Frameless desktop HUD video player with reactive beatbars, spring-decay physics, and camera punch screen shake.
* **BeatBar Skin Maker** (`BeatbarSkinMaker.exe`): Vector SVG designer, live animated hit testing, and wing symmetry mirroring.
* **BeatBar Web Viewer**: Mobile-first touch streaming client for Android smartphones and desktop browsers with QR code pairing.

### Downloads
* **`{zip_filename}`** (Recommended): Complete standalone suite. Extract and double-click `BeatbarLauncher.exe` to run.
* **Standalone Executables**: If you only need individual applications, download `BeatbarMaker.exe`, `BeatbarViewer.exe`, or `BeatbarSkinMaker.exe` directly.

### Requirements
* Windows 10/11 (64-bit)
* FFmpeg recommended for video thumbnail caching and audio stream extraction
"""
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write(notes_content.strip())
    print(f"[INFO] Created GitHub release notes template: {notes_file}")
    print()

    print("=" * 70)
    print("                     RELEASE PACKAGING COMPLETE")
    print("=" * 70)
    print(f"Files ready in: {RELEASE_DIR}")
    for item in os.listdir(RELEASE_DIR):
        item_path = os.path.join(RELEASE_DIR, item)
        sz = os.path.getsize(item_path) / (1024 * 1024) if os.path.isfile(item_path) else 0
        print(f"  * {item} ({sz:.2f} MB)" if sz > 0 else f"  * {item}")
    print("=" * 70)


if __name__ == "__main__":
    package_release()
