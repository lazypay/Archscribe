#!/usr/bin/env python3
"""One-time asset prep: build the bundled fonts in assets/fonts/.

Not needed at render time. Run again only when the charset or source fonts
change. Requires: fonttools, brotli (pip install fonttools brotli).

Inputs (downloaded manually or by this script's caller):
- assets/fonts/Excalifont-Regular.woff2   (OFL-1.1, from excalidraw.com)
- <tmp>/NotoSansSC-var.ttf                (OFL-1.1, google/fonts variable font)

Outputs:
- assets/fonts/Excalifont-Regular.ttf     (Pillow engine)
- assets/fonts/NotoSansSC-Regular.ttf     (Pillow engine, CJK)
- assets/fonts/NotoSansSC-Bold.ttf        (Pillow engine, CJK bold)
- assets/fonts/*.woff2                    (future SVG/browser renderer)
- assets/fonts/notosanssc-coverage.json   (runtime missing-glyph fallback check)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"


def build_charset() -> set[int]:
    """Latin + punctuation + GB2312 full hanzi set (6763 chars)."""
    cps: set[int] = set()
    cps.update(range(0x0020, 0x007F))  # ASCII
    cps.update(range(0x00A0, 0x0100))  # Latin-1 supplement
    cps.update(range(0x2000, 0x2070))  # general punctuation
    cps.update(range(0x2190, 0x2200))  # arrows
    cps.update(range(0x3000, 0x3040))  # CJK symbols and punctuation
    cps.update(range(0xFF00, 0xFFF0))  # fullwidth forms
    for hi in range(0xB0, 0xF8):  # GB2312 hanzi zones (level 1 + 2)
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            cps.add(ord(ch))
    return cps


def subset_font(font: TTFont, unicodes: set[int]) -> TTFont:
    opts = Options()
    opts.name_IDs = ["*"]
    opts.recalc_bounds = True
    opts.drop_tables += ["FFTM"]
    sub = Subsetter(opts)
    sub.populate(unicodes=sorted(unicodes))
    sub.subset(font)
    return font


def save_both_flavors(font: TTFont, stem: str) -> None:
    ttf_path = FONT_DIR / f"{stem}.ttf"
    font.flavor = None
    font.save(ttf_path)
    woff2 = TTFont(ttf_path)
    woff2.flavor = "woff2"
    woff2.save(FONT_DIR / f"{stem}.woff2")
    print(f"  {stem}.ttf    {ttf_path.stat().st_size / 1024:.0f} KB")
    print(f"  {stem}.woff2  {(FONT_DIR / (stem + '.woff2')).stat().st_size / 1024:.0f} KB")


def coverage_ranges(unicodes: set[int]) -> list[list[int]]:
    """Compress a codepoint set into sorted [start, end] inclusive ranges."""
    ranges: list[list[int]] = []
    for cp in sorted(unicodes):
        if ranges and cp == ranges[-1][1] + 1:
            ranges[-1][1] = cp
        else:
            ranges.append([cp, cp])
    return ranges


def main() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    excalifont_woff2 = FONT_DIR / "Excalifont-Regular.woff2"
    if excalifont_woff2.is_file():
        print("Excalifont: woff2 -> ttf")
        font = TTFont(excalifont_woff2)
        font.flavor = None
        font.save(FONT_DIR / "Excalifont-Regular.ttf")
        print(f"  Excalifont-Regular.ttf  {(FONT_DIR / 'Excalifont-Regular.ttf').stat().st_size / 1024:.0f} KB")
    else:
        print("warning: Excalifont-Regular.woff2 missing, skipped", file=sys.stderr)

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("TEMP", "/tmp")) / "NotoSansSC-var.ttf"
    if not src.is_file():
        print(f"error: variable font not found: {src}", file=sys.stderr)
        sys.exit(1)

    charset = build_charset()
    print(f"charset: {len(charset)} codepoints")

    for weight, stem in [(400, "NotoSansSC-Regular"), (700, "NotoSansSC-Bold")]:
        print(f"NotoSansSC wght={weight} -> subset")
        font = TTFont(src)
        instantiateVariableFont(font, {"wght": weight}, inplace=True)
        subset_font(font, charset)
        save_both_flavors(font, stem)

    # Actual glyph coverage of the produced subset (some codepoints may be
    # absent from the source font); used at render time to detect missing
    # glyphs and fall back to a system font.
    produced = TTFont(FONT_DIR / "NotoSansSC-Regular.ttf")
    cmap = produced.getBestCmap()
    (FONT_DIR / "notosanssc-coverage.json").write_text(
        json.dumps(coverage_ranges(set(cmap))), encoding="utf-8"
    )
    print(f"coverage: {len(cmap)} glyph-mapped codepoints -> notosanssc-coverage.json")


if __name__ == "__main__":
    main()
