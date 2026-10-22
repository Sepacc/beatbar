"""
svg_utils.py - SVG Parsing, Color Extraction, Transformation, and Validation Utilities.
"""

import re
import xml.etree.ElementTree as ET
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer


HEX_COLOR_PATTERN = re.compile(r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b')


def validate_svg(svg_str: str):
    """
    Validates if an SVG string is valid XML and has an <svg> root element.
    Returns (is_valid: bool, error_message: str).
    """
    if not svg_str or not svg_str.strip():
        return False, "SVG content is empty."
    try:
        root = ET.fromstring(svg_str)
        # Check tag (ignoring namespace)
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag.lower() != "svg":
            return False, f"Root element is <{tag}>, expected <svg>."
        return True, ""
    except ET.ParseError as e:
        return False, f"XML Parse Error: {e}"
    except Exception as e:
        return False, str(e)


def normalize_hex(color_str: str) -> str:
    """Normalizes 3-char hex to 6-char lowercase hex."""
    color_str = color_str.strip().lower()
    if len(color_str) == 4 and color_str.startswith("#"):
        return f"#{color_str[1]*2}{color_str[2]*2}{color_str[3]*2}"
    return color_str


def extract_colors(svg_str: str) -> list[str]:
    """
    Extracts all unique hex colors from SVG string, ordered by appearance.
    """
    if not svg_str:
        return []
    matches = HEX_COLOR_PATTERN.findall(svg_str)
    seen = set()
    unique = []
    for m in matches:
        norm = normalize_hex(m)
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def replace_color(svg_str: str, old_color: str, new_color: str) -> str:
    """
    Replaces occurrences of old_color with new_color (case-insensitive).
    """
    if not svg_str or not old_color or not new_color:
        return svg_str

    old_norm = normalize_hex(old_color)
    new_norm = normalize_hex(new_color)

    # Regex replacement for 6-digit or 3-digit hex match
    def _sub_func(match):
        val = normalize_hex(match.group(0))
        if val == old_norm:
            return new_norm
        return match.group(0)

    return HEX_COLOR_PATTERN.sub(_sub_func, svg_str)


def replace_multiple_colors(svg_str: str, color_map: dict[str, str]) -> str:
    """
    Replaces multiple colors simultaneously.
    color_map: { old_hex: new_hex }
    """
    if not svg_str or not color_map:
        return svg_str

    norm_map = {normalize_hex(k): normalize_hex(v) for k, v in color_map.items()}

    def _sub_func(match):
        val = normalize_hex(match.group(0))
        return norm_map.get(val, match.group(0))

    return HEX_COLOR_PATTERN.sub(_sub_func, svg_str)


def get_svg_dimensions(svg_str: str) -> tuple[float, float]:
    """
    Extracts width and height or viewBox width/height from SVG.
    Returns (width, height). Defaults to (100.0, 100.0) if unparseable.
    """
    try:
        root = ET.fromstring(svg_str)
        # Check viewBox first
        vb = root.get("viewBox") or root.get("viewbox")
        if vb:
            parts = [float(p) for p in re.split(r'[\s,]+', vb.strip()) if p]
            if len(parts) >= 4:
                return parts[2], parts[3]
        w = root.get("width", "100")
        h = root.get("height", "100")
        w_val = float(re.sub(r'[^\d.]', '', w)) if re.sub(r'[^\d.]', '', w) else 100.0
        h_val = float(re.sub(r'[^\d.]', '', h)) if re.sub(r'[^\d.]', '', h) else 100.0
        return w_val, h_val
    except Exception:
        return 100.0, 100.0


def mirror_svg_horizontally(svg_str: str) -> str:
    """
    Mirrors the SVG horizontally across its central vertical axis.
    Wraps existing inner content in a transform: translate(W, 0) scale(-1, 1).
    """
    try:
        root = ET.fromstring(svg_str)
        w, h = get_svg_dimensions(svg_str)
        # Create a new group with mirror transform
        children = list(root)
        if not children:
            return svg_str

        # Check if defs exists
        defs_elem = None
        other_children = []
        for child in children:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag.lower() == "defs":
                defs_elem = child
            else:
                other_children.append(child)

        # Clear non-defs children from root
        for c in other_children:
            root.remove(c)

        mirror_group = ET.Element("g", {"transform": f"translate({w}, 0) scale(-1, 1)"})
        for c in other_children:
            mirror_group.append(c)
        root.append(mirror_group)

        return ET.tostring(root, encoding="utf-8").decode("utf-8")
    except Exception as e:
        print("Failed to mirror SVG:", e)
        return svg_str


def format_svg(svg_str: str) -> str:
    """
    Beautifies / indents SVG XML string.
    """
    try:
        root = ET.fromstring(svg_str)
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="utf-8").decode("utf-8")
    except Exception:
        return svg_str


def svg_to_pixmap(svg_str: str, width: int = 120, height: int = 120) -> QPixmap:
    """
    Renders an SVG string to a QPixmap of the specified dimensions.
    """
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    if not svg_str:
        return pixmap

    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
    return pixmap
