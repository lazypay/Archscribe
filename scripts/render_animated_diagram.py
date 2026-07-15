#!/usr/bin/env python3
import argparse
import bisect
import json
import math
import random
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    from svg.path import parse_path
except ImportError:  # pragma: no cover - exercised only when optional dependency is missing.
    parse_path = None

# Sibling modules must import even when this file is loaded from an arbitrary
# path (tests, editors), so pin the scripts dir onto sys.path.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import graph_model

try:
    import icon_browser
except ImportError:  # pragma: no cover - allows import when run as a module path.
    icon_browser = None

try:
    import svg_renderer
except ImportError:  # pragma: no cover - allows import when run as a module path.
    svg_renderer = None

ANIMATION_CHOICES = ("flow", "draw", "relay", "trace", "chapter", "failure-recovery")

# When set to "skip", draw_svg_icon_tile only paints the tile chrome and leaves
# the glyph to the browser engine, which stamps animated frames afterwards.
ICON_GLYPH_MODE = "draw"

# Optional primitive-op recorder. When a list is installed here, every draw_*
# call appends a JSON-friendly op describing itself (CSS-space coordinates).
# The browser/SVG renderer replays these ops with rough.js, so both renderers
# share one layout. Managed by render_static_with_ops().
OPS_SINK = None


def ops_record(op):
    if OPS_SINK is not None:
        OPS_SINK.append(op)


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
    "icon_fill": "#061015",
    "decision_fill": "#052515",
    "src_card_fill": "#04200f",
    "layer_card_fill": "#17091d",
    "pack_card_fill": "#04200f",
}

# Snapshot of the default (dark hand-drawn) palette. Styles are expressed as
# partial overrides merged onto this base so new keys always have a sane value.
DEFAULT_THEME = dict(THEME)

STYLE_THEMES = {
    "default": {},
    # DailyDoseOfDS-style light paper: warm white canvas, sage/periwinkle
    # band tints, near-black ink, white cards with colored strokes.
    "paper": {
        "bg": "#fdfcf8", "white": "#2f2b26", "muted": "#6f6a61", "frame": "#3a3733",
        "core_fill": "#ffffff", "core_stroke": "#4f7fd0", "green": "#3f9e7d", "green_fill": "#c9e2d5",
        "purple": "#6b7cc9", "purple_fill": "#ccd5f0", "cyan": "#2f9d98", "blue_fill": "#eef3fb",
        "highlight": "#b9e0d2", "amber": "#e08a3c", "pink": "#d96a92",
        "archive_fill": "#edf1fb", "source_fill": "#e9f2ec", "pack_fill": "#ffffff",
        "icon_fill": "#ffffff", "decision_fill": "#eaf5ef",
        "src_card_fill": "#ffffff", "layer_card_fill": "#ffffff", "pack_card_fill": "#ffffff",
    },
}

# Light styles skip the dark grain/vignette finish for a clean paper look.
STYLE_FINISH = {"paper": "light"}
FINISH_MODE = "dark"
CURRENT_STYLE = "default"


def apply_style(name):
    """Switch the live THEME palette and finish mode to the named style."""
    global FINISH_MODE, CURRENT_STYLE
    if name not in STYLE_THEMES:
        choices = ", ".join(STYLE_THEMES)
        raise SystemExit(f"unknown style '{name}'. choices: {choices}")
    THEME.clear()
    THEME.update(DEFAULT_THEME)
    THEME.update(STYLE_THEMES[name])
    FINISH_MODE = STYLE_FINISH.get(name, "dark")
    CURRENT_STYLE = name

ROOT = Path(__file__).resolve().parents[1]
TABLER_ICON_DIR = ROOT / "assets" / "icons" / "tabler"
FONT_DIR = ROOT / "assets" / "fonts"
BUNDLED_HAND_FONT = FONT_DIR / "Excalifont-Regular.ttf"
BUNDLED_CJK_FONTS = {
    False: FONT_DIR / "NotoSansSC-Regular.ttf",
    True: FONT_DIR / "NotoSansSC-Bold.ttf",
}
_CJK_COVERAGE_RANGES = None
_CJK_COVERAGE_STARTS = None
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
    # Stable semantic vocabulary. These aliases intentionally decouple specs
    # from the underlying icon filename so the art pack can evolve later.
    "cloud": "world", "cluster": "server", "container": "cube", "kubernetes": "cube",
    "queue": "message", "cache": "database", "load-balancer": "settings", "cdn": "world",
    "warehouse": "database", "lake": "database", "vector-db": "database", "stream": "arrow-down-circle",
    "etl": "settings", "analytics": "search", "dashboard": "eye", "model": "brain",
    "agent": "brain", "prompt": "message", "embedding": "hash", "rag": "search",
    "tool-call": "settings", "guardrail": "shield-check", "evaluation": "check",
    "identity": "lock-check", "key": "lock-check", "firewall": "shield-check", "audit": "clipboard-text",
    "policy": "file-text", "secret": "lock-check", "compliance": "check", "user": "message",
    "team": "message", "admin": "shield-check", "customer": "message", "payment": "check",
    "notification": "message", "success": "check", "warning": "shield-check", "failure": "arrow-down-circle",
    "pending": "clock", "retry": "arrow-down-circle", "manual-step": "clipboard-text",
    "memory": "database", "validate": "shield-check", "scope": "search", "budget": "clock",
    "output": "package", "think": "brain", "act": "settings", "observe": "eye",
    "working-memory": "clipboard-text", "code": "terminal-2", "trigger": "calendar-event",
    "prompt": "message", "embedding": "hash", "analytics": "eye", "dashboard": "eye",
    "firewall": "shield-check", "notification": "message", "customer": "message", "admin": "shield-check",
    # Loop-workflow vocabulary (agent loops, pipelines, orchestration). Each key
    # has a dedicated illustrated builder; the Tabler name is the outline fallback.
    "loop": "arrow-down-circle", "iterate": "arrow-down-circle", "cycle": "arrow-down-circle",
    "plan": "clipboard-text", "roadmap": "clipboard-text",
    "decision": "check", "condition": "check",
    "merge": "arrow-down-circle", "join": "arrow-down-circle", "aggregate": "arrow-down-circle",
    "split": "arrow-down-circle", "fanout": "arrow-down-circle", "fan-out": "arrow-down-circle",
    "parallel": "arrow-down-circle", "branch": "arrow-down-circle",
    "handoff": "package", "hand-off": "package", "delegate": "package",
    "subagent": "brain", "sub-agent": "brain", "worker": "brain",
    "orchestrator": "settings", "coordinator": "settings", "dispatch": "settings",
    "human": "message", "review": "clipboard-text", "approval": "check", "hitl": "clipboard-text",
    "checkpoint": "check", "milestone": "check",
    "rollback": "arrow-down-circle", "revert": "arrow-down-circle", "undo": "arrow-down-circle",
    "sandbox": "cube", "experiment": "cube", "lab": "cube",
    "compare": "search", "ab-test": "search", "benchmark": "search", "versus": "search",
    "score": "check", "grade": "check", "rating": "check", "rank": "check",
    "error": "arrow-down-circle", "exception": "arrow-down-circle", "fault": "arrow-down-circle",
    "wait": "clock", "delay": "clock", "timeout": "clock", "sleep": "clock",
    "emit": "message", "broadcast": "message", "publish": "message", "webhook": "api",
    "ingest": "arrow-down-circle", "intake": "arrow-down-circle", "import": "arrow-down-circle", "receive": "arrow-down-circle",
}
SVG_ICON_CACHE = {}

# Single source of truth for icon sizing so every tile across the diagram is
# visually consistent. Supersampling keeps the rasterized strokes crisp.
ICON_TILE = 50
ICON_PAD = 7
# Frameless (plain) icons have no tile chrome, so the glyph can breathe wider.
ICON_PAD_PLAIN = 2
ICON_SUPERSAMPLE = 3


def hex_rgba(value, alpha=255):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def c(v):
    return int(round(v * SCALE))


def scaled_box(x, y, w, h):
    return (c(x), c(y), c(x + w), c(y + h))


def font_candidates(hand=False, cjk=False, bold=False):
    """Bundled fonts first (identical output on Windows / macOS / Codex Linux
    sandbox), then platform fonts as fallback."""
    if hand:
        return [
            str(BUNDLED_HAND_FONT),
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
            str(BUNDLED_CJK_FONTS[bold]),
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    return [
        # Noto Sans SC ships clean Latin glyphs, so plain labels stay
        # consistent across platforms too.
        str(BUNDLED_CJK_FONTS[bold]),
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]


def cjk_coverage_ranges():
    global _CJK_COVERAGE_RANGES, _CJK_COVERAGE_STARTS
    if _CJK_COVERAGE_RANGES is None:
        try:
            raw = json.loads((FONT_DIR / "notosanssc-coverage.json").read_text(encoding="utf-8"))
            _CJK_COVERAGE_RANGES = [(int(a), int(b)) for a, b in raw]
        except (OSError, ValueError):
            _CJK_COVERAGE_RANGES = []
        _CJK_COVERAGE_STARTS = [a for a, _ in _CJK_COVERAGE_RANGES]
    return _CJK_COVERAGE_RANGES, _CJK_COVERAGE_STARTS


def bundled_cjk_covers(text):
    ranges, starts = cjk_coverage_ranges()
    if not ranges:
        return False
    for ch in str(text):
        cp = ord(ch)
        if cp == 0x0A:  # newline, never rendered as a glyph
            continue
        i = bisect.bisect_right(starts, cp) - 1
        if i < 0 or cp > ranges[i][1]:
            return False
    return True


def load_font(size, hand=False, cjk=False, bold=False, text=""):
    candidates = font_candidates(hand=hand, cjk=cjk, bold=bold)
    if cjk and text and not bundled_cjk_covers(text):
        # Rare glyph outside the bundled subset: prefer full system CJK fonts.
        bundled = str(BUNDLED_CJK_FONTS[bold])
        candidates = [p for p in candidates if p != bundled] + [bundled]
    for path in candidates:
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


def _word_safe(raw, wrapped):
    """True when wrapping only happened at word boundaries (CJK is always safe)."""
    if wrapped == raw or has_cjk(raw):
        return True
    return wrapped.replace("\n", " ") == raw


def fit_text(draw, text, w, h, size, min_size=10, hand=False, bold=False, spacing=3, wrap=True):
    raw_text = str(text)
    has_cjk_text = has_cjk(raw_text)
    max_width = c(w)
    max_height = c(h)
    start_size = int(size)
    emergency_min = min(start_size, int(min_size), EMERGENCY_MIN_TEXT_SIZE)
    # Pass 1 only accepts word-boundary wraps: a long single word shrinks to
    # fit on one line instead of breaking mid-word at full size. Pass 2
    # re-allows mid-word breaks as the last resort before the emergency floor.
    for allow_word_breaks in (False, True):
        for candidate_size in range(start_size, emergency_min - 1, -1):
            candidate_font = load_font(candidate_size, hand=hand and not has_cjk_text, cjk=has_cjk_text, bold=bold, text=raw_text)
            for candidate_text in text_variants(draw, raw_text, candidate_font, max_width, wrap):
                if not allow_word_breaks and not _word_safe(raw_text, candidate_text):
                    continue
                tw, th = text_size(draw, candidate_text, candidate_font, spacing=spacing)
                if tw <= max_width and th <= max_height:
                    return candidate_text, candidate_size, candidate_font

    fallback_font = load_font(emergency_min, hand=hand and not has_cjk_text, cjk=has_cjk_text, bold=bold, text=raw_text)
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
        font = load_font(size, hand=hand and not has_cjk(text), cjk=has_cjk(text), bold=bold, text=text)
    ops_record({"op": "text", "text": str(text), "x": x, "y": y, "w": w, "h": h, "size": size,
                "color": color, "align": align, "hand": bool(hand), "bold": bool(bold), "spacing": spacing})
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
    ops_record({"op": "rect", "x": x, "y": y, "w": w, "h": h, "stroke": stroke, "fill": fill,
                "width": width, "radius": radius, "style": style})
    ex.rect(x, y, w, h, stroke, fill or "transparent", width, style)
    draw.rounded_rectangle(scaled_box(x, y, w, h), radius=c(radius), outline=hex_rgba(stroke), fill=hex_rgba(fill) if fill else None, width=max(1, c(width)))


def draw_ellipse(ex, draw, x, y, w, h, stroke, fill=None, width=2):
    ops_record({"op": "ellipse", "x": x, "y": y, "w": w, "h": h, "stroke": stroke, "fill": fill, "width": width})
    ex.ellipse(x, y, w, h, stroke, fill or "transparent", width)
    draw.ellipse(scaled_box(x, y, w, h), outline=hex_rgba(stroke), fill=hex_rgba(fill) if fill else None, width=max(1, c(width)))


def draw_line(ex, draw, points, stroke, width=2, style="solid", arrow=False):
    ops_record({"op": "line", "points": [[px, py] for px, py in points], "stroke": stroke,
                "width": width, "style": style, "arrow": bool(arrow)})
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
    ops_record({"op": "diamond", "x": x, "y": y, "w": w, "h": h, "stroke": stroke, "fill": fill, "width": width})
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


def is_custom_icon(kind):
    """Custom icons are encoded as '@<absolute path>' (see resolve_custom_icons)."""
    return isinstance(kind, str) and kind.startswith("@")


def custom_icon_path(kind):
    return Path(str(kind)[1:])


def resolve_icon_name(kind):
    if is_custom_icon(kind):
        return str(kind)
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


_PILLOW_ILL_FAMILIES = (
    ("loop", ("loop", "iterate", "cycle", "retry", "rollback", "revert", "undo")),
    ("decision", ("decision", "condition")),
    ("error", ("error", "exception", "fault", "warning")),
    ("wait", ("wait", "delay", "timeout", "sleep", "hourglass")),
    # Before the shield family so "checkpoint" is not swallowed by "check".
    ("file", ("plan", "roadmap", "checkpoint", "milestone")),
    ("brain", ("brain", "think", "model", "reason", "subagent", "sub-agent", "worker")),
    ("agent", ("agent",)),
    ("gear", ("gear", "act", "tool", "settings", "etl", "load-balancer",
              "orchestr", "coordinator", "dispatch")),
    ("analytics", ("analytics", "dashboard", "compare", "ab-test", "benchmark", "versus")),
    ("eye", ("eye", "observe", "monitor")),
    ("db", ("db", "database", "memory", "working-memory", "warehouse", "lake",
            "storage", "cache", "vector", "embedding", "ingest", "intake", "import", "receive")),
    ("search", ("search", "scan", "rag", "scope")),
    ("shield", ("shield", "validate", "guard", "check", "success", "firewall",
                "admin", "compliance", "approve", "score", "grade", "rating", "rank")),
    ("clock", ("clock", "budget", "schedule", "pending", "time")),
    ("notification", ("notification", "emit", "broadcast", "publish", "webhook")),
    ("message", ("message", "chat", "prompt", "queue")),
    ("api", ("api",)),
    ("package", ("package", "output", "deliver", "cube", "box", "container",
                 "handoff", "hand-off", "delegate", "sandbox", "experiment", "lab")),
    ("cloud", ("cloud", "deploy", "cdn", "globe", "world")),
    ("server", ("server", "cluster")),
    ("lock", ("lock", "secret", "key", "identity")),
    ("user", ("user", "customer", "team", "human", "review", "approval", "hitl")),
    ("terminal", ("terminal", "code")),
    ("file", ("file", "document", "policy", "audit", "clipboard", "manual-step", "folder")),
)


def draw_illustrated_icon_raster(draw, kind, x, y, color, scale=1.0, hero=False):
    """Dependency-free Pillow fallback: static rest poses of the duotone set.

    Mirrors the browser engine's "Neon Sketch Duotone" language - plate-free
    theme-ink strokes with one semantic accent - collapsed to the closest of
    ~19 hand-kept families.
    """
    semantic = str(kind).lower()
    family = "module"
    for name, keys in _PILLOW_ILL_FAMILIES:
        if semantic.startswith(keys):
            family = name
            break
    t = ICON_TILE * scale / 48.0 * (1.16 if hero else 1.0)
    ox = x + ICON_TILE * scale / 2 - 24 * t
    oy = y + ICON_TILE * scale / 2 - 24 * t

    def P(vx, vy):
        return (c(ox + vx * t), c(oy + vy * t))

    # ImageDraw here overwrites rather than alpha-blends, so translucent
    # duotone tones are premixed against the card/background color.
    def _mix(top, base, k):
        a = hex_rgba(top)
        b = hex_rgba(base)
        return tuple(int(a[i] * k + b[i] * (1 - k)) for i in range(3)) + (255,)

    ink = hex_rgba(THEME["white"])
    ink_soft = _mix(THEME["white"], THEME["icon_fill"], 0.52)
    ghost = _mix(THEME["white"], THEME["icon_fill"], 0.24)
    acc = hex_rgba(color)
    acc_soft = _mix(color, THEME["icon_fill"], 0.22)

    def W(w):
        return max(2, c(w * t))

    def line(pts, col=None, w=2.8, ghosted=True):
        seq = [P(px, py) for px, py in pts]
        if col is None:
            if ghosted:
                gseq = [(px_ + c(0.75 * t), py_ - c(0.55 * t)) for px_, py_ in seq]
                draw.line(gseq, fill=ghost, width=max(1, c(w * t * 0.55)), joint="curve")
            draw.line(seq, fill=ink, width=W(w), joint="curve")
        else:
            draw.line(seq, fill=col, width=W(w), joint="curve")

    def ell(x0, y0, x1, y1, outline=None, fill=None, w=2.8):
        draw.ellipse((*P(x0, y0), *P(x1, y1)), outline=outline, fill=fill, width=W(w))

    def rrect(x0, y0, x1, y1, r, outline=None, fill=None, w=2.8):
        draw.rounded_rectangle((*P(x0, y0), *P(x1, y1)), radius=c(r * t),
                               outline=outline, fill=fill, width=W(w))

    def arc(x0, y0, x1, y1, start, end, col=None, w=2.8):
        draw.arc((*P(x0, y0), *P(x1, y1)), start, end, fill=col or ink, width=W(w))

    if family == "brain":
        ell(9.5, 8, 38.5, 40, outline=ink)
        line([(24, 11), (24, 37)], col=ink_soft, w=1.8)
        line([(16.5, 18.5), (24, 24.5), (31.5, 17.5)], col=hex_rgba(color, 150), w=2)
        line([(18.5, 30), (24, 24.5), (29.5, 30)], col=hex_rgba(color, 150), w=2)
        for px, py in ((16.5, 18.5), (24, 24.5), (31.5, 17.5), (18.5, 30), (29.5, 30)):
            ell(px - 2, py - 2, px + 2, py + 2, outline=acc, fill=acc_soft, w=1)
    elif family == "agent":
        rrect(11, 15, 37, 36.5, 6.5, outline=ink)
        line([(8.2, 23.5), (8.2, 30.5)], w=2.6)
        line([(39.8, 23.5), (39.8, 30.5)], w=2.6)
        line([(24, 15), (24, 9.6)], w=2.2)
        ell(21.9, 6.1, 26.1, 10.3, fill=acc)
        for ex_ in (18.6, 29.4):
            ell(ex_ - 2.7, 21.6, ex_ + 2.7, 27, fill=acc)
        arc(18.5, 26.5, 29.5, 33.9, 20, 160, col=acc, w=2.2)
    elif family == "gear":
        for i in range(8):
            a = i * math.pi / 4
            line([(22 + math.cos(a) * 12.6, 22 + math.sin(a) * 12.6),
                  (22 + math.cos(a) * 17.6, 22 + math.sin(a) * 17.6)], w=4.4, ghosted=False)
        ell(10.4, 10.4, 33.6, 33.6, outline=ink, w=3)
        ell(17.4, 17.4, 26.6, 26.6, outline=acc, fill=acc_soft, w=2)
        ell(33.1, 33.1, 41.9, 41.9, outline=ink_soft, w=2.2)
        ell(36.1, 36.1, 38.9, 38.9, fill=acc)
    elif family == "eye":
        arc(5.5, 9.5, 42.5, 38.5, 199, 341, w=3)
        arc(5.5, 9.5, 42.5, 38.5, 19, 161, w=3)
        ell(16.6, 16.6, 31.4, 31.4, outline=acc, fill=acc_soft, w=2.4)
        ell(20.8, 20.8, 27.2, 27.2, fill=acc)
        ell(25.1, 20.5, 27.3, 22.7, fill=ink)
        for lx0, ly0, lx1, ly1 in ((13, 13.5, 11, 10.8), (24, 10.4, 24, 7.4), (35, 13.5, 37, 10.8)):
            line([(lx0, ly0), (lx1, ly1)], col=ink_soft, w=2, ghosted=False)
    elif family == "db":
        ell(10.5, 9.2, 37.5, 18.8, outline=ink, w=3)
        line([(10.5, 14), (10.5, 33.5)], w=3)
        line([(37.5, 14), (37.5, 33.5)], w=3)
        arc(10.5, 28.7, 37.5, 38.3, 0, 180, w=3)
        line([(13.5, 22.4), (34.5, 22.4)], col=hex_rgba(color, 150), w=2, ghosted=False)
        line([(13.5, 27.6), (34.5, 27.6)], col=hex_rgba(color, 150), w=2, ghosted=False)
    elif family == "search":
        ell(8.2, 8.2, 32.8, 32.8, outline=ink, w=3)
        line([(29.6, 29.6), (38.6, 38.6)], w=4.2)
        line([(11.5, 20.5), (29.5, 20.5)], col=acc, w=2.2, ghosted=False)
        for hx, hy in ((16.5, 17.2), (24.5, 24.0)):
            ell(hx - 1.9, hy - 1.9, hx + 1.9, hy + 1.9, fill=hex_rgba(color, 140))
    elif family == "shield":
        pts = [P(24, 6.5), P(37.8, 11.2), P(36.4, 26), P(24, 38.5), P(11.6, 26), P(10.2, 11.2)]
        draw.polygon(pts, fill=acc_soft)
        line([(24, 6.5), (37.8, 11.2), (36.4, 26), (24, 38.5), (11.6, 26), (10.2, 11.2), (24, 6.5)], w=3)
        line([(17, 23.5), (22, 29), (31.5, 17.5)], col=acc, w=3.4, ghosted=False)
    elif family == "clock":
        ell(6.8, 6.8, 41.2, 41.2, outline=ink, w=3)
        for i in range(4):
            a = i * math.pi / 2
            line([(24 + math.cos(a) * 13.2, 24 + math.sin(a) * 13.2),
                  (24 + math.cos(a) * 15.8, 24 + math.sin(a) * 15.8)], w=2.4, ghosted=False)
        line([(24, 24), (30.2, 20.4)], w=3.2, ghosted=False)
        line([(24, 24), (24, 11.6)], col=acc, w=3, ghosted=False)
        ell(21.9, 21.9, 26.1, 26.1, fill=acc)
    elif family == "notification":
        arc(17.5, 10.5, 30.5, 30, 180, 360, w=2.8)
        line([(17.5, 20), (17.5, 27.5), (13.5, 30.5), (34.5, 30.5), (30.5, 27.5), (30.5, 20)], w=2.8)
        line([(24, 10.5), (24, 7.8)], w=2.2)
        ell(21.6, 32.1, 26.4, 36.9, fill=acc)
    elif family == "message":
        rrect(7.5, 9.5, 40.5, 32, 8, outline=ink)
        line([(15.5, 31.5), (12.5, 39.5), (21.5, 31.8)], w=2.6)
        for dx_ in (16.8, 24, 31.2):
            ell(dx_ - 2.2, 18.6, dx_ + 2.2, 23, fill=acc)
    elif family == "api":
        line([(17.5, 11.5), (8.5, 24), (17.5, 36.5)], w=3.2)
        line([(30.5, 11.5), (39.5, 24), (30.5, 36.5)], w=3.2)
        line([(27, 13.5), (21, 34.5)], col=ink_soft, w=2.4, ghosted=False)
        ell(21.5, 21.5, 26.5, 26.5, fill=acc)
    elif family == "package":
        rrect(10.5, 18, 37.5, 36.5, 2.5, outline=ink, fill=acc_soft)
        line([(10.5, 18), (37.5, 18)], w=3)
        line([(24, 18), (24, 36.5)], col=ink_soft, w=1.8, ghosted=False)
        line([(17.5, 30.5), (17.5, 25)], col=acc, w=1.9, ghosted=False)
        line([(15.2, 27), (17.5, 24.6), (19.8, 27)], col=acc, w=1.9, ghosted=False)
    elif family == "cloud":
        ell(12.2, 8, 35.8, 30, outline=ink, w=3)
        arc(6, 17, 22, 32.5, 90, 270, w=3)
        arc(27, 15, 43.5, 32.5, 270, 90, w=3)
        line([(14, 31.4), (36, 31.4)], w=3)
        for sx in (17.5, 24, 30.5):
            line([(sx, 35), (sx, 38.6)], col=acc, w=2.4, ghosted=False)
            line([(sx, 40.6), (sx, 42.5)], col=hex_rgba(color, 140), w=2.4, ghosted=False)
    elif family == "server":
        for sy in (9.5, 19.5, 29.5):
            rrect(10.5, sy, 37.5, sy + 9, 2.5, outline=ink, w=2.6)
            ell(31.8, sy + 2.8, 35.2, sy + 6.2, outline=acc, fill=acc_soft, w=1)
            line([(14.5, sy + 4.5), (22.5, sy + 4.5)], col=ink_soft, w=2, ghosted=False)
        ell(31.8, 22.3, 35.2, 25.7, fill=acc)
    elif family == "lock":
        arc(16.5, 7.5, 31.5, 22.5, 180, 360, w=3)
        line([(16.5, 15), (16.5, 21)], w=3)
        line([(31.5, 15), (31.5, 21)], w=3)
        rrect(12.5, 21, 35.5, 37.5, 4, outline=ink, fill=acc_soft)
        ell(21.4, 25.4, 26.6, 30.6, fill=acc)
        line([(24, 29.5), (24, 33)], col=acc, w=2.4, ghosted=False)
    elif family == "user":
        ell(17.8, 9.8, 30.2, 22.2, outline=ink, w=2.8)
        arc(10.5, 26.5, 37.5, 47.5, 180, 360, w=3)
        ell(32.1, 11.1, 36.9, 15.9, fill=acc)
    elif family == "terminal":
        rrect(8.5, 11, 39.5, 37, 3.5, outline=ink)
        line([(8.5, 17.5), (39.5, 17.5)], col=ink_soft, w=1.8, ghosted=False)
        for dx_ in (11.5, 15, 18.5):
            ell(dx_ - 1.1, 13.1, dx_ + 1.1, 15.3, fill=ink_soft)
        line([(12.5, 22.5), (16.5, 25.5), (12.5, 28.5)], col=acc, w=2.2, ghosted=False)
        line([(19.5, 25.5), (30, 25.5)], col=acc, w=2.4, ghosted=False)
        line([(12.5, 32.5), (26, 32.5)], col=ink_soft, w=2.2, ghosted=False)
    elif family == "analytics":
        line([(10.5, 9.5), (10.5, 37), (39.5, 37)], w=2.8)
        for bx, bh in ((15, 10), (22.5, 15), (30, 21)):
            rrect(bx, 37 - bh, bx + 5.2, 37, 1.4, outline=acc, fill=acc_soft, w=1.7)
        line([(13, 30), (20.5, 25), (28, 21), (36.5, 12.5)], col=acc, w=2.2, ghosted=False)
    elif family == "file":
        line([(13, 8.5), (29, 8.5), (35.5, 15), (35.5, 39.5), (13, 39.5), (13, 8.5)], w=2.8)
        line([(29, 8.5), (29, 15), (35.5, 15)], col=ink_soft, w=2.2, ghosted=False)
        for i, (lx, ly) in enumerate(((17.5, 21), (17.5, 26), (17.5, 31))):
            line([(lx, ly), (lx + (9 if i == 2 else 13.5), ly)], col=acc, w=2, ghosted=False)
    elif family == "loop":
        arc(11, 11, 37, 37, -60, 150, w=3)
        arc(11, 11, 37, 37, 120, 330, col=acc, w=3)
        line([(20.5, 8.5), (27, 11.2), (21.5, 15.5)], w=2.8)
        line([(27.5, 39.5), (21, 36.8), (26.5, 32.5)], col=acc, w=2.8, ghosted=False)
        ell(21.9, 21.9, 26.1, 26.1, fill=acc)
    elif family == "decision":
        pts = [P(24, 9.5), P(38.5, 24), P(24, 38.5), P(9.5, 24)]
        draw.polygon(pts, fill=acc_soft)
        line([(24, 9.5), (38.5, 24), (24, 38.5), (9.5, 24), (24, 9.5)], w=2.8)
        line([(2.5, 24), (8, 24)], col=ink_soft, w=2.2, ghosted=False)
        line([(40, 24), (45.5, 24)], col=ink_soft, w=2.2, ghosted=False)
        arc(20.8, 16.6, 27.6, 23.4, 150, 450, col=acc, w=2.2)
        ell(22.8, 28.2, 26, 31.4, fill=acc)
    elif family == "error":
        pts = [P(24, 9), P(41, 36.5), P(7, 36.5)]
        draw.polygon(pts, fill=acc_soft)
        line([(24, 9), (41, 36.5), (7, 36.5), (24, 9)], w=2.8)
        line([(24, 18), (24, 27.5)], col=acc, w=3, ghosted=False)
        ell(22.1, 30.5, 25.9, 34.3, fill=acc)
    elif family == "wait":
        line([(14.5, 9), (33.5, 9)], w=2.8)
        line([(14.5, 39), (33.5, 39)], w=2.8)
        line([(17, 9), (17, 12), (21.5, 20), (22.2, 24), (17, 32), (17, 39)], w=2.6)
        line([(31, 9), (31, 12), (26.5, 20), (25.8, 24), (31, 32), (31, 39)], w=2.6)
        pts = [P(19.2, 13.5), P(28.8, 13.5), P(24, 22)]
        draw.polygon(pts, fill=acc_soft)
        line([(19.2, 13.5), (28.8, 13.5)], col=acc, w=1.8, ghosted=False)
        pts = [P(18.5, 38.4), P(29.5, 38.4), P(24, 31.5)]
        draw.polygon(pts, fill=acc)
    else:  # module: IC chip fallback
        rrect(13, 13, 35, 35, 4.5, outline=ink)
        for v in (17.5, 24, 30.5):
            for pts in (((v, 13), (v, 8.5)), ((v, 35), (v, 39.5)),
                        ((13, v), (8.5, v)), ((35, v), (39.5, v))):
                line(list(pts), col=ink_soft, w=2, ghosted=False)
        rrect(19, 19, 29, 29, 2, outline=acc, fill=acc_soft, w=1.8)
        ell(22.2, 22.2, 25.8, 25.8, fill=acc)
    return True


def draw_svg_icon_tile(ex, draw, kind, x, y, color, scale, plain=False, glyph_color=None, icon_style="outline"):
    icon_name = resolve_icon_name(kind)
    tile = int(round(ICON_TILE * scale))
    pad = int(round((ICON_PAD_PLAIN if plain else ICON_PAD) * scale))
    radius = int(round(11 * scale))
    stroke_color = glyph_color or THEME["white"]

    illustrated = icon_style in ("illustrated", "hero") and not is_custom_icon(kind)
    if not plain:
        # Keep Excalidraw editable with a simple local placeholder while the
        # PNG/GIF use the higher fidelity Tabler SVG asset.
        ex.rect(x + 1 * scale, y + 1 * scale, tile - 2 * scale, tile - 2 * scale, color, THEME["icon_fill"], 1, "solid")
        if not illustrated:
            # The duotone illustrations are plate-free; tile chrome is only
            # for outline glyphs.
            box = (c(x), c(y), c(x + tile), c(y + tile))
            draw.rounded_rectangle(box, radius=c(radius), outline=hex_rgba(color, 150), fill=hex_rgba(THEME["icon_fill"], 170), width=max(1, c(1.25)))
    else:
        # Frameless: no raster chrome, but keep an editable marker in the
        # .excalidraw file so the icon spot is still visible/movable there.
        ex.ellipse(x + tile * 0.16, y + tile * 0.16, tile * 0.68, tile * 0.68, color, "transparent", 1)

    # In browser mode the glyph is stamped per-frame later; only paint the tile.
    if ICON_GLYPH_MODE == "skip" and not is_custom_icon(kind):
        return True

    if icon_style in ("illustrated", "hero") and not is_custom_icon(kind):
        return draw_illustrated_icon_raster(draw, kind, x, y, color, scale, hero=icon_style == "hero")

    icon_size = max(28, int(round((tile - pad * 2) * SCALE)))
    if is_custom_icon(kind):
        icon_img = load_custom_icon_image(custom_icon_path(kind), icon_size)
    else:
        icon_img = load_svg_icon(icon_name, stroke_color, icon_size)
    if icon_img is None:
        return False
    ox = c(x) + (c(tile) - icon_size) // 2
    oy = c(y) + (c(tile) - icon_size) // 2
    draw._image.alpha_composite(icon_img, (ox, oy))
    return True


def load_custom_icon_image(path, size):
    """Rasterize a user-supplied icon for the Pillow pipeline.

    PNG keeps its original colors; SVG is traced as white outline strokes
    (best effort - filled brand marks look best in the browser renderer).
    """
    cache_key = (str(path), size)
    if cache_key in SVG_ICON_CACHE:
        return SVG_ICON_CACHE[cache_key].copy()
    if not path.is_file():
        return None
    rendered = None
    try:
        if path.suffix.lower() == ".png":
            img = Image.open(path).convert("RGBA")
            ratio = min(size / img.width, size / img.height)
            fitted = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                                Image.Resampling.LANCZOS)
            rendered = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            rendered.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        elif path.suffix.lower() == ".svg" and parse_path is not None:
            rendered = render_svg_outline(path, THEME["white"], size)
    except Exception:
        rendered = None
    if rendered is None:
        return None
    SVG_ICON_CACHE[cache_key] = rendered
    return rendered.copy()


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


def icon(ex, draw, kind, x, y, color=None, scale=1.0, plain=False, glyph_color=None,
         icon_style="outline", icon_motion="auto", icon_size="standard"):
    global OPS_SINK
    color = color or THEME["cyan"]
    icon_name = resolve_icon_name(kind)
    custom = is_custom_icon(kind)
    if custom or (TABLER_ICON_DIR / f"{icon_name}.svg").is_file():
        # One semantic op fully describes the tile for the browser renderer;
        # suppress the raster fallback's primitive ops to avoid duplicates.
        op = {"op": "icon", "name": icon_name, "semantic": str(kind), "x": x, "y": y,
              "tile": int(round(ICON_TILE * scale)),
              "pad": int(round((ICON_PAD_PLAIN if plain else ICON_PAD) * scale)),
              "radius": int(round(11 * scale)), "accent": color,
              "glyph": glyph_color or THEME["white"], "fill": THEME["icon_fill"],
              "iconStyle": icon_style, "iconMotion": icon_motion, "iconSize": icon_size}
        if custom:
            op["custom"] = True
            op["file"] = str(custom_icon_path(kind))
        if plain:
            op["plain"] = True
        ops_record(op)
        saved, OPS_SINK = OPS_SINK, None
        try:
            if not draw_svg_icon_tile(ex, draw, kind, x, y, color, scale, plain=plain, glyph_color=glyph_color, icon_style=icon_style):
                draw_primitive_icon(ex, draw, kind, x, y, color, scale)
        finally:
            OPS_SINK = saved
        return
    if draw_svg_icon_tile(ex, draw, kind, x, y, color, scale, plain=plain, glyph_color=glyph_color, icon_style=icon_style):
        return
    draw_primitive_icon(ex, draw, kind, x, y, color, scale)


def icon_presentation(item, default_style="outline"):
    """Extract optional high-fidelity icon presentation fields from a spec item."""
    item = item or {}
    return {
        "icon_style": item.get("icon_style", default_style),
        "icon_motion": item.get("icon_motion", "auto"),
        "icon_size": item.get("icon_size", "standard"),
    }


# The classic "@archscribe" signature measures ~149 CSS px; longer signatures
# shift the whole brand block left (so nothing clips at the canvas edge) and
# stretch the hand-drawn underline to match the text.
SIGNATURE_X = 998
SIGNATURE_RIGHT_LIMIT = 1180
SIGNATURE_UNDERLINE_REF = 150.0


def signature_text_width(draw, text):
    font = load_font(24, cjk=True, bold=True, text=text)
    lines = str(text).splitlines() or [""]
    return max(draw.textlength(line, font=font) for line in lines) / SCALE


def custom_image(ex, draw, path, x, y, w, h):
    """A user image (brand logo etc.) fitted into a w x h box, aspect kept.

    Records an 'image' op for the browser renderer and pastes a raster
    letterboxed copy for the Pillow pipeline. Returns False when the file
    cannot be rasterized locally (caller may fall back to text)."""
    path = Path(str(path))
    ops_record({"op": "image", "name": f"img:{path}", "file": str(path),
                "x": x, "y": y, "w": w, "h": h})
    ex.rect(x, y, w, h, THEME["frame"], "transparent", 1, "solid")
    img = None
    try:
        if path.suffix.lower() == ".png" and path.is_file():
            img = Image.open(path).convert("RGBA")
        elif path.suffix.lower() == ".svg" and path.is_file() and parse_path is not None:
            img = render_svg_outline(path, THEME["white"], c(min(w, h)))
    except Exception:
        img = None
    if img is None:
        return False
    bw, bh = c(w), c(h)
    ratio = min(bw / img.width, bh / img.height)
    fitted = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                        Image.Resampling.LANCZOS)
    draw._image.alpha_composite(fitted, (c(x) + (bw - fitted.width) // 2, c(y) + (bh - fitted.height) // 2))
    return True


def draw_signature(ex, draw, text, x, y, stretch=1.0):
    ops_record({"op": "signature", "text": str(text), "x": x, "y": y, "stretch": round(stretch, 3),
                "layers": [[-1, 1, THEME["purple"], 165], [1, -1, THEME["cyan"], 135], [0, 0, THEME["white"], 245]],
                "underline": THEME["purple"], "underline2": THEME["white"]})
    ex.text(text, x, y, int(round(120 * stretch)), 36, 23, THEME["white"], align="left")
    font = load_font(24, cjk=True, bold=True, text=text)
    sx, sy = c(x), c(y)
    k = stretch
    for dx, dy, color, alpha in [(-1, 1, THEME["purple"], 165), (1, -1, THEME["cyan"], 135), (0, 0, THEME["white"], 245)]:
        draw.text((sx + c(dx), sy + c(dy)), text, font=font, fill=hex_rgba(color, alpha))
    draw.line([(sx + c(6 * k), sy + 56), (sx + c(28 * k), sy + 61), (sx + c(62 * k), sy + 58), (sx + c(86 * k), sy + 63)],
              fill=hex_rgba(THEME["purple"], 170), width=3)
    draw.line([(sx + c(8 * k), sy + 54), (sx + c(84 * k), sy + 60)], fill=hex_rgba(THEME["white"], 125), width=1)


def brand(ex, draw, signature):
    text = str(signature)
    w_text = signature_text_width(draw, text)
    shift = max(0, int(round(SIGNATURE_X + w_text - SIGNATURE_RIGHT_LIMIT)))
    stretch = max(1.0, min(3.0, w_text / SIGNATURE_UNDERLINE_REF))
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
        draw_ellipse(ex, draw, 955 - shift + dx, 143 + dy, 5, 5, color, color, 1)
    draw_signature(ex, draw, text, SIGNATURE_X - shift, 135, stretch)


def small_input(ex, draw, x, y, item, plain=False):
    kind = item.get("icon", "file")
    color = item.get("color", THEME["cyan"])
    # Plain style: no tile chrome, glyph strokes take the item's accent color
    # (custom icons keep their own colors either way).
    icon(ex, draw, kind, x + 9, y, color, 1.0, plain=plain, glyph_color=color if plain else None,
         **icon_presentation(item))
    draw_text(ex, draw, item.get("label", ""), x - 5, y + 54, 78, 22, 12, THEME["white"], "center", fit=True, min_size=8)


def core_card(ex, draw, x, y, card, w=260):
    # Text boxes scale with the card; ratios reproduce the legacy w=260 offsets.
    draw_rect(ex, draw, x, y, w, 90, THEME["core_stroke"], THEME["blue_fill"], 2, 9)
    hero = card.get("icon_size") == "hero" or card.get("icon_style") == "hero"
    icon(ex, draw, card.get("icon", "file"), x + (7 if hero else 14), y + (5 if hero else 13),
         card.get("color", THEME["cyan"]), scale=1.38 if hero else 1.0, **icon_presentation(card))
    draw_text(ex, draw, card.get("title", ""), x + round(w * 0.423), y + 11, round(w * 0.385), 28, 20, THEME["white"], "center", hand=True, bold=True, fit=True, min_size=15)
    draw_text(ex, draw, card.get("body", ""), x + round(w * 0.354), y + 42, round(w * 0.577), 38, 14, THEME["white"], "center", spacing=3, fit=True, min_size=11)


def mini_card(ex, draw, x, y, w, h, card, stroke, fill):
    draw_rect(ex, draw, x, y, w, h, stroke, fill, 2, 8)
    icon(ex, draw, card.get("icon", "file"), x + 10, y + 10, card.get("color", THEME["cyan"]), **icon_presentation(card))
    draw_text(ex, draw, card.get("title", ""), x + 78, y + 12, 115, 24, 17, THEME["white"], "left", bold=True, fit=True, min_size=12)
    draw_text(ex, draw, card.get("body", ""), x + 78, y + 38, w - 92, h - 43, 12, THEME["white"], "left", spacing=3, fit=True, min_size=10)


def pack_row(ex, draw, x, y, card):
    draw_rect(ex, draw, x, y, 228, 84, THEME["green"], THEME["pack_card_fill"], 2, 8)
    icon(ex, draw, card.get("icon", "file"), x + 12, y + 10, card.get("color", THEME["cyan"]), **icon_presentation(card))
    draw_text(ex, draw, card.get("title", ""), x + 86, y + 12, 120, 25, 17, THEME["white"], "center", bold=True, fit=True, min_size=12)
    draw_text(ex, draw, card.get("body", ""), x + 80, y + 42, 135, 30, 12, THEME["white"], "center", spacing=3, fit=True, min_size=10)


def draw_chrome(ex, draw, spec, plan):
    """Shared title block, outer frame and brand signature for every layout."""
    title = spec.get("title", {})
    draw_line(ex, draw, [(29, 31), (29, 78)], THEME["purple"], 11)
    draw_text(ex, draw, title.get("prefix", "The internals of"), 45, 14, 535, 66, 47, THEME["white"], "left", hand=True, bold=True)
    draw_rect(ex, draw, 600, 27, 392, 72, THEME["highlight"], THEME["highlight"], 2, 16)
    draw_text(ex, draw, title.get("highlight", "Memory Pack"), 622, 19, 350, 76, 44, THEME["green"], "center", hand=True, bold=True)
    draw_text(ex, draw, title.get("subtitle", ""), 104, 90, 420, 25, 15, THEME["muted"], "left")
    fx, fy, fw, fh = plan["frame"]
    draw_rect(ex, draw, fx, fy, fw, fh, THEME["frame"], None, 2, 29)
    brand(ex, draw, spec.get("signature", "@archscribe"))


def render_panorama(ex, draw, spec, plan):
    inputs_plan = plan["inputs"]
    draw_rect(ex, draw, *inputs_plan["box"], THEME["green"], None, 2, 8)
    box_cx = inputs_plan["box"][0] + inputs_plan["box"][2] / 2
    draw_text(ex, draw, spec.get("input_title", "Source / Input"), box_cx - 106, 137, 210, 28, 22, THEME["white"], "center", hand=True, bold=True)
    plain_inputs = spec.get("input_style", "boxed") == "plain"
    for x, item in zip(inputs_plan["xs"], inputs_plan["items"]):
        small_input(ex, draw, x, 174, item, plain=plain_inputs)
    acx = inputs_plan["arrow_cx"]
    draw_line(ex, draw, [(acx, 258), (acx, 316)], THEME["white"], 2, "solid", True)

    core = spec.get("core", {})
    core_plan = plan["core"]
    card_w = core_plan["w"]
    draw_rect(ex, draw, *core_plan["group"], THEME["core_stroke"], THEME["core_fill"], 2, 20)
    draw_text(ex, draw, core.get("title", "Archive Core"), 462, 327, 210, 31, 22, THEME["white"], "center", hand=True, bold=True)
    draw_text(ex, draw, core.get("subtitle", "(local read-only pipeline)"), 635, 336, 220, 23, 13, THEME["white"], "center")
    for i, (x, card) in enumerate(zip(core_plan["xs"], core_plan["cards"])):
        core_card(ex, draw, x, 366, card, w=card_w)
        if i:
            draw_line(ex, draw, [(core_plan["xs"][i - 1] + card_w, 411), (x, 411)], THEME["white"], 2, "solid", True)
    last_cx = core_plan["last_cx"]
    draw_line(ex, draw, [(last_cx, 456), (last_cx, 481), (768, 481), (768, 508)], THEME["white"], 2, "solid", True)

    decision = spec.get("decision", {"title": "Ready?", "body": "safe, traced\nusable"})
    draw_diamond(ex, draw, 706, 508, 120, 120, THEME["green"], THEME["decision_fill"], 2)
    draw_text(ex, draw, decision.get("title", "Ready?"), 728, 541, 78, 26, 20, THEME["white"], "center", fit=True, min_size=14)
    draw_text(ex, draw, decision.get("body", ""), 728, 569, 78, 34, 14, THEME["white"], "center", fit=True, min_size=10)
    draw_rect(ex, draw, 1022, 527, 100, 94, THEME["core_stroke"], THEME["blue_fill"], 2, 9)
    icon(ex, draw, spec.get("output", {}).get("icon", "file"), 1035, 537, THEME["cyan"], **icon_presentation(spec.get("output", {})))
    draw_text(ex, draw, spec.get("output", {}).get("label", "Report"), 1038, 588, 70, 24, 18, THEME["white"], "center", bold=True, fit=True, min_size=12)
    draw_line(ex, draw, [(826, 568), (1022, 568)], THEME["white"], 2, "solid", True)
    draw_text(ex, draw, decision.get("yes_label", "Yes"), 877, 543, 91, 25, 15, THEME["white"], "center", fit=True, min_size=10)
    loop_x = core_plan["first_loop_x"]
    draw_line(ex, draw, [(707, 568), (510, 568), (loop_x, 568), (loop_x, 456)], THEME["muted"], 2, "dashed", True)
    draw_text(ex, draw, spec.get("loop_label", "Loop until checked and updated"), 330, 504, 540, 25, 14, THEME["white"], "center")
    draw_text(ex, draw, spec.get("retry_label", "No / missing source or conflict"), 475, 580, 250, 24, 14, THEME["white"], "center")

    panels = plan["panels"]
    present = panels["present"]
    px = panels["x"]

    if "left_panel" in present:
        lx = px["left_panel"]
        left = spec.get("left_panel", {})
        draw_line(ex, draw, [(lx + 117, 637), (lx + 117, 736)], THEME["white"], 2, "solid", True)
        draw_line(ex, draw, [(lx + 166, 736), (lx + 166, 637)], THEME["white"], 2, "solid", True)
        draw_text(ex, draw, left.get("down_label", "Read"), lx + 40, 677, 105, 22, 16, THEME["white"], "center", fit=True, min_size=10)
        draw_text(ex, draw, left.get("up_label", "Context"), lx + 169, 676, 76, 22, 16, THEME["white"], "center", fit=True, min_size=10)
        draw_rect(ex, draw, lx, 735, 281, 344, THEME["green"], THEME["source_fill"], 2, 14)
        draw_text(ex, draw, left.get("title", "Memory Sources"), lx + 19, 752, 180, 30, 22, THEME["white"], "left", hand=True, bold=True)
        if left.get("badge_file"):
            custom_image(ex, draw, left["badge_file"], lx + 192, 758, 76, 28)
        else:
            draw_text(ex, draw, left.get("badge", "read only"), lx + 205, 779, 62, 18, 11, THEME["green"], "center")
        for (y, h), card in zip(graph_model.LEFT_CARD_SLOTS, left.get("cards", [])[:3]):
            mini_card(ex, draw, lx + 12, y, 258, h, card, THEME["green"], THEME["src_card_fill"])

    if "center_panel" in present:
        cx0 = px["center_panel"]
        center = spec.get("center_panel", {})
        draw_rect(ex, draw, cx0, 734, 522, 346, THEME["purple"], THEME["archive_fill"], 2, 14)
        draw_text(ex, draw, center.get("title", "Archive Layers"), cx0 + 179, 756, 180, 34, 23, THEME["white"], "center", hand=True, bold=True)
        draw_text(ex, draw, center.get("subtitle", "(local, readable, traceable storage)"), cx0 + 111, 790, 300, 24, 14, THEME["white"], "center")
        layer_xs = panels["layer_xs"]
        layer_cards = list(center.get("cards", []))[:4]
        while len(layer_cards) < len(layer_xs):
            layer_cards.append({"title": "", "body": "", "icon": "file"})
        for i, (x, card) in enumerate(zip(layer_xs, layer_cards)):
            draw_rect(ex, draw, x, 827, 112, 142, THEME["purple"], THEME["layer_card_fill"], 2, 8)
            icon(ex, draw, card.get("icon", "file"), x + 18, 840, card.get("color", THEME["cyan"]), **icon_presentation(card))
            draw_text(ex, draw, card.get("title", ""), x + 10, 910, 92, 25, 18, THEME["white"], "center", bold=True, fit=True, min_size=12)
            draw_text(ex, draw, card.get("body", ""), x + 8, 936, 96, 28, 11, THEME["white"], "center", spacing=2, fit=True, min_size=8)
            if i:
                draw_line(ex, draw, [(layer_xs[i - 1] + 112, 890), (x, 890)], THEME["white"], 2, "solid", True)
        draw_rect(ex, draw, cx0 + 158, 1010, 220, 50, THEME["purple"], THEME["archive_fill"], 2, 8)
        draw_text(ex, draw, center.get("footer", "Redact + Dedup"), cx0 + 195, 1017, 165, 33, 20, THEME["white"], "center", hand=True, bold=True, fit=True, min_size=14)
        draw_line(ex, draw, [(cx0 + 270, 969), (cx0 + 270, 1010)], THEME["muted"], 2, "dashed", True)

    if "right_panel" in present:
        rx = px["right_panel"]
        right = spec.get("right_panel", {})
        if "center_panel" in present:
            c_right = px["center_panel"] + 522
            draw_line(ex, draw, [(c_right, 890), (rx, 890)], THEME["white"], 2, "solid", True)
            draw_text(ex, draw, right.get("incoming_label", "Compile"), rx - 54, 868, 65, 20, 12, THEME["white"], "center")
        draw_rect(ex, draw, rx, 735, 258, 344, THEME["green"], THEME["pack_fill"], 2, 14)
        draw_text(ex, draw, right.get("title", "Memory Pack"), rx + 44, 750, 170, 34, 22, THEME["white"], "center", hand=True, bold=True)
        for y, card in zip(graph_model.PACK_YS, right.get("cards", [])[:3]):
            pack_row(ex, draw, rx + 14, y, card)
        draw_line(ex, draw, [(rx + 132, 735), (rx + 132, 691), (766, 691), (766, 628)], THEME["white"], 2, "solid", True)
        draw_text(ex, draw, right.get("return_label", "Reusable"), 867, 669, 75, 23, 16, THEME["white"], "center")

    plus_marks = [(375, 292, THEME["cyan"]), (704, 293, THEME["green"]), (1048, 292, THEME["purple"])]
    if present:
        plus_marks += [(315, 707, THEME["green"]), (868, 707, THEME["purple"])]
    for x, y, color in plus_marks:
        draw_line(ex, draw, [(x - 8, y), (x + 8, y)], color, 2)
        draw_line(ex, draw, [(x, y - 8), (x, y + 8)], color, 2)


def render_swimlane(ex, draw, spec, plan):
    if spec.get("subtitle"):
        draw_text(ex, draw, spec["subtitle"], 105, 145, 1000, 30, 17, THEME["muted"], "center")
    lanes = plan["lanes"]
    col_w = lanes.get("column_w", 178)
    for i, lane in enumerate(lanes["items"]):
        y, lane_h = lane["_y"], lane["_h"]
        tint = lane.get("_tint") or {"stroke": "green", "band": "source_fill", "column": "green_fill"}
        stroke = THEME[tint["stroke"]]
        draw_rect(ex, draw, lanes["x"], y, lanes["w"], lane_h, stroke, THEME[tint["band"]], 2, 12)
        # Darker title column on the left (reference style), then title + subtitle.
        draw_rect(ex, draw, lanes["x"], y, col_w, lane_h, stroke, THEME[tint["column"]], 1.5, 12)
        title_h = 40 if lane.get("subtitle") else 74
        draw_text(ex, draw, lane.get("title", ""), lanes["x"] + 18, y + (18 if lane.get("subtitle") else 24),
                  col_w - 34, title_h, 22, THEME["white"], "left", hand=True, bold=True, fit=True, min_size=14)
        if lane.get("subtitle"):
            draw_text(ex, draw, lane.get("subtitle", ""), lanes["x"] + 18, y + 62, col_w - 34, lane_h - 74, 13,
                      THEME["muted"], "left", spacing=2, fit=True, min_size=9)
        for step in lane.get("steps", []):
            x, sy, w, h = step["_box"]
            draw_rect(ex, draw, x, sy, w, h, stroke, THEME["icon_fill"], 1.5, 10)
            icon(ex, draw, step.get("icon", "file"), x + 9, sy + 15, step.get("color", THEME["cyan"]), **icon_presentation(step))
            draw_text(ex, draw, step.get("title", ""), x + 66, sy + 10, w - 74, 58, 15, THEME["white"], "left", bold=True, fit=True, min_size=9)
    for edge in plan["edges"]:
        pts = [tuple(p) for p in edge["points"]]
        color = THEME.get(edge.get("color"), THEME["muted"] if edge.get("loop") else THEME["white"])
        draw_line(ex, draw, pts, color, 2, edge.get("style", "solid"), True)
        if edge.get("label"):
            mx, my, horiz = _edge_label_anchor(pts)
            if edge.get("loop"):
                lw, ly = 260, my - 22
            elif horiz and abs(pts[0][1] - pts[-1][1]) < 4:
                # Straight in-lane hop: the gap is narrow, so lift the label
                # into the empty strip above the cards (arrow y = card center).
                lw, ly = 150, my - 59
            elif horiz:
                lw, ly = 200, my - 22
            else:
                lw, ly = 130, my - 11
            draw_text(ex, draw, edge["label"], mx - lw / 2, ly, lw, 18, 12,
                      THEME["muted"] if edge.get("loop") else THEME["white"], "center", fit=True, min_size=9)


def _edge_label_anchor(points):
    """Midpoint of the longest segment: labels sit on the calm lane run, not
    on the short stubs that leave/enter a node."""
    best, best_len = None, -1
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        if seg > best_len:
            best_len = seg
            best = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, abs(b[0] - a[0]) >= abs(b[1] - a[1]))
    return best


def render_graph(ex, draw, spec, plan):
    if spec.get("subtitle"):
        draw_text(ex, draw, spec["subtitle"], 105, 145, 1000, 30, 17, THEME["muted"], "center")

    for edge in plan["graph_edges"]:
        pts = [tuple(p) for p in edge["points"]]
        color = THEME.get(edge.get("color"), THEME["muted"] if edge.get("loop") else THEME["white"])
        draw_line(ex, draw, pts, color, 2, edge.get("style", "solid"), True)
        if edge.get("label"):
            mx, my, horiz = _edge_label_anchor(pts)
            lw = 150 if horiz else 130
            ly = my - 24 if horiz else my - 11
            draw_text(ex, draw, edge["label"], mx - lw / 2, ly, lw, 22, 13,
                      THEME["muted"] if edge.get("loop") else THEME["white"], "center", fit=True, min_size=9)

    for g in plan["graph_nodes"]:
        x, y, w, h = g["_box"]
        stroke, fill = THEME[g["_accent"]], THEME[g["_fill"]]
        kind = g["_kind"]
        if kind == "decision":
            draw_diamond(ex, draw, x, y, w, h, stroke, THEME["decision_fill"], 2)
            draw_text(ex, draw, g.get("label", ""), x + 18, y + h / 2 - 22, w - 36, 26, 18,
                      THEME["white"], "center", hand=True, bold=True, fit=True, min_size=11)
            draw_text(ex, draw, g.get("body", ""), x + 20, y + h / 2 + 6, w - 40, 26, 12,
                      THEME["muted"], "center", fit=True, min_size=8)
            continue
        if kind == "terminal":
            draw_rect(ex, draw, x, y, w, h, stroke, THEME["icon_fill"], 2, min(w, h) // 2)
            draw_text(ex, draw, g.get("label", ""), x + 14, y, w - 28, h, 17,
                      THEME["white"], "center", hand=True, bold=True, fit=True, min_size=11)
            continue
        draw_rect(ex, draw, x, y, w, h, stroke, fill, 2, 12)
        icon_xy = g.get("_icon_xy")
        if icon_xy and w < 150:  # narrow card: icon on top, label under it
            icon(ex, draw, g["icon"], icon_xy[0], icon_xy[1], g.get("color", THEME["cyan"]), **icon_presentation(g))
            draw_text(ex, draw, g.get("label", ""), x + 6, icon_xy[1] + 62, w - 12, 24, 15,
                      THEME["white"], "center", bold=True, fit=True, min_size=10)
        elif icon_xy:
            icon(ex, draw, g["icon"], icon_xy[0], icon_xy[1], g.get("color", THEME["cyan"]), **icon_presentation(g))
            tx = icon_xy[0] + 70
            if g.get("body"):
                draw_text(ex, draw, g.get("label", ""), tx, y + 12, x + w - tx - 10, 26, 17,
                          THEME["white"], "left", hand=True, bold=True, fit=True, min_size=11)
                draw_text(ex, draw, g.get("body", ""), tx, y + 40, x + w - tx - 10, h - 50, 12,
                          THEME["muted"], "left", spacing=2, fit=True, min_size=8)
            else:
                draw_text(ex, draw, g.get("label", ""), tx, y, x + w - tx - 10, h, 17,
                          THEME["white"], "left", hand=True, bold=True, fit=True, min_size=11)
        else:
            if g.get("body"):
                draw_text(ex, draw, g.get("label", ""), x + 10, y + 12, w - 20, 28, 17,
                          THEME["white"], "center", hand=True, bold=True, fit=True, min_size=11)
                draw_text(ex, draw, g.get("body", ""), x + 12, y + 42, w - 24, h - 52, 12,
                          THEME["muted"], "center", spacing=2, fit=True, min_size=8)
            else:
                draw_text(ex, draw, g.get("label", ""), x + 10, y, w - 20, h, 17,
                          THEME["white"], "center", hand=True, bold=True, fit=True, min_size=11)

    if spec.get("footer"):
        fy = plan["canvas"]["height"] - 74
        draw_text(ex, draw, spec["footer"], 105, fy, 1000, 26, 14, THEME["muted"], "center")


LAYOUT_PAINTERS = {
    "panorama": render_panorama,
    "swimlane": render_swimlane,
    "graph": render_graph,
}

# Plan of the most recent render_static call: geometry, animation paths and
# graph topology for the active layout (see scripts/graph_model.py).
CURRENT_PLAN = None


def render_static(spec):
    global CURRENT_PLAN
    plan = graph_model.build_plan(spec)
    if plan["layout"] == "graph":
        width = plan["canvas"]["width"]
        height = plan["canvas"]["height"]
    else:
        width = spec.get("canvas", {}).get("width", plan["canvas"]["width"])
        height = spec.get("canvas", {}).get("height", plan["canvas"]["height"])
    plan["canvas"] = {"width": width, "height": height}
    CURRENT_PLAN = plan

    ex = Excal(width, height)
    img = Image.new("RGBA", (width * SCALE, height * SCALE), hex_rgba(THEME["bg"]))
    draw = ImageDraw.Draw(img)
    draw_chrome(ex, draw, spec, plan)
    LAYOUT_PAINTERS[plan["layout"]](ex, draw, spec, plan)
    return ex, img.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")


def finish_glow_rects(plan, mode=None):
    """Resolve the plan's glow rectangles for the requested finish mode."""
    mode = mode or FINISH_MODE
    key = "light" if mode == "light" else "color"
    return [(tuple(item["box"]), item[key], item["width"]) for item in plan["glow_rects"]]


def render_static_with_ops(spec):
    """Run render_static while recording the primitive op stream.

    Returns (excal_builder, raster_image, ops_document). The ops document is
    JSON-friendly and consumed by scripts/svg_renderer.py, which replays it
    with rough.js inside Chromium so both renderers share one layout.
    """
    global OPS_SINK
    ops = []
    OPS_SINK = ops
    try:
        ex, img = render_static(spec)
    finally:
        OPS_SINK = None
    plan = CURRENT_PLAN
    return ex, img, {
        "canvas": {
            "width": plan["canvas"]["width"],
            "height": plan["canvas"]["height"],
            "fps": spec.get("canvas", {}).get("fps", DEFAULT_FPS),
            "frames": spec.get("canvas", {}).get("frames", DEFAULT_FRAMES),
        },
        "style": CURRENT_STYLE,
        "layout": plan["layout"],
        "bg": THEME["bg"],
        "finish": {
            "mode": FINISH_MODE,
            "glow_rects": [
                {"box": list(box), "color": THEME[color_key], "width": w}
                for box, color_key, w in finish_glow_rects(plan)
            ],
        },
        "theme": dict(THEME),
        "animation": {
            "flow_paths": [
                {"points": [list(p) for p in fp["points"]], "color": THEME[fp["color"]], "offset": fp["offset"]}
                for fp in plan["flow_paths"]
            ],
            "pulse_targets": [
                {"box": list(pt["box"]), "color": THEME[pt["color"]]} for pt in plan["pulse_targets"]
            ],
        },
        "graph": {"canvas": plan["canvas"], "nodes": plan["nodes"], "edges": _json_edges(plan["edges"])},
        "ops": ops,
    }


def _json_edges(edges):
    return [dict(edge, points=[list(p) for p in edge["points"]]) for edge in edges]


def light_finish(base, plan):
    """Clean finish for light styles: soft colored frame glow, no grain/vignette."""
    width, height = base.size
    img = base.convert("RGBA")
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for rect, color_key, line_width in finish_glow_rects(plan, "light"):
        g.rounded_rectangle(rect, radius=18, outline=hex_rgba(THEME[color_key], 70), width=line_width)
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3)))
    return img.convert("RGB")


def premium_finish(base, plan=None):
    plan = plan or CURRENT_PLAN
    if FINISH_MODE == "light":
        return light_finish(base, plan)
    width, height = base.size
    img = base.convert("RGBA")
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for rect, color_key, line_width in finish_glow_rects(plan, "dark"):
        g.rounded_rectangle(rect, radius=18, outline=hex_rgba(THEME[color_key], 70), width=line_width)
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
    for radius, alpha in [(15, 34), (9, 90), (4.5, 205)]:
        a = int(alpha * strength)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=hex_rgba(color, a))
    core = 2.4 * (0.6 + 0.4 * strength)
    draw.ellipse((x - core, y - core, x + core, y + core), fill=hex_rgba(THEME["white"], int(235 * min(1.0, strength + 0.15))))


def draw_flow_segment(draw, points, color, head_t, length_frac=0.18, width=6, samples=16):
    """Draw a bright 'energy segment' that travels along the polyline (effect A).

    The lit portion runs from the head position backwards by `length_frac` of the
    total path length, brightest at the head and fading toward the tail. Distances
    are clamped to the path so the segment never wraps across the start/end seam.
    """
    total = path_len(points)
    if total <= 0:
        return
    head_d = (head_t % 1.0) * total
    seg_len = length_frac * total
    prev = None
    for i in range(samples + 1):
        d = head_d - seg_len * (i / samples)
        if d < 0:
            break
        pt = point_at_distance(points, d)
        if prev is not None:
            frac = 1.0 - (i - 0.5) / samples
            alpha = int(165 * frac)
            w = max(1, int(round(width * (0.35 + 0.65 * frac))))
            draw.line([prev, pt], fill=hex_rgba(color, alpha), width=w)
        prev = pt


def pulse_rect(draw, rect, color, phase, radius=10):
    x1, y1, x2, y2 = rect
    alpha = int(36 + 42 * (0.5 + 0.5 * math.sin(phase)))
    for grow, width in [(0, 2), (4, 1)]:
        draw.rounded_rectangle((x1 - grow, y1 - grow, x2 + grow, y2 + grow), radius=radius + grow, outline=hex_rgba(color, max(18, alpha - grow * 7)), width=width)


def icon_center(kind, x, y, scale=1.0):
    tile = ICON_TILE * scale
    return x + tile / 2, y + tile / 2


def collect_icon_instances(spec, plan=None):
    """Icon instances (kind/x/y/color/ordinal) for the icon-motion layer.

    Geometry comes from the layout plan so every layout is covered; the
    ordinals stay stable within one plan, which is all the effects need.
    """
    plan = plan or graph_model.build_plan(spec or {})
    instances = []
    for entry in plan["icons"]:
        instances.append(
            {
                "kind": entry["kind"],
                "x": entry["x"],
                "y": entry["y"],
                "scale": entry.get("scale", 1.0),
                "color": entry.get("color") or THEME["cyan"],
                "group": entry["group"],
                "ordinal": entry["ordinal"],
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


def draw_icon_motion_layer(draw, spec, progress, idx, plan=None):
    icons = collect_icon_instances(spec, plan)
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


def animate_frame(base, idx, total, spec=None, icon_motion=True, plan=None):
    plan = plan or CURRENT_PLAN or graph_model.build_plan(spec or {})
    frame = base.convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    progress = idx / total
    paths = [([tuple(p) for p in fp["points"]], THEME[fp["color"]], fp["offset"]) for fp in plan["flow_paths"]]
    flow_speed = 1          # integer loops per GIF -> seamless; keep slow & readable
    heads_per_path = 2      # multiple dots streaming along each arrow (effect B)
    trail_dots = 6          # comet tail length (effect C)
    trail_step = 0.020
    for points, color, offset in paths:
        for h in range(heads_per_path):
            head_t = (progress * flow_speed + offset + h / heads_per_path) % 1.0
            draw_flow_segment(draw, points, color, head_t)   # effect A
            for k in range(trail_dots):                       # effect C + D
                tt = head_t - k * trail_step
                if tt < 0:
                    continue
                strength = 0.95 * (1.0 - k / trail_dots) ** 1.25
                x, y = point_at_fraction(points, tt)
                draw_glow_dot(draw, x, y, color, strength)
    if icon_motion:
        draw_icon_motion_layer(draw, spec, progress, idx, plan)
    pulse_targets = [(tuple(pt["box"]), THEME[pt["color"]]) for pt in plan["pulse_targets"]]
    if pulse_targets:
        active = (idx // 6) % len(pulse_targets)
        for pos, (rect, color) in enumerate(pulse_targets):
            if pos == active:
                pulse_rect(draw, rect, color, progress * math.tau * 2, 12)
    frame.alpha_composite(overlay)
    return frame.convert("RGB")


ICON_GLYPH_FRAMES = 24


def icon_requests(spec, plan=None):
    seen = []
    for inst in collect_icon_instances(spec, plan):
        if is_custom_icon(inst["kind"]):
            # Custom icons are painted statically by icon(); the browser glyph
            # engine only serves the bundled Tabler set.
            continue
        key = (resolve_icon_name(inst["kind"]), inst.get("color", THEME["cyan"]))
        if key not in seen:
            seen.append(key)
    return seen


def stamp_glyphs(base_rgb, spec, glyph_frames, gif_t, plan=None):
    if not glyph_frames:
        return base_rgb
    total = ICON_GLYPH_FRAMES
    pick = int(round(gif_t * total)) % total
    canvas = base_rgb.convert("RGBA")
    for inst in collect_icon_instances(spec, plan):
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


def render_browser_glyphs(spec, plan=None):
    if icon_browser is None or not icon_browser.is_available():
        return {}
    glyph_px = int(round((ICON_TILE - 2 * ICON_PAD)))
    requests = icon_requests(spec, plan)
    if not requests:
        return {}
    return icon_browser.render_glyph_frames(
        requests,
        glyph_px=max(28, glyph_px),
        frames=ICON_GLYPH_FRAMES,
        base_color=THEME["white"],
        stroke=2.0,
    )


def spec_uses_illustrations(node):
    if isinstance(node, dict):
        return node.get("icon_style") in ("illustrated", "hero") or any(spec_uses_illustrations(v) for v in node.values())
    if isinstance(node, list):
        return any(spec_uses_illustrations(v) for v in node)
    return False


def write_outputs(spec, outdir, basename, icon_engine="pillow", formats=("gif", "png", "excalidraw")):
    global ICON_GLYPH_MODE
    outdir.mkdir(parents=True, exist_ok=True)
    canvas_frames = spec.get("canvas", {}).get("frames", DEFAULT_FRAMES)

    glyph_frames = {}
    use_browser = False
    if icon_engine in ("browser", "auto") and not spec_uses_illustrations(spec):
        glyph_frames = render_browser_glyphs(spec)
        use_browser = bool(glyph_frames)
        if icon_engine == "browser" and not use_browser:
            print("warning: browser icon engine unavailable, falling back to pillow", file=sys.stderr)

    ICON_GLYPH_MODE = "skip" if use_browser else "draw"
    try:
        ex, static = render_static(spec)
        plan = CURRENT_PLAN
        final = premium_finish(static, plan)
    finally:
        ICON_GLYPH_MODE = "draw"

    png_path = outdir / f"{basename}.png"
    gif_path = outdir / f"{basename}.gif"
    excalidraw_path = outdir / f"{basename}.excalidraw"

    want = set(formats)
    need_animation = "gif" in want
    if use_browser and ("png" in want or need_animation):
        png_img = stamp_glyphs(final, spec, glyph_frames, 0.0, plan)
        if "png" in want:
            png_img.save(png_path, "PNG")
        frames = [] if not need_animation else [
            animate_frame(stamp_glyphs(final, spec, glyph_frames, i / canvas_frames, plan), i, canvas_frames, spec, icon_motion=False, plan=plan)
            for i in range(canvas_frames)
        ]
    else:
        if "png" in want:
            final.save(png_path, "PNG")
        frames = [animate_frame(final, i, canvas_frames, spec, plan=plan) for i in range(canvas_frames)] if need_animation else []

    duration = int(1000 / spec.get("canvas", {}).get("fps", DEFAULT_FPS))
    if "gif" in want:
        frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=False)
    if "excalidraw" in want:
        ex.write(excalidraw_path)
    result = {
        "elements": len(ex.elements),
        "canvas": dict(plan["canvas"]),
        "icon_engine": "browser" if use_browser else "pillow",
    }
    if "png" in want:
        result["png"] = str(png_path)
    if "gif" in want:
        result["gif"] = str(gif_path)
    if "excalidraw" in want:
        result["excalidraw"] = str(excalidraw_path)
    return result


def write_outputs_browser(spec, outdir, basename, animation="flow", formats=("gif", "mp4", "png", "excalidraw")):
    """Render via the rough.js/Chromium pipeline (scripts/svg_renderer.py)."""
    global ICON_GLYPH_MODE
    outdir.mkdir(parents=True, exist_ok=True)
    ICON_GLYPH_MODE = "skip"  # ops carry the icon; skip Pillow glyph work
    try:
        ex, _static, doc = render_static_with_ops(spec)
    finally:
        ICON_GLYPH_MODE = "draw"

    browser_formats = [f for f in formats if f in ("png", "gif", "mp4", "svg", "html")]
    result = svg_renderer.render_all(doc, outdir, basename, animation=animation, formats=browser_formats)

    if "excalidraw" in formats:
        excalidraw_path = outdir / f"{basename}.excalidraw"
        ex.write(excalidraw_path)
        result["excalidraw"] = str(excalidraw_path)
    result["elements"] = len(ex.elements)
    result["canvas"] = dict(doc["canvas"])
    result["renderer"] = "browser"
    return result


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


def _probe_mp4(mp4_path):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,pix_fmt,nb_frames,r_frame_rate",
        "-of", "json", str(mp4_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    streams = json.loads(proc.stdout).get("streams", [])
    return streams[0] if streams else None


def _graph_content_bounds(plan):
    xs, ys = [], []
    for node in plan.get("graph_nodes", []):
        x, y, w, h = node["_box"]
        xs.extend([x, x + w])
        ys.extend([y, y + h])
    for edge in plan.get("graph_edges", []):
        for x, y in edge.get("points", []):
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def graph_layout_checks(spec):
    if graph_model.get_layout(spec) != "graph":
        return []
    plan = graph_model.build_plan(spec)
    width, height = plan["canvas"]["width"], plan["canvas"]["height"]
    bounds = _graph_content_bounds(plan)
    checks = []
    if bounds:
        left, top, right, bottom = bounds
        pad = 18
        checks.append({
            "name": "graph_content_inside_canvas",
            "ok": left >= pad and top >= 117 and right <= width - pad and bottom <= height - 96,
            "bounds": [round(left), round(top), round(right), round(bottom)],
            "canvas": {"width": width, "height": height},
            "fix": "switch to direction:'down', reduce graph nodes, or let graph use its natural canvas",
        })
        content_h = bottom - top
        checks.append({
            "name": "graph_vertical_balance",
            "ok": content_h / max(1, height) >= 0.42,
            "content_ratio": round(content_h / max(1, height), 3),
            "fix": "avoid forcing a tall canvas for a shallow graph; graph now ignores width/height overrides",
        })
    meta = plan.get("graph_meta", {})
    checks.append({
        "name": "graph_long_chain_orientation",
        "ok": not (meta.get("requested_direction") == "right" and meta.get("n_layers", 0) > 7 and not meta.get("auto_stacked")),
        "layers": meta.get("n_layers"),
        "actual_direction": "right" if meta.get("horizontal") else "down",
        "fix": "use direction:'down' for more than 7 sequential layers",
    })
    return checks


def check_outputs(result, spec):
    """Validate whichever artifacts are present in the render result.

    GIF/PNG/Excalidraw checks preserve the classic contract; MP4 is
    validated when produced. Missing artifact keys are simply skipped so the
    same checker covers every --formats combination.
    """
    canvas = spec.get("canvas", {})
    result_canvas = result.get("canvas", {})
    expected_width = result_canvas.get("width") or canvas.get("width", DEFAULT_W)
    expected_height = result_canvas.get("height") or canvas.get("height", DEFAULT_H)
    expected_frames = result.get("frames", canvas.get("frames", DEFAULT_FRAMES))
    expected_fps = canvas.get("fps", DEFAULT_FPS)

    checks = []

    if "gif" in result:
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

    if "mp4" in result:
        mp4_path = Path(result["mp4"])
        checks.append({"name": "mp4_exists", "ok": mp4_path.is_file() and mp4_path.stat().st_size > 0})
        stream = _probe_mp4(mp4_path)
        if stream is not None:
            checks.extend(
                [
                    {"name": "mp4_width", "ok": int(stream.get("width", 0)) in (expected_width, expected_width - 1), "expected": expected_width, "actual": stream.get("width")},
                    {"name": "mp4_height", "ok": int(stream.get("height", 0)) in (expected_height, expected_height - 1), "expected": expected_height, "actual": stream.get("height")},
                    {"name": "mp4_pix_fmt", "ok": stream.get("pix_fmt") == "yuv420p", "actual": stream.get("pix_fmt")},
                ]
            )

    if "svg" in result:
        svg_path = Path(result["svg"])
        svg_ok = svg_path.is_file() and svg_path.stat().st_size > 0
        checks.append({"name": "svg_exists", "ok": svg_ok})
        if svg_ok:
            svg_text = svg_path.read_text(encoding="utf-8")
            checks.append({"name": "svg_fonts_embedded", "ok": "@font-face" in svg_text and "Excalifont" in svg_text})

    if "html" in result:
        html_path = Path(result["html"])
        html_ok = html_path.is_file() and html_path.stat().st_size > 0
        checks.append({"name": "html_exists", "ok": html_ok})
        if html_ok:
            html_text = html_path.read_text(encoding="utf-8")
            expected_nodes = len(graph_model.build_graph(spec)["nodes"])
            hotspots = html_text.count('class="hotspot"')
            checks.extend(
                [
                    {"name": "html_hotspots", "ok": hotspots == expected_nodes, "expected": expected_nodes, "actual": hotspots},
                    {"name": "html_graph_embedded", "ok": "ARCHSCRIBE_GRAPH" in html_text},
                    {"name": "html_fonts_embedded", "ok": "@font-face" in html_text},
                ]
            )

    if "excalidraw" in result:
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

    if "png" in result:
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

    checks.extend(graph_layout_checks(spec))

    return {"ok": all(check["ok"] for check in checks), "checks": checks}


KNOWN_ICONS = set(ICON_ALIASES) | {"folder", "file", "scan", "shield", "db", "hash", "package"}

CUSTOM_ICON_SUFFIXES = {".svg", ".png"}


def resolve_icon_file(value, spec_dir=None):
    """Resolve an icon_file/badge_file value to an absolute Path.

    Relative paths are resolved against the spec file's directory (falling
    back to the current working directory).
    """
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (Path(spec_dir) if spec_dir else Path.cwd()) / path
    return path.resolve()


def resolve_custom_icons(spec, spec_dir=None):
    """Rewrite icon_file/badge_file entries into the internal '@<abs path>' form.

    Called once after the spec is loaded; everything downstream (layout plan,
    painters, op stream, browser renderer) only sees the '@' convention.
    """
    def walk(node):
        if isinstance(node, dict):
            if node.get("icon_file"):
                node["icon"] = "@" + str(resolve_icon_file(node["icon_file"], spec_dir))
            if node.get("badge_file"):
                node["badge_file"] = str(resolve_icon_file(node["badge_file"], spec_dir))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    return spec

# Top-level spec keys accepted per layout; anything else earns a warning so
# agent typos ("output s", "stage") surface immediately instead of silently
# rendering defaults.
COMMON_SPEC_KEYS = {"layout", "style", "animation", "title", "subtitle", "signature", "canvas", "density", "aspect_ratio", "motion_level"}
LAYOUT_SPEC_KEYS = {
    "panorama": COMMON_SPEC_KEYS | {
        "input_title", "input_style", "inputs", "core", "decision", "output", "loop_label", "retry_label",
        "left_panel", "center_panel", "right_panel",
    },
    "swimlane": COMMON_SPEC_KEYS | {"lanes", "connections", "footer"},
    "graph": COMMON_SPEC_KEYS | {"nodes", "edges", "direction", "footer"},
}


def validate_spec(spec, spec_dir=None):
    """Pre-flight validation with agent-actionable messages.

    Errors block rendering (wrong shapes, missing required sections).
    Warnings render fine but flag likely mistakes (unknown keys/icons,
    overlong labels that will shrink or wrap).
    """
    errors, warnings = [], []

    def err(path, message, fix):
        errors.append({"path": path, "message": message, "fix": fix})

    def warn(path, message, fix):
        warnings.append({"path": path, "message": message, "fix": fix})

    if not isinstance(spec, dict):
        err("$", "spec must be a JSON object", "wrap the content in an object: {\"layout\": ..., ...}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    for key in ("title", "canvas"):
        if key in spec and not isinstance(spec[key], dict):
            err(f"$.{key}", "must be an object", f'use "{key}": {{...}}')
    for key in ("core", "decision", "output", "left_panel", "center_panel", "right_panel", "center"):
        if key in spec and spec[key] is not None and not isinstance(spec[key], dict):
            err(f"$.{key}", "must be an object", f'use "{key}": {{...}}')
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    canvas = spec.get("canvas", {})
    limits = {"width": (480, 4096), "height": (360, 4096), "fps": (1, 60), "frames": (2, 600)}
    for key, (lo, hi) in limits.items():
        if key in canvas and (not isinstance(canvas[key], (int, float)) or isinstance(canvas[key], bool) or not lo <= canvas[key] <= hi):
            err(f"$.canvas.{key}", f"must be a number from {lo} to {hi}", f"set {key} within {lo}..{hi}")
    if spec.get("density", "balanced") not in ("airy", "balanced", "compact"):
        err("$.density", "unknown density", "use airy, balanced, or compact")
    if spec.get("aspect_ratio", "auto") not in ("auto", "landscape", "portrait", "square"):
        err("$.aspect_ratio", "unknown aspect_ratio", "use auto, landscape, portrait, or square")
    if spec.get("motion_level", "standard") not in ("none", "subtle", "standard", "cinematic"):
        err("$.motion_level", "unknown motion_level", "use none, subtle, standard, or cinematic")

    layout = spec.get("layout", "panorama")
    if layout not in graph_model.LAYOUTS:
        err("$.layout", f"unknown layout '{layout}'", f"use one of: {', '.join(graph_model.LAYOUTS)}")
        layout = "panorama"

    style = spec.get("style", "default")
    if style not in STYLE_THEMES:
        err("$.style", f"unknown style '{style}'", f"use one of: {', '.join(STYLE_THEMES)}")
    animation = spec.get("animation", "flow")
    if animation not in ANIMATION_CHOICES:
        err("$.animation", f"unknown animation '{animation}'", f"use one of: {', '.join(ANIMATION_CHOICES)}")

    for key in sorted(set(spec) - LAYOUT_SPEC_KEYS[layout]):
        warn(f"$.{key}", f"unknown key for layout '{layout}' (ignored)",
             f"valid keys: {', '.join(sorted(LAYOUT_SPEC_KEYS[layout]))}")

    if len(str(spec.get("signature", ""))) > 28:
        warn("$.signature", "is very long; the brand block will shift far into the title area",
             "keep the signature under ~28 chars")

    def check_icon_file(path, value):
        file_path = resolve_icon_file(value, spec_dir)
        if file_path.suffix.lower() not in CUSTOM_ICON_SUFFIXES:
            err(path, f"unsupported icon file type '{file_path.suffix or value}'",
                "use a local .svg or .png file")
        elif not file_path.is_file():
            err(path, f"file not found: {file_path}",
                "check the path; relative paths resolve against the spec file's folder")

    def check_icon(path, item):
        if item.get("icon_style", "outline") not in ("outline", "illustrated", "hero"):
            err(f"{path}.icon_style", "unknown icon style", "use outline, illustrated, or hero")
        if item.get("icon_size", "standard") not in ("compact", "standard", "hero"):
            err(f"{path}.icon_size", "unknown icon size", "use compact, standard, or hero")
        allowed_motion = ("auto", "none", "think-pulse", "gear-spin", "eye-scan", "memory-write",
                          "shield-check", "scope-scan", "budget-gauge", "trigger-ping", "tool-spark", "output-pop")
        if item.get("icon_motion", "auto") not in allowed_motion:
            err(f"{path}.icon_motion", "unknown icon motion", f"use one of: {', '.join(allowed_motion)}")
        if item.get("icon_file"):
            check_icon_file(f"{path}.icon_file", item["icon_file"])
            return
        icon_name = item.get("icon")
        if is_custom_icon(icon_name):
            return
        if icon_name and resolve_icon_name(icon_name) not in KNOWN_ICONS and not (
            TABLER_ICON_DIR / f"{resolve_icon_name(icon_name)}.svg"
        ).is_file():
            warn(f"{path}.icon", f"unknown icon '{icon_name}' (a plain circle will be drawn)",
                 "pick one from assets/icons/tabler/ or the aliases in references/spec-format.md")

    def check_items(path, items, min_n, max_n, label_key, label_max, required):
        if not isinstance(items, list):
            err(path, "must be a list", f"provide {min_n}-{max_n} objects")
            return
        if required and len(items) < min_n:
            err(path, f"needs at least {min_n} items (got {len(items)})", "add more items or switch layout")
        if len(items) > max_n:
            warn(path, f"has {len(items)} items; only the first {max_n} are rendered", f"trim to {max_n}")
        for i, item in enumerate(items[:max_n]):
            if not isinstance(item, dict):
                err(f"{path}[{i}]", "must be an object", f'use {{"{label_key}": "...", "icon": "..."}}')
                continue
            text = item.get(label_key, "")
            if not text:
                warn(f"{path}[{i}].{label_key}", "is empty", "add a short label so the box is not blank")
            elif len(str(text)) > label_max:
                warn(f"{path}[{i}].{label_key}", f"is long ({len(str(text))} chars); text will shrink to fit",
                     f"keep it under ~{label_max} chars")
            check_icon(f"{path}[{i}]", item)

    if layout == "panorama":
        input_style = spec.get("input_style", "boxed")
        if input_style not in ("boxed", "plain"):
            err("$.input_style", f"unknown input_style '{input_style}'",
                "use 'boxed' (default, framed tiles) or 'plain' (frameless colored icons)")
        check_items("$.inputs", spec.get("inputs", []), 2, 6, "label", 16, required=True)
        cards = spec.get("core", {}).get("cards", [])
        check_items("$.core.cards", cards, 2, 4, "title", 18, required=True)
        if spec.get("left_panel", {}).get("badge_file"):
            check_icon_file("$.left_panel.badge_file", spec["left_panel"]["badge_file"])
        for panel in ("left_panel", "center_panel", "right_panel"):
            if panel in spec and not spec.get(panel, {}).get("cards"):
                warn(f"$.{panel}.cards", "is empty, so the whole panel is omitted",
                     "add 1-4 cards or drop the panel key")
            max_cards = 4 if panel == "center_panel" else 3
            check_items(f"$.{panel}.cards", spec.get(panel, {}).get("cards", []), 0, max_cards, "title", 16, required=False)
    elif layout == "swimlane":
        lanes = spec.get("lanes", [])
        if "lanes" not in spec:
            err("$.lanes", "is required for the swimlane layout",
                'add "lanes": [{"title": ..., "subtitle": ..., "steps": [...]}, ...] (2-5 items)')
        check_items("$.lanes", lanes, 2, 5, "title", 20, required=True)
        if isinstance(lanes, list):
            for i, lane in enumerate(lanes[:5]):
                if isinstance(lane, dict):
                    check_items(f"$.lanes[{i}].steps", lane.get("steps", []), 1, 5, "title", 22, required=True)
                    if len(str(lane.get("subtitle", ""))) > 60:
                        warn(f"$.lanes[{i}].subtitle", "is long; the title column will shrink it hard",
                             "keep lane subtitles under ~60 chars")
                    if lane.get("accent") is not None and lane["accent"] not in ("green", "purple"):
                        warn(f"$.lanes[{i}].accent", f"unknown accent '{lane['accent']}' (alternating tint used)",
                             "use green or purple")
        if "connections" in spec and not isinstance(spec["connections"], list):
            err("$.connections", "must be a list", 'use [{"from": "step-id", "to": "step-id"}]')
    elif layout == "graph":
        if spec.get("direction", "right") not in ("right", "down"):
            err("$.direction", "unknown direction", "use 'right' (default) or 'down'")
        nodes = spec.get("nodes", [])
        if "nodes" not in spec:
            err("$.nodes", "is required for the graph layout",
                'add "nodes": [{"id": "plan", "label": "Plan", "icon": "plan"}, ...] (2-24 items)')
        check_items("$.nodes", nodes, 2, 24, "label", 20, required=True)
        node_ids = set()
        if isinstance(nodes, list):
            if spec.get("direction", "right") == "right" and len(nodes) > 8 and not any(
                isinstance(node, dict) and isinstance(node.get("x"), (int, float)) and isinstance(node.get("y"), (int, float))
                for node in nodes
            ):
                warn("$.direction", "long graph chains are auto-stacked downward",
                     "use direction:'down' explicitly, or reduce to 8 or fewer sequential nodes for a rightward graph")
            if any(key in canvas for key in ("width", "height")):
                warn("$.canvas", "graph layout owns width/height to prevent clipping or dead space",
                     "use canvas fps/frames for animation timing; omit width/height unless you also pin node coordinates")
            for i, node in enumerate(nodes[:24]):
                if not isinstance(node, dict):
                    continue
                nid = node.get("id")
                if not nid:
                    warn(f"$.nodes[{i}].id", "is missing; an auto id will be assigned",
                         "give every node a short stable id so edges can reference it")
                elif str(nid) in node_ids:
                    err(f"$.nodes[{i}].id", f"duplicate id '{nid}'", "make node ids unique")
                node_ids.add(str(nid) if nid else f"n{i}")
                if node.get("kind", "card") not in graph_model.GRAPH_NODE_KINDS:
                    err(f"$.nodes[{i}].kind", f"unknown kind '{node.get('kind')}'",
                        "use card (default), decision, or terminal")
                if node.get("accent") is not None and node["accent"] not in graph_model.GRAPH_ACCENTS:
                    warn(f"$.nodes[{i}].accent", f"unknown accent '{node['accent']}' (auto color used)",
                         f"use one of: {', '.join(sorted(graph_model.GRAPH_ACCENTS))}")
                has_x, has_y = isinstance(node.get("x"), (int, float)), isinstance(node.get("y"), (int, float))
                if has_x != has_y:
                    warn(f"$.nodes[{i}]", "has only one of x/y; the node falls back to auto layout",
                         "give both x and y (box center) or neither")
        edges = spec.get("edges", [])
        if not isinstance(edges, list):
            err("$.edges", "must be a list",
                'use [{"from": "plan", "to": "act"}, {"from": "check", "to": "plan", "kind": "loop"}]')
        else:
            if len(edges) > 40:
                warn("$.edges", f"has {len(edges)} edges; only the first 40 are rendered", "trim to 40")
            for i, edge in enumerate(edges[:40]):
                if not isinstance(edge, dict):
                    err(f"$.edges[{i}]", "must be an object", 'use {"from": "id", "to": "id"}')
                    continue
                for end in ("from", "to"):
                    if not edge.get(end):
                        err(f"$.edges[{i}].{end}", "is required", "reference a node id")
                    elif node_ids and str(edge[end]) not in node_ids:
                        err(f"$.edges[{i}].{end}", f"references unknown node '{edge[end]}'",
                            f"use one of: {', '.join(sorted(node_ids))}")
                if edge.get("kind", "flow") not in ("flow", "loop"):
                    err(f"$.edges[{i}].kind", f"unknown kind '{edge.get('kind')}'",
                        "use flow (default) or loop (dashed return channel)")
                if edge.get("accent") is not None and edge["accent"] not in graph_model.GRAPH_ACCENTS:
                    warn(f"$.edges[{i}].accent", f"unknown accent '{edge['accent']}' (auto color used)",
                         f"use one of: {', '.join(sorted(graph_model.GRAPH_ACCENTS))}")
                if edge.get("label") and len(str(edge["label"])) > 24:
                    warn(f"$.edges[{i}].label", "is long; edge labels shrink to fit",
                         "keep edge labels under ~24 chars")

    output = spec.get("output")
    if isinstance(output, dict) and output.get("icon_file"):
        check_icon_file("$.output.icon_file", output["icon_file"])

    title = spec.get("title", {})
    if isinstance(title, dict):
        highlight = str(title.get("highlight", ""))
        if len(highlight) > 16:
            warn("$.title.highlight", f"is long ({len(highlight)} chars) for the highlight box",
                 "keep it under ~16 chars; move detail into title.subtitle")
    else:
        err("$.title", "must be an object", '{"prefix": ..., "highlight": ..., "subtitle": ...}')

    return {"ok": not errors, "errors": errors, "warnings": warnings}


DEFAULT_FORMATS_BROWSER = "gif,mp4,png,excalidraw"
DEFAULT_FORMATS_PILLOW = "gif,png,excalidraw"
ALL_FORMATS = {"gif", "mp4", "png", "excalidraw", "svg", "html"}
BROWSER_ONLY_FORMATS = {"mp4", "svg", "html"}


def missing_requested_formats(result, formats):
    return [fmt for fmt in formats if fmt not in result]


def main():
    parser = argparse.ArgumentParser(description="Render a premium hand-drawn animated diagram from a JSON spec.")
    parser.add_argument("--spec", required=True, help="Path to spec JSON.")
    parser.add_argument("--outdir", required=True, help="Output directory.")
    parser.add_argument("--basename", default="animated-diagram", help="Output basename.")
    parser.add_argument("--verify", action="store_true", help="Print frame-diff verification after rendering.")
    parser.add_argument("--check", action="store_true", help="Validate the produced output contracts; exits nonzero on failure.")
    parser.add_argument(
        "--renderer",
        choices=["auto", "browser", "pillow"],
        default="auto",
        help="Diagram renderer: 'browser' replays the layout with rough.js in headless Chromium "
        "(hand-drawn shapes, webfonts, animation presets, MP4); 'pillow' is the classic dependency-light "
        "raster pipeline; 'auto' prefers browser when available.",
    )
    parser.add_argument(
        "--animation",
        choices=list(ANIMATION_CHOICES),
        default=None,
        help="Animation preset (browser renderer): 'flow' eased energy beams (default), "
        "'draw' whiteboard build-up, 'relay' narrative hand-off. Overrides the spec 'animation' field.",
    )
    parser.add_argument(
        "--formats",
        default=None,
        help="Comma-separated outputs. Browser renderer default: gif,mp4,png,excalidraw "
        "(svg and html also available). Pillow renderer default: gif,png,excalidraw.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the spec and exit without rendering (exit 2 on errors). "
        "Prints field-level errors/warnings as JSON.",
    )
    parser.add_argument(
        "--icon-engine",
        choices=["auto", "browser", "pillow"],
        default="auto",
        help="Icon renderer for the pillow pipeline: 'browser' uses headless Chromium for crisp animated icons, "
        "'pillow' stays dependency-light, 'auto' prefers browser when available.",
    )
    parser.add_argument(
        "--style",
        choices=list(STYLE_THEMES),
        default=None,
        help="Visual style/palette. Overrides the spec 'style' field. Defaults to the spec value or 'default'.",
    )
    parser.add_argument(
        "--strict-formats",
        action="store_true",
        help="Fail if any requested format is not produced. Use this for publishing runs.",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec_dir = spec_path.resolve().parent

    validation = validate_spec(spec, spec_dir=spec_dir)
    if args.validate_only:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        sys.exit(0 if validation["ok"] else 2)
    for warning in validation["warnings"]:
        print(f"warning: {warning['path']} {warning['message']} -> {warning['fix']}", file=sys.stderr)
    if not validation["ok"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit("spec validation failed; fix the errors above and rerun (see references/spec-format.md)")

    resolve_custom_icons(spec, spec_dir)

    style = args.style or spec.get("style", "default")
    apply_style(style)

    browser_ready = svg_renderer is not None and svg_renderer.is_available()
    renderer = args.renderer
    if renderer == "auto":
        renderer = "browser" if browser_ready else "pillow"
    if renderer == "browser" and not browser_ready:
        print("warning: browser renderer unavailable (playwright/rough.js missing), falling back to pillow", file=sys.stderr)
        renderer = "pillow"

    animation = args.animation or spec.get("animation", "flow")
    if animation not in ANIMATION_CHOICES:
        choices = ", ".join(ANIMATION_CHOICES)
        raise SystemExit(f"unknown animation '{animation}'. choices: {choices}")

    default_formats = DEFAULT_FORMATS_BROWSER if renderer == "browser" else DEFAULT_FORMATS_PILLOW
    formats = tuple(dict.fromkeys(f.strip() for f in (args.formats or default_formats).split(",") if f.strip()))
    unknown_formats = sorted(set(formats) - ALL_FORMATS)
    if unknown_formats:
        raise SystemExit(f"unknown format(s): {', '.join(unknown_formats)}. choices: {', '.join(sorted(ALL_FORMATS))}")
    if args.strict_formats and renderer != "browser":
        unsupported = sorted(set(formats) & BROWSER_ONLY_FORMATS)
        if unsupported:
            raise SystemExit(
                f"requested format(s) require the browser renderer under --strict-formats: "
                f"{', '.join(unsupported)}"
            )

    if renderer == "browser":
        result = write_outputs_browser(spec, Path(args.outdir), args.basename, animation=animation, formats=formats)
    else:
        if animation != "flow":
            print(f"warning: animation preset '{animation}' requires the browser renderer; using classic flow", file=sys.stderr)
        unsupported = [f for f in formats if f in ("mp4", "svg", "html")]
        if unsupported:
            print(f"warning: format(s) {', '.join(unsupported)} require the browser renderer; skipped", file=sys.stderr)
        result = write_outputs(spec, Path(args.outdir), args.basename, icon_engine=args.icon_engine,
                               formats=tuple(f for f in formats if f in {"gif", "png", "excalidraw"}))
        result["renderer"] = "pillow"

    result["style"] = style
    if args.verify and "gif" in result:
        result["verification"] = frame_diff_report(result["gif"])
    if args.check:
        result["checks"] = check_outputs(result, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict_formats:
        missing = missing_requested_formats(result, formats)
        if missing:
            print(f"missing requested format(s): {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
    if args.check and not result["checks"]["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
