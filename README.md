<div align="center">

# Archscribe

**Premium hand-drawn, dark-background animated architecture & process diagrams for articles, systems, and workflows.**

[![Codex Skill](https://img.shields.io/badge/Codex-Skill-22C86F?style=for-the-badge)](./SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pillow](https://img.shields.io/badge/Pillow-Renderer-8A2BE2?style=for-the-badge)](https://python-pillow.org/)
[![Excalidraw](https://img.shields.io/badge/Excalidraw-JSON-6965DB?style=for-the-badge)](https://excalidraw.com/)
[![Animated GIF](https://img.shields.io/badge/Animated-GIF-FFB000?style=for-the-badge)](./scripts/render_animated_diagram.py)
[![License](https://img.shields.io/badge/License-MIT-111827?style=for-the-badge)](./LICENSE)

`JSON spec` -> `.excalidraw` + `.png` + animated `.gif`

</div>

<p align="center">
  <a href="#gallery">Gallery</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#spec-structure">Spec</a> ·
  <a href="#verification">Verification</a>
</p>

`archscribe` is a Codex / Claude skill and local renderer for creating premium black-canvas technical diagrams with hand-drawn typography, editable Excalidraw output, static PNG previews, and genuinely animated GIFs.

It is designed for article explanations, system architecture diagrams, process diagrams, and DailyDoseOfDS-style black-background technical sketches.

## Gallery

The default visual system uses a dark canvas, moving flow highlights, animated icon micro-interactions, pulsing modules, subtle grain, vignette, and a top-right hand-drawn signature.

<table>
  <tr>
    <td width="50%" align="center">
      <strong>Animated GIF</strong><br />
      <img src="./assets/previews/memory-pack.gif" alt="Archscribe animated architecture diagram" width="100%" />
    </td>
    <td width="50%" align="center">
      <strong>Static PNG</strong><br />
      <img src="./assets/previews/memory-pack.png" alt="Archscribe static architecture diagram" width="100%" />
    </td>
  </tr>
</table>

## Features

- Generates `.excalidraw`, `.png`, and animated `.gif` from one JSON spec
- Produces real animation with restrained flow dots, subtle module emphasis, and crisp animated SVG icons
- Keeps the `.excalidraw` source editable and text-based
- Two icon engines: `browser` (headless Chromium, best quality, genuinely animated strokes) and `pillow` (dependency-light fallback); `auto` picks the best available
- Uses a bundled local Tabler SVG icon subset (MIT) for clean professional symbols
- Works offline with no remote APIs or remote icon libraries at render time
- Includes frame-diff verification to prove GIF motion
- Uses a fixed high-quality layout for clean technical storytelling

## Outputs

Each render produces:

```text
<basename>.excalidraw
<basename>.png
<basename>.gif
```

The default canvas is:

```text
1210 x 1138
20 fps
41 frames
2.05 seconds
```

## Quick Start

```bash
git clone https://github.com/lazypay/Archscribe.git
cd Archscribe
python3 -m pip install -r requirements.txt
python3 scripts/render_animated_diagram.py \
  --spec assets/default-spec.json \
  --outdir outputs \
  --basename sample \
  --verify
```

## Installation

Place this folder in your Codex skills directory:

```bash
~/.codex/skills/archscribe
```

Typical local install path:

```bash
${CODEX_HOME:-$HOME/.codex}/skills/archscribe
```

Install the runtime dependency:

```bash
python3 -m pip install -r requirements.txt
```

## Use With Codex

Invoke the skill by name:

```text
Use $archscribe to turn this article into a premium hand-drawn animated architecture GIF.
```

Chinese prompt example:

```text
用 $archscribe 把这篇文章整理成手绘动态架构图（岚叔 / DailyDoseOfDS 风格），输出 GIF、PNG 和 Excalidraw。
```

## CLI Usage

Start from the bundled template:

```bash
cp assets/default-spec.json work/my-diagram-spec.json
```

Render:

```bash
python3 scripts/render_animated_diagram.py \
  --spec work/my-diagram-spec.json \
  --outdir outputs \
  --basename my-diagram \
  --verify \
  --check
```

The `--verify` flag prints sampled frame differences. Nonzero changed pixels confirm that the GIF is genuinely animated.

The `--check` flag validates the generated PNG, GIF, and Excalidraw output
contract and exits nonzero if a required property fails. It checks dimensions,
GIF frame count and frame duration, sampled GIF motion, unique Excalidraw IDs,
text font family, and that no external files are embedded.

## Spec Structure

The renderer uses `assets/default-spec.json` as a compact art-directed template.

Most edits happen in these fields:

```text
signature
title.prefix
title.highlight
title.subtitle
inputs
core.cards
decision
output
left_panel
center_panel
right_panel
```

Supported icon keys:

```text
folder
file
scan
shield
db
hash
package
message
event
api
clock
brain
gear
eye
terminal
globe
video
snapshot
server
lock
check
clipboard
```

For details, see [references/spec-format.md](./references/spec-format.md).

## Verification

Validate the skill structure:

```bash
python3 ${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py \
  ${CODEX_HOME:-$HOME/.codex}/skills/archscribe
```

Validate GIF media parameters:

```bash
ffprobe -v error -select_streams v:0 -count_frames \
  -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames \
  -show_entries format=duration \
  -of default=noprint_wrappers=1 outputs/my-diagram.gif
```

Validate animation:

```bash
python3 scripts/render_animated_diagram.py \
  --spec assets/default-spec.json \
  --outdir outputs \
  --basename sample \
  --verify \
  --check
```

## Dependencies

Required:

- Python 3.9+
- Pillow 10.0.0+
- svg.path 7.0+

Install Python packages with:

```bash
python3 -m pip install -r requirements.txt
```

Optional (browser icon engine, recommended for best quality):

```bash
python3 -m pip install -r requirements-browser.txt
python3 -m playwright install chromium
```

Optional tools:

- `ffprobe` for media inspection
- Excalidraw web app or editor plugin for manual editing of generated `.excalidraw` files

## Project Layout

```text
archscribe/
├── SKILL.md
├── README.md
├── LICENSE
├── requirements.txt
├── requirements-browser.txt
├── agents/
│   └── openai.yaml
├── assets/
│   ├── default-spec.json
│   ├── icons/
│   │   └── tabler/
│   └── previews/
│       ├── memory-pack.gif
│       └── memory-pack.png
├── references/
│   └── spec-format.md
└── scripts/
    ├── render_animated_diagram.py
    └── icon_browser.py
```

## Design Notes

This project intentionally keeps the visual system narrow:

- Dark canvas
- Hand-drawn title treatment
- Top input strip
- Middle core pipeline
- Bottom source, layer, and pack panels
- Top-right signature
- Clean static diagram with motion added only in GIF overlays, mainly path dots plus small focus-icon sweeps or glints

That constraint keeps outputs consistent and polished across different architecture topics.

## Acknowledgements

The dark hand-drawn animated visual style is inspired by **岚叔**'s animated
architecture diagrams and **DailyDoseOfDS**-style black-background technical
sketches. Archscribe is an independent re-implementation of that look as an open
skill; all credit for the original aesthetic goes to those creators.

## License

MIT

Bundled icons in `assets/icons/tabler` are from Tabler Icons and are MIT
licensed; see `assets/icons/tabler/LICENSE`.
