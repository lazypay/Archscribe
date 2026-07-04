---
name: archscribe
description: Create premium hand-drawn architecture and process diagrams in a dark, animated style, with 3 layout templates (panorama / pipeline / layers), editable .excalidraw files, static PNG/SVG previews, animated GIFs, publish-ready MP4s, and a click-to-explore interactive HTML. Use this skill whenever the user asks for 岚叔动态架构图, Excalidraw-like diagrams, DailyDoseOfDS-style black-background sketches, animated architecture/process GIFs, polished flowcharts, visual explanations of articles or system designs, or asks to replicate or improve a reference diagram with hand-drawn animated effects.
---

# Archscribe

Turn any article, system description, or process into a polished hand-drawn
diagram. One render produces:

- Animated `.gif` + much smaller `.mp4` (X / WeChat native support)
- Static `.png` preview, editable `.excalidraw` source
- Optional standalone `.svg` and an interactive `.html` (click a module to
  highlight its connections)

Everything needed ships inside the skill (fonts, icons, rough.js), so output
is identical on any machine. Most users describe what they want in one
sentence; you do the rest with the workflow below.

## Step 0: Environment Check

Run once per session before rendering:

```bash
python -c "import PIL, svg.path"                               # base deps
python -c "from playwright.sync_api import sync_playwright"    # browser renderer
```

- Base deps missing: `python -m pip install -r requirements.txt`
- Playwright missing: `python -m pip install -r requirements-browser.txt && python -m playwright install chromium`
- No `ffmpeg` on PATH: MP4 is skipped automatically; GIF/PNG still render. Do not block on ffmpeg.
- If Chromium cannot run at all, add `--renderer pillow` (classic raster pipeline; GIF animation only in the legacy flow style, no mp4/svg/html).

## Step 1: Pick a Layout

Three templates, selected by the top-level spec field `"layout"`:

| Layout | Shape | Pick it when the content is... | Capacity |
|---|---|---|---|
| `panorama` (default) | inputs on top, core pipeline + decision in the middle, 3 detail panels below | a whole system: sources, processing, storage, outputs | 2-6 inputs, 2-4 core cards, 0-3 panels |
| `pipeline` | one left-to-right stage row, optional decision diamond + output, optional notes under stages, optional retry loop | a linear process: CI/CD, approval flow, data pipeline, lifecycle | 2-6 stages (+decision +output) |
| `layers` | stacked horizontal bands connected downward | a layered stack: tech stack, N-tier architecture, org levels, protocol stack | 2-5 layers × 1-5 items |

Decision rule: "does X flow through steps?" → `pipeline`. "is X built out of
levels?" → `layers`. "how does the whole system fit together?" → `panorama`.
If unsure, `panorama` is the safest and richest.

Elasticity notes (panorama): input count 2-6 and core card count 2-4 are
positioned automatically; each bottom panel is drawn only if it has `cards`,
and if you omit all three panels the canvas shrinks to a compact top-half
diagram. `pipeline`/`layers` compute their canvas height from content.

## Step 2: Write the Spec

- Start from an example: `assets/default-spec.json` (panorama),
  `assets/examples/pipeline-spec.json`, `assets/examples/layers-spec.json`.
- Full field reference: `references/spec-format.md`.
- Keep labels short (titles 1-3 words); move detail into bodies/notes.
- Use the user's language for labels unless the reference style calls for English.
- Check the spec before rendering (fast, no browser):

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
```

It prints field-level errors/warnings with a `path`, `message`, and `fix`
(e.g. `$.stages needs at least 2 items`). Fix errors and rerun; warnings are
advisory (long labels shrink, unknown icons fall back to a circle). A normal
render also runs this validation and refuses to render on errors.

## Step 3: Render

```bash
python /path/to/skill/scripts/render_animated_diagram.py \
  --spec /path/to/spec.json \
  --outdir /path/to/output-dir \
  --basename descriptive-name \
  --style default \
  --animation flow \
  --verify \
  --check
```

(PowerShell: put everything on one line.)

Iteration tip: render `--formats png` first (about 2 seconds) to check the
layout, then run the full render once it looks right (animation capture takes
roughly 15-45 s).

## Step 4: Validate and Deliver

- `--check` must report `"ok": true`; it validates dimensions, frame count,
  FPS, real GIF motion, MP4 stream properties, SVG font embedding, HTML
  hotspot count, and the Excalidraw contract. It exits nonzero on failure.
- Open the PNG visually: fix overlap, cramped text, weak hierarchy.
- Deliver: show the GIF inline when supported; attach the MP4 for publishing;
  link the PNG, `.excalidraw`, and (when produced) the interactive `.html`.

## Renderers

Selected with `--renderer` (default `auto`, which prefers `browser`):

- `browser` (default, best quality): replays the layout with rough.js inside
  headless Chromium. Real hand-drawn wobble, webfont text, crisp inline
  icons, animation presets, MP4/SVG/HTML output.
- `pillow` (fallback): classic dependency-light raster pipeline. Works with
  no browser; classic flow GIF only.

## Animation Presets

Selected with `--animation` or a spec `"animation"` field (CLI wins; default `flow`):

- `flow` (default): eased energy beams travel each arrow with a bright orb
  head, arrival ripples, modules breathing in wave order. Short seamless
  loop, safe for every topic.
- `draw`: whiteboard build-up. Shapes stroke-reveal in draw order, text fades
  in, icons pop last, hold, loop. 72+ frames. Best for explanations and
  article hero images.
- `relay`: narrative hand-off. The canvas dims, one edge at a time carries a
  bright beam, its destination lights up, visited edges stay faintly lit.
  88+ frames. Best for "follow the data" storytelling.

All presets work on all three layouts and loop seamlessly. An ambient layer
follows the style automatically (title-capsule breathing, scanlines for
terminal, grid ripple for blueprint, floating dots for candy).

## Styles

4 palettes via `--style` or a spec `"style"` field (CLI wins; default `default`):

- `default`: dark hand-drawn neon on pure black (brand default).
- `blueprint`: deep navy monochrome, technical blueprint feel.
- `terminal`: near-black canvas with phosphor-green CRT tones.
- `candy`: fresh pastel on a light paper canvas (clean finish, no grain).

Layout, animation, and icons are identical across styles; only the palette changes.

## Output Formats

Selected with `--formats` (comma list). Browser default: `gif,mp4,png,excalidraw`.
Also available: `svg`, `html`. Pillow default: `gif,png,excalidraw`.

- MP4 is ~1/6 the size of the GIF and X / WeChat render it natively; prefer
  it for publishing, keep the GIF for inline previews.
- `html` is a standalone interactive page: click a module to highlight its
  connections, toggle 整条链路 for the whole BFS chain, hover for tooltips,
  Esc to reset. Offer it when the user wants to explore or present the
  architecture, not just embed an image.

## Style Rules

- Use a dark canvas with a thin outer rounded frame (light canvas for `candy`).
- Use one highlighted title phrase in a colored capsule.
- Put the author signature in the top-right brand slot unless the user asks otherwise.
- Prefer clean white main arrows. Use colored motion only in the animation overlay.
- Keep static diagrams restrained. Let animation add motion, not clutter.
- Use short text. If a phrase cannot fit, rewrite it instead of shrinking until unreadable.
- Match icons to meaning. Supported keys: `file`, `folder`, `scan`, `shield`,
  `db`, `hash`, `package`, `message`, `event`, `api`, `clock`, `brain`,
  `gear`, `eye`, `terminal`, `globe`, `video`, `snapshot`, `server`, `lock`,
  `check`, `clipboard`. Good mappings: planning/thinking -> `brain`,
  actions/tools -> `gear`, observation -> `eye`, API calls -> `api`,
  schedules -> `clock`, outputs/packages -> `package`.
- Brand assets: when the user supplies (or asks for) a product logo or a
  colorful icon, put a local `.svg`/`.png` path in `icon_file` on that item
  (keeps original colors), or `left_panel.badge_file` for a logo in the
  panel header. Paths resolve relative to the spec file.
- Reference-style replicas: `input_style: "plain"` gives the frameless
  colorful input icons seen in DailyDoseOfDS-style diagrams;
  `left_panel.down_label`/`up_label` and `decision.yes_label` rename the
  built-in arrow labels; long `signature` domains auto-fit without clipping.

## Troubleshooting

- **Spec validation failed (exit before render)**: read the printed JSON;
  each error has `path` + `fix`. Common: missing `stages` for pipeline,
  missing `layers` for layers, fewer than 2 items.
- **"browser renderer unavailable" warning**: Playwright or Chromium missing.
  Install per Step 0, or accept the pillow fallback.
- **`--check` fails on `gif_frames`**: the spec `canvas.frames` is below the
  preset minimum (`draw` 72, `relay` 88); the renderer raises the frame count
  automatically, so this usually signals a stale expectation elsewhere.
- **`mp4_skipped` in the result JSON**: ffmpeg not on PATH. Install it or drop
  `mp4` from `--formats`.
- **CJK shows fallback-looking glyphs**: characters outside the bundled
  GB2312 subset switch to a system font automatically. Cosmetic only.
- **Text overflows a card**: shorten the copy (preferred) instead of relying
  on the automatic emergency shrink.
- **Renders feel slow**: animation frames are captured per frame in Chromium
  (roughly 0.3-0.7 s/frame). Iterate with `--formats png`, and only render
  gif+mp4 once the layout is final.

## Programmatic Verification Commands

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
python scripts/render_animated_diagram.py --spec spec.json --outdir out --basename d --formats png --check
ffprobe -v error -select_streams v:0 -count_frames -show_entries stream=width,height,r_frame_rate,nb_read_frames -of default=noprint_wrappers=1 out/d.gif
```

The `--verify` flag adds a sampled frame-diff report proving the GIF is not
static; `--check` includes the same probe plus the full output contract.
