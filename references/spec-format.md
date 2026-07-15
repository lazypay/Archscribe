# Archscribe Spec Format

Use this reference when authoring JSON for `scripts/render_animated_diagram.py`.

## Common fields

```json
{
  "layout": "panorama | swimlane | graph",
  "style": "default | paper",
  "animation": "flow | draw | relay | trace | chapter | failure-recovery",
  "title": {"prefix": "...", "highlight": "...", "subtitle": "..."},
  "signature": "@handle",
  "canvas": {"width": 1210, "height": 820, "fps": 20, "frames": 41},
  "density": "airy | balanced | compact",
  "aspect_ratio": "auto | landscape | portrait | square",
  "motion_level": "none | subtle | standard | cinematic"
}
```

`canvas` is optional. Valid limits are width 480-4096, height 360-4096, FPS 1-60, and frames 2-600. Layout geometry remains the source of truth unless width/height are explicitly overridden. For `graph`, width/height are diagnostic warnings and the planner uses its natural canvas to avoid clipping or dead space; use `fps` and `frames` freely.

Validate before rendering:

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
```

## Panorama

Use for a complete system. Main fields:

- `inputs`: 2-6 objects with `label`, `icon`, optional `color`/`icon_file`.
- `core.cards`: 2-4 cards with `title`, `body`, `icon`.
- `decision`, `output`, `loop_label`, `retry_label`.
- Optional `left_panel`, `center_panel`, `right_panel` with `cards`.
- `input_style`: `boxed` or `plain`.

Example: `assets/default-spec.json`.

## Swimlane (category bands)

Use 2-5 `lanes`, each with `title` and 1-5 `steps`. Give steps stable `id` values.

- Lane fields: `title`, optional `subtitle` (small text under the title, e.g. "Triggered by: user prompt"; keep it under ~60 chars), optional `accent` (`green` or `purple`) to override the alternating band tint.
- Each lane renders as a tinted band with a darker title column on the left; bands alternate sage-green / periwinkle tints automatically.
- `connections` contain `from`, `to`, `label`, `style`, `accent`, and use automatic orthogonal anchors. An in-lane connection that runs right-to-left (a loop back) automatically drops into a dashed channel under the cards; the lane grows to make room.

Example: `assets/examples/swimlane-spec.json` (the "four types of agent loops" reference diagram, `paper` style). Icon-catalog variants: `assets/examples/loop-icon-pack-spec.json`, `assets/examples/illustrated-icon-catalog-spec.json`.

## Graph (free-form workflow)

Use when no fixed template fits: declare the workflow as nodes + edges and let the engine lay it out. Every workflow gets its own loop structure instead of one hardcoded retry lane.

```json
{
  "layout": "graph",
  "direction": "right",
  "nodes": [
    {"id": "plan", "label": "Plan", "icon": "plan"},
    {"id": "act", "label": "Act", "icon": "agent", "body": "tool calls"},
    {"id": "gate", "label": "Pass?", "kind": "decision"},
    {"id": "ship", "label": "Ship", "kind": "terminal"}
  ],
  "edges": [
    {"from": "plan", "to": "act"},
    {"from": "act", "to": "gate"},
    {"from": "gate", "to": "ship", "label": "yes"},
    {"from": "gate", "to": "plan", "kind": "loop", "label": "replan"}
  ]
}
```

- `nodes`: 2-24 items. Each has a unique `id`, `label`, optional `body`, `icon` (any icon key), `kind` (`card` default, `decision` diamond, `terminal` pill), `accent` (THEME key: `green`, `purple`, `amber`, `pink`, `cyan`, `core_stroke`, `white`, `muted`), and optional `x`/`y` (box center) to pin a node manually; omit both for auto layout.
- `edges`: up to 40 items with `from`/`to` node ids, optional `label`, `accent`, `style`, and `kind`:
  - `flow` (default): forward step. Auto layout assigns layers by longest path, orders rows by barycenter, and phase-orders the beams by topological depth, so forks diverge and joins converge visibly.
  - `loop`: dashed return channel routed through its own lane below the grid (right of it when `direction: "down"`), fired after the forward wave completes. Multiple loops get separate lanes, colors, and phases. Cycles declared as plain `flow` edges are detected automatically and treated as loops.
- `direction`: `right` (default) or `down`.
- Long rightward graphs with more than 7 sequential layers auto-stack downward unless nodes have manual coordinates. This prevents clipped side content and top-heavy empty lower halves.
- Bodies show on wide cards; when many layers squeeze cards below ~150 px the card switches to icon-over-label and hides `body`.

Example: `assets/examples/graph-workflow-spec.json` (preview: `assets/previews/layout-graph.png`).

## Animation

- `flow`: continuous beams and module pulses.
- `draw`: shape reveal and text build-up; at least 72 frames.
- `relay`: one edge at a time; at least 88 frames.
- `trace`: request-path narrative timing; at least 88 frames.
- `chapter`: staged build-up; at least 96 frames.
- `failure-recovery`: longer retry/failure narrative; at least 96 frames.

The Pillow renderer always uses classic flow.

## Icons

Stable core keys: `folder`, `file`, `scan`, `shield`, `db`, `hash`, `package`, `message`, `event`, `api`, `clock`, `brain`, `gear`, `eye`, `terminal`, `globe`, `video`, `snapshot`, `server`, `lock`, `check`, `clipboard`.

Semantic aliases include cloud/data/AI/security/business/state vocabulary such as `cloud`, `cluster`, `container`, `queue`, `cache`, `vector-db`, `agent`, `model`, `rag`, `tool-call`, `guardrail`, `evaluation`, `identity`, `audit`, `user`, `success`, `failure`, and `retry`, plus the loop-workflow pack: `loop`, `iterate`, `plan`, `decision`, `condition`, `split`, `parallel`, `merge`, `handoff`, `delegate`, `subagent`, `worker`, `orchestrator`, `dispatch`, `human`, `review`, `approval`, `checkpoint`, `milestone`, `rollback`, `sandbox`, `experiment`, `compare`, `benchmark`, `score`, `grade`, `error`, `exception`, `wait`, `timeout`, `emit`, `broadcast`, `webhook`, `ingest`, and `receive`.

Use `icon_file` for a local SVG/PNG. Relative paths resolve against the spec. Custom SVG must be trusted local content.

### Illustrated and hero icons

```json
{
  "title": "Think",
  "icon": "brain",
  "icon_style": "hero",
  "icon_size": "hero",
  "icon_motion": "auto"
}
```

`icon_style` values:

- `outline`: bundled line icon, best for dense diagrams.
- `illustrated`: plate-free duotone illustration — theme-ink hand-drawn strokes plus one semantic accent on the moving part.
- `hero`: enlarged illustrated object for the primary concepts.

`icon_motion` values:

- `auto` (default): the icon plays the job story bound to its semantic key — a synapse signal for `brain`, a one-pitch gear turn for `act`, a chip drop for `memory`, a shackle click for `lock`, and so on (full table in `references/illustrated-icons.md`). Stories loop seamlessly and are phase-staggered per icon.
- `none`: freeze at the rest pose.
- Legacy values (`think-pulse`, `gear-spin`, `eye-scan`, `memory-write`, `shield-check`, `scope-scan`, `budget-gauge`, `trigger-ping`, `tool-spark`, `output-pop`) remain valid and behave like `auto`.

The browser output keeps the illustration as SVG. Pillow produces a simplified raster counterpart. Excalidraw remains editable through a local placeholder rather than embedding opaque files.

Complete example: `assets/examples/illustrated-loop-spec.json`.

## Copy and quality

- Highlight: ideally ≤16 characters.
- Card titles: 1-3 words.
- Bodies: preferably two short lines.
- Keep signatures below about 28 characters.
- Avoid relying on emergency font shrinking.
- `--formats` is exact; supported values are `gif`, `mp4`, `png`, `excalidraw`, `svg`, `html`.
- Use `--check`; then inspect the PNG for overlap, crossing lines, clipping, weak contrast, and mobile readability.
