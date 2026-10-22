"""
icon_utils.py - Feather SVG Icon Loader and Painter for Beatmaker Pro.

Loads and renders SVG icons from the 'feather' directory with custom colors,
anti-aliasing, and size scaling for PyQt6 buttons, labels, and QPainter tracks.
"""

import os
from PyQt6.QtCore import Qt, QRectF, QByteArray
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "main" else CURRENT_DIR

CANDIDATE_FEATHER_DIRS = [
    os.path.join(ROOT_DIR, "assets", "feather"),
    os.path.join(ROOT_DIR, "assets", "icons"),
    os.path.join(ROOT_DIR, "feather"),
    os.path.join(CURRENT_DIR, "feather"),
]
FEATHER_DIR = next((d for d in CANDIDATE_FEATHER_DIRS if os.path.isdir(d)), CANDIDATE_FEATHER_DIRS[0])

# In-memory cache for rendered QIcons to ensure snappy UI rendering
_ICON_CACHE = {}
_RENDERER_CACHE = {}
_SUITE_PIXMAP_CACHE = {}
_SUITE_ICON_CACHE = {}


def get_suite_svg_path(name: str):
    """Finds path for a suite SVG by name, normalizing aliases."""
    if not name:
        return None
    norm = str(name).lower().strip()
    if norm.endswith(".svg"):
        norm = norm[:-4]
    
    alias_map = {
        "main": "beatbar-main",
        "launcher": "beatbar-main",
        "hub": "beatbar-main",
        "beatbar_main": "beatbar-main",
        "maker": "beatbar-maker",
        "beatbar_maker": "beatbar-maker",
        "viewer": "beatbar-viewer",
        "beatbar_viewer": "beatbar-viewer",
        "skins": "beatbar-skins",
        "skin": "beatbar-skins",
        "skin_maker": "beatbar-skins",
        "beatpanel": "beatbar-skins",
        "beatbar_skins": "beatbar-skins",
        "web": "beatbar-web",
        "web_viewer": "beatbar-web",
        "beatbar_web": "beatbar-web",
    }
    filename = alias_map.get(norm, norm if norm.startswith("beatbar-") else f"beatbar-{norm}") + ".svg"
    candidate = os.path.join(ROOT_DIR, "assets", filename)
    if os.path.exists(candidate):
        return candidate
    alt_candidate = os.path.join(CURRENT_DIR, "..", "assets", filename)
    if os.path.exists(alt_candidate):
        return os.path.abspath(alt_candidate)
    return None


def get_suite_svg_content(name: str, dark_mode: bool = False):
    """Returns SVG text content for a suite component with optional dark mode palette."""
    path = get_suite_svg_path(name)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if dark_mode:
            content = (
                content.replace("#0c0c0e", "#ffffff")
                .replace("#27242b", "#8b949e")
                .replace("stroke:#000;", "stroke:none;")
                .replace('stroke="#000"', 'stroke="none"')
            )
        return content
    except Exception as e:
        print(f"Error loading suite SVG {name}: {e}")
        return None


def get_suite_renderer(name: str, dark_mode: bool = False):
    """Returns a cached QSvgRenderer for a suite icon."""
    key = ("suite_renderer", name, dark_mode)
    if key in _RENDERER_CACHE:
        return _RENDERER_CACHE[key]
    content = get_suite_svg_content(name, dark_mode=dark_mode)
    if not content:
        return None
    renderer = QSvgRenderer(QByteArray(content.encode("utf-8")))
    _RENDERER_CACHE[key] = renderer
    return renderer


def get_suite_pixmap(name: str, size: int = 24, dark_mode: bool = False, tile: bool = False, tile_color: str = "#ffffff"):
    """
    Renders a BeatBar Suite SVG into a crisp QPixmap.
    If dark_mode=True: adjusts black lettermark and bars to light/white for dark UI backgrounds.
    If tile=True: renders the SVG inside a rounded squircle badge (default white).
    """
    key = (name, size, dark_mode, tile, tile_color)
    if key in _SUITE_PIXMAP_CACHE:
        return _SUITE_PIXMAP_CACHE[key]

    renderer = get_suite_renderer(name, dark_mode=(dark_mode and not tile))
    if not renderer or not renderer.isValid():
        return QPixmap()

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if tile:
        radius = max(3.0, size * 0.22)
        painter.setBrush(QColor(tile_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), radius, radius)
        pad = max(2.0, size * 0.12)
        target_rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
        renderer.render(painter, target_rect)
    else:
        renderer.render(painter, QRectF(0, 0, size, size))

    painter.end()
    _SUITE_PIXMAP_CACHE[key] = pixmap
    return pixmap


def get_suite_icon(name: str, size: int = 32, dark_mode: bool = True):
    """
    Returns a multi-resolution QIcon for application windows, taskbars, and dialogs.
    """
    key = ("suite_icon", name, size, dark_mode)
    if key in _SUITE_ICON_CACHE:
        return _SUITE_ICON_CACHE[key]

    icon = QIcon()
    for s in [16, 20, 24, 32, 48, 64, 128, 256]:
        pm = get_suite_pixmap(name, size=s, dark_mode=dark_mode)
        if pm and not pm.isNull():
            icon.addPixmap(pm)

    if icon.isNull():
        # Fallback to single size
        pm = get_suite_pixmap(name, size=size, dark_mode=dark_mode)
        if pm and not pm.isNull():
            icon = QIcon(pm)

    _SUITE_ICON_CACHE[key] = icon
    return icon

def get_feather_svg_content(name, color="#ffffff", stroke_width=2, fill=None):
    """Returns SVG text content with color, fill, and stroke-width adjusted."""
    svg_path = os.path.join(FEATHER_DIR, f"{name}.svg")
    if not os.path.exists(svg_path):
        return None
    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Replace stroke="currentColor" with the target color
        content = content.replace('stroke="currentColor"', f'stroke="{color}"')
        if fill is not None and fill != "none":
            content = content.replace('fill="none"', f'fill="{fill}"')
            content = content.replace('fill="currentColor"', f'fill="{fill}"')
        if stroke_width != 2:
            content = content.replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
        return content
    except Exception as e:
        print(f"Error loading SVG {name}: {e}")
        return None

def get_feather_renderer(name, color="#ffffff", stroke_width=2, fill=None):
    """Returns a cached QSvgRenderer for the specified icon, color, and fill."""
    key = (name, color, stroke_width, fill)
    if key in _RENDERER_CACHE:
        return _RENDERER_CACHE[key]
    
    content = get_feather_svg_content(name, color, stroke_width, fill=fill)
    if not content:
        return None
    renderer = QSvgRenderer(QByteArray(content.encode('utf-8')))
    _RENDERER_CACHE[key] = renderer
    return renderer

def get_feather_icon(name, color="#ffffff", size=16, stroke_width=2, fill=None):
    """
    Renders a Feather SVG icon with a specified color, size, stroke width, and optional fill.
    Returns a crisp QIcon.
    """
    key = (name, color, size, stroke_width, fill)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    renderer = get_feather_renderer(name, color, stroke_width, fill=fill)
    if not renderer or not renderer.isValid():
        return QIcon()

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon

def draw_feather_icon(painter, name, rect, color="#ffffff", stroke_width=2):
    """
    Directly renders a Feather SVG icon into a QPainter target rectangle.
    Useful for custom paintEvent methods on timeline badges and canvas items.
    """
    renderer = get_feather_renderer(name, color, stroke_width)
    if renderer and renderer.isValid():
        target = QRectF(rect)
        renderer.render(painter, target)
        return True
    return False
