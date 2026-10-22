# Beatbar Web Viewer (Mobile & Android Optimized)

A high-performance, mobile-first web port of the Beatbar Viewer application designed for viewing on Android smartphones, tablets, and desktop browsers.

---

## 🌟 Highlights & Capabilities

- **Android Mobile-First Design**:
  - Fullscreen touch-optimized playback with automatic landscape rotation lock support.
  - Double-tap left/right to skip 5 seconds with animated ripples.
  - Auto-inactivity collapse: after 2.5s of no touch interaction during playback, UI bars seamlessly fade out leaving only the video and the floating centerpiece beatbar.
  - Hardware accelerated Canvas rendering (`window.devicePixelRatio` scaling) for razor-sharp visuals on OLED and high-DPI retina screens.
  - 1-tap QR Code pairing for instantly opening the viewer from an Android camera.
- **Universal Beatmap Parsing**:
  - Supports `.beat` ZIP archives (extracts `manifest.json`, `beatmap.json`, `video_name.txt`, zones, and settings).
  - Supports V2 Beatmap `.json` files (`beats`, `zones`, `settings`, `bpm`, `lead_time`).
  - Supports legacy `.json` files and raw beat timestamps.
  - Automatic detection of 5+ rapid beat streaks (bursts) and rhythm zones (`climax`, `edging`, `intense`, `speedy`).
- **Faithful Desktop Beatbar Reproduction**:
  - Angled trapezoid metallic panel with glowing purple/violet cyberpunk borders and top rim highlight.
  - Moving beats approaching the central target with configurable lead time (1.5s) and zone directions (RTL, LTR, BOTH).
  - Central target reticle with spring-decay pop scale on beat hits.
  - Triangular indicator arrow (▲).
  - Expanding glowing shockwave rings and sparkling burst particles.
  - Secondary timeline in the bottom notch with active fill and interactive touch/click seeking.
  - Camera punch screen shake zoom on beat hits.
- **Interactive Video Library**:
  - Scans specified directory (`C:\HDD\code\gemini antigrav\beatmake\videos`).
  - Auto-matches each video with its corresponding `.beat` or `.json` file.
  - Fast thumbnail generation & caching via FFmpeg.
  - Search filtering by title/filename and filter tabs (All, With Beats, Missing Beats).
  - Upload/Attach modal to drop or select a new `.beat` or `.json` file directly from a phone or PC.
- **Smooth Streaming**:
  - Full HTTP 206 Partial Content (Byte-Range requests) support for instant, butter-smooth seeking on Android Chrome/Firefox.

---

## 🚀 Quick Start

Run the web viewer with any of the following commands:

```bash
# Method 1: Convenience script
python run_web.py

# Method 2: Convenience script with auto-open browser
python run_web.py --open

# Method 3: As a Python module
python -m web

# Method 4: Via main editor CLI
python main.py --web

# Method 5: Via desktop viewer entry point
python viewer/main.py --web
```

### CLI Options

| Argument | Default | Description |
|---|---|---|
| `--port` | `8080` | Port to listen on |
| `--host` | `0.0.0.0` | Host interface (`0.0.0.0` allows LAN connections from Android) |
| `--folder` | `.../videos` | Target video folder to scan and display in library |
| `--open` | `False` | Opens default web browser on launch |
| `--debug` | `False` | Enables Flask debug mode |

---

## 📱 Connecting from Android

1. Make sure your Android device is connected to the same Wi-Fi network as your PC.
2. Launch the server (`python run_web.py`).
3. The console will display your LAN IP addresses (e.g., `http://192.168.0.101:8080`).
4. On your PC browser, click the **QR Code** or **Connect Phone** button in the header, or point your Android camera at the QR code on screen.
5. Tap the link to open the Beatbar Viewer directly on your phone!

---

## 🎮 Controls & Gestures

### Mobile Touch Gestures
- **Single Tap**: Toggle controls overlay (top bar & bottom bar).
- **Double Tap Left**: Skip -5 seconds with animated `« 5s` ripple.
- **Double Tap Right**: Skip +5 seconds with animated `5s »` ripple.
- **Touch Drag on Beatbar Notch**: Instant scrubbing to target position.
- **Touch Drag on Bottom Timeline**: Smooth scrubbing with zone indicators.
- **Sound Button**: Opens vertical volume slider popup.

### Keyboard Shortcuts (Desktop / Bluetooth Keyboard)
- `Space`: Play / Pause
- `Left Arrow`: Seek -5 seconds
- `Right Arrow`: Seek +5 seconds
- `Up Arrow`: Volume +5%
- `Down Arrow`: Volume -5%
- `M`: Toggle Mute
- `S`: Toggle Camera Punch Screen Shake
- `F` or `F11`: Toggle Fullscreen
- `N`: Next Video in Library
- `Esc`: Return to Library or Exit Fullscreen
