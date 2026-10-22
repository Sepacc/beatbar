"""
templates.py - SVG Component Templates, Presets, and Fallbacks for Beatbar Skin Maker.

Loads base templates from viewer/skins and provides additional modular templates
for Main Panel, Left Wing, Right Wing, Target, and Beats.
"""

import os
from beatpanel.svg_utils import mirror_svg_horizontally

# Path to shared assets/skins directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_SKINS_DIR = os.path.join(BASE_DIR, "assets", "skins")
VIEWER_SKINS_DIR = ASSETS_SKINS_DIR if os.path.isdir(ASSETS_SKINS_DIR) else os.path.join(BASE_DIR, "viewer", "skins")


def load_file_or_fallback(filename: str, fallback_content: str) -> str:
    """Attempts to read file from viewer/skins; returns fallback if missing."""
    path = os.path.join(VIEWER_SKINS_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return fallback_content.strip()


# ==============================================================================
# BASE FALLBACK STRINGS (Identical to viewer/skins/*.svg)
# ==============================================================================

FALLBACK_PANEL_CYBER = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3500 180" width="3500" height="180">
  <defs>
    <linearGradient id="cyberPanelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#2a2a30" />
      <stop offset="25%" stop-color="#18181c" />
      <stop offset="85%" stop-color="#0e0e12" />
      <stop offset="100%" stop-color="#1e1e24" />
    </linearGradient>
    <linearGradient id="cyberBorderGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#707078" />
      <stop offset="15%" stop-color="#9b51e0" />
      <stop offset="50%" stop-color="#d434ef" />
      <stop offset="85%" stop-color="#9b51e0" />
      <stop offset="100%" stop-color="#707078" />
    </linearGradient>
  </defs>
  <path d="
    M 5 15
    L 75 9
    L 1420 9
    L 1450 3
    L 2050 3
    L 2080 9
    L 3425 9
    L 3495 15
    L 3425 132
    L 2480 132
    L 2450 168
    L 1050 168
    L 1020 132
    L 75 132
    Z
  " fill="url(#cyberPanelGrad)" stroke="url(#cyberBorderGrad)" stroke-width="3" stroke-linejoin="round" />
  <path d="M 80 12 L 1420 12 L 1450 6 L 2050 6 L 2080 12 L 3420 12" 
        stroke="#ffffff" stroke-width="1.2" opacity="0.4" fill="none" />
  <path d="M 1018 134 L 1048 170 L 2452 170 L 2482 134" 
        stroke="#e056fd" stroke-width="1.5" opacity="0.6" fill="none" />
</svg>"""

FALLBACK_PANEL_CLEAN = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3497 174" width="3497" height="174">
  <defs>
    <linearGradient id="cleanPanelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#303038" />
      <stop offset="100%" stop-color="#141418" />
    </linearGradient>
  </defs>
  <path d="M 5 9 L 3437 9 L 3437 15 L 3367 132 L 2480 132 L 2449 165 L 994 165 L 963 132 L 76 132 L 5 15 Z"
        fill="url(#cleanPanelGrad)" stroke="#555562" stroke-width="2.5" stroke-linejoin="round" />
  <path d="M 963 132 L 2480 132" stroke="#be2edd" stroke-width="2" opacity="0.8" />
</svg>"""

FALLBACK_WING_SIGIL_LEFT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 70" width="60" height="70">
  <defs>
    <linearGradient id="metalWing" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="40%" stop-color="#b0b0b8" />
      <stop offset="70%" stop-color="#606068" />
      <stop offset="100%" stop-color="#282830" />
    </linearGradient>
  </defs>
  <g fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M 8 10 L 26 62 L 40 22 L 54 62" stroke="url(#metalWing)" stroke-width="3.5" />
    <path d="M 16 18 L 28 54 L 38 28 L 48 54" stroke="#e056fd" stroke-width="1.8" opacity="0.85" />
    <line x1="4" y1="28" x2="18" y2="40" stroke="#ffffff" stroke-width="1.5" opacity="0.7" />
    <line x1="2" y1="44" x2="14" y2="52" stroke="#ffffff" stroke-width="1.2" opacity="0.5" />
  </g>
</svg>"""

FALLBACK_WING_SIGIL_RIGHT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 70" width="60" height="70">
  <defs>
    <linearGradient id="metalWingR" x1="100%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="40%" stop-color="#b0b0b8" />
      <stop offset="70%" stop-color="#606068" />
      <stop offset="100%" stop-color="#282830" />
    </linearGradient>
  </defs>
  <g fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M 52 10 L 34 62 L 20 22 L 6 62" stroke="url(#metalWingR)" stroke-width="3.5" />
    <path d="M 44 18 L 32 54 L 22 28 L 12 54" stroke="#e056fd" stroke-width="1.8" opacity="0.85" />
    <line x1="56" y1="28" x2="42" y2="40" stroke="#ffffff" stroke-width="1.5" opacity="0.7" />
    <line x1="58" y1="44" x2="46" y2="52" stroke="#ffffff" stroke-width="1.2" opacity="0.5" />
  </g>
</svg>"""

FALLBACK_CREST_TARGET = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 70" width="120" height="70">
  <defs>
    <linearGradient id="crestGlow" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#e056fd" />
      <stop offset="50%" stop-color="#be2edd" />
      <stop offset="100%" stop-color="#4834d4" />
    </linearGradient>
    <filter id="purpleNeon" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2.5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>
  <g filter="url(#purpleNeon)">
    <path d="M 60 35 C 50 20, 32 10, 10 16 C 18 26, 22 36, 16 48 C 28 44, 38 48, 42 56 C 48 45, 54 40, 60 35 Z" 
          fill="url(#crestGlow)" stroke="#f368e0" stroke-width="1.5" />
    <path d="M 60 35 C 70 20, 88 10, 110 16 C 102 26, 98 36, 104 48 C 92 44, 82 48, 78 56 C 72 45, 66 40, 60 35 Z" 
          fill="url(#crestGlow)" stroke="#f368e0" stroke-width="1.5" />
  </g>
  <path d="M 12 18 C 30 25, 45 32, 58 35" stroke="#ffffff" stroke-width="1.2" fill="none" opacity="0.8" />
  <path d="M 108 18 C 90 25, 75 32, 62 35" stroke="#ffffff" stroke-width="1.2" fill="none" opacity="0.8" />
  <path d="M 18 46 C 32 43, 44 42, 56 42" stroke="#ffffff" stroke-width="0.8" fill="none" opacity="0.6" />
  <path d="M 102 46 C 88 43, 76 42, 64 42" stroke="#ffffff" stroke-width="0.8" fill="none" opacity="0.6" />
  <path d="M 52 26 C 48 14, 42 6, 36 2 C 44 8, 48 18, 50 28 Z" fill="#ffffff" stroke="#e056fd" stroke-width="1" />
  <path d="M 68 26 C 72 14, 78 6, 84 2 C 76 8, 72 18, 70 28 Z" fill="#ffffff" stroke="#e056fd" stroke-width="1" />
  <path d="M 48 24 C 48 18, 72 18, 72 24 C 74 34, 72 48, 60 58 C 48 48, 46 34, 48 24 Z" 
        fill="#120c1e" stroke="#e056fd" stroke-width="2" />
  <polygon points="60,20 64,25 60,30 56,25" fill="#f368e0" stroke="#ffffff" stroke-width="0.8" />
  <polygon points="52,33 58,35 53,38" fill="#ffffff" />
  <polygon points="68,33 62,35 67,38" fill="#ffffff" />
  <circle cx="54.5" cy="35" r="1.2" fill="#e056fd" />
  <circle cx="65.5" cy="35" r="1.2" fill="#e056fd" />
  <path d="M 53 45 Q 60 50 67 45" stroke="#e056fd" stroke-width="1.5" fill="none" />
  <polygon points="56,45 58,48 57,45" fill="#ffffff" />
  <polygon points="64,45 62,48 63,45" fill="#ffffff" />
  <polygon points="57,54 60,59 63,54" fill="#be2edd" />
</svg>"""

FALLBACK_CREST_BEAT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 50" width="60" height="50">
  <defs>
    <linearGradient id="beatGlow" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="30%" stop-color="#e056fd" />
      <stop offset="100%" stop-color="#680a9e" />
    </linearGradient>
  </defs>
  <path d="M 30 25 C 22 15, 12 10, 4 12 C 8 20, 10 26, 6 34 C 14 30, 22 34, 25 38 C 28 32, 29 28, 30 25 Z" 
        fill="url(#beatGlow)" stroke="#f368e0" stroke-width="1.2" />
  <path d="M 30 25 C 38 15, 48 10, 56 12 C 52 20, 50 26, 54 34 C 46 30, 38 34, 35 38 C 32 32, 31 28, 30 25 Z" 
        fill="url(#beatGlow)" stroke="#f368e0" stroke-width="1.2" />
  <polygon points="30,8 40,24 30,44 20,24" fill="#200d38" stroke="#ffffff" stroke-width="1.5" />
  <polygon points="30,12 37,24 30,40 23,24" fill="url(#beatGlow)" opacity="0.9" />
  <circle cx="27" cy="22" r="1.8" fill="#ffffff" />
  <circle cx="33" cy="22" r="1.8" fill="#ffffff" />
  <circle cx="27" cy="22" r="0.8" fill="#e056fd" />
  <circle cx="33" cy="22" r="0.8" fill="#e056fd" />
  <path d="M 24 16 L 19 6 L 26 12" stroke="#ffffff" stroke-width="1" fill="#e056fd" />
  <path d="M 36 16 L 41 6 L 34 12" stroke="#ffffff" stroke-width="1" fill="#e056fd" />
</svg>"""

FALLBACK_DIAMOND_BEAT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50">
  <defs>
    <linearGradient id="diamondGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f3ff" />
      <stop offset="50%" stop-color="#be2edd" />
      <stop offset="100%" stop-color="#ff007f" />
    </linearGradient>
  </defs>
  <polygon points="25,4 46,25 25,46 4,25" fill="url(#diamondGrad)" stroke="#ffffff" stroke-width="2" />
  <polygon points="25,12 38,25 25,38 12,25" fill="#ffffff" opacity="0.6" />
  <circle cx="25" cy="25" r="3" fill="#ffffff" />
</svg>"""

FALLBACK_ORB_BEAT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50">
  <defs>
    <radialGradient id="orbGrad" cx="35%" cy="35%" r="65%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="30%" stop-color="#38ef7d" />
      <stop offset="70%" stop-color="#11998e" />
      <stop offset="100%" stop-color="#05332f" />
    </radialGradient>
  </defs>
  <circle cx="25" cy="25" r="22" fill="url(#orbGrad)" stroke="#ffffff" stroke-width="2" />
  <circle cx="20" cy="18" r="5" fill="#ffffff" opacity="0.8" />
</svg>"""

# Additional Creative Variations
EXTRA_PANEL_HEX = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3500 180" width="3500" height="180">
  <defs>
    <linearGradient id="hexPanelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1c1f2e" />
      <stop offset="50%" stop-color="#0c0e18" />
      <stop offset="100%" stop-color="#181a26" />
    </linearGradient>
    <linearGradient id="hexBorderGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#00f3ff" />
      <stop offset="50%" stop-color="#ff007f" />
      <stop offset="100%" stop-color="#00f3ff" />
    </linearGradient>
  </defs>
  <path d="M 30 18 L 120 8 L 1600 8 L 1640 2 L 1860 2 L 1900 8 L 3380 8 L 3470 18 L 3410 130 L 2500 130 L 2460 170 L 1040 170 L 1000 130 L 90 130 Z"
        fill="url(#hexPanelGrad)" stroke="url(#hexBorderGrad)" stroke-width="3" stroke-linejoin="round" />
  <polyline points="150,22 1600,22 1630,12 1870,12 1900,22 3350,22" stroke="#00f3ff" stroke-width="1.5" opacity="0.5" fill="none" />
  <line x1="1020" y1="165" x2="2480" y2="165" stroke="#ff007f" stroke-width="2" opacity="0.7" />
</svg>"""

EXTRA_TARGET_CROSSHAIR = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 70" width="100" height="70">
  <defs>
    <radialGradient id="crosshairGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#00f3ff" stop-opacity="0.8" />
      <stop offset="60%" stop-color="#00f3ff" stop-opacity="0.2" />
      <stop offset="100%" stop-color="#00f3ff" stop-opacity="0" />
    </radialGradient>
  </defs>
  <!-- Reticle Halo -->
  <circle cx="50" cy="35" r="28" fill="url(#crosshairGlow)" />
  <circle cx="50" cy="35" r="24" fill="none" stroke="#00f3ff" stroke-width="2" stroke-dasharray="8 4" />
  <circle cx="50" cy="35" r="16" fill="#0d1822" stroke="#ffffff" stroke-width="1.8" />
  <circle cx="50" cy="35" r="6" fill="#ff007f" stroke="#ffffff" stroke-width="1" />
  <!-- Crosshairs -->
  <line x1="15" y1="35" x2="30" y2="35" stroke="#00f3ff" stroke-width="2.5" />
  <line x1="70" y1="35" x2="85" y2="35" stroke="#00f3ff" stroke-width="2.5" />
  <line x1="50" y1="6" x2="50" y2="17" stroke="#00f3ff" stroke-width="2.5" />
  <line x1="50" y1="53" x2="50" y2="64" stroke="#00f3ff" stroke-width="2.5" />
</svg>"""

EXTRA_BEAT_SHARD = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50">
  <defs>
    <linearGradient id="shardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="40%" stop-color="#ff007f" />
      <stop offset="100%" stop-color="#79003e" />
    </linearGradient>
  </defs>
  <polygon points="25,2 45,14 45,36 25,48 5,36 5,14" fill="url(#shardGrad)" stroke="#ffffff" stroke-width="1.5" />
  <polygon points="25,10 37,18 37,32 25,40 13,32 13,18" fill="#180514" stroke="#ff007f" stroke-width="1.2" />
  <circle cx="25" cy="25" r="4" fill="#ffffff" />
</svg>"""

EXTRA_WING_BLADE_LEFT = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 70" width="60" height="70">
  <defs>
    <linearGradient id="bladeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f3ff" />
      <stop offset="60%" stop-color="#0066aa" />
      <stop offset="100%" stop-color="#002244" />
    </linearGradient>
  </defs>
  <g fill="none" stroke-linejoin="round">
    <path d="M 6 12 L 32 60 L 52 48 L 24 24 Z" fill="url(#bladeGrad)" stroke="#ffffff" stroke-width="1.5" />
    <path d="M 16 16 L 38 52 L 48 44" stroke="#00f3ff" stroke-width="1.2" />
    <line x1="4" y1="26" x2="20" y2="38" stroke="#ffffff" stroke-width="2" stroke-linecap="round" />
  </g>
</svg>"""

EXTRA_WING_BLADE_RIGHT = mirror_svg_horizontally(EXTRA_WING_BLADE_LEFT)

TARGET_HIT_CREST_IGNITED = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 70" width="120" height="70">
  <defs>
    <radialGradient id="hitGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="1" />
      <stop offset="40%" stop-color="#e056fd" stop-opacity="0.9" />
      <stop offset="80%" stop-color="#be2edd" stop-opacity="0.4" />
      <stop offset="100%" stop-color="#4834d4" stop-opacity="0" />
    </radialGradient>
  </defs>
  <!-- Radiant Shock Aura -->
  <ellipse cx="60" cy="35" rx="55" ry="30" fill="url(#hitGlow)" opacity="0.6" />
  <path d="M 60 35 C 48 16, 28 8, 4 14 C 14 26, 18 38, 12 52 C 26 48, 38 52, 42 60 C 50 48, 56 42, 60 35 Z" 
        fill="#ffffff" stroke="#f368e0" stroke-width="2.5" />
  <path d="M 60 35 C 72 16, 92 8, 116 14 C 106 26, 102 38, 108 52 C 94 48, 82 52, 78 60 C 70 48, 64 42, 60 35 Z" 
        fill="#ffffff" stroke="#f368e0" stroke-width="2.5" />
  <!-- Skull Head Ignited -->
  <path d="M 46 22 C 46 14, 74 14, 74 22 C 76 34, 74 50, 60 62 C 46 50, 44 34, 46 22 Z" 
        fill="#ffffff" stroke="#e056fd" stroke-width="2.5" />
  <polygon points="60,16 66,22 60,28 54,22" fill="#e056fd" stroke="#ffffff" stroke-width="1.2" />
  <!-- Eyes Glowing Crosses -->
  <polygon points="53,30 55,36 51,33" fill="#be2edd" />
  <polygon points="67,30 65,36 69,33" fill="#be2edd" />
  <circle cx="53" cy="33" r="3.2" fill="#be2edd" stroke="#ffffff" stroke-width="1" />
  <circle cx="67" cy="33" r="3.2" fill="#be2edd" stroke="#ffffff" stroke-width="1" />
  <!-- Impact Starburst -->
  <path d="M 60 8 L 62 26 L 60 44 L 58 26 Z" fill="#ffffff" opacity="0.8" />
  <path d="M 38 35 L 56 34 L 74 35 L 56 36 Z" fill="#ffffff" opacity="0.8" />
</svg>"""

TARGET_HIT_CROSSHAIR_LOCKED = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 70" width="100" height="70">
  <defs>
    <radialGradient id="burstGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="1" />
      <stop offset="35%" stop-color="#ff007f" stop-opacity="0.9" />
      <stop offset="70%" stop-color="#00f3ff" stop-opacity="0.4" />
      <stop offset="100%" stop-color="#00f3ff" stop-opacity="0" />
    </radialGradient>
  </defs>
  <!-- Impact Flare -->
  <circle cx="50" cy="35" r="32" fill="url(#burstGlow)" />
  <circle cx="50" cy="35" r="26" fill="none" stroke="#ffffff" stroke-width="3" />
  <circle cx="50" cy="35" r="18" fill="#ff007f" stroke="#ffffff" stroke-width="2.5" />
  <circle cx="50" cy="35" r="8" fill="#ffffff" />
  <!-- 4 Corner Lock brackets -->
  <path d="M 22 20 L 22 14 L 28 14" stroke="#00f3ff" stroke-width="3" fill="none" stroke-linecap="round" />
  <path d="M 78 20 L 78 14 L 72 14" stroke="#00f3ff" stroke-width="3" fill="none" stroke-linecap="round" />
  <path d="M 22 50 L 22 56 L 28 56" stroke="#00f3ff" stroke-width="3" fill="none" stroke-linecap="round" />
  <path d="M 78 50 L 78 56 L 72 56" stroke="#00f3ff" stroke-width="3" fill="none" stroke-linecap="round" />
</svg>"""

TARGET_HIT_RABBIT_WINK = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="80" height="80">
  <defs>
    <radialGradient id="rabbitGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
      <stop offset="60%" stop-color="#ff007f" stop-opacity="0.3" />
      <stop offset="100%" stop-color="#ff007f" stop-opacity="0" />
    </radialGradient>
  </defs>
  <circle cx="40" cy="45" r="34" fill="url(#rabbitGlow)" />
  <!-- Bunny Ears -->
  <path d="M 26 38 C 22 22, 20 8, 28 4 C 36 2, 38 18, 34 36 Z" fill="#ffffff" stroke="#ff007f" stroke-width="2" />
  <path d="M 27 34 C 25 22, 24 12, 29 8 C 34 6, 35 18, 32 32 Z" fill="#ff76ac" />
  <path d="M 54 38 C 58 22, 60 8, 52 4 C 44 2, 42 18, 46 36 Z" fill="#ffffff" stroke="#ff007f" stroke-width="2" />
  <path d="M 53 34 C 55 22, 56 12, 51 8 C 46 6, 45 18, 48 32 Z" fill="#ff76ac" />
  <!-- Bunny Head -->
  <ellipse cx="40" cy="50" rx="22" ry="19" fill="#ffffff" stroke="#ff007f" stroke-width="2" />
  <!-- Wink Left Eye / Open Star Right Eye -->
  <path d="M 28 48 Q 33 43 38 48" stroke="#1c1c24" stroke-width="2.5" fill="none" stroke-linecap="round" />
  <!-- Right Eye Star Burst -->
  <polygon points="48,46 50,49 53,49 51,51 52,54 48,52 45,54 46,51 44,49 47,49" fill="#ff007f" />
  <!-- Cute Nose & Open Cheerful Mouth -->
  <polygon points="38,53 42,53 40,55" fill="#ff007f" />
  <path d="M 36 57 Q 40 62 44 57 Z" fill="#ff007f" stroke="#ffffff" stroke-width="0.8" />
</svg>"""


def get_template_library() -> dict[str, dict[str, str]]:
    """
    Returns the core Cyber Wings component templates categorized by component key:
    {
      "panel": { ... },
      "wing_left": { ... },
      "wing_right": { ... },
      "target": { ... },
      "target_hit": { ... },
      "beat": { ... }
    }
    """
    return {
        "panel": {
            "Cyber Wings (Default)": load_file_or_fallback("panel_cyber_wings.svg", FALLBACK_PANEL_CYBER)
        },
        "wing_left": {
            "W-Sigil Metal Left (Default)": load_file_or_fallback("wing_sigil_left.svg", FALLBACK_WING_SIGIL_LEFT)
        },
        "wing_right": {
            "W-Sigil Metal Right (Default)": load_file_or_fallback("wing_sigil_right.svg", FALLBACK_WING_SIGIL_RIGHT)
        },
        "target": {
            "Demonic Crest Skull (Default)": load_file_or_fallback("crest_target.svg", FALLBACK_CREST_TARGET)
        },
        "target_hit": {
            "Demonic Crest Skull (Hit Ignited)": TARGET_HIT_CREST_IGNITED
        },
        "beat": {
            "Demonic Crest (Default)": load_file_or_fallback("crest_beat.svg", FALLBACK_CREST_BEAT)
        }
    }
