# Beatbar Suite v1.2.1 Release Notes

Released on 2026-10-27

## Overview
Beatbar Suite v1.2.1 is a major stability, performance, and usability update across the entire rhythm production, video synchronization, vector skin styling, and streaming workstation. This release introduces one-click automated updates, quick-access recent media history, non-blocking background library scanning, PyInstaller binary size optimizations, concurrent process locks, and multi-device gesture enhancements.

---

## What's New & Fixed in v1.2.1

### 1. BeatBar Suite Launcher
* **Automated One-Click Suite Updater**: Added a one-click update pipeline (`Update Suite`) that automatically pulls remote Git updates and checks suite executables against source modifications and version tags, automatically recompiling dirty components without manual intervention.
* **Quick-Access Recent Projects & Media History**: Integrated a header dropdown menu displaying recently modified `.beat` projects and `.mp4` videos with relative timestamps and file sizes. Clicking a `.beat` opens the action launcher; clicking an `.mp4` instantly plays it in BeatBar Viewer.
* **Fast-Click Duplicate Instance Prevention (Bug 2.4)**: Addressed an issue where rapid double-clicking on launch buttons spawned redundant heavy processes by disabling action buttons immediately on click until process registration is confirmed.
* **Debounced Geometry Autosave**: Debounced window move and resize events with a single-shot 500ms `QTimer`, eliminating redundant synchronous disk writes on every pixel adjustment.
* **PyInstaller Compilation Exclusions Optimization**: Excluded `unittest`, `doctest`, and `pdb` frameworks from production builds of `BeatbarMaker.exe`, trimming over 25 MB of unused binary footprint.
* **Viewer PyInstaller Web Package Bundling (Bug 2.2)**: Bundled `web` and added `web` to PyInstaller search paths so `BeatbarViewer.exe` can access `web.video_scanner` without crashing on standalone installations.
* **Port Binding Pre-Check Before Launching Web Server**: Added socket availability pre-checks prior to starting the local Flask server. If port 8080 is held by an external process, the launcher automatically selects an available port (e.g., 8081).
* **BeatDropzone Program ID Key Fixes (Bug 2.1)**: Corrected program ID mappings (`beatbar_viewer`, `beatbar_maker`, `beatbar_skins`) in `BeatDropZoneWidget` so drag-and-drop actions reliably launch the selected tool.

### 2. BeatBar Viewer
* **Background Threading for Library Scanner**: Moved file discovery, beatmap parsing, and FFmpeg thumbnail extraction into a background `QThread` (`LibraryScanWorker`). Tracks stream progressively into the UI via Qt signals, completely eliminating GUI freezes when opening the Media Library drawer or rescanning.

### 3. BeatBar Skin Maker
* **Graceful Config File Creation on Fresh Installs**: When exporting custom skins on fresh setups where `viewer/.config` does not yet exist, Skin Maker automatically initializes `viewer/.config` with the default schema before writing skin properties.

### 4. BeatBar Web Viewer
* **Mutex Lock & Atomic Temp File on Preview Generation**: Protected 5-second hover preview video creation with per-file `threading.Lock` mutexes and atomic `.tmp_<uuid>.mp4` file renaming, preventing competing concurrent FFmpeg processes from corrupting files under heavy HTTP traffic.
* **Touch Gesture Collision Fix (Bug 5.5)**: Replaced delayed click listeners with dedicated `touchstart` gesture handlers (`preventDefault()`), preventing single-tap UI visibility toggles from firing simultaneously during double-tap skip seeking on mobile touchscreens.

---

## What's Included in This Release

### Desktop Applications (.exe)
* **BeatBar Suite Launcher** (`BeatbarLauncher.exe`): Central studio dashboard, binary version inspector, and automated one-click updater.
* **BeatBar Maker** (`BeatbarMaker.exe`): Multi-band audio DSP transient analysis, tempo estimation, snapping grid, and rhythm zones editor.
* **BeatBar Viewer** (`BeatbarViewer.exe`): Frameless desktop HUD video player with reactive beatbars, spring physics, dynamic camera shake, and progressive library browsing.
* **BeatBar Skin Maker** (`BeatbarSkinMaker.exe`): Vector SVG designer, live animated hit testing, and wing symmetry mirroring.
* **BeatBar Web Viewer**: Mobile-first touch streaming client for Android smartphones and desktop browsers with QR code pairing.

### Downloads
* **`BeatbarSuite-v1.2.1-Windows.zip`** (Recommended): Complete standalone suite. Extract and double-click `BeatbarLauncher.exe` to run.
* **Standalone Executables**: If you only need individual applications, download `BeatbarLauncher.exe`, `BeatbarMaker.exe`, `BeatbarViewer.exe`, or `BeatbarSkinMaker.exe` directly from the release folder.

### Requirements
* Windows 10/11 (64-bit)
* FFmpeg recommended for video thumbnail caching and audio stream extraction
