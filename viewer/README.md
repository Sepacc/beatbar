# Beatbar Video Viewer

A modern, video viewer program that plays video tracks synchronized with interactive, customizable beatbars, animated targets, responsive controls, and dynamic camera punch screen shakes.

Developed to match the UI/UX specifications provided in `beatmake.jpg`, `beatmake-2.jpg`, `beatmake-settings.jpg`, and `beatmake-bar.svg`.

---

## Features Overview

### 1. Video Title / Next Video Button (Top Center)
- Centered dark capsule pill displaying the current video's title.
- Features a **Next Video** arrow button (`▶|`): clicking advances immediately to the next video file in the playlist folder, automatically discovering and loading its matching beatbar JSON.

### 2. Window Controls (Top Right)
- Sleek dark capsule containing **Minimize (`—`)**, **Maximize / Restore (`▢`)**, and **Close (`✕`)** buttons.
- Fully frameless window with native OS dragging (drag by top bar) and double-click to maximize/restore.

### 3. Bottom Control Bar & Sound Changing Bar
A row of rounded dark control buttons at the bottom-left:
- **Sound Button & Sound Changing Bar**: Hovering or clicking the volume button pops up the vertical sound changing bar (dark vertical pill with slider groove and white thumb thumb, as in `beatmake-2.jpg`). Supports mouse drag, wheel scrolling, and click-to-mute.
- **Play / Pause**: Toggles playback state.
- **Speed Button (0.3x - 3.0x)**: Click to cycle through speeds: `0.3x -> 0.5x -> 0.75x -> 1.0x -> 1.25x -> 1.5x -> 2.0x -> 3.0x`.
- **Screen Shake Toggle**: Quick toggle for camera punch zoom in-n-out on beat hits.
- **Loop Toggle**: Toggles video loop on/off.
- **Open File**: Quick file dialog to open any video (`.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`) or beatbar (`.json`).
- **Fullscreen Button**: Toggles borderless fullscreen mode (`F11`).

### 4. Player Timeline with Player Knob
- Dark rounded track across the bottom bar with progress gradient fill.
- **Timeline Knob (Player)**: Modeled after `beatmake-2.jpg` as a white rounded square with a black play/pause symbol inside!
  - Clicking the knob toggles Play / Pause.
  - Dragging the knob scrubs the video and beatbar in real-time.
  - Clicking anywhere on the track seeks to that position.
- Accurate timecode readout (`MM:SS / MM:SS`).

### 5. Settings Button & Settings Window (Top Left)
- White rounded square button at the top-left opening the Settings Modal (styled after `beatmake-settings.jpg`):
  - **Choose Video File**: Select any video file.
  - **Choose Beatbar File**: Select any beatbar JSON file.
  - **Choose Beatbar Skin**: Switch between Cyber Wings (`beatmake-2.jpg`), Clean Template (`beatmake-bar.svg`), or Custom SVG/Image.
  - **Choose Beats Skin**: Switch between Purple Demonic Crests, Neon Gems, Colored Rhythm Bars, or Radiant Orbs.
  - **Settings Variables**:
    - Screen Shake Mode (Intense Zones & 5+ Bursts, Always, Off)
    - Shake Strength (Subtle 1.03x to Strong 1.08x)
    - Hit Animation Style (Shockwave Ring, Radiant Sparkle Burst, All)
    - Beat Scroll Direction (Right-to-Left, Left-to-Right)
    - Note Lead Time (Speed): 0.6s - 3.0s
    - Inactivity Collapse Delay (1.5s, 2.5s, 4.0s, Never)
  - **Some Pallete (Theme & Color Customizer)**:
    - Violet Amethyst (Purple `#be2edd`, Magenta `#e056fd`, White `#ffffff`)
    - Cyber Synthwave (Cyan `#00f3ff`, Pink `#ff007f`)
    - Emerald Groove (Green `#2ecc40`, Mint `#38ef7d`)
    - Solar Flare (Gold `#ff9f1a`, Orange `#ff5252`)
    - Crimson Fury (Blood Red `#ff1744`, Coral)
    - Interactive RGB Custom Color Pickers!

### 6. Centerpiece Beatbar
- **Fancy Angled Panel**: Symmetrical trapezoid wings geometry matching `beatmake-bar.svg` with upper raised tab, metallic bevel, and decorative "W" wing sigils on left and right ends.
- **Beats Moving Space**: Beats travel horizontally across the lane toward the central target.
- **Central Target ("Thing that beats go into")**:
  - Demonic winged crest with glowing eyes and horns (as in `beatmake-2.jpg`).
  - Triangular indicator arrow (`▲`) pointing up from the bottom edge to mark the hit point.
  - Customizable hit animations: expanding glowing shockwave rings, radiant sparkle particles, and scale-pop flashes.
- **Secondary Timeline**:
  - Positioned inside the bottom notch cutout of the panel (`another timeline, that gets filled as video goes on`).
  - Sleek silver/white progress bar that fills progressively from 0% to 100% as the video plays. Supports click/drag seeking.

### 7. Inactivity Auto-Collapse
- After 2.5 seconds of user inactivity (configurable in Settings), the bottom bar and top controls smoothly collapse/hide, leaving the user with **only the video and the floating beatbar**.
- Moving the mouse or pressing any key immediately restores the controls.

### 8. Screen Shake (Zoom In-n-Out)
- Triggers a slight camera punch zoom in-and-out centered on the video every time a beat lands on the target when:
  1. The beat is inside an **intense zone** (`climax`, `edging`) or **speedy zone** (`speeding_up`).
  2. OR when there is a rapid streak/group of **5+ beats in a row** (gap <= 0.35s).
- Smooth spring-decay interpolation over ~120ms ensures high-impact visual feedback without video stutter.

### 9. Refined Beats Saving & Loading Process
- The beatmap generator now saves **only a clean JSON file** containing:
  - Video and audio file association
  - Settings variables (BPM, speed, lead time, screen shake)
  - Zone timings and types (Normal, Climax, Speeding Up, Slowing, Pause, Edging)
  - Timed beat list
- No unnecessary `.srt` or `.txt` files are output.
- Backwards compatible with legacy files.

---

## Running the Viewer

### 1. Launch with Default Media (Auto-matches `wicked-r34-level-1.mp4`):
```bash
python viewer/main.py
```
or:
```bash
python -m viewer
```

### 2. Launch with a Specific Video and Beatbar:
```bash
python viewer/main.py path/to/video.mp4 path/to/beatbar.json
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `Left` / `Right` | Seek -5s / +5s |
| `Up` / `Down` | Volume +5% / -5% |
| `M` | Mute / Unmute |
| `S` | Toggle Screen Shake |
| `L` | Toggle Loop Mode |
| `N` | Play Next Video in Folder |
| `F` / `F11` | Toggle Fullscreen |
| `Esc` | Exit Fullscreen / Close Settings |

---

## Creating Custom Beatbar Skins

Users can create custom beatbars using `viewer/beatmake-bar.svg` as a template:
1. Open `viewer/skins/panel_template.svg` (or `viewer/beatmake-bar.svg`) in any vector editor (Inkscape, Illustrator, Figma, Affinity Designer).
2. Modify the colors, borders, or graphic elements while keeping the general canvas viewBox (`3497 x 174`).
3. Save as `.svg` or export as `.png` into `viewer/skins/`.
4. In the viewer, click the **Settings** button (top-left) -> **Beatbar Skin** -> **Custom SVG / Image...** and select your file.
