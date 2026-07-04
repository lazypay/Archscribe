# Animated Excalidraw GIF Spec Format

Use this reference when creating or editing a spec for `scripts/render_animated_diagram.py`.

## Top-Level Shape

```json
{
  "layout": "panorama | pipeline | layers",
  "style": "default | blueprint | terminal | candy",
  "animation": "flow | draw | relay",
  "title": { "prefix": "...", "highlight": "...", "subtitle": "..." },
  "signature": "@handle",
  "canvas": { "frames": 41, "fps": 20 },
  "...layout-specific fields..."
}
```

Everything except the layout-specific content is optional and defaults
sensibly. `canvas.width/height` may override the computed size but normally
should be omitted: each layout computes its own height from content.

Validate cheaply before rendering:

```bash
python scripts/render_animated_diagram.py --spec spec.json --outdir out --validate-only
```

Errors block rendering and carry `path` / `message` / `fix`; warnings flag
likely mistakes (unknown keys or icons, overlong labels).

## Layout: panorama (default)

The classic full-system view. Example: `assets/default-spec.json`.

1. Top title: `title.prefix` plus highlighted `title.highlight`
2. Top input box: `input_title` + `inputs` (2-6 compact sources, auto-spaced).
   `input_style: "plain"` drops each icon's framed tile: frameless glyphs
   stroked in the item's accent `color` (default `"boxed"`).
3. Middle core: `core.title/subtitle` + `core.cards` (2-4 stage cards,
   auto-sized), a `decision` diamond (`title`, `body`, optional `yes_label`,
   default "Yes"), an `output` card, `loop_label`, `retry_label`
4. Bottom `left_panel`: source/context cards (up to 3; `title`, `badge`,
   `cards`). The two vertical arrows to the core are labelled with
   `down_label` (default "Read") and `up_label` (default "Context").
   `badge_file` replaces the `badge` text with a local logo image
   (SVG/PNG, fitted to the header's badge slot).
5. Bottom `center_panel`: internal layers (up to 4 cards; `title`, `subtitle`,
   `footer`)
6. Bottom `right_panel`: packaged outputs (up to 3 cards; `title`,
   `incoming_label`, `return_label`)
7. Top right brand slot: dotted mark plus `signature`. Long signatures
   (for example `DailyDoseofDS.com`) shift left automatically and stretch
   the hand-drawn underline, so nothing clips at the canvas edge.

Elastic behavior:

- `inputs` and `core.cards` counts move/resize automatically; 4 inputs and
  3 cards reproduce the canonical hand-tuned look.
- A bottom panel is rendered only when it has a non-empty `cards` list.
  Present panels re-center; omit all three and the canvas shrinks to a
  compact top-half diagram (height 704 instead of 1138).

Card fields everywhere: `{"title": ..., "body": ..., "icon": ...}`
(inputs use `label` instead of `title`/`body`).

## Layout: pipeline

A linear left-to-right process. Example: `assets/examples/pipeline-spec.json`.

```json
{
  "layout": "pipeline",
  "subtitle": "one line under the title, optional",
  "stages": [
    { "title": "Build", "body": "compile + unit\ntests", "icon": "settings",
      "note": "optional dashed note under the stage" }
  ],
  "decision": { "title": "Green?", "body": "all gates", "yes_label": "Yes",
                 "no_label": "No / fix and push again" },
  "output": { "label": "Release", "icon": "package" },
  "footer": "one line at the bottom, optional"
}
```

- `stages`: required, 2-6. Each gets a numbered badge, icon, title, body.
  Stage accent colors cycle automatically (`accent` may pin a THEME key).
- `decision` optional: appended after the last stage. `no_label: "..."`
  additionally draws a dashed retry loop back to stage 1 (set it to omit).
- `output` optional: final card; connects from the decision (labelled with
  `yes_label`) or from the last stage.
- `note` per stage: dashed annotation card below (adds canvas height).
- 5-6 stages plus decision plus output get cramped; drop notes or the
  decision when the row is that dense.

## Layout: layers

Stacked horizontal bands. Example: `assets/examples/layers-spec.json`.

```json
{
  "layout": "layers",
  "subtitle": "one line under the title, optional",
  "layers": [
    { "title": "Gateway", "subtitle": "auth, quota,\nrouting",
      "connection_label": "gRPC",
      "items": [ { "label": "Router", "icon": "api" } ] }
  ]
}
```

- `layers`: required, 2-5, drawn top to bottom. Band colors cycle
  automatically (`accent` may pin a THEME key).
- `items`: 0-5 mini-cards per band, auto-sized.
- `connection_label`: text on the arrows to the NEXT band (set on the upper
  band).
- Canvas height grows with the layer count.

## Animation

Optional top-level `animation` field; the `--animation` CLI flag wins
(default `flow`):

- `flow`: eased energy beams along every arrow, arrival ripples, wave-order
  module breathing. Shortest loop, default.
- `draw`: whiteboard build-up; elements stroke-reveal in draw order, hold,
  loop. Frame count is raised to at least 72.
- `relay`: one edge at a time carries a beam across a dimmed canvas; visited
  edges stay faintly lit. Frame count is raised to at least 88.

All presets work on all three layouts. The pillow renderer ignores this field
and always uses the classic flow.

## Style

Optional top-level `style` field; the `--style` CLI flag wins:

- `default`: dark hand-drawn neon on pure black (brand default).
- `blueprint`: deep navy monochrome, technical blueprint feel.
- `terminal`: near-black canvas with phosphor-green CRT tones.
- `candy`: fresh pastel on a light paper canvas (clean finish, no
  grain/vignette).

Layout, animation, and icons are identical across styles; only colors change.

## Recommended Copy Length

- `title.prefix`: 2 to 4 words
- `title.highlight`: 1 to 3 words (≤ 16 chars)
- Input labels / item labels: 1 word
- Core/stage card title: 1 to 2 words
- Card body: 2 lines, each under 22 characters
- Signature: short handle such as `@archscribe`; longer domains
  (e.g. `DailyDoseofDS.com`) auto-fit up to ~28 chars

## Text Fitting

The renderer automatically fits text in compact labels and cards by wrapping
lines and reducing font size, with a smaller emergency size as a last resort.
It is a safety net, not a replacement for concise copy. Manual line breaks
are preserved. English wraps on spaces; CJK can wrap between characters.

## Icons

Supported icon keys:

`folder`, `file`, `scan`, `shield`, `db`, `hash`, `package`, `message`,
`event`, `api`, `clock`, `brain`, `gear`, `eye`, `terminal`, `globe`,
`video`, `snapshot`, `server`, `lock`, `check`, `clipboard`

Icons come from a bundled local Tabler SVG subset (MIT). Unknown keys warn at
validation time and render as a plain circle. With the browser renderer the
SVGs are inlined and animated with a looping stroke sweep; the pillow
fallback rasterizes the same SVGs locally (`--icon-engine` tunes only that
path). In the `flow` preset every icon also gets a subtle wave-ordered
scale "pop" that travels through the diagram.

### Custom icons and logos (`icon_file`)

Any item that accepts `icon` also accepts `icon_file`: a local `.svg` or
`.png` drawn inside the tile with its **original colors** (brand logos,
colorful product icons). Relative paths resolve against the spec file's
folder; `icon_file` wins over `icon`.

```json
{ "title": "Long-Term Memory", "icon_file": "assets/zep-logo.png" }
```

- Validation errors if the file is missing or not `.svg`/`.png`.
- Browser renderer embeds the file as-is (full color, aspect kept).
  The pillow fallback pastes PNGs directly; SVG files are traced as white
  outlines there, so prefer PNG when you must support the pillow path.
- Custom icons skip the Tabler stroke-sweep (they keep their own colors)
  but still join the flow "pop" wave.

## Quality Bar

Default outputs (browser renderer): `.png`, `.gif`, `.mp4`, `.excalidraw`.
Optional: `.svg` (standalone vector, fonts embedded) and `.html`
(interactive: hotspot per graph node, click-to-highlight, BFS trace toggle).
Select with `--formats`.

Verify (all automated by `--check`):

- GIF/PNG dimensions match the layout's computed canvas
- GIF has the expected frame count and FPS (presets may raise frames)
- Frame-diff shows real motion
- MP4 stream is yuv420p at canvas size (when produced)
- SVG embeds the bundled fonts (when produced)
- HTML contains one hotspot per graph node and the embedded graph (when produced)
- Excalidraw JSON has unique IDs, `fontFamily: 5`, empty `files`

## Common Command

```bash
python scripts/render_animated_diagram.py \
  --spec assets/default-spec.json \
  --outdir /tmp/diagram-output \
  --basename memory-pack \
  --animation flow \
  --verify \
  --check
```
