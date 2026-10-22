# Beatbar Suite - Comprehensive Project Guide

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Web%20%7C%20Android-lightgrey.svg)]()

This document is the companion reference guide located inside the [`Guide/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide) directory. For the master repository overview, see [README.md](file:///c:/HDD/code/gemini%20antigrav/beatmake/README.md).

---

## Contents

1. [Applications Overview](#1-applications-overview)
   - [Beatbar Maker (`main`)](#beatbar-maker)
   - [Beatbar Viewer (`viewer`)](#beatbar-viewer)
   - [Beatbar Skins Maker (`beatpanel`)](#beatbar-skins-maker)
   - [Web Beatbar Viewer (`web`)](#web-beatbar-viewer)
   - [Suite Launcher (`launcher`)](#suite-launcher)
2. [File Tree](#2-file-tree)
3. [Installation and Dependencies](#3-installation-and-dependencies)
4. [Standalone Batch Launchers](#4-standalone-batch-launchers)
5. [License Details](#5-license-details)
6. [Credits and Third-Party Licenses](#6-credits-and-third-party-licenses)

---

## 1. Applications Overview

### Beatbar Maker
*Directory: [`main/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/main)*
* Launcher: [`run_beatbar_maker.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/run_beatbar_maker.bat)
* Features:
  - Multi-band digital signal processing (DSP) using `librosa` and `scipy`.
  - Automatic kick, snare, and percussion onset detection.
  - Dynamic tempo estimation and beat quantization grid (1/1 to 1/8).
  - Rhythm zones editor (Normal, Climax, Speeding Up, Slowing, Pause, Edging).
  - Automatic difficulty rating from Level 1 to 10 (Easy to Master).
  - Synchronized video/audio timeline with waveform preview and interactive marker editing.
  - Packaging engine for `.beat` archives and `.json` beatmaps.

### Beatbar Viewer
*Directory: [`viewer/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/viewer)*
* Launcher: [`run_beatbar_viewer.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/run_beatbar_viewer.bat)
* Features:
  - Frameless modern HUD window with auto-collapsing controls after 2.5s of inactivity.
  - Symmetrical vector beatbar with animated approaching notes and reactive target reticle.
  - Spring-decay hit physics, radiant sparkle particles, and expanding shockwave rings.
  - Dynamic Camera Punch screen shake zoom on intense zones and 5+ note bursts.
  - Secondary timeline embedded inside the beatbar bottom notch.
  - Slide-out library drawer with video thumbnails, search filtering, and 5-star ratings.
  - Settings modal with custom themes and color pickers.

### Beatbar Skins Maker
*Directory: [`beatpanel/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/beatpanel)*
* Launcher: [`run_skin_maker.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/run_skin_maker.bat)
* Features:
  - Dedicated vector designer for the 5 core SVG components: `panel.svg`, `wing_left.svg`, `wing_right.svg`, `target.svg`, and `beat.svg`.
  - Real-time physics simulation matching the desktop viewer.
  - Manual "Trigger Hit" button for particle and shockwave testing.
  - Color Swatch Inspector that parses hex codes directly from SVGs for instant replacement.
  - Wing Symmetry Mirroring to mirror wings with matrix transforms.
  - 1-click export to `viewer/skins/` with configuration updates.

### Web Beatbar Viewer
*Directory: [`web/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/web)*
* Launcher: [`run_web_viewer.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/run_web_viewer.bat)
* Features:
  - Mobile-first web server built on Flask and HTML5 Canvas.
  - Optimized for Android smartphones and tablets with touch gestures (double-tap to skip, swipe scrub).
  - 1-tap QR Code pairing for scanning from mobile cameras.
  - Full HTTP 206 Byte-Range streaming for instant video scrubbing.
  - Universal `.beat` and `.json` beatmap parser.

### Suite Launcher
*Directory: [`launcher/`](file:///c:/HDD/code/gemini%20antigrav/beatmake/launcher)*
* Launcher: [`run_launcher.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/run_launcher.bat)
* Features:
  - Compact studio hub with cards for all suite applications.
  - Process supervisor that prevents duplicate instances and tracks run status.
  - Version synchronization tracking between source files and compiled `.exe` binaries.
  - Built-in PyInstaller compilation dialog.
  - Drag-and-drop `.beat` file dropzone.

---

## 2. File Tree

```
beatmake/
├── LICENSE
├── README.md
├── requirements.txt
├── run_launcher.bat
├── run_launcher.vbs
├── ratings_manager.py
├── docs/
│   └── screenshots/
│       └── .gitkeep
├── Guide/
│   ├── README.txt
│   ├── guide.txt
│   ├── PROJECT_GUIDE.md
│   ├── install_dependencies.bat
│   ├── run_beatbar_maker.bat
│   ├── run_beatbar_viewer.bat
│   ├── run_skin_maker.bat
│   ├── run_web_viewer.bat
│   └── run_launcher.bat
├── main/
├── viewer/
├── beatpanel/
├── web/
├── launcher/
├── assets/
└── videos/
```

---

## 3. Installation and Dependencies

Run [`install_dependencies.bat`](file:///c:/HDD/code/gemini%20antigrav/beatmake/Guide/install_dependencies.bat) or run:

```bash
pip install -r requirements.txt
```

### Python Dependencies Summary
* `PyQt6`: Desktop GUI framework and vector graphics engine
* `opencv-python`: Video decoding and frame analysis
* `numpy`: Numerical mathematics and vector arrays
* `scipy`: Digital signal processing and peak detection
* `librosa`: Audio transient analysis and tempo tracking
* `Pillow`: Image processing and QR code rendering
* `Flask`: Web streaming HTTP server
* `qrcode[pil]`: Mobile LAN pairing QR code generation
* `pyinstaller`: (Optional) Windows `.exe` compiler

---

## 4. Standalone Batch Launchers

All `.bat` files in this directory are fully self-contained and support arguments:

* `install_dependencies.bat`: Installs requirements and verifies libraries and FFmpeg.
* `run_beatbar_maker.bat`: Opens Beatbar Maker.
* `run_beatbar_viewer.bat`: Opens Beatbar Viewer (supports video path arguments).
* `run_skin_maker.bat`: Opens Beatbar Skins Maker.
* `run_web_viewer.bat`: Starts Web Viewer and opens browser to `http://localhost:8080`.
* `run_launcher.bat`: Opens Suite Launcher hub.

---

## 5. License Details

This project is released under the **MIT License**. See [LICENSE](file:///c:/HDD/code/gemini%20antigrav/beatmake/LICENSE) for the full license text.

---

## 6. Credits and Third-Party Licenses

* **Feather Icons**: Copyright (c) 2013-2017 Cole Bemis. Licensed under the [MIT License](https://github.com/feathericons/feather/blob/main/LICENSE). Used for application toolbar and UI icons (`assets/feather/*.svg`).
* **Anybody Font**: Designed by Etcetera Type Co. (Tyler Finck). Licensed under the [SIL Open Font License 1.1](https://github.com/Etcetera-Type-Co/Anybody/blob/master/OFL.txt). Used for app icon and branding typography (https://fontsource.org/fonts/anybody).
