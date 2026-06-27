# Animated Excalidraw GIF Spec Format

Use this reference when creating or editing a spec for `scripts/render_animated_diagram.py`.

## Style

An optional top-level `style` field selects the palette. The layout, animation,
and icons are identical across styles; only colors (and the finish for light
styles) change.

```json
{
  "style": "candy"
}
```

Available styles:

- `default`: dark hand-drawn neon on pure black (brand default).
- `blueprint`: deep navy monochrome, technical blueprint feel.
- `terminal`: near-black canvas with phosphor-green CRT tones.
- `candy`: fresh, cute pastel on a light paper canvas (uses a clean light finish
  with no grain or vignette).

The CLI flag `--style` overrides the spec field. If neither is set, `default` is
used. Light styles automatically switch to a clean finish (no grain/vignette).

## Layout Model

The renderer is optimized for a premium dark hand-drawn architecture/process diagram:

1. Top title: `title.prefix` plus highlighted `title.highlight`
2. Top input box: four compact input sources
3. Middle core: three major process cards, a decision diamond, and an output card
4. Bottom left panel: source/context cards
5. Bottom center panel: internal storage or processing layers
6. Bottom right panel: final package/output cards
7. Top right brand slot: dotted mark plus `signature`

Keep the copy short. The renderer uses fixed art-directed positions and applies
basic text fitting in compact regions, but short labels still produce the best
visual hierarchy.

## Recommended Copy Length

- `title.prefix`: 2 to 4 words
- `title.highlight`: 1 to 3 words
- Input labels: 1 word
- Core card title: 1 to 2 words
- Core card body: 2 lines, each under 22 characters
- Panel card title: 1 to 3 words
- Panel card body: 1 to 2 short lines
- Signature: short handle, such as `@archscribe`

## Text Fitting

The renderer automatically fits text in compact labels and cards by wrapping
lines and reducing font size. When a label is still too tight, it may use a
smaller emergency size to preserve the full text. This is intended as a safety
net for labels, not as a replacement for concise copy.

Text fitting is applied to:

- Input labels
- Core card titles and bodies
- Decision diamond text
- Bottom panel cards
- Output and package labels

Manual line breaks in the spec are preserved. English text wraps on spaces,
while CJK text can wrap between characters when needed.

## Icons

Supported icon keys:

- `folder`
- `file`
- `scan`
- `shield`
- `db`
- `hash`
- `package`
- `message`
- `event`
- `api`
- `clock`
- `brain`
- `gear`
- `eye`
- `terminal`
- `globe`
- `video`
- `snapshot`
- `server`
- `lock`
- `check`
- `clipboard`

Icons are rendered from a bundled local Tabler SVG subset (MIT). Avoid remote icon
libraries by default; add audited local SVG assets when the diagram needs new
semantics.

Two icon engines render these SVGs (select with `--icon-engine`):

- `browser`: headless Chromium renders the SVGs and animates each stroke with a
  looping energy sweep. Crisp, professional, uniformly sized. Needs Playwright +
  Chromium (`requirements-browser.txt`).
- `pillow`: pure-Python rasterization, no browser, fully portable.
- `auto` (default): browser when available, else pillow.

All icons use a single tile size so the diagram looks consistent. Keep motion
restrained: the stroke sweep plus path dots are enough; do not pile on glows.

## Quality Bar

The output should include:

- `.png` static preview
- `.gif` animated version
- `.excalidraw` editable source

Verify:

- GIF dimensions match the requested canvas
- GIF has the requested frame count and FPS
- Frame-diff shows real motion
- Excalidraw JSON has unique IDs
- All text elements use `fontFamily: 5`
- `files` is empty unless the user explicitly wants embedded images

## Common Command

```bash
python scripts/render_animated_diagram.py \
  --spec assets/default-spec.json \
  --outdir /tmp/diagram-output \
  --basename memory-pack \
  --verify
```
