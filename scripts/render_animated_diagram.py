#!/usr/bin/env python3
import argparse
import json
import math
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    from svg.path import parse_path
except ImportError:  # pragma: no cover - exercised only when optional dependency is missing.
    parse_path = None

try:
    import icon_browser
except ImportError:  # pragma: no cover - allows import when run as a module path.
    icon_browser = None

# When set to "skip", draw_svg_icon_tile only paints the tile chrome and leaves
# the glyph to the browser engine, which stamps animated frames afterwards.
ICON_GLYPH_MODE = "draw"


DEFAULT_W = 1210
DEFAULT_H = 1138
DEFAULT_FRAMES = 41
DEFAULT_FPS = 20
SCALE = 2
UPDATED = 1782475200000

THEME = {
    "bg": "#000000",
    "white": "#f4f0ee",
    "muted": "#cfc7c5",
    "frame": "#5c6265",
    "core_fill": "#04171e",
    "core_stroke": "#1d8be8",
    "green": "#22c86f",
    "green_fill": "#02160a",
    "purple": "#bd54d3",
    "purple_fill": "#120814",
    "cyan": "#7ee3d6",
    "blue_fill": "#081626",
    "highlight": "#124238",
    "amber": "#f4b64e",
    "pink": "#ff7ab6",
    "archive_fill": "#080711",
    "source_fill": "#02160a",
    "pack_fill": "#04180d",
}

ROOT = Path(__file__).resolve().parents[1]
TABLER_ICON_DIR = ROOT / "assets" / "icons" / "tabler"
ICON_ALIASES = {
    "file": "file-text",
    "document": "file-text",
    "folder": "folder",
    "scan": "search",
    "search": "search",
    "shield": "shield-check",
    "shield-check": "shield-check",
    "db": "database",
    "database": "database",
    "hash": "hash",
    "package": "package",
    "cube": "cube",
    "message": "message",
    "event": "calendar-event",
    "calendar": "calendar-event",
    "calendar-event": "calendar-event",
    "api": "api",
    "clock": "clock",
    "schedule": "clock",
    "brain": "brain",
    "gear": "settings",
    "settings": "settings",
    "eye": "eye",
    "observe": "eye",
    "terminal": "terminal-2",
    "terminal-2": "terminal-2",
    "world": "world",
    "globe": "world",
    "video": "video",
    "photo": "photo",
    "snapshot": "photo",
    "server": "server",
    "lock": "lock-check",
    "lock-check": "lock-check",
    "check": "check",
    "arrow-down-circle": "arrow-down-circle",
    "clipboard": "clipboard-text",
    "clipboard-text": "clipboard-text",
}
SVG_ICON_CACHE = {}

# Single source of truth for icon sizing so every tile across the diagram is
# visually consistent. Supersampling keeps the rasterized strokes crisp.
ICON_TILE = 50
ICON_PAD = 7
ICON_SUPERSAMPLE = 3


def hex_rgba(value, alpha=255):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def c(v):
    return int(round(v * SCALE))


def scaled_box(x, y, w, h):
    return (c(x), c(y), c(x + w), c(y + h))


def font_candidates(hand=False, cjk=False, bold=False):
    if hand:
        return [
            "C:/Windows/Fonts/segoeprb.ttf",
            "C:/Windows/Fonts/segoepr.ttf",
            "C:/Windows/Fonts/comicbd.ttf",
            "C:/Windows/Fonts/comic.ttf",
            "/System/Library/Fonts/Supplemental/Chalkduster.ttf",
            "/System/Library/Fonts/MarkerFelt.ttc",
            "/System/Library/Fonts/Noteworthy.ttc",
            "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
        ]
    if cjk:
        return [
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
    return [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]


def load_font(size, hand=False, cjk=False, bold=False):
    for path in font_candidates(hand=hand, cjk=cjk, bold=bold):
        try:
            return ImageFont.truetype(path, c(size))
        except OSError:
            continue
    return ImageFont.load_default()


def has_cjk(text):
    return any("\u3400" <= ch <= "\u9fff" for ch in text)


def text_size(draw, text, font, spacing=3):
    if not text:
        return 0, 0
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=c(spacing))
    return box[2] - box[0], box[3] - box[1]


def wrap_token(draw, token, font, max_width):
    if not token:
        return [token]
    parts = []
    current = ""
    for char in token:
        candidate = current + char
        if current and text_size(draw, candidate, font)[0] > max_width:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def wrap_line(draw, line, font, max_width):
    if not line:
        return [line]
    tokens = list(line) if has_cjk(line) else line.split(" ")
    separator = "" if has_cjk(line) else " "
    lines = []
    current = ""
    for token in tokens:
        candidate = token if not current else current + separator + token
        if text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if text_size(draw, token, font)[0] <= max_width:
            current = token
        else:
            split_parts = wrap_token(draw, token, font, max_width)
            lines.extend(split_parts[:-1])
            current = split_parts[-1] if split_parts else ""
    if current:
        lines.append(current)
    return lines


def wrap_text(draw, text, font, max_width):
    lines = []
    for raw_line in str(text).splitlines() or [""]:
        lines.extend(wrap_line(draw, raw_line, font, max_width))
    return "\n".join(lines)


EMERGENCY_MIN_TEXT_SIZE = 6


def text_variants(draw, text, font, max_width, wrap):
    raw = str(text)
    if not wrap:
        return [raw]
    wrapped = wrap_text(draw, raw, font, max_width)
    if wrapped == raw:
        return [wrapped]
    return [wrapped, raw]


def fit_text(draw, text, w, h, size, min_size=10, hand=False, bold=False, spacing=3, wrap=True):
    raw_text = str(text)
    has_cjk_text = has_cjk(raw_text)
    max_width = c(w)
    max_height = c(h)
    start_size = int(size)
    emergency_min = min(start_size, int(min_size), EMERGENCY_MIN_TEXT_SIZE)
    for candidate_size in range(start_size, emergency_min - 1, -1):
        candidate_font = load_font(candidate_size, hand=hand and not has_cjk_text, cjk=has_cjk_text, bold=bold)
        for candidate_text in text_variants(draw, raw_text, candidate_font, max_width, wrap):
            tw, th = text_size(draw, candidate_text, candidate_font, spacing=spacing)
            if tw <= max_width and th <= max_height:
                return candidate_text, candidate_size, candidate_font

    fallback_font = load_font(emergency_min, hand=hand and not has_cjk_text, cjk=has_cjk_text, bold=bold)
    fallback_text = wrap_text(draw, raw_text, fallback_font, max_width) if wrap else raw_text
    return fallback_text, emergency_min, fallback_font


class Excal:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.elements = []
        self.count = 0
        self.rng = random.Random(2069769416930414980)

    def base(self, prefix, kind, x, y, w, h, stroke, fill="transparent", stroke_width=2, stroke_style="solid", roundness=None):
        self.count += 1
        element = {
            "id": f"{prefix}-{self.count:04d}",
            "type": kind,
            "x": round(x, 2),
            "y": round(y, 2),
            "width": round(w, 2),
            "height": round(h, 2),
            "angle": 0,
            "strokeColor": stroke,
            "backgroundColor": fill or "transparent",
            "fillStyle": "solid",
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": f"a{self.count:04d}",
            "roundness": roundness,
            "seed": self.rng.randint(1, 2147483646),
            "version": 1,
            "versionNonce": self.rng.randint(1, 2147483646),
            "isDeleted": False,
            "boundElements": None,
            "updated": UPDATED,
            "link": None,
            "locked": False,
        }
        self.elements.append(element)
        return element

    def rect(self, x, y, w, h, stroke, fill="transparent", width=2, style="solid"):
        return self.base("rect", "rectangle", x, y, w, h, stroke, fill, width, style, {"type": 3})

    def ellipse(self, x, y, w, h, stroke, fill="transparent", width=2, style="solid"):
        return self.base("ellipse", "ellipse", x, y, w, h, stroke, fill, width, style, None)

    def diamond(self, x, y, w, h, stroke, fill="transparent", width=2):
        return self.base("diamond", "diamond", x, y, w, h, stroke, fill, width, "solid", {"type": 2})

    def text(self, text, x, y, w, h, size, color, align="left"):
        element = self.base("text", "text", x, y, w, h, color, "transparent", 1, "solid", None)
        element.update(
            {
                "text": text,
                "fontSize": int(round(size)),
                "fontFamily": 5,
                "textAlign": align,
                "verticalAlign": "top",
                "baseline": int(round(size * 1.25)),
                "containerId": None,
                "originalText": text,
                "lineHeight": 1.25,
            }
        )
        return element

    def line(self, points, stroke, width=2, style="solid", arrow=False):
        kind = "arrow" if arrow else "line"
        min_x = min(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_x = max(x for x, _ in points)
        max_y = max(y for _, y in points)
        element = self.base(
            kind,
            kind,
            min_x,
            min_y,
            max_x - min_x,
            max_y - min_y,
            stroke,
            "transparent",
            width,
            style,
            {"type": 2},
        )
        element["points"] = [[round(x - min_x, 2), round(y - min_y, 2)] for x, y in points]
        element["startBinding"] = None
        element["endBinding"] = None
        return element

    def write(self, path):
        data = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {
                "viewBackgroundColor": THEME["bg"],
                "gridSize": 20,
                "currentItemFontFamily": 5,
            },
            "files": {},
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def draw_text(ex, draw, text, x, y, w, h, size, color=None, align="center", hand=False, bold=False, spacing=3, fit=False, min_size=10, wrap=True):
    color = color or THEME["white"]
    if fit:
        text, size, font = fit_text(draw, text, w, h, size, min_size=min_size, hand=hand, bold=bold, spacing=spacing, wrap=wrap)
    else:
        font = load_font(size, hand=hand and not has_cjk(text), cjk=has_cjk(text), bold=bold)
    ex.text(text, x, y, w, h, size, color, align=align)
    tw, th = text_size(draw, text, font, spacing=spacing)
    tx = c(x)
    if align == "center":
        tx = c(x) + (c(w) - tw) / 2
    elif align == "right":
        tx = c(x + w) - tw
    ty = c(y) + (c(h) - th) / 2
    draw.multiline_text((tx, ty), text, font=font, fill=hex_rgba(color), spacing=c(spacing), align=align)


def draw_rect(ex, draw, x, y, w, h, stroke, fill=None, width=2, radius=10, style="solid"):
    ex.rect(x, y, w, h, stroke, fill or "transparent", width, style)
    draw.rounded_rectangle(scaled_box(x, y, w, h), radius=c(radius), outline=hex_rgba(stroke), fill=hex_rgba(fill) if fill else None, width=max(1, c(width)))


def draw_ellipse(ex, draw, x, y, w, h, stroke, fill=None, width=2):
    ex.ellipse(x, y, w, h, stroke, fill or "transparent", width)
    draw.ellipse(scaled_box(x, y, w, h), outline=hex_rgba(stroke), fill=hex_rgba(fill) if fill else None, width=max(1, c(width)))


def draw_line(ex, draw, points, stroke, width=2, style="solid", arrow=False):
    ex.line(points, stroke, width, style, arrow)
    scaled = [(c(x), c(y)) for x, y in points]
    if style == "solid":
        draw.line(scaled, fill=hex_rgba(stroke), width=max(1, c(width)), joint="curve")
    else:
        total = path_len(points)
        dist = 0
        dash = 8 if style == "dashed" else 2
        gap = 8 if style == "dashed" else 7
        while dist < total:
            start = point_at_distance(points, dist)
            end = point_at_distance(points, min(total, dist + dash))
            draw.line([(c(start[0]), c(start[1])), (c(end[0]), c(end[1]))], fill=hex_rgba(stroke), width=max(1, c(width)))
            dist += dash + gap
    if arrow and len(points) >= 2:
        arrow_head(draw, points[-2], points[-1], stroke, width)


def draw_diamond(ex, draw, x, y, w, h, stroke, fill=None, width=2):
    ex.diamond(x, y, w, h, stroke, fill or "transparent", width)
    pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
    scaled = [(c(px), c(py)) for px, py in pts]
    draw.polygon(scaled, outline=hex_rgba(stroke), fill=hex_rgba(fill) if fill else None)
    draw.line(scaled + [scaled[0]], fill=hex_rgba(stroke), width=max(1, c(width)))


def path_len(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def point_at_distance(points, distance):
    left = distance
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        if seg == 0:
            continue
        if left <= seg:
            t = left / seg
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        left -= seg
    return points[-1]


def point_at_fraction(points, t):
    total = path_len(points)
    return point_at_distance(points, (t % 1.0) * total)


def arrow_head(draw, a, b, stroke, width=2):
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    length = 14 + width
    spread = 0.52
    p1 = (b[0] - length * math.cos(angle - spread), b[1] - length * math.sin(angle - spread))
    p2 = (b[0] - length * math.cos(angle + spread), b[1] - length * math.sin(angle + spread))
    draw.line([(c(p1[0]), c(p1[1])), (c(b[0]), c(b[1])), (c(p2[0]), c(p2[1]))], fill=hex_rgba(stroke), width=max(1, c(width)))


def resolve_icon_name(kind):
    return ICON_ALIASES.get(str(kind or "file"), str(kind or "file"))


def load_svg_icon(icon_name, color, size):
    if parse_path is None:
        return None
    cache_key = (icon_name, color, size)
    if cache_key in SVG_ICON_CACHE:
        return SVG_ICON_CACHE[cache_key].copy()

    path = TABLER_ICON_DIR / f"{icon_name}.svg"
    if not path.is_file():
        return None
    try:
        rendered = render_svg_outline(path, color, size)
    except Exception:
        return None
    SVG_ICON_CACHE[cache_key] = rendered
    return rendered.copy()


def strip_namespace(tag):
    return tag.rsplit("}", 1)[-1]


def svg_number(value, default=0.0):
    if value is None:
        return default
    return float(str(value).replace("px", "").strip() or default)


def icon_point(x, y, scale, offset):
    return (offset + x * scale, offset + y * scale)


def draw_svg_polyline(draw, points, color, width):
    if len(points) >= 2:
        draw.line(points, fill=hex_rgba(color, 245), width=width, joint="curve")
    elif points:
        x, y = points[0]
        radius = max(1, width // 2)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=hex_rgba(color, 245))


def sample_svg_segment(segment, scale, offset):
    try:
        length = max(1.0, float(segment.length(error=1e-3)))
    except Exception:
        length = 8.0
    steps = max(3, min(48, int(length * scale / 4)))
    points = []
    for i in range(steps + 1):
        point = segment.point(i / steps)
        points.append(icon_point(point.real, point.imag, scale, offset))
    return points


def draw_svg_path(draw, d, color, width, scale, offset):
    parsed = parse_path(d)
    for segment in parsed:
        points = sample_svg_segment(segment, scale, offset)
        draw_svg_polyline(draw, points, color, width)


def draw_svg_shape(draw, element, color, width, scale, offset):
    tag = strip_namespace(element.tag)
    if tag == "path":
        d = element.attrib.get("d")
        if d:
            draw_svg_path(draw, d, color, width, scale, offset)
    elif tag == "line":
        points = [
            icon_point(svg_number(element.attrib.get("x1")), svg_number(element.attrib.get("y1")), scale, offset),
            icon_point(svg_number(element.attrib.get("x2")), svg_number(element.attrib.get("y2")), scale, offset),
        ]
        draw_svg_polyline(draw, points, color, width)
    elif tag in {"polyline", "polygon"}:
        raw_points = element.attrib.get("points", "").replace(",", " ").split()
        coords = [svg_number(item) for item in raw_points]
        points = [icon_point(coords[i], coords[i + 1], scale, offset) for i in range(0, len(coords) - 1, 2)]
        if tag == "polygon" and points:
            points.append(points[0])
        draw_svg_polyline(draw, points, color, width)
    elif tag == "circle":
        cx = svg_number(element.attrib.get("cx"))
        cy = svg_number(element.attrib.get("cy"))
        r = svg_number(element.attrib.get("r"))
        x, y = icon_point(cx, cy, scale, offset)
        rr = r * scale
        draw.ellipse((x - rr, y - rr, x + rr, y + rr), outline=hex_rgba(color, 245), width=width)
    elif tag == "rect":
        x = svg_number(element.attrib.get("x"))
        y = svg_number(element.attrib.get("y"))
        w = svg_number(element.attrib.get("width"))
        h = svg_number(element.attrib.get("height"))
        rx = svg_number(element.attrib.get("rx"), 0.0)
        x1, y1 = icon_point(x, y, scale, offset)
        x2, y2 = icon_point(x + w, y + h, scale, offset)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=rx * scale, outline=hex_rgba(color, 245), width=width)


def render_svg_outline(path, color, size):
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    view_box = root.attrib.get("viewBox", "0 0 24 24").split()
    vb_w = svg_number(view_box[2], 24.0) if len(view_box) >= 4 else 24.0

    # Render large, then downscale with LANCZOS so the line art is smooth and
    # the stroke weight stays bold instead of thin and broken at small sizes.
    render_size = max(48, size) * ICON_SUPERSAMPLE
    margin = max(2, int(round(render_size * 0.06)))
    scale = (render_size - margin * 2) / vb_w
    width = max(3, int(round(render_size / 24 * 2.0)))
    img = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for element in root.iter():
        draw_svg_shape(draw, element, color, width, scale, margin)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def draw_svg_icon_tile(ex, draw, kind, x, y, color, scale):
    icon_name = resolve_icon_name(kind)
    tile = int(round(ICON_TILE * scale))
    pad = int(round(ICON_PAD * scale))
    radius = int(round(11 * scale))
    stroke_color = THEME["white"]

    # Keep Excalidraw editable with a simple local placeholder while the PNG/GIF
    # use the higher fidelity Tabler SVG asset.
    ex.rect(x + 1 * scale, y + 1 * scale, tile - 2 * scale, tile - 2 * scale, color, "#061015", 1, "solid")

    box = (c(x), c(y), c(x + tile), c(y + tile))
    draw.rounded_rectangle(box, radius=c(radius), outline=hex_rgba(color, 150), fill=hex_rgba("#061015", 170), width=max(1, c(1.25)))

    # In browser mode the glyph is stamped per-frame later; only paint the tile.
    if ICON_GLYPH_MODE == "skip":
        return True

    icon_size = max(28, int(round((tile - pad * 2) * SCALE)))
    icon_img = load_svg_icon(icon_name, stroke_color, icon_size)
    if icon_img is None:
        return False
    ox = c(x) + (c(tile) - icon_size) // 2
    oy = c(y) + (c(tile) - icon_size) // 2
    draw._image.alpha_composite(icon_img, (ox, oy))
    return True


def draw_primitive_icon(ex, draw, kind, x, y, color=None, scale=1.0):
    color = color or THEME["cyan"]
    if kind == "folder":
        draw_line(ex, draw, [(x, y + 9 * scale), (x, y + 35 * scale), (x + 48 * scale, y + 35 * scale), (x + 48 * scale, y + 7 * scale), (x + 26 * scale, y + 7 * scale), (x + 21 * scale, y), (x + 2 * scale, y), (x + 2 * scale, y + 9 * scale)], THEME["white"], 2)
        draw_rect(ex, draw, x + 5 * scale, y + 15 * scale, 38 * scale, 15 * scale, color, color, 1, 3)
    elif kind == "file":
        draw_rect(ex, draw, x + 7 * scale, y, 33 * scale, 36 * scale, THEME["white"], color, 2, 4)
        draw_line(ex, draw, [(x + 15 * scale, y + 14 * scale), (x + 31 * scale, y + 14 * scale)], THEME["bg"], 2)
        draw_line(ex, draw, [(x + 15 * scale, y + 24 * scale), (x + 31 * scale, y + 24 * scale)], THEME["bg"], 2)
    elif kind == "scan":
        draw_ellipse(ex, draw, x + 14, y + 11, 38, 38, THEME["white"], None, 4)
        draw_line(ex, draw, [(x + 47, y + 45), (x + 64, y + 62)], THEME["white"], 5)
    elif kind == "shield":
        pts = [(x + 38, y + 7), (x + 63, y + 17), (x + 58, y + 47), (x + 38, y + 65), (x + 18, y + 47), (x + 13, y + 17)]
        draw.polygon([(c(px), c(py)) for px, py in pts], fill=hex_rgba(THEME["green"], 180), outline=hex_rgba(THEME["white"]))
        draw_line(ex, draw, pts + [pts[0]], THEME["white"], 3)
        draw_line(ex, draw, [(x + 27, y + 37), (x + 36, y + 48), (x + 51, y + 27)], THEME["white"], 4)
    elif kind == "db":
        draw_ellipse(ex, draw, x + 15, y + 9, 50, 17, THEME["white"], color, 2)
        draw_rect(ex, draw, x + 15, y + 17, 50, 37, THEME["white"], color, 2, 0)
        draw_ellipse(ex, draw, x + 15, y + 45, 50, 17, THEME["white"], color, 2)
    elif kind == "hash":
        draw_line(ex, draw, [(x + 27, y + 14), (x + 22, y + 58)], THEME["amber"], 4)
        draw_line(ex, draw, [(x + 50, y + 14), (x + 45, y + 58)], THEME["amber"], 4)
        draw_line(ex, draw, [(x + 15, y + 29), (x + 62, y + 29)], THEME["white"], 4)
        draw_line(ex, draw, [(x + 13, y + 45), (x + 60, y + 45)], THEME["white"], 4)
    elif kind == "package":
        draw_line(ex, draw, [(x + 38, y + 8), (x + 66, y + 23), (x + 66, y + 52), (x + 38, y + 68), (x + 10, y + 52), (x + 10, y + 23), (x + 38, y + 8)], THEME["white"], 3)
        draw_line(ex, draw, [(x + 10, y + 23), (x + 38, y + 38), (x + 66, y + 23)], THEME["amber"], 3)
        draw_line(ex, draw, [(x + 38, y + 38), (x + 38, y + 68)], THEME["amber"], 3)
    else:
        draw_ellipse(ex, draw, x + 18, y + 18, 36, 36, color, color, 2)


def icon(ex, draw, kind, x, y, color=None, scale=1.0):
    color = color or THEME["cyan"]
    if draw_svg_icon_tile(ex, draw, kind, x, y, color, scale):
        return
    draw_primitive_icon(ex, draw, kind, x, y, color, scale)


def draw_signature(ex, draw, text, x, y):
    ex.text(text, x, y, 120, 36, 23, THEME["white"], align="left")
    font = load_font(24, cjk=True, bold=True)
    sx, sy = c(x), c(y)
    for dx, dy, color, alpha in [(-1, 1, THEME["purple"], 165), (1, -1, THEME["cyan"], 135), (0, 0, THEME["white"], 245)]:
        draw.text((sx + c(dx), sy + c(dy)), text, font=font, fill=hex_rgba(color, alpha))
    draw.line([(sx + 6, sy + 56), (sx + 28, sy + 61), (sx + 62, sy + 58), (sx + 86, sy + 63)], fill=hex_rgba(THEME["purple"], 170), width=3)
    draw.line([(sx + 8, sy + 54), (sx + 84, sy + 60)], fill=hex_rgba(THEME["white"], 125), width=1)


def brand(ex, draw, signature):
    dots = [
        (0, 0, THEME["cyan"]),
        (10, 8, THEME["white"]),
        (0, 16, THEME["purple"]),
        (10, 24, THEME["white"]),
        (20, 0, THEME["white"]),
        (30, 8, THEME["pink"]),
        (20, 16, THEME["white"]),
        (30, 24, THEME["green"]),
    ]
    for dx, dy, color in dots:
        draw_ellipse(ex, draw, 955 + dx, 143 + dy, 5, 5, color, color, 1)
    draw_signature(ex, draw, signature, 998, 135)


def small_input(ex, draw, x, y, item):
    kind = item.get("icon", "file")
    color = item.get("color", THEME["cyan"])
    icon(ex, draw, kind, x + 9, y, color, 1.0)
    draw_text(ex, draw, item.get("label", ""), x - 5, y + 54, 78, 22, 12, THEME["white"], "center", fit=True, min_size=8)


def core_card(ex, draw, x, y, card):
    draw_rect(ex, draw, x, y, 260, 90, THEME["core_stroke"], THEME["blue_fill"], 2, 9)
    icon(ex, draw, card.get("icon", "file"), x + 14, y + 13, card.get("color", THEME["cyan"]))
    draw_text(ex, draw, card.get("title", ""), x + 110, y + 11, 100, 28, 20, THEME["white"], "center", hand=True, bold=True, fit=True, min_size=15)
    draw_text(ex, draw, card.get("body", ""), x + 92, y + 42, 150, 38, 14, THEME["white"], "center", spacing=3, fit=True, min_size=11)


def mini_card(ex, draw, x, y, w, h, card, stroke, fill):
    draw_rect(ex, draw, x, y, w, h, stroke, fill, 2, 8)
    icon(ex, draw, card.get("icon", "file"), x + 10, y + 10, card.get("color", THEME["cyan"]))
    draw_text(ex, draw, card.get("title", ""), x + 78, y + 12, 115, 24, 17, THEME["white"], "left", bold=True, fit=True, min_size=12)
    draw_text(ex, draw, card.get("body", ""), x + 78, y + 38, w - 92, h - 43, 12, THEME["white"], "left", spacing=3, fit=True, min_size=10)


def pack_row(ex, draw, x, y, card):
    draw_rect(ex, draw, x, y, 228, 84, THEME["green"], "#04200f", 2, 8)
    icon(ex, draw, card.get("icon", "file"), x + 12, y + 10, card.get("color", THEME["cyan"]))
    draw_text(ex, draw, card.get("title", ""), x + 86, y + 12, 120, 25, 17, THEME["white"], "center", bold=True, fit=True, min_size=12)
    draw_text(ex, draw, card.get("body", ""), x + 80, y + 42, 135, 30, 12, THEME["white"], "center", spacing=3, fit=True, min_size=10)


def render_static(spec):
    width = spec.get("canvas", {}).get("width", DEFAULT_W)
    height = spec.get("canvas", {}).get("height", DEFAULT_H)
    ex = Excal(width, height)
    img = Image.new("RGBA", (width * SCALE, height * SCALE), hex_rgba(THEME["bg"]))
    draw = ImageDraw.Draw(img)

    title = spec.get("title", {})
    draw_line(ex, draw, [(29, 31), (29, 78)], THEME["purple"], 11)
    draw_text(ex, draw, title.get("prefix", "The internals of"), 45, 14, 535, 66, 47, THEME["white"], "left", hand=True, bold=True)
    draw_rect(ex, draw, 600, 27, 392, 72, THEME["highlight"], THEME["highlight"], 2, 16)
    draw_text(ex, draw, title.get("highlight", "Memory Pack"), 622, 19, 350, 76, 44, THEME["green"], "center", hand=True, bold=True)
    draw_text(ex, draw, title.get("subtitle", ""), 104, 90, 420, 25, 15, THEME["muted"], "left")

    draw_rect(ex, draw, 18, 117, 1174, 994, THEME["frame"], None, 2, 29)
    brand(ex, draw, spec.get("signature", "@archscribe"))

    inputs = spec.get("inputs", [])
    while len(inputs) < 4:
        inputs.append({"label": "", "icon": "file"})
    draw_rect(ex, draw, 389, 130, 430, 128, THEME["green"], None, 2, 8)
    draw_text(ex, draw, spec.get("input_title", "Source / Input"), 498, 137, 210, 28, 22, THEME["white"], "center", hand=True, bold=True)
    for x, item in zip([423, 532, 640, 748], inputs[:4]):
        small_input(ex, draw, x, 174, item)
    draw_line(ex, draw, [(605, 258), (605, 316)], THEME["white"], 2, "solid", True)

    core = spec.get("core", {})
    cards = core.get("cards", [])
    while len(cards) < 3:
        cards.append({"title": "", "body": "", "icon": "file"})
    draw_rect(ex, draw, 53, 317, 1104, 320, THEME["core_stroke"], THEME["core_fill"], 2, 20)
    draw_text(ex, draw, core.get("title", "Archive Core"), 462, 327, 210, 31, 22, THEME["white"], "center", hand=True, bold=True)
    draw_text(ex, draw, core.get("subtitle", "(local read-only pipeline)"), 635, 336, 220, 23, 13, THEME["white"], "center")
    core_card(ex, draw, 95, 366, cards[0])
    core_card(ex, draw, 472, 366, cards[1])
    core_card(ex, draw, 850, 366, cards[2])
    draw_line(ex, draw, [(355, 411), (472, 411)], THEME["white"], 2, "solid", True)
    draw_line(ex, draw, [(732, 411), (850, 411)], THEME["white"], 2, "solid", True)
    draw_line(ex, draw, [(982, 456), (982, 481), (768, 481), (768, 508)], THEME["white"], 2, "solid", True)

    decision = spec.get("decision", {"title": "Ready?", "body": "safe, traced\nusable"})
    draw_diamond(ex, draw, 706, 508, 120, 120, THEME["green"], "#052515", 2)
    draw_text(ex, draw, decision.get("title", "Ready?"), 728, 541, 78, 26, 20, THEME["white"], "center", fit=True, min_size=14)
    draw_text(ex, draw, decision.get("body", ""), 728, 569, 78, 34, 14, THEME["white"], "center", fit=True, min_size=10)
    draw_rect(ex, draw, 1022, 527, 100, 94, THEME["core_stroke"], THEME["blue_fill"], 2, 9)
    icon(ex, draw, spec.get("output", {}).get("icon", "file"), 1035, 537, THEME["cyan"])
    draw_text(ex, draw, spec.get("output", {}).get("label", "Report"), 1038, 588, 70, 24, 18, THEME["white"], "center", bold=True, fit=True, min_size=12)
    draw_line(ex, draw, [(826, 568), (1022, 568)], THEME["white"], 2, "solid", True)
    draw_text(ex, draw, "Yes", 900, 543, 45, 25, 15, THEME["white"], "center")
    draw_line(ex, draw, [(707, 568), (510, 568), (222, 568), (222, 456)], THEME["muted"], 2, "dashed", True)
    draw_text(ex, draw, spec.get("loop_label", "Loop until checked and updated"), 330, 504, 540, 25, 14, THEME["white"], "center")
    draw_text(ex, draw, spec.get("retry_label", "No / missing source or conflict"), 475, 580, 250, 24, 14, THEME["white"], "center")

    draw_line(ex, draw, [(156, 637), (156, 736)], THEME["white"], 2, "solid", True)
    draw_line(ex, draw, [(205, 736), (205, 637)], THEME["white"], 2, "solid", True)
    draw_text(ex, draw, "Read", 109, 677, 45, 22, 16, THEME["white"], "center")
    draw_text(ex, draw, "Context", 211, 676, 70, 22, 16, THEME["white"], "center")

    left = spec.get("left_panel", {})
    draw_rect(ex, draw, 39, 735, 281, 344, THEME["green"], THEME["source_fill"], 2, 14)
    draw_text(ex, draw, left.get("title", "Memory Sources"), 58, 752, 180, 30, 22, THEME["white"], "left", hand=True, bold=True)
    draw_text(ex, draw, left.get("badge", "read only"), 244, 779, 62, 18, 11, THEME["green"], "center")
    for (y, h), card in zip([(797, 78), (892, 78), (987, 62)], left.get("cards", [])[:3]):
        mini_card(ex, draw, 51, y, 258, h, card, THEME["green"], "#04200f")

    center = spec.get("center_panel", {})
    draw_rect(ex, draw, 333, 734, 522, 346, THEME["purple"], THEME["archive_fill"], 2, 14)
    draw_text(ex, draw, center.get("title", "Archive Layers"), 512, 756, 180, 34, 23, THEME["white"], "center", hand=True, bold=True)
    draw_text(ex, draw, center.get("subtitle", "(local, readable, traceable storage)"), 444, 790, 300, 24, 14, THEME["white"], "center")
    layer_cards = center.get("cards", [])[:4]
    while len(layer_cards) < 4:
        layer_cards.append({"title": "", "body": "", "icon": "file"})
    for x, card in zip([346, 486, 626, 766], layer_cards):
        draw_rect(ex, draw, x, 827, 112, 142, THEME["purple"], "#17091d", 2, 8)
        icon(ex, draw, card.get("icon", "file"), x + 18, 840, card.get("color", THEME["cyan"]))
        draw_text(ex, draw, card.get("title", ""), x + 10, 910, 92, 25, 18, THEME["white"], "center", bold=True, fit=True, min_size=12)
        draw_text(ex, draw, card.get("body", ""), x + 8, 936, 96, 28, 11, THEME["white"], "center", spacing=2, fit=True, min_size=8)
    draw_line(ex, draw, [(458, 890), (486, 890)], THEME["white"], 2, "solid", True)
    draw_line(ex, draw, [(598, 890), (626, 890)], THEME["white"], 2, "solid", True)
    draw_line(ex, draw, [(738, 890), (766, 890)], THEME["white"], 2, "solid", True)
    draw_rect(ex, draw, 491, 1010, 220, 50, THEME["purple"], THEME["archive_fill"], 2, 8)
    draw_text(ex, draw, center.get("footer", "Redact + Dedup"), 528, 1017, 165, 33, 20, THEME["white"], "center", hand=True, bold=True, fit=True, min_size=14)
    draw_line(ex, draw, [(603, 969), (603, 1010)], THEME["muted"], 2, "dashed", True)

    right = spec.get("right_panel", {})
    draw_line(ex, draw, [(855, 890), (904, 890)], THEME["white"], 2, "solid", True)
    draw_text(ex, draw, right.get("incoming_label", "Compile"), 850, 868, 65, 20, 12, THEME["white"], "center")
    draw_rect(ex, draw, 904, 735, 258, 344, THEME["green"], THEME["pack_fill"], 2, 14)
    draw_text(ex, draw, right.get("title", "Memory Pack"), 948, 750, 170, 34, 22, THEME["white"], "center", hand=True, bold=True)
    for y, card in zip([786, 884, 982], right.get("cards", [])[:3]):
        pack_row(ex, draw, 918, y, card)
    draw_line(ex, draw, [(1036, 735), (1036, 691), (766, 691), (766, 628)], THEME["white"], 2, "solid", True)
    draw_text(ex, draw, right.get("return_label", "Reusable"), 867, 669, 75, 23, 16, THEME["white"], "center")

    for x, y, color in [(375, 292, THEME["cyan"]), (704, 293, THEME["green"]), (1048, 292, THEME["purple"]), (315, 707, THEME["green"]), (868, 707, THEME["purple"])]:
        draw_line(ex, draw, [(x - 8, y), (x + 8, y)], color, 2)
        draw_line(ex, draw, [(x, y - 8), (x, y + 8)], color, 2)

    return ex, img.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")


def premium_finish(base):
    width, height = base.size
    img = base.convert("RGBA")
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for rect, color, line_width in [
        ((18, 117, 1192, 1111), THEME["frame"], 3),
        ((53, 317, 1157, 637), THEME["core_stroke"], 3),
        ((333, 734, 855, 1080), THEME["purple"], 3),
        ((39, 735, 320, 1079), THEME["green"], 3),
        ((904, 735, 1162, 1079), THEME["green"], 3),
        ((600, 27, 992, 99), THEME["green"], 2),
    ]:
        g.rounded_rectangle(rect, radius=18, outline=hex_rgba(color, 70), width=line_width)
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4)))

    grain = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grain)
    rng = random.Random(2069769416930414980)
    for _ in range(2600):
        x = rng.randrange(width)
        y = rng.randrange(height)
        tone = rng.randrange(120, 220)
        gd.point((x, y), fill=(tone, tone, tone, rng.randrange(4, 14)))
    img.alpha_composite(grain)

    mask_small = Image.new("L", (180, 170), 0)
    pixels = []
    cx, cy = 90, 78
    max_dist = math.dist((0, 0), (cx, cy))
    for y in range(170):
        for x in range(180):
            dist = math.dist((x, y), (cx, cy)) / max_dist
            pixels.append(int(max(0, min(115, (dist - 0.38) * 150))))
    mask_small.putdata(pixels)
    mask = mask_small.resize((width, height), Image.Resampling.BICUBIC)
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vignette.putalpha(mask)
    img.alpha_composite(vignette)
    return img.convert("RGB")


def draw_glow_dot(draw, x, y, color, strength=1.0):
    for radius, alpha in [(9, 24), (5, 62), (3, 180)]:
        a = int(alpha * strength)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=hex_rgba(color, a))
    draw.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=hex_rgba(THEME["white"], 230))


def pulse_rect(draw, rect, color, phase, radius=10):
    x1, y1, x2, y2 = rect
    alpha = int(36 + 42 * (0.5 + 0.5 * math.sin(phase)))
    for grow, width in [(0, 2), (4, 1)]:
        draw.rounded_rectangle((x1 - grow, y1 - grow, x2 + grow, y2 + grow), radius=radius + grow, outline=hex_rgba(color, max(18, alpha - grow * 7)), width=width)


def icon_center(kind, x, y, scale=1.0):
    tile = ICON_TILE * scale
    return x + tile / 2, y + tile / 2


def collect_icon_instances(spec):
    spec = spec or {}
    instances = []

    inputs = spec.get("inputs", [])
    for ordinal, (x, item) in enumerate(zip([423, 532, 640, 748], inputs[:4])):
        instances.append(
            {
                "kind": item.get("icon", "file"),
                "x": x + 9,
                "y": 174,
                "scale": 1.0,
                "color": item.get("color", THEME["cyan"]),
                "group": "input",
                "ordinal": ordinal,
            }
        )

    core_cards = spec.get("core", {}).get("cards", [])
    for ordinal, (x, card) in enumerate(zip([95, 472, 850], core_cards[:3]), start=4):
        instances.append(
            {
                "kind": card.get("icon", "file"),
                "x": x + 14,
                "y": 379,
                "scale": 1.0,
                "color": card.get("color", THEME["cyan"]),
                "group": "core",
                "ordinal": ordinal,
            }
        )

    output = spec.get("output", {})
    instances.append(
        {
            "kind": output.get("icon", "file"),
            "x": 1035,
            "y": 537,
            "scale": 1.0,
            "color": output.get("color", THEME["cyan"]),
            "group": "output",
            "ordinal": 7,
        }
    )

    left_cards = spec.get("left_panel", {}).get("cards", [])
    for ordinal, ((y, _h), card) in enumerate(zip([(797, 78), (892, 78), (987, 62)], left_cards[:3]), start=8):
        instances.append(
            {
                "kind": card.get("icon", "file"),
                "x": 61,
                "y": y + 10,
                "scale": 1.0,
                "color": card.get("color", THEME["cyan"]),
                "group": "panel",
                "ordinal": ordinal,
            }
        )

    center_cards = spec.get("center_panel", {}).get("cards", [])
    for ordinal, (x, card) in enumerate(zip([346, 486, 626, 766], center_cards[:4]), start=11):
        instances.append(
            {
                "kind": card.get("icon", "file"),
                "x": x + 18,
                "y": 840,
                "scale": 1.0,
                "color": card.get("color", THEME["cyan"]),
                "group": "layer",
                "ordinal": ordinal,
            }
        )

    right_cards = spec.get("right_panel", {}).get("cards", [])
    for ordinal, (y, card) in enumerate(zip([786, 884, 982], right_cards[:3]), start=15):
        instances.append(
            {
                "kind": card.get("icon", "file"),
                "x": 930,
                "y": y + 10,
                "scale": 1.0,
                "color": card.get("color", THEME["cyan"]),
                "group": "pack",
                "ordinal": ordinal,
            }
        )

    return instances


def draw_icon_halo(draw, cx, cy, color, phase, active=False):
    if not active:
        return
    pulse = 0.5 + 0.5 * math.sin(phase)
    base_alpha = 48 + int(32 * pulse)
    for radius, alpha_scale, width in [(24, 0.72, 1), (30, 0.28, 1)]:
        alpha = min(150, int(base_alpha * alpha_scale))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=hex_rgba(color, alpha), width=width)


def draw_orbit_dot(draw, cx, cy, color, progress, ordinal, active=False):
    if not active:
        return
    speed = 1.35
    radius = 24
    angle = math.tau * ((progress * speed + ordinal * 0.071) % 1.0)
    x = cx + radius * math.cos(angle)
    y = cy + radius * math.sin(angle)
    draw.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5), fill=hex_rgba(THEME["white"], 220))
    draw.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=hex_rgba(color, 230))


def draw_icon_specific_motion(draw, kind, x, y, scale, color, progress, phase, active=False):
    if not active:
        return
    if kind == "scan":
        cx, cy = icon_center(kind, x, y, scale)
        radius = 22 * scale
        start = int((progress * 360 * 1.4 + 50) % 360)
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=start, end=start + 95, fill=hex_rgba(THEME["cyan"], 150), width=2)
        sweep = math.radians(start + 115)
        draw.line((cx, cy, cx + radius * math.cos(sweep), cy + radius * math.sin(sweep)), fill=hex_rgba(THEME["white"], 95), width=1)
    elif kind == "shield":
        shine = (math.sin(phase * 1.3) + 1) / 2
        alpha = 65 + int(90 * shine)
        draw.line((x + 17 * scale, y + 15 * scale, x + 43 * scale, y + 41 * scale), fill=hex_rgba(THEME["white"], alpha), width=1)
    elif kind == "db":
        offset = 2.5 * math.sin(phase)
        for yy, alpha in [(y + 15 * scale + offset, 88), (y + 27 * scale - offset, 70), (y + 39 * scale + offset, 88)]:
            draw.arc((x + 10 * scale, yy - 6 * scale, x + 44 * scale, yy + 6 * scale), 0, 180, fill=hex_rgba(THEME["white"], alpha), width=1)
    elif kind == "package":
        pulse = 0.5 + 0.5 * math.sin(phase)
        points = [(x + 27 * scale, y + 7 * scale), (x + 45 * scale, y + 18 * scale), (x + 45 * scale, y + 38 * scale), (x + 27 * scale, y + 48 * scale), (x + 9 * scale, y + 38 * scale), (x + 9 * scale, y + 18 * scale)]
        target = points[int((progress * len(points) + 0.5) % len(points))]
        draw_glow_dot(draw, target[0], target[1], THEME["amber"], 0.28 + 0.12 * pulse)
    elif kind == "folder":
        tab_alpha = 80 + int(80 * (0.5 + 0.5 * math.sin(phase)))
        draw.line((x + 8 * scale, y + 18 * scale, x + 40 * scale, y + 18 * scale), fill=hex_rgba(color, tab_alpha), width=1)
    elif kind == "file":
        cursor_y = y + 14 * scale + 14 * scale * ((progress * 1.3) % 1.0)
        draw.line((x + 13 * scale, cursor_y, x + 34 * scale, cursor_y), fill=hex_rgba(THEME["white"], 120), width=1)
    elif kind == "hash":
        shift = 2 * math.sin(phase)
        draw.line((x + 12 * scale, y + 22 * scale + shift, x + 42 * scale, y + 22 * scale + shift), fill=hex_rgba(THEME["amber"], 140), width=1)
        draw.line((x + 12 * scale, y + 34 * scale - shift, x + 42 * scale, y + 34 * scale - shift), fill=hex_rgba(THEME["white"], 110), width=1)


def draw_icon_motion_layer(draw, spec, progress, idx):
    icons = collect_icon_instances(spec)
    if not icons:
        return
    active = (idx // 4) % len(icons)
    for instance in icons:
        kind = instance["kind"]
        x = instance["x"]
        y = instance["y"]
        scale = instance.get("scale", 1.0)
        color = instance.get("color", THEME["cyan"])
        ordinal = instance.get("ordinal", 0)
        cx, cy = icon_center(kind, x, y, scale)
        phase = math.tau * (progress * 2.0 + ordinal * 0.083)
        is_active = ordinal == active
        draw_icon_halo(draw, cx, cy, color, phase, is_active)
        draw_orbit_dot(draw, cx, cy, color, progress, ordinal, is_active)
        draw_icon_specific_motion(draw, kind, x, y, scale, color, progress, phase, is_active)


def animate_frame(base, idx, total, spec=None, icon_motion=True):
    frame = base.convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    progress = idx / total
    paths = [
        ([(605, 239), (605, 316)], THEME["green"], 0.00),
        ([(355, 411), (472, 411)], THEME["cyan"], 0.10),
        ([(732, 411), (850, 411)], THEME["cyan"], 0.24),
        ([(982, 456), (982, 481), (768, 481), (768, 508)], THEME["core_stroke"], 0.38),
        ([(826, 568), (1022, 568)], THEME["green"], 0.54),
        ([(707, 568), (510, 568), (222, 568), (222, 456)], THEME["purple"], 0.66),
        ([(156, 637), (156, 736)], THEME["green"], 0.18),
        ([(205, 736), (205, 637)], THEME["green"], 0.58),
        ([(458, 890), (486, 890), (598, 890), (626, 890), (738, 890), (766, 890)], THEME["purple"], 0.32),
        ([(855, 890), (904, 890)], THEME["white"], 0.46),
        ([(1036, 735), (1036, 691), (766, 691), (766, 628)], THEME["amber"], 0.72),
    ]
    for points, color, offset in paths:
        for trail, strength in [(0, 0.78), (-0.045, 0.30)]:
            x, y = point_at_fraction(points, progress + offset + trail)
            draw_glow_dot(draw, x, y, color, strength)
    if icon_motion:
        draw_icon_motion_layer(draw, spec, progress, idx)
    pulse_targets = [
        ((389, 138, 819, 239), THEME["green"]),
        ((95, 366, 355, 456), THEME["core_stroke"]),
        ((472, 366, 732, 456), THEME["green"]),
        ((850, 366, 1110, 456), THEME["core_stroke"]),
        ((706, 508, 826, 628), THEME["green"]),
        ((333, 734, 855, 1080), THEME["purple"]),
        ((904, 735, 1162, 1079), THEME["green"]),
    ]
    active = (idx // 6) % len(pulse_targets)
    for pos, (rect, color) in enumerate(pulse_targets):
        if pos == active:
            pulse_rect(draw, rect, color, progress * math.tau * 2, 12)
    frame.alpha_composite(overlay)
    return frame.convert("RGB")


ICON_GLYPH_FRAMES = 24


def icon_requests(spec):
    seen = []
    for inst in collect_icon_instances(spec):
        key = (resolve_icon_name(inst["kind"]), inst.get("color", THEME["cyan"]))
        if key not in seen:
            seen.append(key)
    return seen


def stamp_glyphs(base_rgb, spec, glyph_frames, gif_t):
    if not glyph_frames:
        return base_rgb
    total = ICON_GLYPH_FRAMES
    pick = int(round(gif_t * total)) % total
    canvas = base_rgb.convert("RGBA")
    for inst in collect_icon_instances(spec):
        key = (resolve_icon_name(inst["kind"]), inst.get("color", THEME["cyan"]))
        seq = glyph_frames.get(key)
        if not seq:
            continue
        scale = inst.get("scale", 1.0)
        glyph_side = int(round((ICON_TILE - 2 * ICON_PAD) * scale))
        if glyph_side <= 0:
            continue
        glyph = seq[pick % len(seq)]
        if glyph.size != (glyph_side, glyph_side):
            glyph = glyph.resize((glyph_side, glyph_side), Image.Resampling.LANCZOS)
        ox = int(round(inst["x"] + ICON_PAD * scale))
        oy = int(round(inst["y"] + ICON_PAD * scale))
        canvas.alpha_composite(glyph, (ox, oy))
    return canvas.convert("RGB")


def render_browser_glyphs(spec):
    if icon_browser is None or not icon_browser.is_available():
        return {}
    glyph_px = int(round((ICON_TILE - 2 * ICON_PAD)))
    requests = icon_requests(spec)
    if not requests:
        return {}
    return icon_browser.render_glyph_frames(
        requests,
        glyph_px=max(28, glyph_px),
        frames=ICON_GLYPH_FRAMES,
        base_color=THEME["white"],
        stroke=2.0,
    )


def write_outputs(spec, outdir, basename, icon_engine="pillow"):
    global ICON_GLYPH_MODE
    outdir.mkdir(parents=True, exist_ok=True)
    canvas_frames = spec.get("canvas", {}).get("frames", DEFAULT_FRAMES)

    glyph_frames = {}
    use_browser = False
    if icon_engine in ("browser", "auto"):
        glyph_frames = render_browser_glyphs(spec)
        use_browser = bool(glyph_frames)
        if icon_engine == "browser" and not use_browser:
            print("warning: browser icon engine unavailable, falling back to pillow", file=sys.stderr)

    ICON_GLYPH_MODE = "skip" if use_browser else "draw"
    try:
        ex, static = render_static(spec)
        final = premium_finish(static)
    finally:
        ICON_GLYPH_MODE = "draw"

    png_path = outdir / f"{basename}.png"
    gif_path = outdir / f"{basename}.gif"
    excalidraw_path = outdir / f"{basename}.excalidraw"

    if use_browser:
        png_img = stamp_glyphs(final, spec, glyph_frames, 0.0)
        png_img.save(png_path, "PNG")
        frames = []
        for i in range(canvas_frames):
            base_i = stamp_glyphs(final, spec, glyph_frames, i / canvas_frames)
            frames.append(animate_frame(base_i, i, canvas_frames, spec, icon_motion=False))
    else:
        final.save(png_path, "PNG")
        frames = [animate_frame(final, i, canvas_frames, spec) for i in range(canvas_frames)]

    duration = int(1000 / spec.get("canvas", {}).get("fps", DEFAULT_FPS))
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=False)
    ex.write(excalidraw_path)
    return {
        "png": str(png_path),
        "gif": str(gif_path),
        "excalidraw": str(excalidraw_path),
        "elements": len(ex.elements),
        "icon_engine": "browser" if use_browser else "pillow",
    }


def frame_diff_report(gif_path):
    with Image.open(gif_path) as im:
        picks = [0, max(1, im.n_frames // 4), max(2, im.n_frames // 2), max(3, 3 * im.n_frames // 4), im.n_frames - 1]
        frames = []
        for idx in picks:
            im.seek(idx)
            frames.append(im.convert("RGB"))
        frame_count = im.n_frames
    diffs = []
    for left, right, a, b in zip(frames, frames[1:], picks, picks[1:]):
        diff = ImageChops.difference(left, right)
        bbox = diff.getbbox()
        changed = 0
        if bbox:
            cropped = diff.crop(bbox)
            data = cropped.get_flattened_data() if hasattr(cropped, "get_flattened_data") else cropped.getdata()
            changed = sum(1 for px in data if px != (0, 0, 0))
        diffs.append({"from": a, "to": b, "changed_pixels": changed})
    return {"frames": frame_count, "diffs": diffs}


def check_outputs(result, spec):
    canvas = spec.get("canvas", {})
    expected_width = canvas.get("width", DEFAULT_W)
    expected_height = canvas.get("height", DEFAULT_H)
    expected_frames = canvas.get("frames", DEFAULT_FRAMES)
    expected_fps = canvas.get("fps", DEFAULT_FPS)

    checks = []

    gif_path = Path(result["gif"])
    with Image.open(gif_path) as gif:
        gif_width = gif.width
        gif_height = gif.height
        gif_frames = gif.n_frames
        duration_ms = gif.info.get("duration")
    actual_fps = round(1000 / duration_ms, 3) if duration_ms else None
    checks.extend(
        [
            {"name": "gif_exists", "ok": gif_path.is_file()},
            {"name": "gif_width", "ok": gif_width == expected_width, "expected": expected_width, "actual": gif_width},
            {"name": "gif_height", "ok": gif_height == expected_height, "expected": expected_height, "actual": gif_height},
            {"name": "gif_frames", "ok": gif_frames == expected_frames, "expected": expected_frames, "actual": gif_frames},
            {"name": "gif_fps", "ok": duration_ms == int(1000 / expected_fps), "expected": expected_fps, "actual": actual_fps},
        ]
    )

    diff_report = frame_diff_report(gif_path)
    checks.append(
        {
            "name": "gif_has_motion",
            "ok": any(item["changed_pixels"] > 0 for item in diff_report["diffs"]),
            "diffs": diff_report["diffs"],
        }
    )

    excalidraw_path = Path(result["excalidraw"])
    excalidraw = json.loads(excalidraw_path.read_text(encoding="utf-8"))
    elements = excalidraw.get("elements", [])
    ids = [element.get("id") for element in elements]
    text_elements = [element for element in elements if element.get("type") == "text"]
    checks.extend(
        [
            {"name": "excalidraw_exists", "ok": excalidraw_path.is_file()},
            {"name": "excalidraw_unique_ids", "ok": len(ids) == len(set(ids))},
            {"name": "excalidraw_text_font_family", "ok": all(element.get("fontFamily") == 5 for element in text_elements)},
            {"name": "excalidraw_files_empty", "ok": excalidraw.get("files") == {}},
        ]
    )

    png_path = Path(result["png"])
    with Image.open(png_path) as png:
        png_width = png.width
        png_height = png.height
    checks.extend(
        [
            {"name": "png_exists", "ok": png_path.is_file()},
            {"name": "png_width", "ok": png_width == expected_width, "expected": expected_width, "actual": png_width},
            {"name": "png_height", "ok": png_height == expected_height, "expected": expected_height, "actual": png_height},
        ]
    )

    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description="Render a premium hand-drawn animated diagram from a JSON spec.")
    parser.add_argument("--spec", required=True, help="Path to spec JSON.")
    parser.add_argument("--outdir", required=True, help="Output directory.")
    parser.add_argument("--basename", default="animated-diagram", help="Output basename.")
    parser.add_argument("--verify", action="store_true", help="Print frame-diff verification after rendering.")
    parser.add_argument("--check", action="store_true", help="Validate PNG, GIF, and Excalidraw output contracts; exits nonzero on failure.")
    parser.add_argument(
        "--icon-engine",
        choices=["auto", "browser", "pillow"],
        default="auto",
        help="Icon renderer: 'browser' uses headless Chromium for crisp animated icons, 'pillow' stays dependency-light, 'auto' prefers browser when available.",
    )
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = write_outputs(spec, Path(args.outdir), args.basename, icon_engine=args.icon_engine)
    if args.verify:
        result["verification"] = frame_diff_report(result["gif"])
    if args.check:
        result["checks"] = check_outputs(result, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.check and not result["checks"]["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
