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

ANIMATION_PRESETS = ("flow", "draw", "relay")
# Minimum loop lengths (frames @ spec fps) for the narrative presets.
PRESET_MIN_FRAMES = {"flow": 0, "draw": 72, "relay": 88}

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

  const drawIcon = (op) => {
    const g = el("g", { "data-op": "icon", "data-icon": op.name });
    g.dataset.cx = op.x + op.tile / 2;
    g.dataset.cy = op.y + op.tile / 2;
    if (!op.plain) {
      g.appendChild(rc.path(roundedRectPath(op.x + 1, op.y + 1, op.tile - 2, op.tile - 2, op.radius), roughOpts(
        rgba(op.accent, 0.59), rgba(op.fill, 0.67), 1.25, { roughness: 0.8 }
      )));
    }
    const markup = icons[op.name];
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
  const beams = doc.animation.flow_paths.map((fp) => {
    const L = lengthOf(fp.points);
    const seg = Math.max(26, L * 0.18);
    const trail = el("path", {
      d: pathD(fp.points), fill: "none", stroke: fp.color, "stroke-width": 3,
      "stroke-linecap": "round", filter: "url(#softglow)", opacity: 0,
    });
    const glow = el("path", {
      d: pathD(fp.points), fill: "none", stroke: fp.color, "stroke-width": 7,
      "stroke-linecap": "round", filter: "url(#softglow)", opacity: 0,
      "stroke-dasharray": `${seg} ${L + seg}`,
    });
    const core = el("path", {
      d: pathD(fp.points), fill: "none", stroke: "#ffffff", "stroke-width": 2.4,
      "stroke-linecap": "round", opacity: 0,
      "stroke-dasharray": `${seg * 0.72} ${L + seg}`,
    });
    overlay.appendChild(trail); overlay.appendChild(glow); overlay.appendChild(core);
    const end = fp.points[fp.points.length - 1];
    const orb = el("circle", { cx: 0, cy: 0, r: 4, fill: "#ffffff", filter: "url(#softglow)", opacity: 0 });
    overlay.appendChild(orb);
    const ripple = el("circle", { cx: end[0], cy: end[1], r: 0, fill: "none", stroke: fp.color, "stroke-width": 2.5, opacity: 0 });
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
    b.glow.setAttribute("stroke-width", 7 * wide);
    b.core.setAttribute("stroke-width", 2.4 * wide);
    b.glow.setAttribute("opacity", 0.85 * alpha);
    b.core.setAttribute("opacity", 0.95 * alpha);
    if (alpha > 0 && pos > 0.01 && pos < 0.995) {
      const pt = pointAt(b, pos);
      b.orb.setAttribute("cx", pt.x); b.orb.setAttribute("cy", pt.y);
      b.orb.setAttribute("r", 3.2 * wide);
      b.orb.setAttribute("opacity", 0.9 * alpha);
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

  // --- ambient layer per style ---------------------------------------------
  const ambient = { mode: doc.style || "default", nodes: [] };
  if (ambient.mode === "terminal") {
    for (let i = 0; i < 2; i++) {
      const line = el("rect", { x: 0, y: 0, width: W, height: 2.5, fill: rgba(doc.theme.green, 0.06) });
      overlay.appendChild(line); ambient.nodes.push(line);
    }
  } else if (ambient.mode === "blueprint") {
    const ring = el("circle", { cx: W / 2, cy: H / 2, r: 0, fill: "none", stroke: rgba(doc.theme.core_stroke, 0.1), "stroke-width": 2 });
    overlay.appendChild(ring); ambient.nodes.push(ring);
  } else if (ambient.mode === "candy") {
    for (let i = 0; i < 6; i++) {
      const colors = [doc.theme.pink, doc.theme.cyan, doc.theme.amber, doc.theme.purple];
      const dot = el("circle", { cx: 60 + (W - 120) * ((i * 0.618) % 1), cy: 0, r: 4 + (i % 3) * 2, fill: rgba(colors[i % 4], 0.35) });
      overlay.appendChild(dot); ambient.nodes.push(dot);
    }
  } else {
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
    if (ambient.mode === "terminal") {
      ambient.nodes.forEach((line, i) => line.setAttribute("y", H * cyc(t * 0.5 + i * 0.5)));
    } else if (ambient.mode === "blueprint") {
      const k = cyc(t);
      ambient.nodes[0].setAttribute("r", k * Math.hypot(W, H) * 0.5);
      ambient.nodes[0].setAttribute("stroke-opacity", (1 - k) * 0.5);
    } else if (ambient.mode === "candy") {
      ambient.nodes.forEach((dot, i) => {
        const base = 90 + (H - 180) * ((i * 0.372 + 0.13) % 1);
        dot.setAttribute("cy", base + 7 * Math.sin(2 * Math.PI * (t + i / 6)));
      });
    } else if (ambient.nodes.length) {
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
            page.evaluate(_ANIMATE_JS, animation)
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
