# Archscribe

Archscribe is a Codex skill and local renderer for premium hand-drawn architecture and process diagrams. It produces PNG, GIF, MP4, SVG, editable Excalidraw, and interactive HTML.

## Capabilities

- Layouts: `panorama`, `pipeline`, `layers`, `hub`, `swimlane`, `sequence`, `graph` (free-form nodes/edges, auto DAG layout, per-workflow loop lanes)
- Styles: `default`, `blueprint`, `terminal`, `candy`, `chalkboard`, `editorial`, `cyber-grid`
- Animation: `flow`, `draw`, `relay`, `trace`, `chapter`, `failure-recovery`
- Browser and Pillow renderers
- Structured spec validation, exact output selection, and output contract checks
- Bundled fonts, icons, and rough.js; Chromium and ffmpeg are optional runtime dependencies
- Three icon levels (`outline`, `illustrated`, `hero`) with deterministic semantic micro-motion

## Quick start

```bash
python scripts/render_animated_diagram.py --spec assets/default-spec.json --outdir outputs --basename diagram --formats png --check
```

See `assets/examples/` for every layout and `references/spec-format.md` for the complete spec.

See `assets/examples/illustrated-loop-spec.json` for the high-fidelity semantic illustration workflow.

## Test

```bash
python -m pytest -q
```
