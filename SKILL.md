---
name: archscribe
description: Create premium hand-drawn architecture, process, sequence, swimlane, hub, and layered diagrams with editable Excalidraw sources, PNG/SVG previews, animated GIF/MP4 output, and interactive HTML. Use whenever the user asks for 岚叔动态架构图、手绘架构图、Excalidraw 风格图、DailyDoseOfDS 风格黑底技术图、动态流程图、时序图、泳道图、系统可视化，或希望复刻并提升参考架构图。
---

# Archscribe

Turn an article, system description, process, or reference image into a polished hand-drawn diagram. The default browser renderer can produce PNG, GIF, MP4, SVG, editable Excalidraw, and interactive HTML.

## 1. Check the environment

Run once per session:

```bash
python -c "import PIL, svg.path"
python -c "from playwright.sync_api import sync_playwright"
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
| `pipeline` | left-to-right processes and retry loops | 2-6 stages, optional decision/output |
| `layers` | technology stacks and layered architectures | 2-5 layers, up to 5 items each |
| `hub` | agents, platforms, ecosystems, control centers | one center, 3-8 satellites |
| `swimlane` | cross-role workflows and approvals | 2-5 lanes, up to 5 steps each |
| `sequence` | API calls, agent tool chains, request/response traces | 2-6 participants, up to 12 messages |
| `graph` | free-form workflows with custom loop topology (retry/replan/recall...) | 2-24 nodes, up to 40 edges, auto DAG layout + loop lanes |

Decision rule:

- Flows through stages → `pipeline`
- Built from levels → `layers`
- One core coordinates capabilities → `hub`
- Ownership changes across roles → `swimlane`
- Ordering between participants matters → `sequence`
- Whole system with multiple regions → `panorama`
- Custom topology: forks/joins, multiple distinct loops, workflow-specific shape → `graph` (declare `nodes` + `edges`; `kind: "loop"` edges become dashed return channels that fire after the forward wave)

## 3. Write and validate the spec

Start from `assets/default-spec.json` or a file under `assets/examples/`. The complete field reference is `references/spec-format.md`.

Keep titles short, use the user's language, and move detail into bodies, notes, or an interactive HTML sidebar.

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
```

Fix every error. Warnings identify long text, unknown icons, ignored fields, or content that exceeds a layout's capacity.

## 4. Choose a visual theme

Available styles:

- `default`: black-canvas neon hand drawing
- `blueprint`: deep-blue technical blueprint
- `terminal`: phosphor-green CRT
- `candy`: light pastel paper
- `chalkboard`: textured classroom chalkboard
- `editorial`: warm, high-contrast publication graphic
- `cyber-grid`: deep cyber infrastructure palette

Styles control the full palette and finish. Use `--style` to override the spec.

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
python scripts/render_animated_diagram.py --spec spec.json --outdir out --basename diagram --formats png --check
```

Then render the publishing set:

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --basename diagram --formats gif,mp4,png,excalidraw,svg,html --verify --check
```

`--formats` is exact: only requested, supported files are emitted. Unknown formats fail. `--check` must return `"ok": true`.

Visually inspect the PNG for overlap, crossing connectors, cramped labels, weak hierarchy, and mobile readability. Shorten copy before reducing text below a readable size.

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

For a DailyDoseOfDS-style short loop, use 1210×1138, 20 FPS, 41 frames, stable camera, 1-3 active paths at a time, illustrated/hero icons on the main concepts, and `flow` animation. Start from `assets/examples/illustrated-loop-spec.json`.

## 8. Delivery

- Show GIF inline when useful.
- Prefer MP4 for publishing and social platforms.
- Include PNG for quick viewing.
- Include `.excalidraw` when editability matters.
- Offer interactive HTML for exploration or presentations.
- Use SVG for scalable static publication.

After changing this `SKILL.md`, open a new task or refresh the session before testing trigger behavior. Script and asset changes can be tested immediately.
