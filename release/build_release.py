"""
build_release.py - Automated release build and package creator for Beatbar Suite v1.2.1.
Compiles 4 standalone executables to release/ and packages BeatbarSuite-v1.2.1-Windows.zip.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from launcher.version_manager import PROGRAM_REGISTRY, ProgramConfig
from launcher.compiler import build_pyinstaller_command, TEMP_BUILD_DIR

RELEASE_DIR = os.path.join(ROOT_DIR, "release")
SUITE_VERSION = "1.2.1"


def compile_program(prog_id: str):
    prog = PROGRAM_REGISTRY[prog_id]
    print(f"\n[{time.strftime('%H:%M:%S')}] >>> Compiling {prog.name} (v{SUITE_VERSION}) to {RELEASE_DIR}...")
    cmd, ver = build_pyinstaller_command(prog, dist_dir=RELEASE_DIR)
    
    t0 = time.time()
    res = subprocess.run(cmd, cwd=ROOT_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed for {prog.name} with code {res.returncode}")
    print(f"[{time.strftime('%H:%M:%S')}] >>> Finished {prog.name} in {time.time()-t0:.1f}s")

    # Clean temporary build directory
    if os.path.exists(TEMP_BUILD_DIR):
        try:
            shutil.rmtree(TEMP_BUILD_DIR, ignore_errors=True)
        except Exception:
            pass


def create_release_zip():
    zip_name = f"BeatbarSuite-v{SUITE_VERSION}-Windows.zip"
    zip_path = os.path.join(RELEASE_DIR, zip_name)
    print(f"\n[{time.strftime('%H:%M:%S')}] >>> Packaging {zip_path}...")

    # Files to include at root of BeatbarSuite/
    root_files = [
        "README.md",
        "LICENSE",
        "requirements.txt",
        "icon_utils.py",
        "run_launcher.bat",
        "run_launcher.vbs"
    ]

    # Directories to include recursively
    include_dirs = [
        "assets",
        "Guide",
        "web",
        "videos"
    ]

    # The 4 compiled executables
    executables = [
        "BeatbarLauncher.exe",
        "BeatbarMaker.exe",
        "BeatbarViewer.exe",
        "BeatbarSkinMaker.exe"
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add executables from release/
        for exe in executables:
            exe_path = os.path.join(RELEASE_DIR, exe)
            if not os.path.isfile(exe_path):
                raise FileNotFoundError(f"Missing compiled executable: {exe_path}")
            arcname = f"BeatbarSuite/{exe}"
            print(f"  Adding {arcname} ({os.path.getsize(exe_path)/(1024*1024):.1f} MB)")
            zf.write(exe_path, arcname)

        # Add root support files
        for f in root_files:
            fp = os.path.join(ROOT_DIR, f)
            if os.path.isfile(fp):
                zf.write(fp, f"BeatbarSuite/{f}")

        # Add directories
        for d in include_dirs:
            dp = os.path.join(ROOT_DIR, d)
            if not os.path.isdir(dp):
                continue
            for r, dirs, files in os.walk(dp):
                # Exclude build caches, pycache, .git
                if any(skip in r for skip in ["__pycache__", ".git", "thumbnails", "previews"]):
                    continue
                for file in files:
                    full_p = os.path.join(r, file)
                    rel_p = os.path.relpath(full_p, ROOT_DIR)
                    arcname = f"BeatbarSuite/{rel_p.replace(os.sep, '/')}"
                    zf.write(full_p, arcname)

    print(f"[{time.strftime('%H:%M:%S')}] >>> Successfully created {zip_path} ({os.path.getsize(zip_path)/(1024*1024):.1f} MB)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-zip", action="store_true")
    args = parser.parse_args()

    if not args.only_zip:
        for pid in ["launcher", "beatbar_skins", "beatbar_viewer", "beatbar_maker"]:
            compile_program(pid)

    create_release_zip()
    print("\n[Done] Release build completed successfully!")
