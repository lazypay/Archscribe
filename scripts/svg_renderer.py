#!/usr/bin/env python3
"""Browser renderer for Archscribe (Phase 1 + 2 of the 2.0 plan).

Replays the primitive-op stream recorded by
``render_animated_diagram.render_static_with_ops`` inside headless Chromium:
rough.js draws every shape with a genuine hand-drawn wobble, text is set in
the bundled Excalifont / Noto Sans SC webfonts, and the bundled Tabler SVGs
are inlined crisp.

Outputs (per ``formats``):

- ``.svg``   standalone vector, fonts embedded
- ``.png``   static screenshot (2x supersampled, resized to canvas)
- ``.gif``   animated, driven by a seek-style ``setProgress(t)`` JS engine
- ``.mp4``   same frames, h264 via ffmpeg (skipped if ffmpeg missing)
- ``.html``  standalone interactive page: click a module to highlight its
             connections (or the whole BFS chain), hover tooltips, keyboard
             accessible; the graph comes from scripts/graph_model.py

Animation presets (all deterministic, frame = f(t)):

- ``flow``   upgraded classic: eased energy beams along edges, arrival
             ripples, wave-order module breathing, icon stroke sweeps
- ``draw``   whiteboard build-up: shapes grow via stroke-dash reveal in draw
             order, text/icons fade in, hold, soft fade-out, loop
- ``relay``  narrative hand-off: canvas dims, one energy beam at a time
             travels the story path, endpoint ripple + module highlight

The op stream is the single source of layout truth: this module contains no
diagram coordinates of its own.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"
VENDOR_DIR = ROOT / "assets" / "vendor"
TABLER_ICON_DIR = ROOT / "assets" / "icons" / "tabler"

ANIMATION_PRESETS = ("flow", "draw", "relay", "trace", "chapter", "failure-recovery")
# Minimum loop lengths (frames @ spec fps) for the narrative presets.
PRESET_MIN_FRAMES = {"flow": 0, "draw": 72, "relay": 88, "trace": 88, "chapter": 96, "failure-recovery": 96}

FONT_FACES = [
    ("Excalifont", "Excalifont-Regular.woff2", 400),
    ("NotoSansSC", "NotoSansSC-Regular.woff2", 400),
    ("NotoSansSC", "NotoSansSC-Bold.woff2", 700),
]


def is_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return (VENDOR_DIR / "rough.js").is_file()


def _font_css() -> str:
    faces = []
    for family, filename, weight in FONT_FACES:
        path = FONT_DIR / filename
        if not path.is_file():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(faces)


_CUSTOM_ICON_MIME = {".svg": "image/svg+xml", ".png": "image/png"}


def _custom_icon_markup(path: Path) -> str | None:
    """Wrap a user-supplied SVG/PNG as an <image> so it keeps its own colors
    and aspect ratio regardless of the file's internal structure."""
    mime = _CUSTOM_ICON_MIME.get(path.suffix.lower())
    if mime is None or not path.is_file():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<image href="data:{mime};base64,{b64}" width="24" height="24" '
            f'preserveAspectRatio="xMidYMid meet"/></svg>')


def _collect_icon_markups(doc) -> dict:
    markups = {}
    for op in doc["ops"]:
        if op["op"] != "icon" or op["name"] in markups:
            continue
        if op.get("file"):
            markup = _custom_icon_markup(Path(op["file"]))
            if markup:
                markups[op["name"]] = markup
            continue
        path = TABLER_ICON_DIR / f"{op['name']}.svg"
        if path.is_file():
            markups[op["name"]] = path.read_text(encoding="utf-8")
    return markups


def _collect_image_hrefs(doc) -> dict:
    """Data URIs for 'image' ops (brand logos placed as-is, no tile chrome)."""
    hrefs = {}
    for op in doc["ops"]:
        if op["op"] != "image" or op["name"] in hrefs:
            continue
        path = Path(op["file"])
        mime = _CUSTOM_ICON_MIME.get(path.suffix.lower())
        if mime and path.is_file():
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            hrefs[op["name"]] = f"data:{mime};base64,{b64}"
    return hrefs


def build_page_html(doc) -> str:
    rough_src = (VENDOR_DIR / "rough.js").read_text(encoding="utf-8")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style id="fonts">{_font_css()}</style>
<style>html,body{{margin:0;padding:0;background:{doc['bg']};}}</style>
</head><body>
<svg id="stage"></svg>
<script>{rough_src}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Static replay (rough.js hand-drawn shapes + webfont text + inline icons)
# ---------------------------------------------------------------------------

_RENDER_JS = r"""
(() => {
  const doc = window.__doc;
  const icons = window.__icons;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("stage");
  const W = doc.canvas.width, H = doc.canvas.height;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  const rc = rough.svg(svg);

  const el = (tag, attrs = {}) => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  };
  const rgba = (hex, alpha = 1) => {
    const v = hex.replace("#", "");
    const n = parseInt(v.length === 3 ? v.split("").map(c => c + c).join("") : v, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
  };
  window.__rgba = rgba;
  const roundedRectPath = (x, y, w, h, r) => {
    r = Math.min(r, w / 2, h / 2);
    return `M ${x + r} ${y}
      L ${x + w - r} ${y} Q ${x + w} ${y} ${x + w} ${y + r}
      L ${x + w} ${y + h - r} Q ${x + w} ${y + h} ${x + w - r} ${y + h}
      L ${x + r} ${y + h} Q ${x} ${y + h} ${x} ${y + h - r}
      L ${x} ${y + r} Q ${x} ${y} ${x + r} ${y}`;
  };
  window.__roundedRectPath = roundedRectPath;
  const hasCJK = (t) => /[\u3400-\u9fff]/.test(t);
  const fontFor = (op) => {
    if (op.hand && !hasCJK(op.text)) return { family: "Excalifont", weight: 400 };
    return { family: "NotoSansSC", weight: op.bold ? 700 : 400 };
  };
  const dashFor = (style) => style === "dashed" ? [8, 8] : style === "solid" ? null : [2, 7];

  svg.appendChild(el("rect", { id: "bg", x: 0, y: 0, width: W, height: H, fill: doc.bg }));

  const defs = el("defs");
  const blur = el("filter", { id: "glow", x: "-40%", y: "-40%", width: "180%", height: "180%" });
  blur.appendChild(el("feGaussianBlur", { stdDeviation: doc.finish.mode === "light" ? 3 : 4 }));
  defs.appendChild(blur);
  const soft = el("filter", { id: "softglow", x: "-80%", y: "-80%", width: "260%", height: "260%" });
  soft.appendChild(el("feGaussianBlur", { stdDeviation: 2.4 }));
  defs.appendChild(soft);
  const illb = el("filter", { id: "illblur", x: "-80%", y: "-80%", width: "260%", height: "260%" });
  illb.appendChild(el("feGaussianBlur", { stdDeviation: 4.5 }));
  defs.appendChild(illb);
  const grain = el("filter", { id: "grain" });
  grain.appendChild(el("feTurbulence", { type: "fractalNoise", baseFrequency: "0.9", numOctaves: "2", stitchTiles: "stitch" }));
  grain.appendChild(el("feColorMatrix", { type: "matrix", values: "0 0 0 0 0.6 0 0 0 0 0.6 0 0 0 0 0.6 0 0 0 0.05 0" }));
  defs.appendChild(grain);
  const vg = el("radialGradient", { id: "vignette", cx: "50%", cy: "46%", r: "72%" });
  vg.appendChild(el("stop", { offset: "38%", "stop-color": "black", "stop-opacity": 0 }));
  vg.appendChild(el("stop", { offset: "100%", "stop-color": "black", "stop-opacity": 0.42 }));
  defs.appendChild(vg);
  svg.appendChild(defs);

  const content = el("g", { id: "content" });
  svg.appendChild(content);

  let seed = 1000;
  const roughOpts = (stroke, fill, width, extra = {}) => Object.assign({
    seed: seed++,
    roughness: 1,
    bowing: 1,
    stroke: stroke,
    strokeWidth: width,
    fill: fill || undefined,
    fillStyle: "solid",
  }, extra);

  const arrowHead = (parent, points, stroke, width) => {
    const [a, b] = [points[points.length - 2], points[points.length - 1]];
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const len = 14 + width, spread = 0.52;
    const p1 = [b[0] - len * Math.cos(angle - spread), b[1] - len * Math.sin(angle - spread)];
    const p2 = [b[0] - len * Math.cos(angle + spread), b[1] - len * Math.sin(angle + spread)];
    parent.appendChild(rc.linearPath([p1, [b[0], b[1]], p2], roughOpts(stroke, null, width, { roughness: 0.6 })));
  };

  const drawText = (op) => {
    const font = fontFor(op);
    const lines = op.text.split("\n");
    const g = el("g", { "data-op": "text" });
    const lineStep = op.size * 1.2 + (op.spacing || 3);
    const anchor = op.align === "center" ? "middle" : op.align === "right" ? "end" : "start";
    const tx = op.align === "center" ? op.x + op.w / 2 : op.align === "right" ? op.x + op.w : op.x;
    lines.forEach((line, i) => {
      const t = el("text", {
        x: tx, y: i * lineStep,
        "text-anchor": anchor,
        "font-family": `${font.family}, NotoSansSC, sans-serif`,
        "font-size": op.size,
        "font-weight": font.weight,
        fill: op.color,
      });
      t.textContent = line;
      g.appendChild(t);
    });
    content.appendChild(g);
    const bb = g.getBBox();
    const dy = (op.y + op.h / 2) - (bb.y + bb.height / 2);
    g.setAttribute("transform", `translate(0 ${dy.toFixed(2)})`);
    for (const t of g.children) {
      const wLine = t.getComputedTextLength();
      if (wLine > op.w * 1.04) {
        t.setAttribute("textLength", op.w);
        t.setAttribute("lengthAdjust", "spacingAndGlyphs");
      }
    }
  };

  // ===== Illustrated icon engine v2: "Neon Sketch Duotone" ==================
  // No plates: theme-ink hand-drawn strokes carry the structure, the item's
  // semantic accent paints the single moving part. Every icon performs one
  // physical job story per cycle; update(p) is deterministic, p=0 is a
  // complete rest pose and p->1 returns to it, so loops are seamless.
  window.__illInstances = [];

  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
  const cyc = (t) => ((t % 1) + 1) % 1;
  const winf = (t, a, b) => clamp01((t - a) / (b - a));
  const eio = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const eoq = (t) => 1 - Math.pow(1 - t, 3);
  const eob = (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
  const bell = (t, c, w) => Math.exp(-Math.pow((t - c) / w, 2));
  const sinS = (t) => 0.5 - 0.5 * Math.cos(2 * Math.PI * t);
  const polar = (cx, cy, r, deg) => {
    const a = (deg - 90) * Math.PI / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  const arcPath = (cx, cy, r, a0, a1) => {
    const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${Math.abs(a1 - a0) > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  const scaleAt = (cx, cy, sx, sy) =>
    `translate(${(cx * (1 - sx)).toFixed(3)} ${(cy * (1 - sy)).toFixed(3)}) scale(${sx.toFixed(4)} ${sy.toFixed(4)})`;
  const circlePath = (cx, cy, r) =>
    `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy}`;

  // Fixed per-family hand tilt keeps the sheet lively without per-frame noise.
  const ILL_TILT = { brain: -1.2, agent: 1.0, gear: 0, eye: -0.8, db: 1.2, search: 0.9,
                     shield: -1.0, clock: 0.8, message: -1.4, api: 0.6, package: -0.9,
                     cloud: 1.1, module: 0.7, server: 0.8, cluster: -0.6, container: 0.5,
                     queue: -0.8, cache: 0.9, vector: -0.7, stream: 0.6, rag: -1.0,
                     prompt: 0.8, terminal: -0.5, lock: 0.7, identity: -0.9, user: 0.6,
                     audit: -0.7, file: 0.9, folder: -0.6, notification: 1.2,
                     analytics: -0.8, globe: 0.5, success: -0.7, failure: 0.8,
                     retry: -0.5, trigger: 1.0, scope: 0.6, firewall: -0.9, embedding: -0.4,
                     loop: 0.6, plan: -0.8, decision: 0, merge: 0.7, split: -0.7,
                     handoff: 0.5, subagent: -0.6, orchestrator: 0.8, human: -0.5,
                     checkpoint: 0.9, rollback: -0.7, sandbox: 0.6, compare: -0.9,
                     score: 0.7, error: -0.6, wait: 0.5, emit: -0.8, ingest: 0.8 };

  const grp = (attrs = {}) => el("g", attrs);
  const sketch = (parent, d, C, w = 3, opacity = 1) => {
    parent.appendChild(el("path", { d, fill: "none", stroke: C.ghost, "stroke-width": w * 0.55,
      "stroke-linecap": "round", "stroke-linejoin": "round",
      transform: "translate(0.75 -0.55) rotate(0.6 24 24)" }));
    const main = el("path", { d, fill: "none", stroke: C.ink, "stroke-width": w,
      "stroke-linecap": "round", "stroke-linejoin": "round", opacity });
    parent.appendChild(main);
    return main;
  };
  const aStroke = (parent, d, C, w = 2.8, extra = {}) => {
    const n = el("path", Object.assign({ d, fill: "none", stroke: C.acc, "stroke-width": w,
      "stroke-linecap": "round", "stroke-linejoin": "round" }, extra));
    parent.appendChild(n);
    return n;
  };
  const ringSet = (ring, k, r0, r1, aMax = 0.85) => {
    if (k <= 0 || k >= 1) { ring.setAttribute("opacity", 0); return; }
    ring.setAttribute("r", (r0 + (r1 - r0) * k).toFixed(2));
    ring.setAttribute("opacity", ((1 - k) * aMax).toFixed(3));
  };
  const glowDisc = (g, C, cx, cy, r) => {
    const n = el("circle", { cx, cy, r, fill: C.acc, opacity: 0.001, filter: "url(#illblur)" });
    g.appendChild(n);
    return { set: (a) => n.setAttribute("opacity", (a * C.glowK).toFixed(3)) };
  };

  /* Builders live in a 48x48 grid; each returns { node, update(p) }. */
  const illBuilders = {

    /* Think: a synapse signal travels the circuit while the brain breathes. */
    brain(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const lobes = "M24 10.5 C 18.5 7, 12 9.5, 11 15 C 7.5 16.5, 7 22, 9.5 25.5 C 8 30, 11.5 34.5, 16 34.8 C 17.5 38.5, 21.5 40, 24 38.4 " +
                    "M24 10.5 C 29.5 7.2, 36 9.7, 37 15 C 40.5 16.6, 41 22.2, 38.5 25.5 C 40 30, 36.5 34.5, 32 34.8 C 30.5 38.5, 26.5 40, 24 38.4";
      sketch(root, lobes, C, 3);
      sketch(root, "M24 11 L 24 38", C, 2, 0.35);
      const wireA = aStroke(root, "M16.5 18.5 L 24 24.5 L 31.5 17.5", C, 2, { opacity: 0.3 });
      const wireB = aStroke(root, "M18.5 30 L 24 24.5 L 29.5 30", C, 2, { opacity: 0.3 });
      const nodes = [[16.5, 18.5], [24, 24.5], [31.5, 17.5], [18.5, 30], [29.5, 30]].map(([x, y]) => {
        const c = el("circle", { cx: x, cy: y, r: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1 });
        root.appendChild(c); return c;
      });
      const dot = el("circle", { r: 2.3, fill: C.acc, opacity: 0 }); root.appendChild(dot);
      let LA = 0, LB = 0;
      return { node: g, update(p) {
        if (!LA) { LA = wireA.getTotalLength(); LB = wireB.getTotalLength(); }
        root.setAttribute("transform", scaleAt(24, 24, 1 + 0.02 * sinS(p), 1 + 0.02 * sinS(p)));
        const wA = eio(winf(p, 0.06, 0.4)), wB = eio(winf(p, 0.5, 0.84));
        let pt = null, on = 0;
        if (p >= 0.04 && p < 0.46) { pt = wireA.getPointAtLength(LA * wA); on = Math.min(winf(p, 0.04, 0.1), 1 - winf(p, 0.4, 0.46)); }
        else if (p >= 0.48 && p < 0.9) { pt = wireB.getPointAtLength(LB * wB); on = Math.min(winf(p, 0.48, 0.54), 1 - winf(p, 0.84, 0.9)); }
        if (pt) { dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y); }
        dot.setAttribute("opacity", (on * 0.95).toFixed(3));
        wireA.setAttribute("opacity", (0.3 + 0.5 * Math.min(wA, 1 - winf(p, 0.42, 0.52))).toFixed(3));
        wireB.setAttribute("opacity", (0.3 + 0.5 * Math.min(wB, 1 - winf(p, 0.86, 0.96))).toFixed(3));
        const flash = [bell(p, 0.07, 0.04), bell(p, 0.24, 0.045) + bell(p, 0.66, 0.045), bell(p, 0.4, 0.04), bell(p, 0.51, 0.04), bell(p, 0.83, 0.04)];
        nodes.forEach((n, i) => { const k = Math.min(1, flash[i]);
          n.setAttribute("fill", k > 0.45 ? C.acc : C.accSoft);
          n.setAttribute("r", (2 + 1.1 * k).toFixed(2)); });
        glow.set(0.10 + 0.1 * sinS(p));
      } };
    },

    /* Agent: blink, glance, antenna ping, gentle head tilt. */
    agent(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 25, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(11, 15, 26, 21.5, 6.5), C, 3);
      sketch(root, "M8.2 23.5 L 8.2 30.5", C, 2.6, 0.85);
      sketch(root, "M39.8 23.5 L 39.8 30.5", C, 2.6, 0.85);
      sketch(root, "M24 15 L 24 9.6", C, 2.2, 0.9);
      const tip = el("circle", { cx: 24, cy: 8.2, r: 2.1, fill: C.acc }); root.appendChild(tip);
      const ring = el("circle", { cx: 24, cy: 8.2, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 }); root.appendChild(ring);
      const eyes = [18.6, 29.4].map((x) => { const e = el("circle", { cx: x, cy: 24.3, r: 2.7, fill: C.acc }); root.appendChild(e); return e; });
      const mouth = aStroke(root, "M18.5 30.6 Q 24 33.6, 29.5 30.6", C, 2.2, { opacity: 0.9 });
      return { node: g, update(p) {
        root.setAttribute("transform", `rotate(${(2.2 * Math.sin(2 * Math.PI * p)).toFixed(2)} 24 26)`);
        const blink = 1 - 0.9 * Math.min(1, bell(p, 0.3, 0.028));
        const gl = 1.4 * (eio(winf(p, 0.42, 0.55)) - eio(winf(p, 0.72, 0.85)));
        eyes.forEach((e) => {
          e.setAttribute("transform", `translate(${gl.toFixed(2)} ${(24.3 * (1 - blink)).toFixed(2)}) scale(1 ${blink.toFixed(3)})`);
        });
        ringSet(ring, winf(p, 0.55, 0.8), 2.5, 8.5);
        tip.setAttribute("r", (2.1 + 0.9 * bell(p, 0.56, 0.04)).toFixed(2));
        mouth.setAttribute("d", `M18.5 30.6 Q 24 ${(33.6 + 0.8 * bell(p, 0.6, 0.1)).toFixed(2)}, 29.5 30.6`);
        glow.set(0.09 + 0.09 * bell(p, 0.58, 0.12));
      } };
    },

    /* Act: one-pitch mechanical turn, counter-rotating pinion, mesh spark. */
    gear(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const big = grp(), small = grp();
      root.appendChild(big); root.appendChild(small);
      let teeth = "";
      for (let i = 0; i < 8; i++) {
        const a = i * 45, [x0, y0] = polar(22, 22, 12.6, a), [x1, y1] = polar(22, 22, 17.6, a);
        teeth += `M ${x0.toFixed(2)} ${y0.toFixed(2)} L ${x1.toFixed(2)} ${y1.toFixed(2)} `;
      }
      sketch(big, teeth, C, 4.4);
      sketch(big, circlePath(22, 22, 11.6), C, 3);
      big.appendChild(el("circle", { cx: 22, cy: 22, r: 4.6, fill: C.accSoft, stroke: C.acc, "stroke-width": 2 }));
      let teeth2 = "";
      for (let i = 0; i < 6; i++) {
        const a = i * 60 + 30, [x0, y0] = polar(37.5, 37.5, 4.6, a), [x1, y1] = polar(37.5, 37.5, 7.8, a);
        teeth2 += `M ${x0.toFixed(2)} ${y0.toFixed(2)} L ${x1.toFixed(2)} ${y1.toFixed(2)} `;
      }
      small.appendChild(el("path", { d: teeth2, fill: "none", stroke: C.inkSoft, "stroke-width": 2.8, "stroke-linecap": "round" }));
      small.appendChild(el("circle", { cx: 37.5, cy: 37.5, r: 4.4, fill: "none", stroke: C.inkSoft, "stroke-width": 2.2 }));
      small.appendChild(el("circle", { cx: 37.5, cy: 37.5, r: 1.4, fill: C.acc }));
      const spark = el("circle", { cx: 30.5, cy: 30.5, r: 2, fill: C.acc, opacity: 0 }); root.appendChild(spark);
      return { node: g, update(p) {
        const drive = eob(winf(p, 0.22, 0.6));
        big.setAttribute("transform", `rotate(${(45 * drive - 4 * bell(p, 0.16, 0.045)).toFixed(2)} 22 22)`);
        small.setAttribute("transform", `rotate(${(-60 * drive + 5 * bell(p, 0.16, 0.045)).toFixed(2)} 37.5 37.5)`);
        spark.setAttribute("opacity", Math.min(1, bell(p, 0.42, 0.07)).toFixed(3));
        spark.setAttribute("r", (1.4 + 1.6 * bell(p, 0.42, 0.07)).toFixed(2));
        glow.set(0.09 + 0.11 * bell(p, 0.42, 0.14));
      } };
    },

    /* Observe: iris glances left and right, cartoon blink to close the loop. */
    eye(C) {
      const g = grp(), root = grp(), iris = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M5.5 24 Q 24 8.5, 42.5 24 Q 24 39.5, 5.5 24 Z", C, 3);
      root.appendChild(iris);
      iris.appendChild(el("circle", { cx: 24, cy: 24, r: 7.4, fill: C.accSoft, stroke: C.acc, "stroke-width": 2.4 }));
      iris.appendChild(el("circle", { cx: 24, cy: 24, r: 3.2, fill: C.acc }));
      iris.appendChild(el("circle", { cx: 26.2, cy: 21.6, r: 1.15, fill: C.ink }));
      root.appendChild(el("path", { d: "M13 13.5 L 11 10.8 M24 10.4 L 24 7.4 M35 13.5 L 37 10.8",
        fill: "none", stroke: C.inkSoft, "stroke-width": 2, "stroke-linecap": "round" }));
      return { node: g, update(p) {
        const gx = -4.4 * (eio(winf(p, 0.05, 0.2)) - eio(winf(p, 0.28, 0.43))) + 4.4 * (eio(winf(p, 0.5, 0.65)) - eio(winf(p, 0.73, 0.88)));
        iris.setAttribute("transform", `translate(${gx.toFixed(2)} 0)`);
        root.setAttribute("transform", scaleAt(24, 24, 1, 1 - 0.93 * Math.min(1, bell(p, 0.945, 0.024))));
        glow.set(0.1 + 0.06 * sinS(p));
      } };
    },

    /* Memory: a record chip drops in, the lid bounces, shelves shimmer. */
    db(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const top = el("ellipse", { cx: 24, cy: 14, rx: 13.5, ry: 4.8, fill: "none", stroke: C.ink, "stroke-width": 3 });
      root.appendChild(el("ellipse", { cx: 24.7, cy: 13.5, rx: 13.5, ry: 4.8, fill: "none", stroke: C.ghost, "stroke-width": 1.6 }));
      root.appendChild(top);
      sketch(root, "M10.5 14 L 10.5 33.5", C, 3);
      sketch(root, "M37.5 14 L 37.5 33.5", C, 3);
      sketch(root, "M10.5 33.5 A 13.5 4.8 0 0 0 37.5 33.5", C, 3);
      const l1 = aStroke(root, "M13.5 22.4 L 34.5 22.4", C, 2, { opacity: 0.4, "stroke-dasharray": "5 4" });
      const l2 = aStroke(root, "M13.5 27.6 L 34.5 27.6", C, 2, { opacity: 0.4, "stroke-dasharray": "5 4" });
      const chip = el("rect", { x: 20, y: 0, width: 8, height: 4.6, rx: 1.6, fill: C.acc, opacity: 0 }); root.appendChild(chip);
      const ripple = el("ellipse", { cx: 24, cy: 14, rx: 0, ry: 0, fill: "none", stroke: C.acc, "stroke-width": 1.4, opacity: 0 }); root.appendChild(ripple);
      return { node: g, update(p) {
        const fall = Math.pow(winf(p, 0.12, 0.3), 2.1);
        const sink = winf(p, 0.3, 0.48);
        chip.setAttribute("transform", `translate(0 ${(2 + 9.5 * fall + 4 * sink).toFixed(2)})`);
        chip.setAttribute("opacity", (Math.min(winf(p, 0.07, 0.13), 1 - sink) * 0.95).toFixed(3));
        top.setAttribute("ry", (4.8 * (1 + 0.24 * bell(p, 0.32, 0.035))).toFixed(2));
        const rk = winf(p, 0.31, 0.52);
        if (rk > 0 && rk < 1) {
          ripple.setAttribute("rx", (4 + 8.5 * rk).toFixed(2)); ripple.setAttribute("ry", (1.4 + 2.8 * rk).toFixed(2));
          ripple.setAttribute("opacity", ((1 - rk) * 0.6).toFixed(3));
        } else ripple.setAttribute("opacity", 0);
        l1.setAttribute("opacity", (0.4 + 0.5 * bell(p, 0.5, 0.08)).toFixed(3));
        l2.setAttribute("opacity", (0.4 + 0.5 * bell(p, 0.58, 0.08)).toFixed(3));
        glow.set(0.09 + 0.1 * bell(p, 0.36, 0.12));
      } };
    },

    /* Search: magnifier sways, accent scanline sweeps, hits flash. */
    search(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 22, 22, 16);
      g.appendChild(root);
      sketch(root, circlePath(20.5, 20.5, 12.3), C, 3);
      sketch(root, "M29.6 29.6 L 38.6 38.6", C, 4.2);
      const scan = aStroke(root, "M10 20.5 L 31 20.5", C, 2.2, { opacity: 0.85 });
      const hits = [[16.5, 17.2], [24.5, 24.0]].map(([x, y]) => {
        const c = el("circle", { cx: x, cy: y, r: 1.9, fill: C.acc, opacity: 0.3 }); root.appendChild(c); return c;
      });
      return { node: g, update(p) {
        root.setAttribute("transform", `rotate(${(-6.5 * Math.sin(2 * Math.PI * p)).toFixed(2)} 24 24)`);
        const sy = 13 + 15 * (eio(winf(p, 0.06, 0.46)) - eio(winf(p, 0.56, 0.96)));
        const half = Math.max(0.5, Math.sqrt(Math.max(0, 12.3 * 12.3 - Math.pow(sy - 20.5, 2))) - 2.2);
        scan.setAttribute("d", `M ${(20.5 - half).toFixed(2)} ${sy.toFixed(2)} L ${(20.5 + half).toFixed(2)} ${sy.toFixed(2)}`);
        hits.forEach((h, i) => {
          const k = Math.exp(-Math.pow((sy - [17.2, 24.0][i]) / 2.4, 2));
          h.setAttribute("opacity", (0.3 + 0.7 * k).toFixed(3));
          h.setAttribute("r", (1.9 + 1.3 * k).toFixed(2));
        });
        glow.set(0.1 + 0.06 * sinS(p));
      } };
    },

    /* Validate: a threat particle is blocked, then the check draws on. */
    shield(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const outline = "M24 6.5 L 37.8 11.2 L 36.4 26 Q 24 41.5, 11.6 26 L 10.2 11.2 Z";
      sketch(root, outline, C, 3);
      const glowStroke = el("path", { d: outline, fill: "none", stroke: C.acc, "stroke-width": 3.4, opacity: 0, "stroke-linejoin": "round" });
      root.appendChild(glowStroke);
      root.appendChild(el("path", { d: outline, fill: C.accSoft, opacity: 0.5, stroke: "none" }));
      const check = aStroke(root, "M17 23.5 L 22 29 L 31.5 17.5", C, 3.4);
      const threat = el("circle", { r: 2.4, fill: C.danger, opacity: 0 }); root.appendChild(threat);
      const ripple = el("circle", { cx: 11.8, cy: 15.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 2, opacity: 0 }); root.appendChild(ripple);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = check.getTotalLength();
        const u = Math.pow(winf(p, 0.1, 0.3), 1.7);
        threat.setAttribute("cx", (2.5 + 9.3 * u).toFixed(2)); threat.setAttribute("cy", (8.5 + 7 * u).toFixed(2));
        threat.setAttribute("opacity", (u > 0 && u < 1 ? Math.min(1, winf(p, 0.08, 0.13)) * 0.95 : 0).toFixed(3));
        ringSet(ripple, winf(p, 0.3, 0.46), 2, 9.5);
        root.setAttribute("transform", `translate(${(1.9 * bell(p, 0.315, 0.035)).toFixed(2)} ${(0.8 * bell(p, 0.315, 0.035)).toFixed(2)})`);
        let o, off;
        if (p < 0.28) { o = 0.22; off = 0; }
        else if (p < 0.36) { o = 0.22 * (1 - winf(p, 0.28, 0.36)); off = 0; }
        else if (p < 0.42) { o = 0; off = L; }
        else if (p < 0.64) { o = 1; off = L * (1 - eoq(winf(p, 0.42, 0.64))); }
        else if (p < 0.86) { o = 1; off = 0; }
        else { o = 0.22 + 0.78 * (1 - eio(winf(p, 0.86, 0.97))); off = 0; }
        check.setAttribute("stroke-dasharray", `${L} ${L}`);
        check.setAttribute("stroke-dashoffset", off.toFixed(2));
        check.setAttribute("opacity", o.toFixed(3));
        glowStroke.setAttribute("opacity", (0.55 * bell(p, 0.33, 0.05) + 0.4 * bell(p, 0.66, 0.06)).toFixed(3));
        glow.set(0.09 + 0.11 * bell(p, 0.6, 0.15));
      } };
    },

    /* Budget: the accent minute hand ticks a full revolution with arc trails. */
    clock(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 24, 17.2), C, 3);
      let ticks = "", minor = "";
      for (let i = 0; i < 12; i++) {
        const a = i * 30, [x0, y0] = polar(24, 24, i % 3 === 0 ? 13.2 : 14.4, a), [x1, y1] = polar(24, 24, 15.8, a);
        (i % 3 === 0 ? (ticks += `M ${x0.toFixed(1)} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)} `)
                     : (minor += `M ${x0.toFixed(1)} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)} `));
      }
      root.appendChild(el("path", { d: ticks, stroke: C.ink, "stroke-width": 2.4, "stroke-linecap": "round", fill: "none", opacity: 0.9 }));
      root.appendChild(el("path", { d: minor, stroke: C.inkSoft, "stroke-width": 1.6, "stroke-linecap": "round", fill: "none" }));
      const [hx, hy] = polar(24, 24, 7.2, 300);
      root.appendChild(el("line", { x1: 24, y1: 24, x2: hx, y2: hy, stroke: C.ink, "stroke-width": 3.2, "stroke-linecap": "round" }));
      const trail = el("path", { d: "", fill: "none", stroke: C.accMid, "stroke-width": 2, "stroke-linecap": "round", opacity: 0 });
      root.appendChild(trail);
      const minute = el("line", { x1: 24, y1: 24, x2: 24, y2: 11.6, stroke: C.acc, "stroke-width": 3, "stroke-linecap": "round" });
      root.appendChild(minute);
      root.appendChild(el("circle", { cx: 24, cy: 24, r: 2.1, fill: C.acc }));
      return { node: g, update(p) {
        const k = p * 12, i = Math.floor(k), f = k - i;
        const ang = (i + eob(clamp01(f / 0.38))) * 30;
        const [mx, my] = polar(24, 24, 12.4, ang);
        minute.setAttribute("x2", mx.toFixed(2)); minute.setAttribute("y2", my.toFixed(2));
        trail.setAttribute("d", arcPath(24, 24, 13.4, ang - 34, ang - 6));
        trail.setAttribute("opacity", (0.55 * clamp01(f / 0.38) * (1 - clamp01((f - 0.5) / 0.5))).toFixed(3));
        glow.set(0.09 + 0.05 * sinS(p));
      } };
    },

    /* Trigger: typing dots, a happy squash, broadcast rings. */
    message(C) {
      const g = grp(), root = grp(), bubble = grp();
      const glow = glowDisc(g, C, 24, 22, 16);
      g.appendChild(root); root.appendChild(bubble);
      sketch(bubble, roundedRectPath(7.5, 9.5, 33, 22.5, 8) + " M15.5 31.5 L 12.5 39.5 L 21.5 31.8", C, 3);
      bubble.appendChild(el("path", { d: roundedRectPath(7.5, 9.5, 33, 22.5, 8), fill: C.accSoft, opacity: 0.4 }));
      const dots = [16.8, 24, 31.2].map((x) => { const d = el("circle", { cx: x, cy: 20.8, r: 2.2, fill: C.acc }); bubble.appendChild(d); return d; });
      const rings = [0, 1].map(() => { const r = el("circle", { cx: 24, cy: 20.8, r: 0, fill: "none", stroke: C.acc,
        "stroke-width": 1.6, opacity: 0 }); root.appendChild(r); return r; });
      return { node: g, update(p) {
        const env = eio(winf(p, 0.02, 0.12)) * (1 - eio(winf(p, 0.44, 0.56)));
        dots.forEach((d, i) => {
          const ph = Math.sin(2 * Math.PI * (p * 2) - i * 0.95);
          d.setAttribute("transform", `translate(0 ${(-3.4 * Math.pow(Math.max(0, ph), 2.2) * env).toFixed(2)})`);
          d.setAttribute("opacity", (0.55 + 0.45 * Math.max(0, ph) * env).toFixed(3));
        });
        const sq = bell(p, 0.68, 0.045);
        bubble.setAttribute("transform", scaleAt(24, 21, 1 + 0.06 * sq, 1 - 0.08 * sq));
        rings.forEach((r, i) => ringSet(r, winf(p, 0.68 + i * 0.07, 0.92 + i * 0.05), 15, 23.5, 0.75 - i * 0.2));
        glow.set(0.09 + 0.1 * bell(p, 0.7, 0.12));
      } };
    },

    /* API: a request token flies between the brackets, a response returns. */
    api(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const lb = grp(), rb = grp();
      root.appendChild(lb); root.appendChild(rb);
      sketch(lb, "M17.5 11.5 L 8.5 24 L 17.5 36.5", C, 3.2);
      sketch(rb, "M30.5 11.5 L 39.5 24 L 30.5 36.5", C, 3.2);
      root.appendChild(el("path", { d: "M27 13.5 L 21 34.5", stroke: C.inkSoft, "stroke-width": 2.4, "stroke-linecap": "round", fill: "none" }));
      const req = el("circle", { r: 2.5, fill: C.acc, opacity: 0 }); root.appendChild(req);
      const res = el("circle", { r: 2.5, fill: C.ink, opacity: 0 }); root.appendChild(res);
      const reqT = [0, 1, 2].map(() => { const t = el("circle", { r: 1.4, fill: C.acc, opacity: 0 }); root.appendChild(t); return t; });
      const resT = [0, 1, 2].map(() => { const t = el("circle", { r: 1.4, fill: C.ink, opacity: 0 }); root.appendChild(t); return t; });
      const fly = (dot, trail, u, dir) => {
        const on = u > 0 && u < 1 ? 1 : 0;
        const x = dir > 0 ? 11 + 26 * u : 37 - 26 * u;
        dot.setAttribute("cx", x.toFixed(2)); dot.setAttribute("cy", (24 - dir * 4.6 * Math.sin(Math.PI * u)).toFixed(2));
        dot.setAttribute("opacity", (on * Math.min(1, u / 0.12, (1 - u) / 0.12)).toFixed(3));
        trail.forEach((t, i) => {
          const ut = u - 0.09 * (i + 1);
          const on2 = ut > 0 && ut < 1 && on ? (1 - 0.28 * (i + 1)) : 0;
          t.setAttribute("cx", (dir > 0 ? 11 + 26 * ut : 37 - 26 * ut).toFixed(2));
          t.setAttribute("cy", (24 - dir * 4.6 * Math.sin(Math.PI * Math.max(0, ut))).toFixed(2));
          t.setAttribute("opacity", (on2 * 0.6).toFixed(3));
        });
      };
      return { node: g, update(p) {
        fly(req, reqT, eio(winf(p, 0.06, 0.42)), 1);
        fly(res, resT, eio(winf(p, 0.52, 0.88)), -1);
        const pinch = 1.7 * (bell(p, 0.24, 0.05) + bell(p, 0.7, 0.05));
        lb.setAttribute("transform", `translate(${pinch.toFixed(2)} 0)`);
        rb.setAttribute("transform", `translate(${(-pinch).toFixed(2)} 0)`);
        glow.set(0.09 + 0.08 * (bell(p, 0.24, 0.1) + bell(p, 0.7, 0.1)));
      } };
    },

    /* Output: flaps swing open, the delivery arrow pops out, box closes. */
    package(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 26, 16);
      g.appendChild(root);
      const arrow = grp(); root.appendChild(arrow);
      const shaft = aStroke(arrow, "M24 26 L 24 10.5", C, 3);
      aStroke(arrow, "M18 16 L 24 9.5 L 30 16", C, 3);
      const box = grp(); root.appendChild(box);
      box.appendChild(el("path", { d: roundedRectPath(10.5, 18, 27, 18.5, 2.5), fill: C.accSoft, opacity: 0.55 }));
      sketch(box, roundedRectPath(10.5, 18, 27, 18.5, 2.5), C, 3);
      sketch(box, "M24 18 L 24 36.5", C, 2, 0.4);
      aStroke(box, "M17.5 30.5 L 17.5 25 M15.2 27 L 17.5 24.6 L 19.8 27", C, 1.9, { opacity: 0.85 });
      const lf = grp(), rf = grp();
      box.appendChild(lf); box.appendChild(rf);
      sketch(lf, "M10.5 18 L 22.5 18", C, 3);
      sketch(rf, "M37.5 18 L 25.5 18", C, 3);
      return { node: g, update(p) {
        const open = eob(winf(p, 0.06, 0.24)) * (1 - eio(winf(p, 0.84, 0.97)));
        lf.setAttribute("transform", `rotate(${(-118 * open).toFixed(2)} 10.5 18)`);
        rf.setAttribute("transform", `rotate(${(118 * open).toFixed(2)} 37.5 18)`);
        const rise = eob(winf(p, 0.26, 0.5));
        const back = Math.pow(winf(p, 0.68, 0.84), 2);
        arrow.setAttribute("transform", `translate(0 ${(15.5 * (1 - rise) + 15.5 * back).toFixed(2)})`);
        arrow.setAttribute("opacity", clamp01(Math.min(winf(p, 0.24, 0.3), 1 - winf(p, 0.8, 0.86))).toFixed(3));
        shaft.setAttribute("stroke-dasharray", "18 30");
        shaft.setAttribute("stroke-dashoffset", (-6 * rise).toFixed(2));
        glow.set(0.09 + 0.11 * bell(p, 0.5, 0.14));
      } };
    },

    /* Deploy: upload dashes stream into a gently bobbing cloud. */
    cloud(C) {
      const g = grp(), root = grp(), cl = grp();
      const glow = glowDisc(g, C, 24, 22, 16);
      g.appendChild(root);
      const streams = [17.5, 24, 30.5].map((x) => {
        const s = el("line", { x1: x, y1: 42.5, x2: x, y2: 30.5, stroke: C.acc, "stroke-width": 2.4,
          "stroke-linecap": "round", "stroke-dasharray": "3.6 8.4", opacity: 0.8 });
        root.appendChild(s); return s;
      });
      root.appendChild(cl);
      const cloudPath = "M14 31.5 Q 7.5 31.5, 7.5 25.5 Q 7.5 20.8, 12 19.8 Q 12.6 13, 19.6 12.4 Q 25.6 7.6, 31.4 12.8 Q 38.8 13, 39.8 20.2 Q 43.5 21.8, 42.6 26.6 Q 41.8 31.5, 35.8 31.5 Z";
      cl.appendChild(el("path", { d: cloudPath, fill: C.accSoft, opacity: 0.4 }));
      sketch(cl, cloudPath, C, 3);
      const rim = el("path", { d: cloudPath, fill: "none", stroke: C.acc, "stroke-width": 3, opacity: 0, "stroke-linejoin": "round" });
      cl.appendChild(rim);
      return { node: g, update(p) {
        cl.setAttribute("transform", `translate(0 ${(-1.5 * Math.sin(2 * Math.PI * p)).toFixed(2)})`);
        streams.forEach((s, i) => {
          s.setAttribute("stroke-dashoffset", (-(p * 2 + i / 3) * 24).toFixed(2));
          s.setAttribute("opacity", (0.5 + 0.4 * sinS(p * 2 + i / 3)).toFixed(3));
        });
        rim.setAttribute("opacity", (0.4 * Math.pow(sinS(p * 2), 3)).toFixed(3));
        glow.set(0.09 + 0.07 * sinS(p));
      } };
    },

    /* Generic module: IC chip, core pulses, pins glint in sequence. */
    module(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(13, 13, 22, 22, 4.5), C, 3);
      const pins = [];
      [17.5, 24, 30.5].forEach((v) => {
        [["v", v, 13, v, 8.5], ["v", v, 35, v, 39.5], ["h", 13, v, 8.5, v], ["h", 35, v, 39.5, v]].forEach(([, x1, y1, x2, y2]) => {
          const pin = el("line", { x1, y1, x2, y2, stroke: C.inkSoft, "stroke-width": 2, "stroke-linecap": "round" });
          root.appendChild(pin); pins.push(pin);
        });
      });
      root.appendChild(el("rect", { x: 19, y: 19, width: 10, height: 10, rx: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.8 }));
      const core = el("circle", { cx: 24, cy: 24, r: 1.8, fill: C.acc }); root.appendChild(core);
      return { node: g, update(p) {
        core.setAttribute("r", (1.8 + 1.0 * sinS(p)).toFixed(2));
        pins.forEach((pin, i) => {
          const k = bell(cyc(p - i / pins.length), 0, 0.06);
          pin.setAttribute("stroke", k > 0.4 ? C.acc : C.inkSoft);
        });
        glow.set(0.08 + 0.07 * sinS(p));
      } };
    },

    /* Server: rack trays, LEDs blink in order, data line hums. */
    server(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const leds = [];
      [9.5, 19.5, 29.5].forEach((y, i) => {
        sketch(root, roundedRectPath(10.5, y, 27, 9, 2.5), C, 2.7);
        const led = el("circle", { cx: 33.5, cy: y + 4.5, r: 1.7, fill: C.accSoft, stroke: C.acc, "stroke-width": 1 });
        root.appendChild(led); leds.push(led);
        root.appendChild(el("line", { x1: 14.5, y1: y + 4.5, x2: 22.5, y2: y + 4.5,
          stroke: i === 1 ? C.acc : C.inkSoft, "stroke-width": 2, "stroke-linecap": "round",
          "stroke-dasharray": i === 1 ? "3 3.5" : "none", "data-hum": i === 1 ? 1 : 0 }));
      });
      const hum = root.querySelector("[data-hum='1']");
      return { node: g, update(p) {
        leds.forEach((led, i) => {
          const k = Math.min(1, bell(p, 0.14 + i * 0.3, 0.07));
          led.setAttribute("fill", k > 0.4 ? C.acc : C.accSoft);
          led.setAttribute("r", (1.7 + 0.9 * k).toFixed(2));
        });
        hum.setAttribute("stroke-dashoffset", (-p * 13).toFixed(2));
        glow.set(0.08 + 0.08 * bell(p, 0.44, 0.2));
      } };
    },

    /* Cluster: three hex nodes, a heartbeat pulse travels the mesh. */
    cluster(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const centers = [[24, 13.5], [14, 30], [34, 30]];
      const hexAt = (cx, cy, r) => {
        let d = "";
        for (let i = 0; i < 6; i++) {
          const [x, y] = polar(cx, cy, r, i * 60 + 30);
          d += (i ? "L" : "M") + ` ${x.toFixed(2)} ${y.toFixed(2)} `;
        }
        return d + "Z";
      };
      const wires = [[0, 1], [1, 2], [2, 0]].map(([a, b]) => {
        const w = el("path", { d: `M ${centers[a][0]} ${centers[a][1]} L ${centers[b][0]} ${centers[b][1]}`,
          stroke: C.inkSoft, "stroke-width": 1.8, fill: "none", "stroke-linecap": "round" });
        root.appendChild(w); return w;
      });
      const cores = centers.map(([cx, cy]) => {
        sketch(root, hexAt(cx, cy, 7.6), C, 2.6);
        const dot = el("circle", { cx, cy, r: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.2 });
        root.appendChild(dot); return dot;
      });
      const pulse = el("circle", { r: 2, fill: C.acc, opacity: 0 }); root.appendChild(pulse);
      return { node: g, update(p) {
        const leg = Math.min(2, Math.floor(p * 3)), u = eio(clamp01(p * 3 - leg));
        const [ax, ay] = centers[leg], [bx, by] = centers[(leg + 1) % 3];
        pulse.setAttribute("cx", (ax + (bx - ax) * u).toFixed(2));
        pulse.setAttribute("cy", (ay + (by - ay) * u).toFixed(2));
        pulse.setAttribute("opacity", (0.95 * Math.min(1, u / 0.15, (1 - u) / 0.15)).toFixed(3));
        cores.forEach((dot, i) => {
          const k = Math.min(1, bell(p, i / 3, 0.05) + bell(p, i / 3 + 1, 0.05));
          dot.setAttribute("fill", k > 0.4 ? C.acc : C.accSoft);
          dot.setAttribute("r", (2 + 1.2 * k).toFixed(2));
        });
        wires.forEach((w, i) => w.setAttribute("stroke", Math.floor(p * 3) === i ? C.accMid : C.inkSoft));
        glow.set(0.08 + 0.06 * sinS(p * 3));
      } };
    },

    /* Container: hex hull, the cargo crate hops and lands with a squash. */
    container(C) {
      const g = grp(), root = grp(), crate = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      let hex = "";
      for (let i = 0; i < 6; i++) {
        const [x, y] = polar(24, 24, 16, i * 60 + 30);
        hex += (i ? "L" : "M") + ` ${x.toFixed(2)} ${y.toFixed(2)} `;
      }
      sketch(root, hex + "Z", C, 3);
      const shadow = el("ellipse", { cx: 24, cy: 31.5, rx: 7, ry: 1.8, fill: C.ink, opacity: 0.18 });
      root.appendChild(shadow);
      root.appendChild(crate);
      crate.appendChild(el("rect", { x: 17.5, y: 17.5, width: 13, height: 13, rx: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 2 }));
      crate.appendChild(el("line", { x1: 17.5, y1: 22, x2: 30.5, y2: 22, stroke: C.acc, "stroke-width": 1.6 }));
      crate.appendChild(el("line", { x1: 24, y1: 22, x2: 24, y2: 30.5, stroke: C.acc, "stroke-width": 1.6, opacity: 0.7 }));
      return { node: g, update(p) {
        const hop = Math.sin(Math.PI * winf(p, 0.18, 0.52));
        const y = -5 * hop * hop;
        const squash = 1 + 0.16 * bell(p, 0.55, 0.035);
        crate.setAttribute("transform", `translate(0 ${y.toFixed(2)}) ${scaleAt(24, 30.5, squash, 1 / squash)}`);
        shadow.setAttribute("rx", (7 - 2.2 * hop).toFixed(2));
        shadow.setAttribute("opacity", (0.18 - 0.08 * hop).toFixed(3));
        glow.set(0.08 + 0.08 * bell(p, 0.55, 0.12));
      } };
    },

    /* Queue: chips advance one slot on the conveyor, one leaves, one joins. */
    queue(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M7 31.5 L 41 31.5", C, 2.8);
      sketch(root, "M35 18 L 41.5 24.5 M35 31 L 41.5 24.5", C, 2.2, 0.0);
      const arrow = aStroke(root, "M37.5 20.5 L 41.5 24.5 L 37.5 28.5", C, 2.2, { opacity: 0.9 });
      void arrow;
      const chips = [0, 1, 2, 3].map((i) => {
        const r = el("rect", { x: 0, y: 22.5, width: 7, height: 6.5, rx: 1.8,
          fill: i === 3 ? C.acc : C.accSoft, stroke: C.acc, "stroke-width": 1.6 });
        root.appendChild(r); return r;
      });
      return { node: g, update(p) {
        const step = eob(winf(p, 0.3, 0.62));
        chips.forEach((r, i) => {
          const x = 6 + (i + step) * 8.6;
          r.setAttribute("x", x.toFixed(2));
          let o = 1;
          if (i === 3) o = 1 - winf(p, 0.42, 0.6);
          if (i === 0) o = winf(p, 0.34, 0.52);
          r.setAttribute("opacity", clamp01(o).toFixed(3));
          r.setAttribute("fill", (i === 3 || (i === 2 && p > 0.62)) ? C.acc : C.accSoft);
        });
        glow.set(0.08 + 0.07 * bell(p, 0.5, 0.14));
      } };
    },

    /* Cache: lightning strikes the memory stack, the hot layer flashes. */
    cache(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 27, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(11.5, 25.4, 25, 5.4, 2.4), C, 2.4);
      sketch(root, roundedRectPath(11.5, 32.6, 25, 5.4, 2.4), C, 2.4);
      const hot = el("rect", { x: 11.5, y: 18.2, width: 25, height: 5.4, rx: 2.4, fill: C.accSoft, stroke: C.acc, "stroke-width": 2 });
      root.appendChild(hot);
      const boltD = "M30.5 5 L 23 15.5 L 27.5 15.5 L 23.5 23.5";
      const bolt = aStroke(root, boltD, C, 2.7, { opacity: 0.75 });
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = bolt.getTotalLength();
        const strike = winf(p, 0.12, 0.26);
        bolt.setAttribute("stroke-dasharray", `${L} ${L}`);
        bolt.setAttribute("stroke-dashoffset", (L * (1 - eoq(strike))).toFixed(2));
        bolt.setAttribute("opacity", (0.3 + 0.7 * Math.min(1, strike * 3) * (1 - winf(p, 0.6, 0.85))).toFixed(3));
        const flash = bell(p, 0.3, 0.08);
        hot.setAttribute("fill", flash > 0.45 ? C.acc : C.accSoft);
        hot.setAttribute("transform", `translate(0 ${(1.1 * bell(p, 0.28, 0.045)).toFixed(2)})`);
        glow.set(0.08 + 0.12 * bell(p, 0.3, 0.1));
      } };
    },

    /* Vector space: constellation nodes flash as a glint hops the edges. */
    vector(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const pts = [[14, 17], [24, 11], [34, 18], [35, 29], [24, 36], [13, 29]];
      const edges = [];
      pts.forEach(([x, y], i) => {
        const [nx, ny] = pts[(i + 1) % pts.length];
        const e = el("line", { x1: x, y1: y, x2: nx, y2: ny, stroke: C.inkSoft, "stroke-width": 1.7 });
        root.appendChild(e); edges.push(e);
      });
      root.appendChild(el("line", { x1: pts[1][0], y1: pts[1][1], x2: pts[4][0], y2: pts[4][1], stroke: C.ghost, "stroke-width": 1.4 }));
      root.appendChild(el("line", { x1: pts[0][0], y1: pts[0][1], x2: pts[3][0], y2: pts[3][1], stroke: C.ghost, "stroke-width": 1.4 }));
      const nodes = pts.map(([x, y], i) => {
        const c = el("circle", { cx: x, cy: y, r: i % 2 ? 2.1 : 2.8, fill: i % 2 ? C.accSoft : C.acc, stroke: C.ink, "stroke-width": 1.1 });
        root.appendChild(c); return c;
      });
      const glint = el("circle", { r: 2, fill: C.acc, opacity: 0 }); root.appendChild(glint);
      return { node: g, update(p) {
        const leg = Math.min(5, Math.floor(p * 6)), u = eio(clamp01(p * 6 - leg));
        const [ax, ay] = pts[leg], [bx, by] = pts[(leg + 1) % 6];
        glint.setAttribute("cx", (ax + (bx - ax) * u).toFixed(2));
        glint.setAttribute("cy", (ay + (by - ay) * u).toFixed(2));
        glint.setAttribute("opacity", (0.9 * Math.min(1, u / 0.2, (1 - u) / 0.2)).toFixed(3));
        nodes.forEach((n, i) => {
          const k = Math.min(1, bell(p, i / 6, 0.04) + bell(p, i / 6 + 1, 0.04));
          n.setAttribute("r", ((i % 2 ? 2.1 : 2.8) + 1.1 * k).toFixed(2));
        });
        edges.forEach((e, i) => e.setAttribute("stroke", i === leg ? C.accMid : C.inkSoft));
        glow.set(0.08 + 0.06 * sinS(p * 2));
      } };
    },

    /* Embedding: scattered tokens funnel into an ordered vector row. */
    embedding(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M11.5 9.5 L 36.5 9.5 L 27.5 22 L 27.5 28 L 20.5 28 L 20.5 22 Z", C, 2.6);
      const scatter = [[17, 5.5], [24, 4], [31, 5.8]].map(([x, y]) => {
        const d = el("circle", { cx: x, cy: y, r: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.2 });
        root.appendChild(d); return { d, x, y };
      });
      const cells = [14.5, 21.5, 28.5].map((x) => {
        const r = el("rect", { x, y: 33, width: 5.6, height: 5.6, rx: 1.4, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.6 });
        root.appendChild(r); return r;
      });
      const drop = el("circle", { r: 1.9, fill: C.acc, opacity: 0 }); root.appendChild(drop);
      return { node: g, update(p) {
        scatter.forEach(({ d, x, y }, i) => {
          const k = bell(cyc(p - i * 0.33), 0.1, 0.07);
          d.setAttribute("cy", (y + 1.2 * Math.sin(2 * Math.PI * (p * 2 + i / 3))).toFixed(2));
          d.setAttribute("fill", k > 0.4 ? C.acc : C.accSoft);
        });
        const leg = Math.min(2, Math.floor(p * 3)), u = winf(p * 3 - leg, 0.12, 0.82);
        const sx = scatter[leg].x;
        const fx = sx + (24 - sx) * Math.min(1, u * 1.8);
        drop.setAttribute("cx", (u < 0.55 ? fx : 24 + ([17.3, 24.3, 31.3][leg] - 24) * winf(u, 0.55, 1)).toFixed(2));
        drop.setAttribute("cy", (7 + 29 * eio(u)).toFixed(2));
        drop.setAttribute("opacity", (u > 0 && u < 1 ? 0.95 : 0).toFixed(3));
        cells.forEach((r, i) => {
          const lit = Math.min(1, bell(p * 3 - i, 0.995, 0.12) + bell(p * 3 - i, 3.995, 0.12));
          r.setAttribute("fill", lit > 0.4 ? C.acc : C.accSoft);
        });
        glow.set(0.08 + 0.07 * sinS(p * 3));
      } };
    },

    /* Stream: payload dots ride the wave. */
    stream(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const waveD = "M7.5 28 C 13 15, 19 38, 24.5 24 C 28.5 14, 34.5 31, 40.5 21";
      const wave = sketch(root, waveD, C, 2.8);
      const dots = [0, 1, 2].map(() => { const d = el("circle", { r: 2.4, fill: C.acc, opacity: 0 }); root.appendChild(d); return d; });
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = wave.getTotalLength();
        dots.forEach((d, i) => {
          const u = cyc(p + i / 3);
          const pt = wave.getPointAtLength(L * u);
          d.setAttribute("cx", pt.x.toFixed(2)); d.setAttribute("cy", pt.y.toFixed(2));
          d.setAttribute("opacity", (0.95 * Math.min(1, u / 0.12, (1 - u) / 0.12)).toFixed(3));
        });
        glow.set(0.08 + 0.06 * sinS(p * 3));
      } };
    },

    /* RAG: a scan bar reads the open book, the grounded line lights up. */
    rag(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M24 12.5 C 19 8.5, 12 9, 8.5 11.5 L 8.5 34 C 12 31.5, 19 31, 24 35 C 29 31, 36 31.5, 39.5 34 L 39.5 11.5 C 36 9, 29 8.5, 24 12.5 Z", C, 2.8);
      sketch(root, "M24 12.5 L 24 35", C, 2, 0.4);
      const rows = [[12, 17.5, 20.5], [12, 22, 20.5], [27.5, 17.5, 36], [27.5, 22, 36], [12, 26.5, 20.5], [27.5, 26.5, 36]].map(([x0, y, x1]) => {
        const ln = el("line", { x1: x0, y1: y, x2: x1, y2: y, stroke: C.inkSoft, "stroke-width": 1.6, "stroke-linecap": "round" });
        root.appendChild(ln); return { ln, y };
      });
      const bar = el("rect", { x: 10, y: 0, width: 28, height: 3.4, rx: 1.7, fill: C.acc, opacity: 0 });
      root.appendChild(bar);
      return { node: g, update(p) {
        const sweep = eio(winf(p, 0.08, 0.62));
        const by = 14.5 + 15 * sweep;
        bar.setAttribute("y", (by - 1.7).toFixed(2));
        bar.setAttribute("opacity", (0.28 * Math.min(1, winf(p, 0.06, 0.14), (1 - winf(p, 0.58, 0.68)))).toFixed(3));
        rows.forEach(({ ln, y }) => {
          const k = Math.exp(-Math.pow((by - y) / 2.6, 2)) * (p < 0.7 ? 1 : 1 - winf(p, 0.7, 0.9));
          ln.setAttribute("stroke", k > 0.4 ? C.acc : C.inkSoft);
          ln.setAttribute("stroke-width", (1.6 + 0.8 * k).toFixed(2));
        });
        glow.set(0.08 + 0.07 * bell(p, 0.4, 0.2));
      } };
    },

    /* Prompt: an input pill types a line, then the send key fires. */
    prompt(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(7.5, 16.5, 33, 15, 7.5), C, 2.8);
      const typed = el("line", { x1: 13, y1: 24, x2: 13, y2: 24, stroke: C.acc, "stroke-width": 2.6, "stroke-linecap": "round" });
      root.appendChild(typed);
      const caret = el("rect", { x: 13, y: 20, width: 2.4, height: 8, rx: 0.8, fill: C.acc });
      root.appendChild(caret);
      const send = grp(); root.appendChild(send);
      send.appendChild(el("circle", { cx: 34, cy: 24, r: 4.4, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.8 }));
      send.appendChild(el("path", { d: "M32 24 L 36 24 M34.4 21.8 L 36.4 24 L 34.4 26.2", fill: "none",
        stroke: C.acc, "stroke-width": 1.7, "stroke-linecap": "round", "stroke-linejoin": "round" }));
      const ring = el("circle", { cx: 34, cy: 24, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 });
      root.appendChild(ring);
      return { node: g, update(p) {
        const k = Math.min(1, Math.floor(winf(p, 0.08, 0.5) * 6) / 5);
        const erase = eio(winf(p, 0.82, 0.95));
        const len = 13.5 * (p < 0.6 ? k : 1 - erase);
        typed.setAttribute("x2", (13 + len).toFixed(2));
        caret.setAttribute("x", (13.8 + len).toFixed(2));
        caret.setAttribute("opacity", (p < 0.08 || p > 0.6) ? (Math.floor(p * 12) % 2 === 0 ? 1 : 0.15) : 1);
        const fire = bell(p, 0.62, 0.05);
        send.setAttribute("transform", scaleAt(34, 24, 1 + 0.22 * fire, 1 + 0.22 * fire));
        ringSet(ring, winf(p, 0.62, 0.82), 5, 11.5, 0.8);
        glow.set(0.08 + 0.09 * bell(p, 0.64, 0.12));
      } };
    },

    /* Terminal: prompt chevron, a command types, response line answers. */
    terminal(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(8.5, 11, 31, 26, 3.5), C, 2.8);
      sketch(root, "M8.5 17.5 L 39.5 17.5", C, 1.8, 0.5);
      [11.5, 15, 18.5].forEach((x) => root.appendChild(el("circle", { cx: x, cy: 14.2, r: 1.1, fill: C.inkSoft })));
      const chev = aStroke(root, "M12.5 22.5 L 16.5 25.5 L 12.5 28.5", C, 2.2);
      void chev;
      const cmd = el("line", { x1: 19.5, y1: 25.5, x2: 19.5, y2: 25.5, stroke: C.acc, "stroke-width": 2.4, "stroke-linecap": "round" });
      root.appendChild(cmd);
      const out = el("line", { x1: 12.5, y1: 32.5, x2: 12.5, y2: 32.5, stroke: C.inkSoft, "stroke-width": 2.2, "stroke-linecap": "round", opacity: 0 });
      root.appendChild(out);
      const cursor = el("rect", { x: 20, y: 22.3, width: 2.4, height: 6.4, rx: 0.7, fill: C.acc });
      root.appendChild(cursor);
      return { node: g, update(p) {
        const typeK = Math.min(1, Math.floor(winf(p, 0.1, 0.44) * 6) / 5);
        const reset = eio(winf(p, 0.86, 0.97));
        const len = 14 * typeK * (1 - reset);
        cmd.setAttribute("x2", (19.5 + len).toFixed(2));
        cursor.setAttribute("x", (20.2 + len).toFixed(2));
        cursor.setAttribute("opacity", (p < 0.1 || p > 0.5) ? (Math.floor(p * 12) % 2 === 0 ? 1 : 0.15) : 1);
        const outK = eio(winf(p, 0.52, 0.66)) * (1 - reset);
        out.setAttribute("x2", (12.5 + 19 * outK).toFixed(2));
        out.setAttribute("opacity", (0.8 * outK).toFixed(3));
        glow.set(0.08 + 0.07 * bell(p, 0.55, 0.18));
      } };
    },

    /* Lock: the shackle pops open, drops back and clicks shut. */
    lock(C) {
      const g = grp(), root = grp(), shack = grp();
      const glow = glowDisc(g, C, 24, 26, 16);
      g.appendChild(root);
      root.appendChild(shack);
      sketch(shack, "M16.5 21 L 16.5 14.5 Q 16.5 7.5, 24 7.5 Q 31.5 7.5, 31.5 14.5 L 31.5 21", C, 3);
      const body = grp(); root.appendChild(body);
      body.appendChild(el("path", { d: roundedRectPath(12.5, 21, 23, 16.5, 4), fill: C.accSoft, opacity: 0.5 }));
      sketch(body, roundedRectPath(12.5, 21, 23, 16.5, 4), C, 3);
      const hole = el("circle", { cx: 24, cy: 28, r: 2.6, fill: C.acc }); body.appendChild(hole);
      body.appendChild(el("line", { x1: 24, y1: 29.5, x2: 24, y2: 33, stroke: C.acc, "stroke-width": 2.4, "stroke-linecap": "round" }));
      const ring = el("circle", { cx: 24, cy: 28, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 }); root.appendChild(ring);
      return { node: g, update(p) {
        const up = eio(winf(p, 0.12, 0.3)) * (1 - eob(winf(p, 0.42, 0.58)));
        shack.setAttribute("transform", `translate(0 ${(-4.2 * up).toFixed(2)}) rotate(${(-10 * up).toFixed(2)} 16.5 21)`);
        const clickK = bell(p, 0.585, 0.03);
        body.setAttribute("transform", scaleAt(24, 29, 1 + 0.05 * clickK, 1 - 0.05 * clickK));
        ringSet(ring, winf(p, 0.6, 0.78), 3, 10.5, 0.8);
        hole.setAttribute("r", (2.6 + 0.9 * bell(p, 0.62, 0.06)).toFixed(2));
        glow.set(0.08 + 0.1 * bell(p, 0.62, 0.12));
      } };
    },

    /* Identity: badge shine sweeps the card, the avatar checks in. */
    identity(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      root.appendChild(el("path", { d: roundedRectPath(8, 14, 32, 20.5, 3.5), fill: C.accSoft, opacity: 0.35 }));
      sketch(root, roundedRectPath(8, 14, 32, 20.5, 3.5), C, 2.8);
      root.appendChild(el("circle", { cx: 15.5, cy: 22, r: 3.2, fill: C.acc }));
      sketch(root, "M11 30.5 Q 15.5 25.5, 20 30.5", C, 2.2, 0.85);
      const rows = [[23.5, 20.5], [23.5, 25], [23.5, 29.5]].map(([x, y], i) => {
        const ln = el("line", { x1: x, y1: y, x2: x + (i === 1 ? 12.5 : 9.5), y2: y,
          stroke: C.inkSoft, "stroke-width": 1.8, "stroke-linecap": "round" });
        root.appendChild(ln); return ln;
      });
      const shine = el("line", { x1: 0, y1: 36.5, x2: 0, y2: 12, stroke: C.ink, "stroke-width": 4.5, opacity: 0, "stroke-linecap": "round" });
      root.appendChild(shine);
      const ping = el("circle", { cx: 15.5, cy: 22, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 });
      root.appendChild(ping);
      return { node: g, update(p) {
        const sx = 4 + 40 * eio(winf(p, 0.12, 0.5));
        shine.setAttribute("x1", (sx - 4).toFixed(2)); shine.setAttribute("x2", (sx + 4).toFixed(2));
        shine.setAttribute("opacity", (0.22 * Math.min(1, winf(p, 0.1, 0.18), 1 - winf(p, 0.44, 0.52))).toFixed(3));
        ringSet(ping, winf(p, 0.56, 0.78), 3.5, 9.5, 0.8);
        rows.forEach((ln, i) => {
          const k = bell(p, 0.6 + i * 0.07, 0.05);
          ln.setAttribute("stroke", k > 0.4 ? C.acc : C.inkSoft);
        });
        glow.set(0.08 + 0.08 * bell(p, 0.55, 0.16));
      } };
    },

    /* User: a nod hello, then the presence dot pings. */
    user(C) {
      const g = grp(), root = grp(), head = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      root.appendChild(head);
      sketch(head, circlePath(24, 16, 6.2), C, 2.8);
      sketch(root, "M10.5 37 Q 12 26.5, 24 26.5 Q 36 26.5, 37.5 37", C, 3);
      root.appendChild(el("path", { d: "M10.5 37 Q 12 26.5, 24 26.5 Q 36 26.5, 37.5 37 Z", fill: C.accSoft, opacity: 0.4 }));
      const dot = el("circle", { cx: 34.5, cy: 13.5, r: 2.4, fill: C.acc }); root.appendChild(dot);
      const ring = el("circle", { cx: 34.5, cy: 13.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 }); root.appendChild(ring);
      return { node: g, update(p) {
        const nod = bell(p, 0.28, 0.09);
        head.setAttribute("transform", `translate(0 ${(2.1 * nod).toFixed(2)}) rotate(${(5 * nod).toFixed(2)} 24 22)`);
        dot.setAttribute("r", (2.4 + 1.0 * bell(p, 0.62, 0.05)).toFixed(2));
        ringSet(ring, winf(p, 0.62, 0.85), 3, 9.5, 0.8);
        glow.set(0.08 + 0.07 * bell(p, 0.6, 0.15));
      } };
    },

    /* Audit: checks stamp down the clipboard one line at a time. */
    audit(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(11, 10.5, 26, 28, 3.5), C, 2.8);
      root.appendChild(el("rect", { x: 18.5, y: 7.5, width: 11, height: 5.5, rx: 2, fill: C.accSoft, stroke: C.ink, "stroke-width": 2 }));
      const rows = [17.5, 24, 30.5].map((y) => {
        root.appendChild(el("line", { x1: 22, y1: y, x2: 33, y2: y, stroke: C.inkSoft, "stroke-width": 1.8, "stroke-linecap": "round" }));
        const chk = el("path", { d: `M14.5 ${y - 0.5} L 16.3 ${y + 1.5} L 19.5 ${y - 2.2}`, fill: "none",
          stroke: C.acc, "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round", opacity: 0 });
        root.appendChild(chk); return chk;
      });
      let Ls = [0, 0, 0];
      return { node: g, update(p) {
        rows.forEach((chk, i) => {
          if (!Ls[i]) Ls[i] = chk.getTotalLength();
          const t0 = 0.14 + i * 0.2;
          const kk = eoq(winf(p, t0, t0 + 0.12));
          const hold = 1 - eio(winf(p, 0.84, 0.96));
          chk.setAttribute("stroke-dasharray", `${Ls[i]} ${Ls[i]}`);
          chk.setAttribute("stroke-dashoffset", (Ls[i] * (1 - kk)).toFixed(2));
          chk.setAttribute("opacity", (kk > 0 ? Math.min(1, kk * 3) * hold : 0).toFixed(3));
        });
        glow.set(0.08 + 0.07 * bell(p, 0.5, 0.2));
      } };
    },

    /* Document: lines write themselves onto the page. */
    file(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M13 8.5 L 29 8.5 L 35.5 15 L 35.5 39.5 L 13 39.5 Z", C, 2.8);
      sketch(root, "M29 8.5 L 29 15 L 35.5 15", C, 2.2, 0.7);
      const rows = [[17.5, 21], [17.5, 26], [17.5, 31]].map(([x, y], i) => {
        const full = i === 2 ? 9 : 13.5;
        const ln = el("line", { x1: x, y1: y, x2: x + full, y2: y, stroke: C.acc, "stroke-width": 2, "stroke-linecap": "round" });
        root.appendChild(ln); return { ln, x, full };
      });
      return { node: g, update(p) {
        const fadeBack = eio(winf(p, 0.86, 0.97));
        rows.forEach(({ ln, x, full }, i) => {
          const t0 = 0.1 + i * 0.2;
          const k = eio(winf(p, t0, t0 + 0.16)) * (1 - fadeBack);
          ln.setAttribute("x2", (x + Math.max(0.6, full * k)).toFixed(2));
          ln.setAttribute("opacity", (0.35 + 0.65 * k).toFixed(3));
        });
        glow.set(0.08 + 0.06 * bell(p, 0.45, 0.2));
      } };
    },

    /* Folder: it opens a crack and a document peeks out. */
    folder(C) {
      const g = grp(), root = grp(), doc2 = grp(), lid = grp();
      const glow = glowDisc(g, C, 24, 25, 16);
      g.appendChild(root);
      sketch(root, "M8.5 14.5 L 8.5 35.5 L 39.5 35.5 L 39.5 17.5 L 22.5 17.5 L 19.5 13 L 10 13 Q 8.5 13, 8.5 14.5 Z", C, 2.8);
      root.appendChild(doc2);
      doc2.appendChild(el("rect", { x: 14, y: 21, width: 15, height: 12, rx: 1.5, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.8 }));
      doc2.appendChild(el("line", { x1: 17, y1: 25.5, x2: 26, y2: 25.5, stroke: C.acc, "stroke-width": 1.5, opacity: 0.8 }));
      root.appendChild(lid);
      lid.appendChild(el("path", { d: "M10.5 35.5 L 14.5 21.5 L 43 21.5 L 39.5 35.5 Z", fill: C.accSoft, opacity: 0.5 }));
      sketch(lid, "M10.5 35.5 L 14.5 21.5 L 43 21.5 L 39.5 35.5 Z", C, 2.8);
      return { node: g, update(p) {
        const peek = eio(winf(p, 0.16, 0.4)) * (1 - eio(winf(p, 0.6, 0.84)));
        doc2.setAttribute("transform", `translate(0 ${(-6.5 * peek).toFixed(2)}) rotate(${(-3 * peek).toFixed(2)} 21 27)`);
        lid.setAttribute("transform", `rotate(${(4.5 * peek).toFixed(2)} 10.5 35.5)`);
        glow.set(0.08 + 0.07 * bell(p, 0.4, 0.18));
      } };
    },

    /* Notification: the bell swings and broadcasts. */
    notification(C) {
      const g = grp(), root = grp(), bellG = grp();
      const glow = glowDisc(g, C, 24, 22, 16);
      g.appendChild(root);
      root.appendChild(bellG);
      sketch(bellG, "M13.5 30.5 Q 17.5 27.5, 17.5 20 Q 17.5 10.5, 24 10.5 Q 30.5 10.5, 30.5 20 Q 30.5 27.5, 34.5 30.5 Z", C, 2.8);
      bellG.appendChild(el("path", { d: "M13.5 30.5 Q 17.5 27.5, 17.5 20 Q 17.5 10.5, 24 10.5 Q 30.5 10.5, 30.5 20 Q 30.5 27.5, 34.5 30.5 Z", fill: C.accSoft, opacity: 0.35 }));
      sketch(bellG, "M24 10.5 L 24 7.8", C, 2.2, 0.9);
      const clap = el("circle", { cx: 24, cy: 34.5, r: 2.4, fill: C.acc }); root.appendChild(clap);
      const arcs = [0, 1].map((i) => {
        const a = el("path", { d: i ? "M35.5 13.5 Q 39.5 18.5, 37.5 24.5" : "M12.5 13.5 Q 8.5 18.5, 10.5 24.5",
          fill: "none", stroke: C.acc, "stroke-width": 2, "stroke-linecap": "round", opacity: 0 });
        root.appendChild(a); return a;
      });
      return { node: g, update(p) {
        const env = Math.exp(-3.2 * winf(p, 0.1, 0.9));
        const sw = 11 * Math.sin(2 * Math.PI * (p - 0.1) * 2.6) * (p > 0.1 ? env : 0);
        bellG.setAttribute("transform", `rotate(${sw.toFixed(2)} 24 8.5)`);
        clap.setAttribute("transform", `translate(${(-sw * 0.32).toFixed(2)} 0)`);
        arcs.forEach((a, i) => {
          const k = bell(p, 0.24 + i * 0.05, 0.09) + bell(p, 0.5 + i * 0.05, 0.08) * 0.6;
          a.setAttribute("opacity", Math.min(1, k).toFixed(3));
        });
        glow.set(0.08 + 0.1 * bell(p, 0.3, 0.16));
      } };
    },

    /* Analytics: bars surge in sequence, the trendline draws across. */
    analytics(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M10.5 9.5 L 10.5 37 L 39.5 37", C, 2.8);
      const bars = [[15, 10, 17], [22.5, 15, 22], [30, 21, 28]].map(([x, base, amp]) => {
        const r = el("rect", { x, y: 37 - base, width: 5.2, height: base, rx: 1.4, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.7 });
        root.appendChild(r); return { r, x, base, amp };
      });
      const line = aStroke(root, "M13 30 L 20.5 25 L 28 21 L 36.5 12.5", C, 2.2, { opacity: 0.9 });
      const tip = el("circle", { r: 2, fill: C.acc, opacity: 0 }); root.appendChild(tip);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = line.getTotalLength();
        const settle = 1 - eio(winf(p, 0.78, 0.95));
        bars.forEach(({ r, base, amp }, i) => {
          const k = eob(winf(p, 0.08 + i * 0.13, 0.28 + i * 0.13)) * settle;
          const h = base + (amp - base) * clamp01(k);
          r.setAttribute("height", h.toFixed(2)); r.setAttribute("y", (37 - h).toFixed(2));
        });
        const dk = eio(winf(p, 0.34, 0.68)) * settle;
        line.setAttribute("stroke-dasharray", `${L} ${L}`);
        line.setAttribute("stroke-dashoffset", (L * (1 - dk)).toFixed(2));
        const pt = line.getPointAtLength(L * clamp01(dk));
        tip.setAttribute("cx", pt.x.toFixed(2)); tip.setAttribute("cy", pt.y.toFixed(2));
        tip.setAttribute("opacity", (dk > 0.02 && settle > 0.5 ? 0.95 : 0).toFixed(3));
        glow.set(0.08 + 0.08 * bell(p, 0.55, 0.18));
      } };
    },

    /* Globe: meridians roll by, a point of presence pings. */
    globe(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 24, 15.5), C, 2.9);
      root.appendChild(el("line", { x1: 8.5, y1: 24, x2: 39.5, y2: 24, stroke: C.inkSoft, "stroke-width": 1.8 }));
      root.appendChild(el("path", { d: "M10 17 Q 24 21.5, 38 17 M10 31 Q 24 26.5, 38 31", stroke: C.ghost, "stroke-width": 1.5, fill: "none" }));
      const mer = [0, 1].map(() => { const e = el("ellipse", { cx: 24, cy: 24, rx: 8, ry: 15.5, fill: "none", stroke: C.inkSoft, "stroke-width": 1.7 });
        root.appendChild(e); return e; });
      const pin = el("circle", { cx: 30, cy: 17.5, r: 2.1, fill: C.acc }); root.appendChild(pin);
      const ring = el("circle", { cx: 30, cy: 17.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 }); root.appendChild(ring);
      return { node: g, update(p) {
        mer.forEach((e, i) => {
          const ph = cyc(p + i * 0.5);
          e.setAttribute("rx", (15.5 * Math.abs(Math.cos(Math.PI * ph))).toFixed(2));
          e.setAttribute("opacity", (0.85 * Math.pow(Math.abs(Math.sin(Math.PI * ph)), 0.4)).toFixed(3));
        });
        pin.setAttribute("r", (2.1 + 1.0 * bell(p, 0.5, 0.06)).toFixed(2));
        ringSet(ring, winf(p, 0.5, 0.74), 3, 9.5, 0.8);
        glow.set(0.08 + 0.06 * sinS(p));
      } };
    },

    /* Success: the check stamps in with a bounce and a halo. */
    success(C) {
      const g = grp(), root = grp(), mark = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 24, 15.5), C, 3);
      root.appendChild(el("circle", { cx: 24, cy: 24, r: 15.5, fill: C.accSoft, opacity: 0.35 }));
      root.appendChild(mark);
      const check = aStroke(mark, "M16 24.5 L 21.5 30.5 L 32.5 17.5", C, 3.6);
      const halo = el("circle", { cx: 24, cy: 24, r: 0, fill: "none", stroke: C.acc, "stroke-width": 2, opacity: 0 }); root.appendChild(halo);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = check.getTotalLength();
        const draw = eoq(winf(p, 0.16, 0.42));
        const rest = 1 - eio(winf(p, 0.82, 0.96));
        check.setAttribute("stroke-dasharray", `${L} ${L}`);
        check.setAttribute("stroke-dashoffset", (L * (1 - draw)).toFixed(2));
        check.setAttribute("opacity", (0.25 + 0.75 * Math.min(draw * 3, 1) * rest + 0.75 * (1 - rest) * 0).toFixed(3));
        const pop = 1 + 0.14 * bell(p, 0.44, 0.05);
        mark.setAttribute("transform", scaleAt(24, 24, pop, pop));
        ringSet(halo, winf(p, 0.42, 0.66), 12, 19, 0.7);
        glow.set(0.08 + 0.1 * bell(p, 0.46, 0.12));
      } };
    },

    /* Failure: the cross slams in and the whole badge flinches. */
    failure(C) {
      const g = grp(), root = grp(), mark = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 24, 15.5), C, 3);
      root.appendChild(el("circle", { cx: 24, cy: 24, r: 15.5, fill: C.accSoft, opacity: 0.3 }));
      root.appendChild(mark);
      const x1 = aStroke(mark, "M17.5 17.5 L 30.5 30.5", C, 3.4);
      const x2 = aStroke(mark, "M30.5 17.5 L 17.5 30.5", C, 3.4);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = x1.getTotalLength();
        const d1 = eoq(winf(p, 0.14, 0.3)), d2 = eoq(winf(p, 0.3, 0.46));
        const rest = 1 - eio(winf(p, 0.82, 0.96));
        [[x1, d1], [x2, d2]].forEach(([n, k]) => {
          n.setAttribute("stroke-dasharray", `${L} ${L}`);
          n.setAttribute("stroke-dashoffset", (L * (1 - k)).toFixed(2));
          n.setAttribute("opacity", (0.25 + 0.75 * Math.min(k * 3, 1) * rest).toFixed(3));
        });
        const shake = 1.6 * bell(p, 0.48, 0.05) * Math.sin(2 * Math.PI * p * 14);
        root.setAttribute("transform", `translate(${shake.toFixed(2)} 0)`);
        glow.set(0.08 + 0.1 * bell(p, 0.42, 0.12));
      } };
    },

    /* Retry: the loop arrow whips one full revolution. */
    retry(C) {
      const g = grp(), root = grp(), spin = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      root.appendChild(spin);
      const arc = aStroke(spin, arcPath(24, 24, 13, 30, 300), C, 3);
      void arc;
      aStroke(spin, "M20.5 8.5 L 27 11.2 L 21.5 15.5", C, 2.8);
      root.appendChild(el("circle", { cx: 24, cy: 24, r: 2.3, fill: C.acc, opacity: 0.9 }));
      const dot = el("circle", { r: 1.9, fill: C.ink, opacity: 0 }); root.appendChild(dot);
      return { node: g, update(p) {
        const turn = 360 * eio(winf(p, 0.18, 0.72));
        spin.setAttribute("transform", `rotate(${turn.toFixed(2)} 24 24)`);
        const [dx, dy] = polar(24, 24, 13, 300 + turn);
        dot.setAttribute("cx", dx.toFixed(2)); dot.setAttribute("cy", dy.toFixed(2));
        dot.setAttribute("opacity", (0.9 * bell(winf(p, 0.18, 0.72), 0.5, 0.32)).toFixed(3));
        glow.set(0.08 + 0.08 * bell(p, 0.45, 0.18));
      } };
    },

    /* Trigger event: the bolt strikes and shockwaves radiate. */
    trigger(C) {
      const g = grp(), root = grp(), boltG = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      root.appendChild(boltG);
      const boltD = "M26.5 8.5 L 17.5 24 L 23.5 24 L 20.5 38.5 L 31 21.5 L 24.5 21.5 Z";
      boltG.appendChild(el("path", { d: boltD, fill: C.accSoft, stroke: "none" }));
      sketch(boltG, boltD, C, 2.6);
      const hot = el("path", { d: boltD, fill: C.acc, opacity: 0, stroke: "none" }); boltG.appendChild(hot);
      const rings = [0, 1].map(() => { const r = el("circle", { cx: 24, cy: 23.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 });
        root.appendChild(r); return r; });
      return { node: g, update(p) {
        const strike = bell(p, 0.3, 0.06);
        hot.setAttribute("opacity", Math.min(1, strike * 1.4).toFixed(3));
        boltG.setAttribute("transform", scaleAt(24, 23.5, 1 + 0.1 * strike, 1 + 0.1 * strike));
        rings.forEach((r, i) => ringSet(r, winf(p, 0.32 + i * 0.08, 0.6 + i * 0.08), 6, 17.5, 0.8 - i * 0.25));
        glow.set(0.08 + 0.12 * bell(p, 0.33, 0.1));
      } };
    },

    /* Scope: the target drifts, the reticle locks on. */
    scope(C) {
      const g = grp(), root = grp(), target = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 24, 13.5), C, 2.8);
      sketch(root, "M24 5.5 L 24 12 M24 36 L 24 42.5 M5.5 24 L 12 24 M36 24 L 42.5 24", C, 2.4);
      root.appendChild(target);
      target.appendChild(el("circle", { cx: 24, cy: 24, r: 4.4, fill: "none", stroke: C.acc, "stroke-width": 2 }));
      target.appendChild(el("circle", { cx: 24, cy: 24, r: 1.7, fill: C.acc }));
      const lockRing = el("circle", { cx: 24, cy: 24, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 });
      root.appendChild(lockRing);
      return { node: g, update(p) {
        const wander = 1 - eio(winf(p, 0.42, 0.6));
        const dx = 4.6 * Math.sin(2 * Math.PI * p * 1) * wander;
        const dy = 3.4 * Math.sin(2 * Math.PI * p * 2 + 1.2) * wander;
        target.setAttribute("transform", `translate(${dx.toFixed(2)} ${dy.toFixed(2)})`);
        ringSet(lockRing, winf(p, 0.62, 0.82), 5, 12, 0.85);
        glow.set(0.08 + 0.09 * bell(p, 0.66, 0.12));
      } };
    },

    /* Loop: twin chase arrows swing half a turn and hand off. */
    loop(C) {
      const g = grp(), root = grp(), spin = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root); root.appendChild(spin);
      [[40, 150], [220, 330]].forEach(([a0, a1]) => sketch(spin, arcPath(24, 24, 13, a0, a1), C, 3));
      [150, 330].forEach((deg) => {
        const th = (deg - 90) * Math.PI / 180;
        const [tx, ty] = polar(24, 24, 13, deg);
        const tux = -Math.sin(th), tuy = Math.cos(th);
        const nx = -Math.cos(th), ny = -Math.sin(th);
        aStroke(spin, `M ${(tx - 4.6 * tux - 2.7 * nx).toFixed(2)} ${(ty - 4.6 * tuy - 2.7 * ny).toFixed(2)} L ${tx.toFixed(2)} ${ty.toFixed(2)} L ${(tx - 4.6 * tux + 2.7 * nx).toFixed(2)} ${(ty - 4.6 * tuy + 2.7 * ny).toFixed(2)}`, C, 2.5);
      });
      const core = el("circle", { cx: 24, cy: 24, r: 2, fill: C.acc }); root.appendChild(core);
      return { node: g, update(p) {
        spin.setAttribute("transform", `rotate(${(180 * eob(winf(p, 0.18, 0.62)) - 6 * bell(p, 0.12, 0.05)).toFixed(2)} 24 24)`);
        core.setAttribute("r", (2 + 1.1 * bell(p, 0.64, 0.06)).toFixed(2));
        glow.set(0.08 + 0.08 * bell(p, 0.42, 0.18));
      } };
    },

    /* Plan: the route draws across the folded map, waypoints light up. */
    plan(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M9 13 L 19 10.5 L 29 13 L 39 10.5 L 39 33.5 L 29 36 L 19 33.5 L 9 36 Z", C, 2.8);
      sketch(root, "M19 10.5 L 19 33.5", C, 1.6, 0.4);
      sketch(root, "M29 13 L 29 36", C, 1.6, 0.4);
      const route = aStroke(root, "M13.5 30 Q 18 20, 24 22.5 Q 31 25.5, 34.5 15.5", C, 2.4);
      const fracs = [0.02, 0.5, 0.98];
      const stops = [[13.5, 30], [24, 22.5], [34.5, 15.5]].map(([x, y]) => {
        const s = el("circle", { cx: x, cy: y, r: 2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.2 });
        root.appendChild(s); return s;
      });
      const ring = el("circle", { cx: 34.5, cy: 15.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 });
      root.appendChild(ring);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = route.getTotalLength();
        const k = eio(winf(p, 0.12, 0.56)) * (1 - eio(winf(p, 0.86, 0.97)));
        route.setAttribute("stroke-dasharray", `${L} ${L}`);
        route.setAttribute("stroke-dashoffset", (L * (1 - k)).toFixed(2));
        stops.forEach((s, i) => {
          const on = clamp01((k - fracs[i]) / 0.07);
          s.setAttribute("fill", on > 0.5 ? C.acc : C.accSoft);
          s.setAttribute("r", (2 + 1.0 * on * (1 - 0.4 * winf(p, 0.86, 0.97))).toFixed(2));
        });
        ringSet(ring, winf(p, 0.58, 0.78), 3, 9, 0.8);
        glow.set(0.08 + 0.07 * bell(p, 0.55, 0.18));
      } };
    },

    /* Decision: a token enters the diamond, it deliberates, routes right. */
    decision(C) {
      const g = grp(), root = grp(), dia = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M2.5 24 L 8 24", C, 2.2, 0.55);
      sketch(root, "M40 24 L 45.5 24", C, 2.2, 0.55);
      root.appendChild(dia);
      dia.appendChild(el("path", { d: "M24 9.5 L 38.5 24 L 24 38.5 L 9.5 24 Z", fill: C.accSoft, opacity: 0.38 }));
      sketch(dia, "M24 9.5 L 38.5 24 L 24 38.5 L 9.5 24 Z", C, 2.8);
      const qm = el("g", { opacity: 0.55 }); dia.appendChild(qm);
      qm.appendChild(el("path", { d: "M20.8 20.2 Q 20.8 16.6, 24.2 16.6 Q 27.6 16.6, 27.6 19.8 Q 27.6 22.4, 24.4 23.2 L 24.4 25.6",
        fill: "none", stroke: C.acc, "stroke-width": 2.2, "stroke-linecap": "round" }));
      qm.appendChild(el("circle", { cx: 24.4, cy: 29.8, r: 1.6, fill: C.acc }));
      const token = el("circle", { r: 2.4, fill: C.acc, opacity: 0 }); root.appendChild(token);
      return { node: g, update(p) {
        const enter = eio(winf(p, 0.06, 0.28));
        const exit = eio(winf(p, 0.62, 0.86));
        token.setAttribute("cx", (3.5 + 20.5 * enter + 20.5 * exit).toFixed(2));
        token.setAttribute("cy", 24);
        token.setAttribute("opacity", (Math.min(1, winf(p, 0.04, 0.1), 1 - winf(p, 0.84, 0.9)) * 0.95).toFixed(3));
        const think = bell(p, 0.45, 0.1);
        dia.setAttribute("transform", scaleAt(24, 24, 1 + 0.05 * think, 1 + 0.05 * think));
        qm.setAttribute("opacity", (0.55 + 0.45 * think).toFixed(3));
        glow.set(0.08 + 0.09 * bell(p, 0.48, 0.14));
      } };
    },

    /* Merge: two lane payloads fuse into one heavier token. */
    merge(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const laneA = sketch(root, "M6.5 14.5 L 16.5 14.5 Q 22.5 14.5, 25.4 19.8 L 26.8 22.4", C, 2.6);
      const laneB = sketch(root, "M6.5 33.5 L 16.5 33.5 Q 22.5 33.5, 25.4 28.2 L 26.8 25.6", C, 2.6);
      sketch(root, "M26.8 24 L 41.5 24", C, 3);
      root.appendChild(el("circle", { cx: 26.8, cy: 24, r: 2, fill: C.inkSoft }));
      const dA = el("circle", { r: 2.2, fill: C.acc, opacity: 0 }), dB = el("circle", { r: 2.2, fill: C.acc, opacity: 0 });
      const dM = el("circle", { r: 3, fill: C.acc, opacity: 0, cy: 24 });
      root.appendChild(dA); root.appendChild(dB); root.appendChild(dM);
      const ring = el("circle", { cx: 26.8, cy: 24, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 });
      root.appendChild(ring);
      let LA = 0, LB = 0;
      return { node: g, update(p) {
        if (!LA) { LA = laneA.getTotalLength(); LB = laneB.getTotalLength(); }
        const u = eio(winf(p, 0.08, 0.42));
        [[dA, laneA, LA], [dB, laneB, LB]].forEach(([d, lane, L]) => {
          const pt = lane.getPointAtLength(L * u);
          d.setAttribute("cx", pt.x.toFixed(2)); d.setAttribute("cy", pt.y.toFixed(2));
          d.setAttribute("opacity", (u > 0 && u < 1 ? Math.min(1, winf(p, 0.06, 0.12)) * 0.95 : 0).toFixed(3));
        });
        ringSet(ring, winf(p, 0.42, 0.58), 2.5, 8.5, 0.85);
        const v = eio(winf(p, 0.46, 0.78));
        dM.setAttribute("cx", (26.8 + 13.5 * v).toFixed(2));
        dM.setAttribute("opacity", (v > 0 && v < 1 ? 0.95 : 0).toFixed(3));
        glow.set(0.08 + 0.1 * bell(p, 0.45, 0.12));
      } };
    },

    /* Split: one payload fans out into two parallel branches. */
    split(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M6.5 24 L 21.2 24", C, 3);
      const laneA = sketch(root, "M21.2 24 Q 27 24, 30 19.2 Q 33 14.5, 41.5 14.5", C, 2.6);
      const laneB = sketch(root, "M21.2 24 Q 27 24, 30 28.8 Q 33 33.5, 41.5 33.5", C, 2.6);
      root.appendChild(el("circle", { cx: 21.2, cy: 24, r: 2, fill: C.inkSoft }));
      const dIn = el("circle", { r: 3, fill: C.acc, opacity: 0, cy: 24 });
      const dA = el("circle", { r: 2.2, fill: C.acc, opacity: 0 }), dB = el("circle", { r: 2.2, fill: C.acc, opacity: 0 });
      root.appendChild(dIn); root.appendChild(dA); root.appendChild(dB);
      let LA = 0, LB = 0;
      return { node: g, update(p) {
        if (!LA) { LA = laneA.getTotalLength(); LB = laneB.getTotalLength(); }
        const u = eio(winf(p, 0.08, 0.36));
        dIn.setAttribute("cx", (6.5 + 14.7 * u).toFixed(2));
        dIn.setAttribute("opacity", (u > 0 && u < 1 ? Math.min(1, winf(p, 0.06, 0.12)) * 0.95 : 0).toFixed(3));
        const v = eio(winf(p, 0.38, 0.8));
        [[dA, laneA, LA], [dB, laneB, LB]].forEach(([d, lane, L]) => {
          const pt = lane.getPointAtLength(L * v);
          d.setAttribute("cx", pt.x.toFixed(2)); d.setAttribute("cy", pt.y.toFixed(2));
          d.setAttribute("opacity", (v > 0 && v < 1 ? 0.95 : 0).toFixed(3));
        });
        glow.set(0.08 + 0.09 * bell(p, 0.4, 0.14));
      } };
    },

    /* Handoff: the baton arcs from one runner node to the next. */
    handoff(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 27, 16);
      g.appendChild(root);
      sketch(root, circlePath(13.5, 29, 6.4), C, 2.8);
      sketch(root, circlePath(34.5, 29, 6.4), C, 2.8);
      const coreA = el("circle", { cx: 13.5, cy: 29, r: 2.2, fill: C.acc });
      const coreB = el("circle", { cx: 34.5, cy: 29, r: 2.2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.1 });
      root.appendChild(coreA); root.appendChild(coreB);
      const baton = el("rect", { x: -2.8, y: -1.7, width: 5.6, height: 3.4, rx: 1.2, fill: C.acc, opacity: 0 });
      root.appendChild(baton);
      const ring = el("circle", { cx: 34.5, cy: 29, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 });
      root.appendChild(ring);
      return { node: g, update(p) {
        const u = eio(winf(p, 0.16, 0.52));
        const x = 13.5 + 21 * u, y = 20.5 - 12 * Math.sin(Math.PI * u);
        baton.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${(200 * u).toFixed(1)})`);
        baton.setAttribute("opacity", (Math.min(1, winf(p, 0.12, 0.18), 1 - winf(p, 0.52, 0.58)) * 0.95).toFixed(3));
        const swap = p > 0.54;
        coreA.setAttribute("fill", swap ? C.accSoft : C.acc);
        coreB.setAttribute("fill", swap ? C.acc : C.accSoft);
        coreB.setAttribute("r", (2.2 + 1.1 * bell(p, 0.56, 0.05)).toFixed(2));
        ringSet(ring, winf(p, 0.56, 0.76), 7, 11.5, 0.8);
        glow.set(0.08 + 0.09 * bell(p, 0.55, 0.14));
      } };
    },

    /* Subagent: the parent boots a mini worker at its side. */
    subagent(C) {
      const g = grp(), root = grp(), mini = grp();
      const glow = glowDisc(g, C, 22, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(7.5, 13, 21.5, 17.5, 5), C, 2.8);
      sketch(root, "M18.2 13 L 18.2 9.4", C, 2, 0.9);
      root.appendChild(el("circle", { cx: 18.2, cy: 8.2, r: 1.7, fill: C.acc }));
      const eyes = [13.5, 23].map((x) => { const e = el("circle", { cx: x, cy: 21.5, r: 2.1, fill: C.acc }); root.appendChild(e); return e; });
      const link = aStroke(root, "M29.2 21.8 Q 37 21.8, 37 27.2", C, 2, { opacity: 0.85 });
      root.appendChild(mini);
      sketch(mini, roundedRectPath(30.5, 27.5, 13, 11, 3.5), C, 2.4);
      [34.2, 39.8].forEach((x) => mini.appendChild(el("circle", { cx: x, cy: 32.8, r: 1.5, fill: C.acc })));
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = link.getTotalLength();
        const wire = eio(winf(p, 0.1, 0.3));
        link.setAttribute("stroke-dasharray", `${L} ${L}`);
        link.setAttribute("stroke-dashoffset", (L * (1 - wire)).toFixed(2));
        const grow = eob(winf(p, 0.3, 0.5)) * (1 - eio(winf(p, 0.86, 0.98)));
        mini.setAttribute("transform", scaleAt(37, 33, Math.max(0.0001, grow), Math.max(0.0001, grow)));
        const gl = 1.4 * (eio(winf(p, 0.32, 0.42)) - eio(winf(p, 0.72, 0.82)));
        eyes.forEach((e) => e.setAttribute("transform", `translate(${gl.toFixed(2)} 0)`));
        glow.set(0.08 + 0.09 * bell(p, 0.42, 0.16));
      } };
    },

    /* Orchestrator: the conductor dispatches to three workers in turn. */
    orchestrator(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, circlePath(24, 12.5, 5.6), C, 2.8);
      const core = el("circle", { cx: 24, cy: 12.5, r: 2, fill: C.acc }); root.appendChild(core);
      const kids = [10.5, 24, 37.5].map((x) => {
        const wire = sketch(root, `M24 18.4 C 24 23.5, ${x} 21.5, ${x} 26.6`, C, 1.8, 0.55);
        sketch(root, roundedRectPath(x - 4.5, 27, 9, 9, 2.2), C, 2.4);
        const dot = el("circle", { cx: x, cy: 31.5, r: 1.7, fill: C.accSoft, stroke: C.acc, "stroke-width": 1 });
        root.appendChild(dot);
        return { wire, dot, sig: root.appendChild(el("circle", { r: 1.9, fill: C.acc, opacity: 0 })) };
      });
      return { node: g, update(p) {
        kids.forEach(({ wire, dot, sig }, i) => {
          const L = wire.getTotalLength();
          const u = eio(winf(p, 0.08 + i * 0.22, 0.3 + i * 0.22));
          const pt = wire.getPointAtLength(L * u);
          sig.setAttribute("cx", pt.x.toFixed(2)); sig.setAttribute("cy", pt.y.toFixed(2));
          sig.setAttribute("opacity", (u > 0 && u < 1 ? 0.95 : 0).toFixed(3));
          const hit = Math.min(1, bell(p, 0.32 + i * 0.22, 0.05));
          dot.setAttribute("fill", hit > 0.4 ? C.acc : C.accSoft);
          dot.setAttribute("r", (1.7 + 1.0 * hit).toFixed(2));
        });
        core.setAttribute("r", (2 + 0.9 * (bell(p, 0.08, 0.04) + bell(p, 0.3, 0.04) + bell(p, 0.52, 0.04))).toFixed(2));
        glow.set(0.08 + 0.07 * bell(p, 0.4, 0.25));
      } };
    },

    /* Human-in-loop: the reviewer holds the gate, then approves. */
    human(C) {
      const g = grp(), root = grp(), person = grp(), head = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root); root.appendChild(person); person.appendChild(head);
      sketch(head, circlePath(15.5, 15.5, 4.6), C, 2.6);
      sketch(person, "M7.5 32 Q 9 23.5, 15.5 23.5 Q 22 23.5, 23.5 32", C, 2.8);
      sketch(root, roundedRectPath(27, 12.5, 14, 21.5, 3.2), C, 2.6);
      const bars = [31.3, 36.7].map((x) => {
        const b = el("line", { x1: x, y1: 17, x2: x, y2: 24, stroke: C.acc, "stroke-width": 2.5, "stroke-linecap": "round" });
        root.appendChild(b); return b;
      });
      const check = aStroke(root, "M30.2 28.8 L 33.2 31.6 L 38 25.6", C, 2.6, { opacity: 0 });
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = check.getTotalLength();
        const nod = bell(p, 0.4, 0.07);
        head.setAttribute("transform", `translate(0 ${(1.9 * nod).toFixed(2)}) rotate(${(4 * nod).toFixed(2)} 15.5 21)`);
        const waitK = p < 0.44 ? 0.45 + 0.55 * Math.pow(sinS(p * 4.5), 2) : 1 - winf(p, 0.46, 0.56);
        bars.forEach((b) => b.setAttribute("opacity", clamp01(p > 0.9 ? winf(p, 0.9, 0.99) * 0.45 : waitK).toFixed(3)));
        const draw = eoq(winf(p, 0.52, 0.7)) * (1 - eio(winf(p, 0.86, 0.96)));
        check.setAttribute("stroke-dasharray", `${L} ${L}`);
        check.setAttribute("stroke-dashoffset", (L * (1 - draw)).toFixed(2));
        check.setAttribute("opacity", (draw > 0 ? Math.min(1, draw * 3) : 0).toFixed(3));
        glow.set(0.08 + 0.09 * bell(p, 0.6, 0.14));
      } };
    },

    /* Checkpoint: a runner dot reaches the planted flag, which flaps proudly. */
    checkpoint(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 28, 24, 16);
      g.appendChild(root);
      sketch(root, "M6.5 36.5 L 41.5 36.5", C, 2.8);
      [13, 21.5].forEach((x) => root.appendChild(el("circle", { cx: x, cy: 36.5, r: 1.7, fill: C.inkSoft })));
      sketch(root, "M31.5 36.5 L 31.5 14.5", C, 2.6);
      const flag = el("path", { d: "M31.5 14.8 L 41.5 18.4 L 31.5 22 Z", fill: C.acc, opacity: 0.92 });
      root.appendChild(flag);
      const base = el("circle", { cx: 31.5, cy: 36.5, r: 1.9, fill: C.acc }); root.appendChild(base);
      const runner = el("circle", { cy: 36.5, r: 2.2, fill: C.acc, opacity: 0 }); root.appendChild(runner);
      const ring = el("circle", { cx: 31.5, cy: 36.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 });
      root.appendChild(ring);
      return { node: g, update(p) {
        const u = eio(winf(p, 0.08, 0.42));
        runner.setAttribute("cx", (7.5 + 24 * u).toFixed(2));
        runner.setAttribute("opacity", (Math.min(1, winf(p, 0.06, 0.12), 1 - winf(p, 0.4, 0.46)) * 0.95).toFixed(3));
        ringSet(ring, winf(p, 0.42, 0.6), 2.5, 9, 0.8);
        const flap = 0.14 * Math.sin(2 * Math.PI * p * 3) * bell(p, 0.55, 0.14);
        flag.setAttribute("transform", scaleAt(31.5, 18.4, 1 + flap, 1 - 0.5 * flap));
        base.setAttribute("r", (1.9 + 1.0 * bell(p, 0.45, 0.05)).toFixed(2));
        glow.set(0.08 + 0.09 * bell(p, 0.5, 0.16));
      } };
    },

    /* Rollback: a glint rides the rewind arc back to the earlier state. */
    rollback(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M8 31.5 L 40 31.5", C, 2.8);
      const arc = sketch(root, "M35.5 26.5 Q 35.5 11.5, 24 11.5 Q 12.5 11.5, 12.5 24", C, 2.6);
      sketch(root, "M9.4 20.8 L 12.5 25 L 15.6 20.9", C, 2.6);
      const dots = [12.5, 24, 35.5].map((x) => {
        const d = el("circle", { cx: x, cy: 31.5, r: 2.1, fill: x > 30 ? C.acc : C.inkSoft });
        root.appendChild(d); return d;
      });
      const glint = el("circle", { r: 2.2, fill: C.acc, opacity: 0 }); root.appendChild(glint);
      const ring = el("circle", { cx: 12.5, cy: 31.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.7, opacity: 0 });
      root.appendChild(ring);
      let L = 0;
      return { node: g, update(p) {
        if (!L) L = arc.getTotalLength();
        const u = eio(winf(p, 0.12, 0.52));
        const pt = arc.getPointAtLength(L * u);
        glint.setAttribute("cx", pt.x.toFixed(2)); glint.setAttribute("cy", pt.y.toFixed(2));
        glint.setAttribute("opacity", (Math.min(1, winf(p, 0.1, 0.16), 1 - winf(p, 0.5, 0.56)) * 0.95).toFixed(3));
        ringSet(ring, winf(p, 0.54, 0.72), 2.5, 8.5, 0.8);
        const flash = Math.min(1, bell(p, 0.58, 0.06));
        dots[0].setAttribute("fill", flash > 0.4 || (p > 0.58 && p < 0.88) ? C.acc : C.inkSoft);
        dots[0].setAttribute("r", (2.1 + 1.1 * flash).toFixed(2));
        dots[2].setAttribute("fill", p > 0.56 && p < 0.9 ? C.accSoft : C.acc);
        glow.set(0.08 + 0.08 * bell(p, 0.55, 0.16));
      } };
    },

    /* Sandbox: the experiment bubbles inside the flask. */
    sandbox(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 28, 16);
      g.appendChild(root);
      sketch(root, "M20.5 8.5 L 20.5 17 L 12 33.5 Q 10.5 36.5, 14 36.5 L 34 36.5 Q 37.5 36.5, 36 33.5 L 27.5 17 L 27.5 8.5", C, 2.8);
      sketch(root, "M17.8 8.5 L 30.2 8.5", C, 2.6);
      const liquid = el("path", { d: "", fill: C.accSoft, opacity: 0.85 }); root.appendChild(liquid);
      const surface = el("line", { stroke: C.acc, "stroke-width": 2.2, "stroke-linecap": "round" }); root.appendChild(surface);
      const bubbles = [0, 1].map(() => { const b = el("circle", { r: 1.2, fill: C.acc, opacity: 0 }); root.appendChild(b); return b; });
      const hw = (y) => 3.2 + (y - 17) * 0.52;
      return { node: g, update(p) {
        const yl = 30.5 - 3.5 * sinS(p);
        const w1 = hw(yl), w2 = hw(34.8);
        liquid.setAttribute("d", `M ${(24 - w1).toFixed(2)} ${yl.toFixed(2)} L ${(24 + w1).toFixed(2)} ${yl.toFixed(2)} L ${(24 + w2).toFixed(2)} 34.8 Q 24 36.2, ${(24 - w2).toFixed(2)} 34.8 Z`);
        surface.setAttribute("x1", (24 - w1).toFixed(2)); surface.setAttribute("x2", (24 + w1).toFixed(2));
        surface.setAttribute("y1", yl.toFixed(2)); surface.setAttribute("y2", yl.toFixed(2));
        bubbles.forEach((b, i) => {
          const u = cyc(p * 2 + i * 0.5);
          const by = 33.5 - (33.5 - yl - 1.5) * u;
          b.setAttribute("cx", (24 + (i ? -2.6 : 2.2) * Math.sin(2 * Math.PI * u)).toFixed(2));
          b.setAttribute("cy", by.toFixed(2));
          b.setAttribute("opacity", (0.9 * Math.min(1, u / 0.15, (1 - u) / 0.12)).toFixed(3));
        });
        glow.set(0.08 + 0.06 * sinS(p));
      } };
    },

    /* Compare: A/B panels trade weight on the balance. */
    compare(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, roundedRectPath(8.5, 13.5, 13.5, 21, 3), C, 2.6);
      sketch(root, roundedRectPath(26, 13.5, 13.5, 21, 3), C, 2.6);
      const barL = el("rect", { x: 11.5, width: 7.5, rx: 1.2, fill: C.accSoft, stroke: C.acc, "stroke-width": 1.5 });
      const barR = el("rect", { x: 29, width: 7.5, rx: 1.2, fill: C.accSoft, stroke: C.inkSoft, "stroke-width": 1.5 });
      root.appendChild(barL); root.appendChild(barR);
      const markL = el("circle", { cx: 15.2, cy: 9.5, r: 1.9, fill: C.acc, opacity: 0 });
      const markR = el("circle", { cx: 32.8, cy: 9.5, r: 1.9, fill: C.acc, opacity: 0 });
      root.appendChild(markL); root.appendChild(markR);
      return { node: g, update(p) {
        const k = sinS(p);
        const hL = 7 + 8 * k, hR = 15 - 8 * k;
        barL.setAttribute("y", (31.5 - hL).toFixed(2)); barL.setAttribute("height", hL.toFixed(2));
        barR.setAttribute("y", (31.5 - hR).toFixed(2)); barR.setAttribute("height", hR.toFixed(2));
        barL.setAttribute("fill", k > 0.6 ? C.acc : C.accSoft);
        barR.setAttribute("fill", k < 0.4 ? C.acc : C.accSoft);
        root.setAttribute("transform", `rotate(${((k - 0.5) * 3.6).toFixed(2)} 24 34.5)`);
        markL.setAttribute("opacity", (clamp01((k - 0.72) / 0.2) * 0.95).toFixed(3));
        markR.setAttribute("opacity", (clamp01((0.28 - k) / 0.2) * 0.95).toFixed(3));
        glow.set(0.08 + 0.05 * Math.abs(k - 0.5) * 2);
      } };
    },

    /* Score: the meter fills and the star stamps its rating. */
    score(C) {
      const g = grp(), root = grp(), star = grp();
      const glow = glowDisc(g, C, 24, 22, 16);
      g.appendChild(root);
      let starD = "";
      for (let i = 0; i < 10; i++) {
        const [sx, sy] = polar(24, 21, i % 2 ? 5.4 : 12.3, i * 36);
        starD += (i ? "L" : "M") + ` ${sx.toFixed(2)} ${sy.toFixed(2)} `;
      }
      root.appendChild(star);
      const fillP = el("path", { d: starD + "Z", fill: C.acc, opacity: 0 }); star.appendChild(fillP);
      sketch(star, starD + "Z", C, 2.6);
      sketch(root, "M13 38.5 L 35 38.5", C, 2.2, 0.5);
      const meter = el("line", { x1: 13, y1: 38.5, x2: 13, y2: 38.5, stroke: C.acc, "stroke-width": 2.6, "stroke-linecap": "round" });
      root.appendChild(meter);
      return { node: g, update(p) {
        const fill = eio(winf(p, 0.08, 0.5)) * (1 - eio(winf(p, 0.88, 0.98)));
        meter.setAttribute("x2", (13 + 22 * fill).toFixed(2));
        const pop = 1 + 0.14 * bell(p, 0.56, 0.05);
        star.setAttribute("transform", scaleAt(24, 21, pop, pop));
        fillP.setAttribute("opacity", (0.5 * (bell(p, 0.58, 0.1) + clamp01((p - 0.58) / 0.06) * (1 - winf(p, 0.84, 0.95)) * 0.7)).toFixed(3));
        glow.set(0.08 + 0.1 * bell(p, 0.58, 0.12));
      } };
    },

    /* Error: the warning triangle flinches and the bang blinks. */
    error(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 26, 16);
      g.appendChild(root);
      root.appendChild(el("path", { d: "M24 9 L 41 36.5 L 7 36.5 Z", fill: C.accSoft, opacity: 0.3 }));
      sketch(root, "M24 9 L 41 36.5 L 7 36.5 Z", C, 2.8);
      const bang = grp(); root.appendChild(bang);
      bang.appendChild(el("line", { x1: 24, y1: 18, x2: 24, y2: 27.5, stroke: C.acc, "stroke-width": 3, "stroke-linecap": "round" }));
      bang.appendChild(el("circle", { cx: 24, cy: 32.4, r: 1.9, fill: C.acc }));
      const ring = el("circle", { cx: 24, cy: 25, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 });
      root.appendChild(ring);
      return { node: g, update(p) {
        root.setAttribute("transform", `translate(${(2.1 * Math.sin(2 * Math.PI * p * 9) * bell(p, 0.3, 0.06)).toFixed(2)} 0)`);
        bang.setAttribute("opacity", (0.45 + 0.55 * Math.min(1, bell(p, 0.28, 0.05) + bell(p, 0.45, 0.05) + bell(p, 0.62, 0.05))).toFixed(3));
        ringSet(ring, winf(p, 0.64, 0.85), 6, 14.5, 0.7);
        glow.set(0.08 + 0.11 * bell(p, 0.35, 0.14));
      } };
    },

    /* Wait: the hourglass drains, then the sand fades back full. */
    wait(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      sketch(root, "M14.5 9 L 33.5 9", C, 2.8);
      sketch(root, "M14.5 39 L 33.5 39", C, 2.8);
      sketch(root, "M17 9 L 17 12 Q 17 19, 22.2 24 Q 17 29, 17 36 L 17 39", C, 2.6);
      sketch(root, "M31 9 L 31 12 Q 31 19, 25.8 24 Q 31 29, 31 36 L 31 39", C, 2.6);
      const sandTop = el("path", { d: "", fill: C.accSoft, opacity: 0.9 }); root.appendChild(sandTop);
      const topLine = el("line", { stroke: C.acc, "stroke-width": 1.8, "stroke-linecap": "round" }); root.appendChild(topLine);
      const stream = el("line", { x1: 24, y1: 24.5, x2: 24, y2: 36.5, stroke: C.acc, "stroke-width": 1.6,
        "stroke-dasharray": "2.2 3.2", opacity: 0 }); root.appendChild(stream);
      const pile = el("path", { d: "", fill: C.acc, opacity: 0.9 }); root.appendChild(pile);
      const hwTop = (y) => Math.max(0.6, 6.4 - (y - 12) * 0.52);
      return { node: g, update(p) {
        const drain = eio(winf(p, 0.08, 0.78));
        const refill = eio(winf(p, 0.86, 0.98));
        const level = 12.5 + 8.5 * drain;
        const w = hwTop(level);
        sandTop.setAttribute("d", `M ${(24 - w).toFixed(2)} ${level.toFixed(2)} L ${(24 + w).toFixed(2)} ${level.toFixed(2)} L 24 22.6 Z`);
        sandTop.setAttribute("opacity", (0.9 * (1 - drain * 0.999) > 0.001 || refill > 0 ? 0.9 * Math.max(1 - drain, refill) : 0).toFixed(3));
        topLine.setAttribute("x1", (24 - w).toFixed(2)); topLine.setAttribute("x2", (24 + w).toFixed(2));
        topLine.setAttribute("y1", level.toFixed(2)); topLine.setAttribute("y2", level.toFixed(2));
        topLine.setAttribute("opacity", Math.max(1 - drain, refill).toFixed(3));
        stream.setAttribute("opacity", (drain > 0.02 && drain < 0.98 ? 0.85 : 0).toFixed(3));
        stream.setAttribute("stroke-dashoffset", (-p * 32).toFixed(2));
        const ph = 1.2 + 4.6 * Math.max(drain, refill * 0);
        const pw = 2.5 + 6.5 * drain;
        pile.setAttribute("d", `M ${(24 - pw).toFixed(2)} 38.6 Q 24 ${(38.6 - 2 * ph).toFixed(2)}, ${(24 + pw).toFixed(2)} 38.6 Z`);
        pile.setAttribute("opacity", (0.9 * (1 - refill)).toFixed(3));
        glow.set(0.08 + 0.05 * sinS(p));
      } };
    },

    /* Emit: the beacon mast broadcasts expanding waves. */
    emit(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 18, 16);
      g.appendChild(root);
      sketch(root, "M24 16 L 24 30.5", C, 2.8);
      sketch(root, "M24 22.5 L 16 38.5 M24 22.5 L 32 38.5 M18.9 32.4 L 29.1 32.4", C, 2.4);
      const tip = el("circle", { cx: 24, cy: 14.2, r: 2.1, fill: C.acc }); root.appendChild(tip);
      const waves = [5.5, 9, 12.5].map((r) => {
        const a = el("path", { d: arcPath(24, 13.2, r, -52, 52), fill: "none", stroke: C.acc,
          "stroke-width": 1.9, "stroke-linecap": "round", opacity: 0 });
        root.appendChild(a); return a;
      });
      return { node: g, update(p) {
        waves.forEach((a, i) => {
          const k = bell(cyc(p * 2), 0.22 + i * 0.17, 0.11);
          a.setAttribute("opacity", (0.9 * Math.min(1, k)).toFixed(3));
        });
        tip.setAttribute("r", (2.1 + 1.0 * bell(cyc(p * 2), 0.14, 0.08)).toFixed(2));
        glow.set(0.08 + 0.08 * bell(cyc(p * 2), 0.3, 0.2));
      } };
    },

    /* Ingest: payloads drop into the intake tray. */
    ingest(C) {
      const g = grp(), root = grp(), tray = grp();
      const glow = glowDisc(g, C, 24, 30, 16);
      g.appendChild(root);
      root.appendChild(tray);
      sketch(tray, "M9 25.5 L 9 34.5 Q 9 38, 12.5 38 L 35.5 38 Q 39 38, 39 34.5 L 39 25.5", C, 2.8);
      sketch(tray, "M9 30.5 L 15.5 30.5 L 18.5 33.5 L 29.5 33.5 L 32.5 30.5 L 39 30.5", C, 2, 0.6);
      const chev = aStroke(root, "M19.5 11.5 L 24 16 L 28.5 11.5", C, 2.2, { opacity: 0.65 });
      const drops = [17.5, 24, 30.5].map((x) => {
        const d = el("circle", { cx: x, r: 2, fill: C.acc, opacity: 0 }); root.appendChild(d); return d;
      });
      return { node: g, update(p) {
        let land = 0;
        drops.forEach((d, i) => {
          const u = cyc(p + i / 3);
          const fall = Math.pow(winf(u, 0.1, 0.52), 1.6);
          d.setAttribute("cy", (7 + 21 * fall).toFixed(2));
          d.setAttribute("opacity", (Math.min(1, winf(u, 0.06, 0.14), (1 - winf(u, 0.5, 0.58))) * 0.95).toFixed(3));
          land += bell(u, 0.53, 0.04);
        });
        const squash = Math.min(1, land);
        tray.setAttribute("transform", scaleAt(24, 38, 1 + 0.03 * squash, 1 - 0.035 * squash));
        chev.setAttribute("opacity", (0.4 + 0.5 * sinS(p * 3)).toFixed(3));
        glow.set(0.08 + 0.06 * squash);
      } };
    },

    /* Firewall: a threat dart is deflected off the bricks. */
    firewall(C) {
      const g = grp(), root = grp();
      const glow = glowDisc(g, C, 24, 24, 16);
      g.appendChild(root);
      const bricks = [];
      [[11, 12.5, 12], [24.5, 12.5, 12.5], [11, 20.5, 7], [19.5, 20.5, 9.5], [30.5, 20.5, 6.5], [11, 28.5, 12], [24.5, 28.5, 12.5]].forEach(([x, y, w]) => {
        const b = el("path", { d: roundedRectPath(x, y, w, 6.5, 1.2), fill: C.accSoft, opacity: 0.35, stroke: "none" });
        root.appendChild(b);
        sketch(root, roundedRectPath(x, y, w, 6.5, 1.2), C, 2.2);
        bricks.push({ b, x, y, w });
      });
      const dart = el("circle", { r: 2.2, fill: C.danger, opacity: 0 }); root.appendChild(dart);
      const spark = el("circle", { cx: 19, cy: 23.5, r: 0, fill: "none", stroke: C.acc, "stroke-width": 1.8, opacity: 0 }); root.appendChild(spark);
      return { node: g, update(p) {
        const inK = Math.pow(winf(p, 0.12, 0.3), 1.4);
        const outK = winf(p, 0.3, 0.5);
        let x, y;
        if (outK <= 0) { x = 2 + 16 * inK; y = 10 + 12.5 * inK; }
        else { x = 18 - 12 * outK; y = 22.5 - 16 * outK * (1 - 0.4 * outK); }
        dart.setAttribute("cx", x.toFixed(2)); dart.setAttribute("cy", y.toFixed(2));
        dart.setAttribute("opacity", ((inK > 0 && outK < 1) ? Math.min(1, winf(p, 0.1, 0.16)) * (1 - outK) : 0).toFixed(3));
        ringSet(spark, winf(p, 0.29, 0.45), 2, 8.5, 0.85);
        const hitK = bell(p, 0.32, 0.07);
        bricks.forEach(({ b, x: bx, y: by }) => {
          const near = Math.exp(-((Math.pow(bx + 5 - 18, 2) + Math.pow(by + 3 - 23, 2)) / 90));
          b.setAttribute("fill", hitK * near > 0.35 ? C.acc : C.accSoft);
        });
        root.setAttribute("transform", `translate(${(1.4 * bell(p, 0.32, 0.04)).toFixed(2)} 0)`);
        glow.set(0.08 + 0.1 * bell(p, 0.34, 0.12));
      } };
    },
  };

  /* Route every semantic key to its builder family (specific keys first). */
  const illKeyFor = (s) => {
    if (/^(loop|iterate|cycle)/.test(s)) return "loop";
    if (/^(plan|roadmap)/.test(s)) return "plan";
    if (/^(decision|condition|if-)/.test(s)) return "decision";
    if (/^(merge|join|aggregate)/.test(s)) return "merge";
    if (/^(split|fanout|fan-out|parallel|branch)/.test(s)) return "split";
    if (/^(handoff|hand-off|delegate)/.test(s)) return "handoff";
    if (/^(subagent|sub-agent|worker)/.test(s)) return "subagent";
    if (/^(orchestr|coordinator|dispatch)/.test(s)) return "orchestrator";
    if (/^(human|review|approval|hitl)/.test(s)) return "human";
    if (/^(checkpoint|milestone)/.test(s)) return "checkpoint";
    if (/^(rollback|revert|undo)/.test(s)) return "rollback";
    if (/^(sandbox|experiment|lab)/.test(s)) return "sandbox";
    if (/^(compare|ab-test|benchmark|versus)/.test(s)) return "compare";
    if (/^(score|grade|rating|rank)/.test(s)) return "score";
    if (/^(error|exception|fault|warning)/.test(s)) return "error";
    if (/^(wait|delay|timeout|sleep|hourglass)/.test(s)) return "wait";
    if (/^(emit|broadcast|publish|webhook)/.test(s)) return "emit";
    if (/^(ingest|intake|import|receive)/.test(s)) return "ingest";
    if (/^embedding/.test(s)) return "embedding";
    if (/^vector/.test(s)) return "vector";
    if (/^cache/.test(s)) return "cache";
    if (/^stream/.test(s)) return "stream";
    if (/^rag/.test(s)) return "rag";
    if (/^prompt/.test(s)) return "prompt";
    if (/^(terminal|code)/.test(s)) return "terminal";
    if (/^(lock|secret|key)/.test(s)) return "lock";
    if (/^identity/.test(s)) return "identity";
    if (/^(user|customer|team)/.test(s)) return "user";
    if (/^(audit|clipboard|manual-step|evaluation)/.test(s)) return "audit";
    if (/^(file|document|policy)/.test(s)) return "file";
    if (/^folder/.test(s)) return "folder";
    if (/^notification/.test(s)) return "notification";
    if (/^(analytics|dashboard)/.test(s)) return "analytics";
    if (/^(globe|world|cdn)/.test(s)) return "globe";
    if (/^(success|approve)/.test(s)) return "success";
    if (/^failure/.test(s)) return "failure";
    if (/^retry/.test(s)) return "retry";
    if (/^(trigger|event|bolt)/.test(s)) return "trigger";
    if (/^scope/.test(s)) return "scope";
    if (/^firewall/.test(s)) return "firewall";
    if (/^server/.test(s)) return "server";
    if (/^(cluster|kubernetes)/.test(s)) return "cluster";
    if (/^container/.test(s)) return "container";
    if (/^queue/.test(s)) return "queue";
    if (/^(brain|think|model|reason)/.test(s)) return "brain";
    if (/^agent/.test(s)) return "agent";
    if (/^(gear|act|tool|settings|etl|load-balancer)/.test(s)) return "gear";
    if (/^(eye|observe|monitor)/.test(s)) return "eye";
    if (/^(db|database|memory|working-memory|warehouse|lake|storage)/.test(s)) return "db";
    if (/^(search|scan)/.test(s)) return "search";
    if (/^(shield|validate|guard|check|admin|compliance)/.test(s)) return "shield";
    if (/^(clock|budget|schedule|pending|time)/.test(s)) return "clock";
    if (/^(message|chat)/.test(s)) return "message";
    if (/^api/.test(s)) return "api";
    if (/^(package|output|deliver|cube|box)/.test(s)) return "package";
    if (/^(cloud|deploy)/.test(s)) return "cloud";
    return "module";
  };

  const drawIllustration = (g, op) => {
    const semantic = String(op.semantic || op.name || "file").toLowerCase();
    const key = illBuilders[illKeyFor(semantic)] ? illKeyFor(semantic) : "module";
    const lightMode = doc.finish.mode === "light";
    const C = {
      ink: op.glyph, inkSoft: rgba(op.glyph, 0.5), ghost: rgba(op.glyph, lightMode ? 0.22 : 0.3),
      acc: op.accent, accSoft: rgba(op.accent, 0.2), accMid: rgba(op.accent, 0.55),
      danger: (doc.theme && doc.theme.pink) || "#ff6fa9",
      glowK: lightMode ? 0.55 : 1,
    };
    const built = illBuilders[key](C);
    const hero = op.iconStyle === "hero" || op.iconSize === "hero";
    const s = (op.iconSize === "compact" ? 0.82 : hero ? 1.16 : 1.0) * op.tile / 48;
    const wrap = el("g", { "data-icon-illustration": semantic });
    wrap.setAttribute("transform",
      `translate(${(op.x + op.tile / 2 - 24 * s).toFixed(2)} ${(op.y + op.tile / 2 - 24 * s).toFixed(2)}) scale(${s.toFixed(4)})`);
    const tilt = grp({ transform: `rotate(${ILL_TILT[key] || 0} 24 24)` });
    tilt.appendChild(built.node);
    wrap.appendChild(tilt);
    g.appendChild(wrap);
    const serial = window.__illInstances.length;
    window.__illInstances.push({
      update: built.update,
      offset: (serial * 0.618) % 1,
      frozen: op.iconMotion === "none",
    });
    return wrap;
  };

  const drawIcon = (op) => {
    const g = el("g", { "data-op": "icon", "data-icon": op.name });
    g.dataset.cx = op.x + op.tile / 2;
    g.dataset.cy = op.y + op.tile / 2;
    const illustrated = !op.custom && (op.iconStyle === "illustrated" || op.iconStyle === "hero");
    // The v2 duotone illustrations are plate-free silhouettes; only outline
    // and custom icons keep the rough tile chrome behind the glyph.
    if (!op.plain && !illustrated) {
      g.appendChild(rc.path(roundedRectPath(op.x + 1, op.y + 1, op.tile - 2, op.tile - 2, op.radius), roughOpts(
        rgba(op.accent, 0.59), rgba(op.fill, 0.67), 1.25, { roughness: 0.8 }
      )));
    }
    if (illustrated) drawIllustration(g, op);
    const markup = illustrated ? null : icons[op.name];
    if (markup) {
      const holder = document.createElement("div");
      holder.innerHTML = markup;
      const src = holder.querySelector("svg");
      const inner = el("g", {});
      const glyphBox = op.tile - 2 * op.pad;
      const vb = (src.getAttribute("viewBox") || "0 0 24 24").split(/\s+/).map(Number);
      const scale = glyphBox / vb[2];
      inner.setAttribute("transform", `translate(${op.x + op.pad} ${op.y + op.pad}) scale(${scale.toFixed(4)})`);
      for (const child of [...src.children]) inner.appendChild(document.importNode(child, true));
      if (!op.custom) {
        // Bundled Tabler line icons get restroked; custom logos keep their colors.
        inner.setAttribute("data-icon-glyph", "1");
        inner.dataset.accent = op.accent;
        inner.querySelectorAll("path,line,polyline,polygon,circle,ellipse,rect").forEach(n => {
          n.setAttribute("fill", "none");
          n.setAttribute("stroke", op.glyph);
          n.setAttribute("stroke-width", 2);
          n.setAttribute("stroke-linecap", "round");
          n.setAttribute("stroke-linejoin", "round");
          n.setAttribute("opacity", 0.92);
        });
      }
      g.appendChild(inner);
    }
    content.appendChild(g);
  };

  const drawSignature = (op) => {
    const g = el("g", { "data-op": "signature", id: "signature" });
    const k = op.stretch || 1;
    for (const [dx, dy, color, alpha] of op.layers) {
      const t = el("text", {
        x: op.x + dx, y: op.y + dy,
        "font-family": "Excalifont, NotoSansSC, sans-serif",
        "font-size": 24, "font-weight": 700,
        fill: rgba(color, alpha / 255),
        "dominant-baseline": "text-before-edge",
      });
      t.textContent = op.text;
      g.appendChild(t);
    }
    g.appendChild(el("polyline", {
      points: `${op.x + 6 * k},${op.y + 56} ${op.x + 28 * k},${op.y + 61} ${op.x + 62 * k},${op.y + 58} ${op.x + 86 * k},${op.y + 63}`,
      fill: "none", stroke: rgba(op.underline, 170 / 255), "stroke-width": 3, "stroke-linecap": "round",
    }));
    g.appendChild(el("line", {
      x1: op.x + 8 * k, y1: op.y + 54, x2: op.x + 84 * k, y2: op.y + 60,
      stroke: rgba(op.underline2, 125 / 255), "stroke-width": 1,
    }));
    content.appendChild(g);
  };

  for (const op of doc.ops) {
    if (op.op === "rect") {
      const node = rc.path(roundedRectPath(op.x, op.y, op.w, op.h, op.radius), roughOpts(
        op.stroke, op.fill, op.width, op.style !== "solid" ? { strokeLineDash: dashFor(op.style) } : {}
      ));
      node.setAttribute("data-op", "rect");
      content.appendChild(node);
    } else if (op.op === "ellipse") {
      content.appendChild(rc.ellipse(op.x + op.w / 2, op.y + op.h / 2, op.w, op.h, roughOpts(op.stroke, op.fill, op.width)));
    } else if (op.op === "diamond") {
      const pts = [[op.x + op.w / 2, op.y], [op.x + op.w, op.y + op.h / 2], [op.x + op.w / 2, op.y + op.h], [op.x, op.y + op.h / 2]];
      content.appendChild(rc.polygon(pts, roughOpts(op.stroke, op.fill, op.width)));
    } else if (op.op === "line") {
      const g = el("g", { "data-op": "line" });
      const opts = roughOpts(op.stroke, null, op.width);
      const dash = dashFor(op.style);
      if (dash) opts.strokeLineDash = dash;
      g.appendChild(rc.linearPath(op.points, opts));
      if (op.arrow && op.points.length >= 2) arrowHead(g, op.points, op.stroke, op.width);
      content.appendChild(g);
    } else if (op.op === "text") {
      drawText(op);
    } else if (op.op === "icon") {
      drawIcon(op);
    } else if (op.op === "image") {
      const href = (window.__images || {})[op.name];
      if (href) {
        const img = el("image", { href, x: op.x, y: op.y, width: op.w, height: op.h,
                                  preserveAspectRatio: "xMidYMid meet", "data-op": "image" });
        content.appendChild(img);
      }
    } else if (op.op === "signature") {
      drawSignature(op);
    }
  }

  // Pose every illustrated icon now that its DOM is attached (getTotalLength
  // needs a live node). The golden-ratio stagger gives static PNG/SVG exports
  // varied, characterful poses instead of one synchronized frame.
  (window.__illInstances || []).forEach((it) => it.update(it.frozen ? 0 : it.offset));

  const finish = el("g", { id: "finish" });
  for (const spec of doc.finish.glow_rects) {
    const [x0, y0, x1, y1] = spec.box;
    finish.appendChild(el("rect", {
      x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 18,
      fill: "none", stroke: rgba(spec.color, 70 / 255), "stroke-width": spec.width,
      filter: "url(#glow)",
    }));
  }
  if (doc.finish.mode !== "light") {
    finish.appendChild(el("rect", { x: 0, y: 0, width: W, height: H, filter: "url(#grain)", opacity: 0.9 }));
    finish.appendChild(el("rect", { x: 0, y: 0, width: W, height: H, fill: "url(#vignette)" }));
  }
  svg.appendChild(finish);
  return content.childNodes.length;
})()
"""

_SERIALIZE_JS = r"""
() => {
  const svg = document.getElementById("stage").cloneNode(true);
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = document.getElementById("fonts").textContent;
  svg.insertBefore(style, svg.firstChild);
  return new XMLSerializer().serializeToString(svg);
}
"""


# ---------------------------------------------------------------------------
# Interactive HTML (Phase 4): click-to-highlight adjacency explorer
# ---------------------------------------------------------------------------

_INTERACTIVE_JS = r"""
(() => {
  const G = window.ARCHSCRIBE_GRAPH;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.querySelector("#diagram svg");
  const theme = G.theme;
  const el = (tag, attrs = {}) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const color = (key) => theme[key] || key || "#ffffff";

  // Adjacency (undirected view) ------------------------------------------------
  const nodesById = {};
  G.nodes.forEach((n) => { nodesById[n.id] = n; });
  const adj = {};
  G.nodes.forEach((n) => { adj[n.id] = new Set(); });
  G.edges.forEach((e) => { adj[e.from].add(e.to); adj[e.to].add(e.from); });
  const edgesOf = (id) => G.edges.filter((e) => e.from === id || e.to === id);

  // Overlay layers: dim below highlights, hotspots stay on top ----------------
  const hotspotLayer = svg.querySelector("#hotspots");
  const dim = el("rect", { x: 0, y: 0, width: G.canvas.width, height: G.canvas.height,
                           fill: G.bg, opacity: 0, "pointer-events": "none" });
  const hi = el("g", { id: "highlights", "pointer-events": "none" });
  svg.insertBefore(dim, hotspotLayer);
  svg.insertBefore(hi, hotspotLayer);

  const tooltip = document.getElementById("tooltip");
  const caption = document.getElementById("caption");
  const traceToggle = document.getElementById("trace");
  const search = document.getElementById("search");

  const pathD = (pts) => pts.map((p, i) => `${i ? "L" : "M"} ${p[0]} ${p[1]}`).join(" ");
  let selected = null;

  const clear = () => {
    selected = null;
    dim.setAttribute("opacity", 0);
    hi.replaceChildren();
    caption.textContent = G.hint;
    document.querySelectorAll(".hotspot.active").forEach((h) => h.classList.remove("active"));
  };

  const outline = (node, strokeColor, width, cls) => {
    const r = el("rect", {
      x: node.x - 4, y: node.y - 4, width: node.w + 8, height: node.h + 8,
      rx: 12, fill: "none", stroke: strokeColor, "stroke-width": width, class: cls || "",
    });
    hi.appendChild(r);
    return r;
  };

  const litEdge = (edge, delay) => {
    const c = color(edge.color === "white" || edge.color === "muted" ? "cyan" : edge.color);
    const base = el("path", { d: pathD(edge.points), fill: "none", stroke: c,
                              "stroke-width": 4.5, "stroke-linecap": "round", opacity: 0.35 });
    const dash = el("path", { d: pathD(edge.points), fill: "none", stroke: c,
                              "stroke-width": 2.5, "stroke-linecap": "round", class: "flowdash" });
    if (delay) dash.style.animationDelay = `${delay}s`;
    hi.appendChild(base); hi.appendChild(dash);
  };

  const bfs = (start) => {
    const depth = { [start]: 0 };
    const queue = [start];
    while (queue.length) {
      const cur = queue.shift();
      for (const nxt of adj[cur]) if (!(nxt in depth)) { depth[nxt] = depth[cur] + 1; queue.push(nxt); }
    }
    return depth;
  };

  const select = (id) => {
    selected = id;
    dim.setAttribute("opacity", 0.62);
    hi.replaceChildren();
    document.querySelectorAll(".hotspot.active").forEach((h) => h.classList.remove("active"));
    const hs = document.querySelector(`.hotspot[data-node="${CSS.escape(id)}"]`);
    if (hs) hs.classList.add("active");

    const node = nodesById[id];
    if (traceToggle.checked) {
      const depth = bfs(id);
      const maxDepth = Math.max(...Object.values(depth));
      G.edges.forEach((e) => {
        if (e.from in depth && e.to in depth) litEdge(e, 0.12 * Math.min(depth[e.from], depth[e.to]));
      });
      Object.entries(depth).forEach(([nid, d]) => {
        const n = nodesById[nid];
        outline(n, d === 0 ? "#ffffff" : color("cyan"), d === 0 ? 3 : 1.6);
      });
      caption.textContent = `${node.label || node.id} — 整条链路:${Object.keys(depth).length} 个节点,最长距离 ${maxDepth}`;
    } else {
      edgesOf(id).forEach((e) => litEdge(e, 0));
      const neigh = [...adj[id]];
      neigh.forEach((nid) => outline(nodesById[nid], color("cyan"), 1.8));
      outline(node, "#ffffff", 3);
      const names = neigh.map((nid) => nodesById[nid].label || nid).filter(Boolean).slice(0, 6);
      caption.textContent = `${node.label || node.id} — 相邻 ${neigh.length} 个节点${names.length ? ":" + names.join("、") : ""}`;
    }
  };

  // Hotspot wiring ---------------------------------------------------------------
  document.querySelectorAll(".hotspot").forEach((hs) => {
    const id = hs.dataset.node;
    const node = nodesById[id];
    const activate = () => (selected === id ? clear() : select(id));
    hs.addEventListener("click", (ev) => { ev.stopPropagation(); activate(); });
    hs.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); activate(); }
    });
    hs.addEventListener("mouseenter", () => {
      if (!node.label) return;
      tooltip.textContent = node.label;
      tooltip.style.opacity = 1;
    });
    hs.addEventListener("mousemove", (ev) => {
      tooltip.style.left = `${ev.clientX + 14}px`;
      tooltip.style.top = `${ev.clientY + 14}px`;
    });
    hs.addEventListener("mouseleave", () => { tooltip.style.opacity = 0; });
  });
  svg.addEventListener("click", () => clear());
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") clear(); });
  traceToggle.addEventListener("change", () => { if (selected) select(selected); });
  document.getElementById("reset").addEventListener("click", clear);
  search.addEventListener("input", () => {
    const q = search.value.trim().toLocaleLowerCase();
    document.querySelectorAll(".hotspot").forEach((hs) => {
      const node = nodesById[hs.dataset.node];
      const match = !q || `${node.label || ""} ${node.id}`.toLocaleLowerCase().includes(q);
      hs.style.stroke = q && match ? color("cyan") : "transparent";
      hs.style.strokeWidth = q && match ? "3" : "0";
    });
    const matches = q ? G.nodes.filter((n) => `${n.label || ""} ${n.id}`.toLocaleLowerCase().includes(q)) : [];
    caption.textContent = q ? `搜索“${search.value}”: ${matches.length} 个节点` : G.hint;
  });
  caption.textContent = G.hint;
  window.__ready = true;
})();
"""


def _build_interactive_html(doc, svg_markup: str, basename: str) -> str:
    graph = doc.get("graph") or {"canvas": doc["canvas"], "nodes": [], "edges": []}
    hint = "点击模块高亮它的连接 · 勾选「整条链路」看全链传播 · Esc 或点空白处重置"

    hotspots = ['<g id="hotspots">']
    for node in graph["nodes"]:
        label = str(node.get("label", "")).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        hotspots.append(
            f'<rect class="hotspot" data-node="{node["id"]}" x="{node["x"]}" y="{node["y"]}" '
            f'width="{node["w"]}" height="{node["h"]}" rx="10" tabindex="0" role="button" '
            f'aria-label="{label or node["id"]}"/>'
        )
    hotspots.append("</g>")
    head, sep, tail = svg_markup.rpartition("</svg>")
    svg_with_hotspots = head + "".join(hotspots) + sep + tail

    payload = {
        "canvas": graph["canvas"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "theme": doc.get("theme", {}),
        "bg": doc.get("bg", "#000000"),
        "hint": hint,
    }
    fg = "#3c3530" if doc.get("finish", {}).get("mode") == "light" else "#f4f0ee"
    bar_bg = "rgba(255,255,255,0.06)" if doc.get("finish", {}).get("mode") != "light" else "rgba(0,0,0,0.05)"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{basename} · Archscribe interactive</title>
<style>
  html, body {{ margin: 0; padding: 0; background: {doc.get('bg', '#000')}; color: {fg};
                font-family: "NotoSansSC", system-ui, sans-serif; }}
  .toolbar {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
              padding: 10px 18px; background: {bar_bg}; font-size: 14px; }}
  .toolbar label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; }}
  .toolbar button {{ background: transparent; color: inherit; border: 1px solid currentColor;
                     border-radius: 8px; padding: 3px 12px; font-size: 13px; cursor: pointer; opacity: .8; }}
  .toolbar button:hover {{ opacity: 1; }}
  .toolbar input[type="search"] {{ min-width: 180px; background: transparent; color: inherit;
      border: 1px solid currentColor; border-radius: 8px; padding: 4px 9px; opacity: .8; }}
  #caption {{ opacity: .75; font-size: 13px; }}
  #diagram {{ display: flex; justify-content: center; padding: 12px; }}
  #diagram svg {{ max-width: 100%; height: auto; }}
  .hotspot {{ fill: transparent; stroke: transparent; cursor: pointer; outline: none; }}
  .hotspot:hover, .hotspot:focus-visible {{ stroke: rgba(255,255,255,.55); stroke-width: 1.6; stroke-dasharray: 5 4; }}
  .hotspot.active {{ stroke: transparent; }}
  .flowdash {{ stroke-dasharray: 10 14; animation: flowmove .8s linear infinite; }}
  @keyframes flowmove {{ to {{ stroke-dashoffset: -24; }} }}
  #tooltip {{ position: fixed; pointer-events: none; opacity: 0; transition: opacity .12s;
              background: rgba(10,10,10,.92); color: #f4f0ee; border: 1px solid rgba(255,255,255,.25);
              padding: 4px 10px; border-radius: 8px; font-size: 13px; z-index: 10; }}
</style></head>
<body>
<div class="toolbar">
  <strong>Archscribe</strong>
  <label><input type="checkbox" id="trace"> 整条链路</label>
  <input id="search" type="search" placeholder="搜索节点" aria-label="搜索节点">
  <button id="reset" type="button">重置</button>
  <span id="caption"></span>
</div>
<div id="diagram">{svg_with_hotspots}</div>
<div id="tooltip"></div>
<script>window.ARCHSCRIBE_GRAPH = {json.dumps(payload, ensure_ascii=False)};</script>
<script>{_INTERACTIVE_JS}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Animation engine: window.__setup(preset) + window.setProgress(t)
# ---------------------------------------------------------------------------

_ANIMATE_JS = r"""
(preset) => {
  const doc = window.__doc;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("stage");
  const content = document.getElementById("content");
  const rgba = window.__rgba;
  const roundedRectPath = window.__roundedRectPath;
  const W = doc.canvas.width, H = doc.canvas.height;
  const el = (tag, attrs = {}) => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  };
  const easeInOut = (t) => 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, t)));
  const pathD = (pts) => pts.map((p, i) => `${i ? "L" : "M"} ${p[0]} ${p[1]}`).join(" ");
  const cyc = (t) => ((t % 1) + 1) % 1;
  const cycDist = (a, b) => { const d = Math.abs(cyc(a) - cyc(b)); return Math.min(d, 1 - d); };

  const overlay = el("g", { id: "overlay" });
  // Insert below the finish layer so grain/vignette still sit on top.
  svg.insertBefore(overlay, document.getElementById("finish"));

  const measure = el("path", { d: "M 0 0", fill: "none" });
  overlay.appendChild(measure);
  const lengthOf = (pts) => { measure.setAttribute("d", pathD(pts)); return measure.getTotalLength(); };

  // --- shared: beams along flow paths -------------------------------------
  // Light finish (paper style) swaps the glowing energy beam for the
  // reference look: a small solid colored dot with a short fading tail.
  const lightFlow = doc.finish.mode === "light";
  const beams = doc.animation.flow_paths.map((fp) => {
    const L = lengthOf(fp.points);
    const seg = Math.max(26, L * (lightFlow ? 0.10 : 0.18));
    const trail = el("path", {
      d: pathD(fp.points), fill: "none", stroke: fp.color, "stroke-width": lightFlow ? 2 : 3,
      "stroke-linecap": "round", filter: "url(#softglow)", opacity: 0,
    });
    const glow = el("path", {
      d: pathD(fp.points), fill: "none", stroke: fp.color, "stroke-width": lightFlow ? 3.5 : 7,
      "stroke-linecap": "round", opacity: 0,
      "stroke-dasharray": `${seg} ${L + seg}`,
      ...(lightFlow ? {} : { filter: "url(#softglow)" }),
    });
    const core = el("path", {
      d: pathD(fp.points), fill: "none", stroke: lightFlow ? fp.color : "#ffffff", "stroke-width": lightFlow ? 1.6 : 2.4,
      "stroke-linecap": "round", opacity: 0,
      "stroke-dasharray": `${seg * 0.72} ${L + seg}`,
    });
    overlay.appendChild(trail); overlay.appendChild(glow); overlay.appendChild(core);
    const end = fp.points[fp.points.length - 1];
    const orb = lightFlow
      ? el("circle", { cx: 0, cy: 0, r: 3.4, fill: fp.color, stroke: "#ffffff", "stroke-width": 1.1, opacity: 0 })
      : el("circle", { cx: 0, cy: 0, r: 4, fill: "#ffffff", filter: "url(#softglow)", opacity: 0 });
    overlay.appendChild(orb);
    const ripple = el("circle", { cx: end[0], cy: end[1], r: 0, fill: "none", stroke: fp.color, "stroke-width": lightFlow ? 1.8 : 2.5, opacity: 0 });
    overlay.appendChild(ripple);
    return { fp, L, seg, trail, glow, core, orb, ripple, end };
  });
  const pointAt = (b, pos) => {
    measure.setAttribute("d", pathD(b.fp.points));
    return measure.getPointAtLength(Math.min(1, Math.max(0, pos)) * b.L);
  };
  const setBeam = (b, pos, alpha, wide = 1) => {
    const off = (b.L + b.seg) * (1 - pos) - b.seg;
    b.glow.setAttribute("stroke-dashoffset", off);
    b.core.setAttribute("stroke-dashoffset", off + b.seg * 0.14);
    b.glow.setAttribute("stroke-width", (lightFlow ? 3.5 : 7) * wide);
    b.core.setAttribute("stroke-width", (lightFlow ? 1.6 : 2.4) * wide);
    b.glow.setAttribute("opacity", (lightFlow ? 0.35 : 0.85) * alpha);
    b.core.setAttribute("opacity", (lightFlow ? 0.55 : 0.95) * alpha);
    if (alpha > 0 && pos > 0.01 && pos < 0.995) {
      const pt = pointAt(b, pos);
      b.orb.setAttribute("cx", pt.x); b.orb.setAttribute("cy", pt.y);
      b.orb.setAttribute("r", (lightFlow ? 3.4 : 3.2) * wide);
      b.orb.setAttribute("opacity", (lightFlow ? 1.0 : 0.9) * alpha);
    } else {
      b.orb.setAttribute("opacity", 0);
    }
  };
  const setTrail = (b, alpha) => b.trail.setAttribute("opacity", alpha);
  const setRipple = (b, k, alpha) => {
    if (k <= 0 || k >= 1) { b.ripple.setAttribute("opacity", 0); return; }
    b.ripple.setAttribute("r", 5 + 19 * k);
    b.ripple.setAttribute("opacity", (1 - k) * 0.6 * alpha);
  };

  // --- shared: module breathing rects --------------------------------------
  const pulses = doc.animation.pulse_targets.map((pt) => {
    const [x0, y0, x1, y1] = pt.box;
    const r = el("rect", {
      x: x0 - 3, y: y0 - 3, width: x1 - x0 + 6, height: y1 - y0 + 6, rx: 13,
      fill: "none", stroke: pt.color, "stroke-width": 2.5, filter: "url(#softglow)", opacity: 0,
    });
    overlay.appendChild(r);
    return { r, color: pt.color };
  });

  // --- shared: icon stroke sweep -------------------------------------------
  const sweeps = [];
  content.querySelectorAll("g[data-icon-glyph]").forEach((glyphG) => {
    const accent = glyphG.dataset.accent || "#ffffff";
    const clone = glyphG.cloneNode(true);
    clone.removeAttribute("data-icon-glyph");
    const shapes = [];
    clone.querySelectorAll("path,line,polyline,polygon,circle,ellipse,rect").forEach((n) => {
      n.setAttribute("stroke", accent);
      n.setAttribute("stroke-width", 2.4);
      n.setAttribute("opacity", 1);
      let L = 0; try { L = n.getTotalLength(); } catch (e) { L = 0; }
      if (L > 1) shapes.push({ n, L }); else n.setAttribute("opacity", 0);
    });
    overlay.appendChild(clone);
    sweeps.push({ shapes });
  });
  const setSweeps = (t, alpha) => {
    sweeps.forEach((s) => {
      s.shapes.forEach((sh, i) => {
        const dash = Math.max(7, sh.L * 0.24);
        const phase = cyc(t + i * 0.045);
        sh.n.setAttribute("stroke-dasharray", `${dash} ${sh.L * 2}`);
        sh.n.setAttribute("stroke-dashoffset", (1 - phase) * (sh.L + dash) - dash);
        sh.n.setAttribute("opacity", alpha);
      });
    });
  };

  // --- shared: icon micro pop (wave-ordered scale around each tile center) --
  const iconGs = [...content.querySelectorAll('g[data-op="icon"]')];
  const setIconPops = (t, strength) => {
    const n = Math.max(1, iconGs.length);
    iconGs.forEach((g, i) => {
      const d = cycDist(t, i / n);
      const k = Math.exp(-Math.pow(d * n * 1.15, 2));
      const s = 1 + strength * k;
      if (s <= 1.0005) { g.removeAttribute("transform"); return; }
      const cx = +g.dataset.cx, cy = +g.dataset.cy;
      g.setAttribute("transform",
        `translate(${(cx * (1 - s)).toFixed(3)} ${(cy * (1 - s)).toFixed(3)}) scale(${s.toFixed(4)})`);
    });
  };

  // --- semantic illustration job stories -----------------------------------
  // Each illustrated icon registered an update(p) closure at draw time.
  // Whole story cycles per GIF loop stay integral so the loop is seamless;
  // longer narrative timelines get proportionally more cycles.
  const illLoopSeconds = (doc.canvas.frames || 41) / (doc.canvas.fps || 20);
  const illCycles = Math.max(1, Math.round(illLoopSeconds / 2.4));
  const setIllustrationMotion = (t) => {
    (window.__illInstances || []).forEach((it) => {
      it.update(it.frozen ? 0 : cyc(t * illCycles + it.offset));
    });
  };

  // --- ambient layer: breathing halo on the title capsule -------------------
  const ambient = { nodes: [] };
  {
    const capsule = doc.ops.find((op) => op.op === "rect" && op.fill === doc.theme.highlight);
    if (capsule) {
      const halo = el("rect", {
        x: capsule.x - 3, y: capsule.y - 3, width: capsule.w + 6, height: capsule.h + 6, rx: 18,
        fill: "none", stroke: doc.theme.green, "stroke-width": 2, filter: "url(#softglow)", opacity: 0,
      });
      overlay.appendChild(halo); ambient.nodes.push(halo);
    }
  }
  const setAmbient = (t) => {
    if (ambient.nodes.length) {
      ambient.nodes[0].setAttribute("opacity", 0.2 + 0.16 * Math.sin(2 * Math.PI * t));
    }
    const sig = document.getElementById("signature");
    if (sig) {
      const jx = 0.7 * Math.sin(2 * Math.PI * (t * 2 + 0.2));
      const jy = 0.5 * Math.sin(2 * Math.PI * (t * 3 + 0.6));
      sig.setAttribute("transform", `translate(${jx.toFixed(2)} ${jy.toFixed(2)})`);
    }
  };

  // --- preset: draw ----------------------------------------------------------
  const drawables = [];
  if (preset === "draw") {
    const kids = [...content.children];
    const N = kids.length;
    kids.forEach((node, i) => {
      const t0 = 0.02 + 0.64 * (i / Math.max(1, N - 1));
      const dur = Math.min(0.1, 1.6 * 0.64 / Math.max(1, N - 1) + 0.045);
      const paths = [];
      node.querySelectorAll("path").forEach((p) => {
        // Illustrated icons animate their own dash offsets; the whiteboard
        // reveal fades them in as a unit instead of redrawing their strokes.
        if (p.closest("[data-icon-illustration]")) return;
        let L = 0; try { L = p.getTotalLength(); } catch (e) { L = 0; }
        if (L > 1) paths.push({ p, L, dash: p.getAttribute("stroke-dasharray") });
      });
      drawables.push({ node, t0, t1: t0 + dur, paths, isPath: node.tagName === "path" || node.dataset.op === "line" });
    });
  }
  const fadeCover = el("rect", { x: 0, y: 0, width: W, height: H, fill: doc.bg, opacity: 0 });
  overlay.appendChild(fadeCover);

  // --- preset: relay ---------------------------------------------------------
  const relay = { order: [], dim: null };
  if (preset === "relay") {
    relay.order = beams.slice().sort((a, b) => a.fp.offset - b.fp.offset);
    relay.dim = el("rect", { x: 0, y: 0, width: W, height: H, fill: doc.bg, opacity: 0.42 });
    overlay.insertBefore(relay.dim, overlay.firstChild);
  }
  const nearestPulse = (pt) => {
    let best = null, bd = 1e9;
    pulses.forEach((p) => {
      const box = p.r; const cx = +box.getAttribute("x") + +box.getAttribute("width") / 2;
      const cy = +box.getAttribute("y") + +box.getAttribute("height") / 2;
      const d = Math.hypot(cx - pt[0], cy - pt[1]);
      if (d < bd) { bd = d; best = p; }
    });
    return best;
  };

  // ---------------------------------------------------------------------------
  window.setProgress = (t) => {
    t = cyc(t);
    setAmbient(t);
    setIllustrationMotion(t);

    if (preset === "flow") {
      beams.forEach((b) => {
        const raw0 = cyc(t + b.fp.offset);
        const pos0 = easeInOut(raw0);
        setBeam(b, pos0, 1);
        setTrail(b, 0);
        setRipple(b, (pos0 - 0.88) / 0.12, 1);
      });
      const n = pulses.length;
      pulses.forEach((p, i) => {
        const d = cycDist(t, i / n);
        const intensity = Math.exp(-Math.pow(d * n * 1.35, 2));
        p.r.setAttribute("opacity", 0.5 * intensity);
      });
      setSweeps(t, 0.85);
      setIconPops(t, 0.08);
      fadeCover.setAttribute("opacity", 0);
    } else if (preset === "draw") {
      drawables.forEach((d) => {
        if (t < d.t0) {
          d.node.setAttribute("opacity", 0);
        } else if (t < d.t1) {
          const k = easeInOut((t - d.t0) / (d.t1 - d.t0));
          d.node.setAttribute("opacity", d.paths.length ? 1 : k);
          d.paths.forEach((ph) => {
            ph.p.setAttribute("stroke-dasharray", `${ph.L * k} ${ph.L}`);
            ph.p.setAttribute("stroke-dashoffset", 0);
            if (ph.p.getAttribute("fill") && ph.p.getAttribute("fill") !== "none") {
              ph.p.setAttribute("fill-opacity", k);
            }
          });
        } else {
          d.node.setAttribute("opacity", 1);
          d.paths.forEach((ph) => {
            if (ph.dash) ph.p.setAttribute("stroke-dasharray", ph.dash);
            else ph.p.removeAttribute("stroke-dasharray");
            ph.p.removeAttribute("stroke-dashoffset");
            ph.p.removeAttribute("fill-opacity");
          });
        }
      });
      beams.forEach((b) => { setBeam(b, 0, 0); setTrail(b, 0); setRipple(b, 0, 0); });
      pulses.forEach((p) => p.r.setAttribute("opacity", 0));
      // Icons pop with a sweep once everything is on canvas.
      setSweeps(t, t > 0.7 ? 0.85 : 0);
      const fade = t > 0.96 ? (t - 0.96) / 0.04 : 0;
      fadeCover.setAttribute("opacity", fade);
    } else if (preset === "relay") {
      const n = relay.order.length;
      const slot = Math.min(n - 1, Math.floor(t * n));
      const local = easeInOut(t * n - slot);
      relay.order.forEach((b, i) => {
        if (i === slot) {
          setBeam(b, local, 1, 1.45);
          setTrail(b, 0.18 * local);
          setRipple(b, (local - 0.8) / 0.2, 1);
        } else if (i < slot) {
          // Story so far stays faintly lit.
          setBeam(b, 0, 0);
          setTrail(b, 0.22);
          setRipple(b, 0, 0);
        } else {
          setBeam(b, 0, 0);
          setTrail(b, 0);
          setRipple(b, 0, 0);
        }
      });
      pulses.forEach((p) => p.r.setAttribute("opacity", 0));
      const active = relay.order[slot];
      const target = nearestPulse(active.end);
      if (target) target.r.setAttribute("opacity", 0.3 + 0.4 * local);
      setSweeps(t, 0.45);
      fadeCover.setAttribute("opacity", 0);
    }
    return 1;
  };
  return beams.length;
}
"""


# ---------------------------------------------------------------------------
# Python driver
# ---------------------------------------------------------------------------


def _save_gif(pil_frames, gif_path, fps) -> None:
    """Quantize all frames against one shared palette (no dithering).

    A stable global palette plus flat color regions compresses drastically
    better than Pillow's default per-frame adaptive palette with dithering,
    and it avoids palette flicker between frames.
    """
    palette_source = pil_frames[len(pil_frames) // 2].quantize(
        colors=255, method=Image.Quantize.MEDIANCUT
    )
    quantized = [
        frame.quantize(palette=palette_source, dither=Image.Dither.NONE)
        for frame in pil_frames
    ]
    quantized[0].save(
        gif_path, save_all=True, append_images=quantized[1:],
        duration=int(1000 / fps), loop=0, optimize=True,
    )


def _encode_mp4(frame_paths, fps, mp4_path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    pattern = str(Path(frame_paths[0]).parent / "frame%04d.png")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", pattern,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
        str(mp4_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"warning: ffmpeg failed: {proc.stderr.strip()[:400]}", file=sys.stderr)
        return False
    return True


def render_all(doc, outdir: Path, basename: str, animation: str = "flow",
               formats=("png", "gif", "mp4", "svg", "excalidraw"), scale: int = 2) -> dict:
    """Render every browser-produced artifact in one Chromium session."""
    from playwright.sync_api import sync_playwright

    outdir.mkdir(parents=True, exist_ok=True)
    icons = _collect_icon_markups(doc)
    images = _collect_image_hrefs(doc)
    width = doc["canvas"]["width"]
    height = doc["canvas"]["height"]
    fps = doc["canvas"].get("fps", 20)
    frames = max(doc["canvas"].get("frames", 41), PRESET_MIN_FRAMES.get(animation, 0))
    runtime_animation = {"trace": "relay", "chapter": "draw", "failure-recovery": "relay"}.get(animation, animation)

    want = set(formats)
    result = {}

    html = build_page_html(doc)
    inject = (
        f"window.__doc = {json.dumps(doc, ensure_ascii=False)};"
        f"window.__icons = {json.dumps(icons, ensure_ascii=False)};"
        f"window.__images = {json.dumps(images, ensure_ascii=False)};"
    )

    def open_page(browser, dsf):
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=dsf,
        )
        page.set_content(html)
        page.evaluate("() => document.fonts.ready.then(() => 1)")
        page.evaluate(inject)
        page.evaluate(_RENDER_JS)
        page.wait_for_timeout(60)
        return page

    def grab(stage) -> Image.Image:
        img = Image.open(BytesIO(stage.screenshot())).convert("RGB")
        if img.size != (width, height):
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        return img

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_page(browser, scale)

        if want & {"svg", "html"}:
            svg_markup = page.evaluate(_SERIALIZE_JS)
            if "svg" in want:
                svg_path = outdir / f"{basename}.svg"
                svg_path.write_text(svg_markup, encoding="utf-8")
                result["svg"] = str(svg_path)
            if "html" in want:
                html_path = outdir / f"{basename}.html"
                html_path.write_text(_build_interactive_html(doc, svg_markup, basename), encoding="utf-8")
                result["html"] = str(html_path)

        if "png" in want:
            png_path = outdir / f"{basename}.png"
            grab(page.locator("#stage")).save(png_path, "PNG")
            result["png"] = str(png_path)

        if want & {"gif", "mp4"}:
            # Animation frames are captured at 1x (the GIF/MP4 target size);
            # SVG filters re-rasterize every frame, so this is ~4x faster
            # than screenshotting the 2x supersampled page.
            page.close()
            page = open_page(browser, 1)
            stage = page.locator("#stage")
            page.evaluate(_ANIMATE_JS, runtime_animation)
            pil_frames = []
            for i in range(frames):
                page.evaluate("(t) => window.setProgress(t)", i / frames)
                pil_frames.append(grab(stage))

            if "gif" in want:
                gif_path = outdir / f"{basename}.gif"
                _save_gif(pil_frames, gif_path, fps)
                result["gif"] = str(gif_path)

            if "mp4" in want:
                mp4_path = outdir / f"{basename}.mp4"
                with tempfile.TemporaryDirectory() as tmp:
                    frame_paths = []
                    for i, frame in enumerate(pil_frames):
                        fp = Path(tmp) / f"frame{i:04d}.png"
                        frame.save(fp, "PNG")
                        frame_paths.append(fp)
                    if _encode_mp4(frame_paths, fps, mp4_path):
                        result["mp4"] = str(mp4_path)
                    else:
                        result["mp4_skipped"] = "ffmpeg unavailable or failed"
            result["frames"] = frames

        browser.close()

    result["animation"] = animation
    return result


def render(doc, outdir: Path, basename: str, scale: int = 2) -> dict:
    """Static-only convenience wrapper (svg + png)."""
    return render_all(doc, outdir, basename, formats=("png", "svg"), scale=scale)
