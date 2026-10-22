# BeatPanel - Beatbar Skin Maker & SVG Previewer

A dedicated desktop tool for creating, customizing, and previewing Beatbar skins for the Beatbar Viewer.

## Features

- **Live Beatbar Preview**:
  - Live animated simulation matching `viewer/beatbar.py` with approaching beats flowing toward the target.
  - Interactive hit animations (shockwaves, particles, and target scale bounce).
  - Manual "Trigger Hit" button to test physics and pop effects.
  - Component visibility toggles (Main Panel, Left Wing, Right Wing, Target, Beats).
  - Flow direction switcher (RTL, LTR, Both Sides).
  - Backdrop modes (Studio Glow, Transparent Grid, Cyber Stage, Pitch Black).

- **5 Core Beatbar Components**:
  1. **Main Panel** (`panel.svg`): Base trapezoidal panel with metallic sheen and cyber borders.
  2. **Left Wing** (`wing_left.svg`): Wing sigil emblem in the left corner.
  3. **Right Wing** (`wing_right.svg`): Mirrored or unique wing sigil in the right corner.
  4. **Center Target** (`target.svg`): Central demon crest skull / reticle with hit pop reaction.
  5. **Beats** (`beat.svg`): Approaching rhythm icons (crest, diamond, orb, shard).

- **Skin Editing & Customization Tools**:
  - **Template Library**: Base templates sourced from `viewer/skins/` plus creative variations.
  - **Color Swatch Inspector**: Auto-detects all hex colors inside the SVG. Click any swatch to pick a replacement color in real time!
  - **SVG XML Live Editor**: Direct code editor with syntax validation, error highlighting, and prettifier.
  - **Wing Symmetry Mirroring**: One-click "Mirror to Opposite Wing" button to generate symmetric wing pairs automatically.
  - **Global Palette Harmonizer**: Apply cohesive color palettes across all 5 SVGs in a single click.
  - **Import / Export**: Import custom SVGs or export individual components.
  - **Export to Viewer**: 1-click export directly to `viewer/skins/` with automatic update of `viewer_config.json`.

## Quick Start

Run the program from the repository root:

```bash
python beatpanel/main.py
```

or as a module:

```bash
python -m beatpanel
```
