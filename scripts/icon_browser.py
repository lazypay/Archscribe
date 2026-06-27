#!/usr/bin/env python3
"""Headless-Chromium icon engine for the Archscribe animated diagram renderer.

Renders the bundled Tabler outline SVGs through a real browser so the line art is
crisp, and animates each icon's stroke with a looping "energy sweep". Returns
per-icon frame sequences that the main renderer composites into the GIF.

This engine is optional. The main renderer falls back to the pure-Pillow icon
path when Playwright/Chromium are unavailable, so the skill stays portable.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TABLER_ICON_DIR = ROOT / "assets" / "icons" / "tabler"

_PAGE = """
<!doctype html><html><head><meta charset='utf-8'>
<style>
  html,body{margin:0;padding:0;background:transparent;}
  #host{width:__SIZE__px;height:__SIZE__px;display:flex;align-items:center;justify-content:center;}
  #host svg{width:__SIZE__px;height:__SIZE__px;overflow:visible;}
</style></head><body><div id='host'></div></body></html>
"""

_JS = """
window.__cfg = {size: __SIZE__, sw: __SW__};
window.prep = function(markup, base, accent){
  const cfg = window.__cfg;
  const host = document.getElementById('host');
  host.innerHTML = markup;
  const svg = host.querySelector('svg');
  svg.setAttribute('width', cfg.size);
  svg.setAttribute('height', cfg.size);
  const els = [...svg.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect')];
  const accents = [];
  els.forEach(el=>{
    el.style.fill='none';
    el.style.stroke=base;
    el.style.strokeWidth=cfg.sw;
    el.style.strokeLinecap='round';
    el.style.strokeLinejoin='round';
    el.style.opacity=0.9;
    let L=0; try{L=el.getTotalLength();}catch(e){L=0;}
    if(L>1){
      const a = el.cloneNode(false);
      a.style.fill='none';
      a.style.stroke=accent;
      a.style.strokeWidth=cfg.sw*1.18;
      a.style.strokeLinecap='round';
      a.style.strokeLinejoin='round';
      a.style.filter='drop-shadow(0 0 2px '+accent+')';
      el.parentNode.appendChild(a);
      accents.push({el:a, L:L});
    }
  });
  window.__accents = accents;
};
window.setProgress = function(t){
  (window.__accents||[]).forEach((o,i)=>{
    const L=o.L;
    const dash=Math.max(7, L*0.24);
    const phase=(t + i*0.045) % 1.0;
    o.el.style.strokeDasharray = dash+' '+(L*2);
    o.el.style.strokeDashoffset = ((1-phase)*(L+dash) - dash).toFixed(2);
  });
};
"""


def is_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


def _read_markup(icon_name: str) -> str | None:
    path = TABLER_ICON_DIR / f"{icon_name}.svg"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def render_glyph_frames(
    requests,
    glyph_px: int,
    frames: int,
    base_color: str = "#f4f0ee",
    stroke: float = 2.0,
    render_px: int = 180,
):
    """Render animated glyph frames for each unique (icon_name, accent_color).

    Returns dict keyed by (icon_name, accent_color) -> list[PIL.Image RGBA].
    Returns an empty dict if the browser engine cannot run.
    """
    requests = list(dict.fromkeys(requests))  # stable de-dupe
    markups = {}
    for icon_name, _accent in requests:
        markup = _read_markup(icon_name)
        if markup is not None:
            markups[icon_name] = markup
    if not markups:
        return {}

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    page_html = _PAGE.replace("__SIZE__", str(render_px))
    js = _JS.replace("__SIZE__", str(render_px)).replace("__SW__", str(stroke))

    result = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": render_px, "height": render_px},
                device_scale_factor=2,
            )
            page.set_content(page_html)
            page.evaluate(js)
            host = page.locator("#host")
            for icon_name, accent in requests:
                markup = markups.get(icon_name)
                if markup is None:
                    continue
                page.evaluate("([m,b,a])=>window.prep(m,b,a)", [markup, base_color, accent])
                seq = []
                for i in range(frames):
                    page.evaluate("(t)=>window.setProgress(t)", i / frames)
                    png = host.screenshot(omit_background=True)
                    glyph = (
                        Image.open(io.BytesIO(png))
                        .convert("RGBA")
                        .resize((glyph_px, glyph_px), Image.Resampling.LANCZOS)
                    )
                    seq.append(glyph)
                result[(icon_name, accent)] = seq
            browser.close()
    except Exception:
        return {}
    return result
