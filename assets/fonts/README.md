# Bundled Fonts

Bundled so rendering looks identical on any machine (the Codex Linux sandbox
has neither Segoe Print nor Microsoft YaHei; without these files the diagrams
silently lose the hand-drawn look).

| File | Role | Source | License |
| --- | --- | --- | --- |
| `Excalifont-Regular.ttf` / `.woff2` | Hand-drawn Latin (titles, card titles) | [Excalidraw](https://plus.excalidraw.com/excalifont) | OFL-1.1 |
| `NotoSansSC-Regular.ttf` / `.woff2` | CJK body text | [google/fonts](https://github.com/google/fonts/tree/main/ofl/notosanssc), subset | OFL-1.1 (`OFL-NotoSansSC.txt`) |
| `NotoSansSC-Bold.ttf` / `.woff2` | CJK bold | same, instanced at wght=700 | OFL-1.1 |
| `notosanssc-coverage.json` | Codepoint ranges covered by the subset; renderer falls back to system fonts for anything outside | generated | - |

The Noto subset covers ASCII, Latin-1, general punctuation, arrows, CJK
punctuation, fullwidth forms, and the full GB2312 hanzi set (6763 chars).

Regenerate with `scripts/prepare_fonts.py` (requires `fonttools` + `brotli`;
see the script docstring for inputs). TTF files feed the Pillow engine; WOFF2
files are for the browser/SVG renderer.
