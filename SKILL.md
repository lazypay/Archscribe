---
name: archscribe
description: Create premium hand-drawn architecture, workflow, and swimlane diagrams in a dark neon or light paper style, with editable Excalidraw sources, PNG/SVG previews, animated GIF/MP4 output, and interactive HTML. Use whenever the user asks for 岚叔动态架构图、手绘架构图、Excalidraw 风格图、DailyDoseOfDS 风格技术图、动态流程图、泳道图、系统可视化，或希望复刻并提升参考架构图。
---

# Archscribe

Turn an article, system description, process, or reference image into a polished hand-drawn diagram. The default browser renderer can produce PNG, GIF, MP4, SVG, editable Excalidraw, and interactive HTML.

## 1. Check the environment

Run once per session:

```bash
python -X utf8 -c "import PIL, svg.path"
python -X utf8 -c "from playwright.sync_api import sync_playwright"
python -X utf8 scripts/doctor.py
```

- Missing base packages: `python -m pip install -r requirements.txt`
- Missing Playwright: `python -m pip install -r requirements-browser.txt && python -m playwright install chromium`
- Missing ffmpeg: MP4 is skipped; other browser formats still work.
- Chromium unavailable: use `--renderer pillow`. Pillow supports PNG, GIF, and Excalidraw with the classic flow animation.

Bundled fonts, icons, and rough.js keep the main visual system portable. Chromium, ffmpeg, and rare CJK fallback fonts remain environment dependencies.

## 2. Pick a layout

| Layout | Use it for | Capacity |
| --- | --- | --- |
| `panorama` | complete systems with inputs, core, decisions, and detail panels | 2-6 inputs, 2-4 core cards, 0-3 panels |
| `swimlane` | category bands / comparison rows (DailyDoseOfDS-style), cross-role workflows, catalogs | 2-5 lanes with title + subtitle column, up to 5 steps each, in-lane dashed loop channels |
| `graph` | free-form per-project workflows with custom loop topology (retry/replan/recall...) | 2-24 nodes, up to 40 edges, auto DAG layout + loop lanes |

Decision rule:

- Whole system with multiple regions → `panorama`
- Parallel categories, variants, roles, or a comparison ("the N types of X") → `swimlane` (each lane gets a tinted band, a darker title column with optional `subtitle` such as "Triggered by: ...", and right-to-left in-lane connections automatically drop into a dashed loop channel under the cards)
- Anything with its own topology: linear stages, forks/joins, multiple distinct loops → `graph` (declare `nodes` + `edges`; `kind: "loop"` edges become dashed return channels that fire after the forward wave). Long rightward graphs auto-stack downward to prevent clipped sides and top-heavy layouts.

## 3. Write and validate the spec

Start from `assets/default-spec.json` or a file under `assets/examples/`. The complete field reference is `references/spec-format.md`.

Keep titles short, use the user's language, and move detail into bodies, notes, or an interactive HTML sidebar.

```bash
python -X utf8 scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
```

Fix every error. Warnings identify long text, unknown icons, ignored fields, content that exceeds a layout's capacity, graph auto-stacking, or ignored graph canvas width/height.

## 4. Choose a visual theme

Two styles, both first-class:

- `default`: black-canvas neon hand drawing — glowing beams, grain, vignette. The brand hero look.
- `paper`: light warm-white paper (DailyDoseOfDS-style) — sage/periwinkle band tints, near-black ink, white cards with colored strokes; the flow animation becomes small solid dots traveling the arrows instead of neon beams.

Styles control the full palette and finish. Use `--style` to override the spec. Any other style name fails validation.

## 5. Choose animation

- `flow`: continuous data movement; safe default
- `draw`: whiteboard construction
- `relay`: one connection at a time
- `trace`: follow a request path
- `chapter`: staged explanatory build-up
- `failure-recovery`: failure/retry-oriented narrative timing

The last three use deterministic narrative choreography and longer minimum timelines. The browser renderer is required for every preset except classic Pillow `flow`.

## 6. Render and verify

First render a PNG for layout review:

```bash
python -X utf8 scripts/render_animated_diagram.py --spec spec.json --outdir out --basename diagram --formats png --check
```

Then render the publishing set:

```bash
python -X utf8 scripts/render_animated_diagram.py --spec spec.json --outdir out --basename diagram --formats gif,mp4,png,excalidraw,svg,html --verify --check --strict-formats
```

`--formats` is exact: only requested, supported files are emitted. Unknown formats fail. Use `--strict-formats` for publishing so missing MP4/SVG/HTML fails instead of silently falling back. `--check` must return `"ok": true`.

Visually inspect the PNG for overlap, crossing connectors, cramped labels, weak hierarchy, clipped edges, and empty-space imbalance. Shorten copy or switch layout before reducing text below a readable size.

## 7. Icons and brands

Specs use stable semantic icon keys. Core keys include `file`, `folder`, `scan`, `shield`, `db`, `package`, `message`, `api`, `clock`, `brain`, `gear`, `eye`, `terminal`, `globe`, `server`, `lock`, `check`, and `clipboard`.

Additional semantic aliases cover cloud infrastructure, data, AI, security, business roles, and states, including `cloud`, `cluster`, `container`, `queue`, `cache`, `vector-db`, `agent`, `model`, `rag`, `tool-call`, `guardrail`, `evaluation`, `identity`, `audit`, `user`, `success`, `failure`, and `retry`.

For a custom logo or colorful icon, use `icon_file` with a local SVG/PNG path. Use `left_panel.badge_file` for a panorama panel brand mark. Paths resolve relative to the spec.

### Illustration system

Every item that accepts `icon` also accepts:

- `icon_style`: `outline`, `illustrated`, or `hero`.
- `icon_size`: `compact`, `standard`, or `hero`.
- `icon_motion`: `auto` (plays the icon's built-in job story) or `none` (freeze at rest pose). Legacy preset names (`think-pulse`, `gear-spin`, `eye-scan`, `memory-write`, `shield-check`, `scope-scan`, `budget-gauge`, `trigger-ping`, `tool-spark`, `output-pop`) are still accepted and behave like `auto`.

Use `outline` for dense secondary nodes, `illustrated` for normal concept cards, and `hero` for the 1-3 concepts that carry the story. The browser renderer draws plate-free "Neon Sketch Duotone" illustrations: theme-ink hand-drawn strokes plus one semantic accent on the moving part, where each of ~56 semantic families performs its own seamless-looping job story (synapse signals, gear pitches, chip drops, shackle clicks — see `references/illustrated-icons.md`). This includes a dedicated loop-workflow pack (`loop`, `decision`, `split`, `merge`, `wait`, `orchestrator`, `subagent`, `handoff`, `human`, `plan`, `score`, `compare`, `sandbox`, `checkpoint`, `error`, `rollback`, `emit`, `ingest`, …) for agent-loop and pipeline diagrams — sample spec `assets/examples/loop-icon-pack-spec.json`. Pillow renders a simplified offline duotone fallback; Excalidraw keeps editable icon placeholders.

For a DailyDoseOfDS-style short loop, use 1210×1138, 20 FPS, 41 frames, stable camera, 1-3 active paths at a time, illustrated/hero icons on the main concepts, and `flow` animation. Start from `assets/examples/illustrated-loop-spec.json` (dark panorama) or `assets/examples/swimlane-spec.json` (light paper bands).

## 8. Delivery

- Show GIF inline when useful.
- Prefer MP4 for publishing and social platforms.
- Include PNG for quick viewing.
- Include `.excalidraw` when editability matters.
- Offer interactive HTML for exploration or presentations.
- Use SVG for scalable static publication.

After changing this `SKILL.md`, open a new task or refresh the session before testing trigger behavior. Script and asset changes can be tested immediately.
