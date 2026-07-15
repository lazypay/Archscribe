<div align="center">

# Archscribe

**Premium hand-drawn animated architecture & process diagrams — dark neon and light paper styles — for articles, systems, and workflows.**

[![Codex Skill](https://img.shields.io/badge/Codex-Skill-22C86F?style=for-the-badge)](./SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pillow](https://img.shields.io/badge/Pillow-Renderer-8A2BE2?style=for-the-badge)](https://python-pillow.org/)
[![Excalidraw](https://img.shields.io/badge/Excalidraw-JSON-6965DB?style=for-the-badge)](https://excalidraw.com/)
[![Animated GIF](https://img.shields.io/badge/Animated-GIF-FFB000?style=for-the-badge)](./scripts/render_animated_diagram.py)
[![License](https://img.shields.io/badge/License-MIT-111827?style=for-the-badge)](./LICENSE)

`JSON spec` -> `.excalidraw` + `.png` + animated `.gif`

[简体中文](./README.md) · **English**

</div>

<p align="center">
  <a href="#gallery">Gallery</a> ·
  <a href="#layouts">Layouts</a> ·
  <a href="#styles">Styles</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#spec-structure">Spec</a> ·
  <a href="#verification">Verification</a>
</p>

`archscribe` is a Codex / Claude skill and local renderer for creating premium hand-drawn technical diagrams with hand-drawn typography, editable Excalidraw output, static PNG previews, and genuinely animated GIFs.

It is designed for article explanations, system architecture diagrams, process diagrams, and DailyDoseOfDS-style technical sketches — in a dark neon or a light paper look.

## Gallery

The homepage uses one full-width example per layout so the details stay readable: `panorama`, `swimlane`, and `graph`. The same spec family can switch between `default` dark neon and `paper` light paper with `--style`.

### 1. System Panorama: Skill Runtime (`panorama` + `default`)

Best for decomposing a system, product, agent, or article into inputs, a core flow, a decision point, and deliverables.

![Archscribe panorama case](./assets/previews/homepage-panorama.gif)

```text
Use $archscribe to turn this Skill / Agent workflow into a dark neon hand-drawn panorama showing inputs, core flow, quality checks, and final artifacts. Output GIF, PNG, and Excalidraw.
```

### 2. Category Comparison: Agent Loops (`swimlane` + `paper`)

Best for DailyDoseOfDS-style category bands, comparisons, role swimlanes, and knowledge cards.

![Archscribe swimlane case](./assets/previews/homepage-swimlane.gif)

```text
Use $archscribe to draw a light paper swimlane diagram about the four types of Agent Loops, with each lane showing triggers, key steps, and loop-back relationships.
```

### 3. Custom Topology: HTML to Motion (`graph` + `paper`)

Best for CI/CD, render pipelines, failure recovery, review loops, and other workflows that need custom graph topology. Long chains auto-stack downward to avoid clipped sides and empty lower halves.

![Archscribe graph case](./assets/previews/homepage-graph.gif)

```text
Use $archscribe to turn the HyperFrames HTML composition, validation, visual inspection, render, and repair loop into an animated graph diagram in the light paper style.
```

## Layouts

Three templates cover most explanations. Pick one with a `"layout"` field in
the spec; content counts are elastic and the canvas height adapts.

| Layout | Best for | Preview |
| --- | --- | --- |
| `panorama` (default) | whole systems: sources → core pipeline → storage/output panels | <img src="./assets/previews/memory-pack.png" alt="panorama layout" width="320" /> |
| `swimlane` | category bands / comparison rows ("the N types of X"), cross-role workflows, catalogs | <img src="./assets/previews/paper-loops.png" alt="swimlane layout" width="320" /> |
| `graph` | free-form nodes/edges with auto DAG layout and loop lanes — per-project topology | <img src="./assets/previews/layout-graph.png" alt="graph layout" width="320" /> |

Elasticity: panorama takes 2-6 inputs, 2-4 core cards, all three bottom panels optional; swimlane takes 2-5 bands with 1-5 steps each, a title column with optional subtitle ("Triggered by: ..."), and in-lane right-to-left connections automatically drop into a dashed loop channel under the cards; graph takes 2-24 nodes and up to 40 edges with `kind: "loop"` return channels — use it for linear flows too. Rightward chains longer than 7 sequential layers auto-stack downward.

## Styles

Archscribe ships with **2 built-in styles**. The diagram layout, animation, and
icons stay identical; only the palette and finish change.
Pick one with the `--style` CLI flag or a `"style"` field in the spec.

| Style | Look | Preview |
| --- | --- | --- |
| `default` | Dark hand-drawn neon on pure black: glowing beams, grain, vignette (brand default) | <img src="./assets/previews/memory-pack.png" alt="default style" width="320" /> |
| `paper` | Warm-white paper: alternating sage/periwinkle band tints, near-black ink, white cards with colored strokes; the flow animation becomes small solid dots | <img src="./assets/previews/paper-loops.png" alt="paper style" width="320" /> |

Select a style on the command line (overrides the spec):

```bash
python3 scripts/render_animated_diagram.py \
  --spec assets/examples/swimlane-spec.json \
  --outdir outputs \
  --basename my-diagram \
  --style paper
```

Or pin it in the spec JSON so the diagram always renders in that style:

```json
{
  "style": "paper",
  "canvas": { "fps": 20, "frames": 41 }
}
```

If both are present, `--style` wins. When neither is set, the renderer uses
`default`. Any other style name fails validation. For `graph`, avoid setting
`canvas.width` / `canvas.height`; the planner uses a natural canvas to prevent
clipping and dead space.

## Features

- 3 layout templates via a spec `layout` field: `panorama` (system overview), `swimlane` (reference-style category bands: subtitle column, alternating tints, in-lane dashed loop channels), `graph` (free-form nodes/edges + auto DAG + loop lanes; long graphs auto-stack downward to avoid clipping)
- Browser renderer (default): rough.js hand-drawn shapes + bundled Excalifont / Noto Sans SC webfonts inside headless Chromium — genuine Excalidraw look, identical on every OS
- 6 animation presets via `--animation`: `flow`, `draw`, `relay`, `trace`, `chapter`, `failure-recovery` — all presets work on all layouts
- Generates `.excalidraw`, `.png`, `.gif`, `.mp4`, standalone `.svg`, and an interactive `.html` from one JSON spec (`--formats`)
- Interactive HTML: click a module to highlight its connections, toggle the full BFS chain, hover tooltips, keyboard accessible — single self-contained file
- MP4 output is a fraction of the GIF size and natively supported by X / WeChat; GIF uses a shared global palette for small files
- 2 built-in styles: `default` dark neon and `paper` light paper (light mode swaps beams for small dots, drops grain and vignette)
- Three icon levels (`outline`, `illustrated`, `hero`) with deterministic semantic micro-motion — see `references/illustrated-icons.md`
- Spec pre-flight validation (`--validate-only` or automatic before render) with field-level `path` / `message` / `fix` errors, built for agent self-correction
- Brand customization: any item takes `icon_file` (local SVG/PNG rendered in its original colors — product logos, colorful icons); `left_panel.badge_file` puts a logo in the panel header; `input_style: "plain"` gives frameless colorful input icons; `down_label` / `up_label` / `yes_label` rename the built-in arrow labels; long signatures (domains) auto-shift and stretch their underline instead of clipping
- Keeps the `.excalidraw` source editable and text-based
- Bundled fonts (OFL) and Tabler SVG icon subset (MIT); works offline with no remote assets at render time; icons get a wave-ordered micro "pop" in the `flow` preset
- `--check` validates the full output contract (dimensions, frames, real motion, MP4 stream, SVG fonts, HTML hotspots, Excalidraw invariants) plus graph clipping, vertical balance, and long-chain orientation; `--verify` prints a frame-diff report
- Classic Pillow pipeline retained as `--renderer pillow` fallback

## Outputs

Default render (`--renderer browser`):

```text
<basename>.excalidraw
<basename>.png
<basename>.gif
<basename>.mp4
```

Optional: `<basename>.svg` (fonts embedded, opens standalone) and
`<basename>.html` (interactive click-to-explore page). The canvas is
`1210 x <computed>` at 20 fps — each layout computes its height from content
(the classic panorama is `1210 x 1138`); `flow` uses 41 frames (~2 s loop),
`draw` 72+, `relay` 88+.

## Quick Start

```bash
git clone https://github.com/lazypay/Archscribe.git
cd Archscribe
python3 -m pip install -r requirements.txt
python3 -X utf8 scripts/render_animated_diagram.py \
  --spec assets/default-spec.json \
  --outdir outputs \
  --basename sample \
  --verify \
  --check
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
python3 -X utf8 scripts/render_animated_diagram.py \
  --spec work/my-diagram-spec.json \
  --outdir outputs \
  --basename my-diagram \
  --style default \
  --animation flow \
  --verify \
  --check
```

Key flags:

- `--renderer auto|browser|pillow` — `browser` (default when available)
  replays the layout with rough.js in headless Chromium; `pillow` is the
  classic raster fallback.
- `--animation flow|draw|relay|trace|chapter|failure-recovery` — motion preset (browser renderer). Overrides
  the spec `animation` field.
- `--formats gif,mp4,png,svg,html,excalidraw` — pick outputs; browser default
  is `gif,mp4,png,excalidraw`.
- `--style default|paper` — palette. See [Styles](#styles).
- `--validate-only` — check the spec and exit (field-level errors/warnings as
  JSON, exit 2 on errors); every render also validates first.
- `--verify` — prints sampled frame differences (nonzero pixels = real motion).
- `--check` — validates the full output contract (PNG/GIF dimensions, frame
  count, FPS, motion, MP4 stream properties, SVG font embedding, HTML
  hotspots, Excalidraw invariants) and exits nonzero on failure.
- `--strict-formats` — use for publishing; fails when any requested format is
  not produced, instead of silently accepting a browser or ffmpeg fallback.
- `--icon-engine` — icon fidelity for the pillow fallback pipeline only.

For fast layout iteration, render `--formats png` first (seconds), then run
the full render once the layout is right.

## Spec Structure

Pick a layout, then fill its content fields. Templates to copy:
`assets/default-spec.json` (panorama), `assets/examples/swimlane-spec.json`
(the paper-style "four types of agent loops" reference look),
`assets/examples/graph-workflow-spec.json` (free-form graph), plus the
`illustrated-loop` / `loop-icon-pack` / `illustrated-icon-catalog` samples.

```text
layout         (optional: panorama | swimlane | graph)
style          (optional: default | paper)
animation      (optional: flow | draw | relay | trace | chapter | failure-recovery)
signature
title.prefix / title.highlight / title.subtitle

panorama:  inputs (2-6), core.cards (2-4), decision, output,
           left_panel / center_panel / right_panel (each optional, needs cards)
swimlane:  lanes (2-5, each title / optional subtitle / optional accent /
           steps(1-5, each id/title/icon)), optional connections
           (from/to/label/style/accent; right-to-left in-lane connections
           drop into the dashed loop channel automatically)
graph:     nodes (2-24), edges (up to 40, including kind:"loop"), direction
           (right/down). Rightward chains longer than 7 layers auto-stack
           downward; canvas width/height are diagnostic warnings and the
           planner computes a natural size.
illustrated icons: see references/illustrated-icons.md
```

Custom icons / logos: every item that accepts `icon` also accepts `icon_file`
(a local `.svg` / `.png`; relative paths resolve against the spec file's
folder). The browser renderer embeds it with its original colors — ideal for
brand logos. `left_panel.badge_file` swaps the text badge for a logo image.

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
python3 -X utf8 ${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py \
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
python3 -X utf8 scripts/render_animated_diagram.py \
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

Recommended (browser renderer — hand-drawn shapes, animation presets, SVG):

```bash
python3 -m pip install -r requirements-browser.txt
python3 -m playwright install chromium
```

Optional tools:

- `ffmpeg` for MP4 output (skipped gracefully when missing), `ffprobe` for media inspection
- Excalidraw web app or editor plugin for manual editing of generated `.excalidraw` files

Bundled assets (no downloads at render time):

- `assets/fonts/` — Excalifont + Noto Sans SC subset (OFL-1.1), see `assets/fonts/README.md`
- `assets/vendor/rough.js` — rough.js 4.6.6 (MIT)
- `assets/icons/tabler/` — Tabler icon subset (MIT)

## Project Layout

```text
archscribe/
├── SKILL.md
├── README.md            # 简体中文 (default)
├── README.en.md         # English (this file)
├── LICENSE
├── requirements.txt
├── requirements-browser.txt
├── agents/
│   └── openai.yaml
├── assets/
│   ├── default-spec.json              # panorama template
│   ├── examples/                      # layout + illustration samples
│   ├── fonts/                     # bundled Excalifont + Noto Sans SC (OFL)
│   ├── vendor/                    # rough.js (MIT)
│   ├── icons/
│   │   └── tabler/
│   └── previews/                  # GitHub gallery + layout previews
├── docs/
│   └── interactive-output-design.md   # 2.0 roadmap
├── references/
│   ├── spec-format.md
│   └── illustrated-icons.md
├── scripts/
│   ├── render_animated_diagram.py     # CLI + validation + pillow pipeline + op recorder
│   ├── svg_renderer.py                # rough.js browser renderer + animation + HTML
│   ├── graph_model.py                 # layout planner + graph topology
│   ├── doctor.py                      # environment self-check
│   ├── prepare_fonts.py               # one-time font asset builder
│   └── icon_browser.py                # legacy icon engine (pillow pipeline)
└── tests/
```

## Design Notes

This project intentionally keeps the visual system narrow:

- Hand-drawn title treatment, top-right signature, two art-directed palettes
  (dark neon / light paper) shared by every layout
- Three layout templates (system panorama / category bands / free-form graph)
  instead of a free-form layout engine — elastic counts, planner-computed
  coordinates
- One geometry source (`scripts/graph_model.py` plans) drives the Pillow
  raster, the browser SVG render, the animation paths, and the interactive
  HTML graph — they can never drift apart
- Clean static diagram with motion added only in overlays: beams (dark) or
  traveling dots (paper), ripples, breathing, icon sweeps

That constraint keeps outputs consistent and polished across different architecture topics.

## Acknowledgements

The dark hand-drawn animated visual style is inspired by **岚叔**'s animated
architecture diagrams; the light paper style and the category-band template are
inspired by **DailyDoseOfDS** (akshay_pachaar) hand-drawn technical sketches.
Archscribe is an independent re-implementation of those looks as an open
skill; all credit for the original aesthetics goes to those creators.

## License

MIT

Bundled icons in `assets/icons/tabler` are from Tabler Icons and are MIT
licensed; see `assets/icons/tabler/LICENSE`.
