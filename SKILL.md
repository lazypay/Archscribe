---
name: archscribe
description: Create premium hand-drawn architecture and process diagrams in a dark, animated GIF style, with editable .excalidraw files, static PNG previews, and genuinely animated GIFs with moving flow highlights. Use this skill whenever the user asks for 岚叔动态架构图, Excalidraw-like diagrams, DailyDoseOfDS-style black-background sketches, animated architecture/process GIFs, polished flowcharts, visual explanations of articles or system designs, or asks to replicate or improve a reference diagram with hand-drawn animated effects.
---

# Archscribe

Create a polished black-background hand-drawn technical diagram with:

- Editable `.excalidraw` source
- Static `.png` preview
- Animated `.gif` with restrained flow dots and crisp, genuinely animated SVG icons

Use the bundled renderer for deterministic output. Avoid external icon libraries unless the user explicitly provides audited assets.

## Icon Engines

The renderer has two icon engines, selected with `--icon-engine`:

- `browser` (best quality): renders the bundled Tabler SVGs through headless Chromium and animates each stroke with a looping energy sweep. Produces clean, professional, uniformly sized icons. Requires `requirements-browser.txt` plus `python -m playwright install chromium`. This is ideal inside Codex, which can run a browser.
- `pillow` (dependency-light fallback): rasterizes the same SVGs locally with no browser. Slightly simpler look, fully portable.
- `auto` (default): uses `browser` when available, otherwise falls back to `pillow`.

Prefer `browser` when a headless Chromium is available. The two engines share the same layout, sizing, and Excalidraw output, so switching only changes icon fidelity.

## Workflow

1. Extract the diagram content.
   - For an article or long post, identify the core architecture, actors, stages, data flow, decisions, and final outputs.
   - For a reference image, preserve the visual grammar: title structure, panels, arrows, density, and signature placement.

2. Create a spec JSON.
   - Start from `assets/default-spec.json`.
   - Keep labels short. Read `references/spec-format.md` when field details or copy length guidance are needed.
   - Use the user’s language for explanatory labels unless the reference style clearly calls for English titles.

3. Render the outputs.

```bash
python /path/to/skill/scripts/render_animated_diagram.py \
  --spec /path/to/spec.json \
  --outdir /path/to/output-dir \
  --basename descriptive-name \
  --icon-engine browser \
  --verify \
  --check
```

Drop `--icon-engine browser` (or use `auto`) to let the renderer pick the best available engine.

4. Validate before delivery.
   - Confirm GIF dimensions, FPS, frame count, and duration with `ffprobe`.
   - Use `--verify` output or `--check` to prove the GIF is not static.
   - Confirm `.excalidraw` JSON has unique IDs, text uses `fontFamily: 5`, and `files` is empty. `--check` validates these output contracts automatically.
   - Open the PNG preview visually and fix overlap, cramped text, or weak hierarchy.

5. Deliver the three files.
   - Show the GIF preview when the interface supports local images.
   - Link the PNG and `.excalidraw` source.

## Style Rules

- Use a dark canvas with a thin outer rounded frame.
- Use one highlighted title phrase in a green capsule.
- Put the author signature in the top-right brand slot unless the user asks otherwise.
- Prefer clean white main arrows. Use colored motion only in the GIF overlay.
- Keep static diagrams restrained. Let animation add motion, not clutter.
- Treat icons as clean semantic anchors first. Keep icons uniformly sized (one tile size everywhere) and inside card bounds; do not add always-on halos or decorative rings.
- With the browser engine, icons animate via a subtle looping stroke sweep. Keep it restrained; let path dots carry the main flow so the diagram stays readable.
- Use short text. If a phrase cannot fit, rewrite it instead of shrinking until unreadable.
- Prefer the bundled Tabler-style SVG icon subset for clean professional line icons. Supported keys include `file`, `folder`, `scan`, `shield`, `db`, `hash`, `package`, `message`, `event`, `api`, `clock`, `brain`, `gear`, `eye`, `terminal`, `globe`, `video`, `snapshot`, `server`, `lock`, `check`, and `clipboard`.
- Match icons to meaning instead of reusing generic files. Good mappings: planning/thinking -> `brain`, actions/tools -> `gear`, observation -> `eye`, API calls -> `api`, schedules -> `clock`, outputs/packages -> `package`.

## Spec Authoring Hints

Map common content to the fixed layout:

- `inputs`: source systems, triggers, documents, tools, or user actions
- `core.cards`: the three main stages of the process
- `decision`: the quality gate or readiness check
- `left_panel`: memory/context/source material
- `center_panel`: internal layers, safeguards, archive stores, or pipeline internals
- `right_panel`: packaged outputs, reusable assets, generated reports, or agent-facing artifacts

If the subject has more than three stages, group adjacent steps into three core cards and move details into the lower panels.

## Verification Commands

Use these checks after rendering:

```bash
ffprobe -v error -select_streams v:0 -count_frames \
  -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames \
  -show_entries format=duration \
  -of default=noprint_wrappers=1 output.gif
```

```bash
python /path/to/skill/scripts/render_animated_diagram.py \
  --spec spec.json \
  --outdir outputs \
  --basename diagram \
  --verify \
  --check
```

The `--verify` report should show nonzero changed pixels between sampled GIF frames.
The `--check` report should return `"ok": true`; it exits nonzero on contract failures.
