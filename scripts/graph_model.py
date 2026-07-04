#!/usr/bin/env python3
"""Layout planning + graph model for Archscribe diagrams.

Single source of truth for diagram geometry. For each layout preset a
``plan_<layout>(spec)`` function turns spec content into a *plan*:

- element geometry (boxes, slots, computed canvas height),
- animation data (``flow_paths`` polylines + ``pulse_targets``, colors as
  THEME keys),
- icon instances (for the pillow icon-motion layer),
- interaction graph (``nodes`` / ``edges`` for the interactive HTML).

Consumers:

- ``render_animated_diagram`` draws the Pillow raster + records the op
  stream from a plan,
- ``svg_renderer`` animates ``flow_paths`` / ``pulse_targets`` in Chromium,
- the interactive HTML uses ``nodes`` / ``edges`` for hotspots and
  adjacency highlighting.

The module is stdlib-only. Coordinates are calibrated so that the classic
default spec (4 inputs / 3 cards / 3 panels) reproduces the original
hand-tuned panorama exactly; tests assert this.
"""
from __future__ import annotations

LAYOUTS = ("panorama", "pipeline", "layers")

# ---------------------------------------------------------------------------
# Legacy panorama constants (canonical art direction at default counts)
# ---------------------------------------------------------------------------

CANVAS_W = 1210
CANVAS_H = 1138

INPUT_Y = 174
CORE_Y = 366
CORE_CARD_H = 90
DECISION_BOX = (706, 508, 120, 120)
OUTPUT_BOX = (1022, 527, 100, 94)

LEFT_CARD_SLOTS = [(797, 78), (892, 78), (987, 62)]  # (y, h) inside left panel
LAYER_Y = 827
LAYER_CARD_W = 112
LAYER_CARD_H = 142
PACK_YS = [786, 884, 982]
PACK_H = 84

PANEL_WIDTHS = {"left_panel": 281, "center_panel": 522, "right_panel": 258}
LEGACY_PANEL_X = {"left_panel": 39, "center_panel": 333, "right_panel": 904}
PANEL_Y = {"left_panel": 735, "center_panel": 734, "right_panel": 735}
PANEL_H = {"left_panel": 344, "center_panel": 346, "right_panel": 344}


def _node(node_id, kind, x, y, w, h, label="", icon=None, group=None):
    node = {"id": node_id, "kind": kind, "x": round(x), "y": round(y), "w": round(w), "h": round(h), "label": label}
    if icon:
        node["icon"] = icon
    if group:
        node["group"] = group
    return node


def _icon(kind, x, y, color, group, ordinal, scale=1.0):
    return {"kind": kind, "x": x, "y": y, "scale": scale, "color": color, "group": group, "ordinal": ordinal}


def get_layout(spec):
    return (spec or {}).get("layout", "panorama")


def build_plan(spec):
    layout = get_layout(spec)
    if layout == "pipeline":
        return plan_pipeline(spec)
    if layout == "layers":
        return plan_layers(spec)
    return plan_panorama(spec)


def build_graph(spec):
    """Interaction graph (canvas + nodes + edges) for any layout."""
    plan = build_plan(spec)
    return {"canvas": plan["canvas"], "nodes": plan["nodes"], "edges": plan["edges"]}


def adjacency(graph):
    """node id -> set of directly connected node ids (undirected view)."""
    neighbors = {n["id"]: set() for n in graph["nodes"]}
    for edge in graph["edges"]:
        neighbors[edge["from"]].add(edge["to"])
        neighbors[edge["to"]].add(edge["from"])
    return neighbors


# ---------------------------------------------------------------------------
# Panorama (elastic: 2-6 inputs, 2-4 core cards, panels optional)
# ---------------------------------------------------------------------------

CORE_CARD_WIDTHS = {2: 300, 3: 260, 4: 230}


def plan_panorama(spec):
    spec = spec or {}
    nodes, edges, flow, pulses, icons = [], [], [], [], []

    inputs = list(spec.get("inputs", []))
    if not inputs:
        inputs = [{"label": "", "icon": "file"} for _ in range(4)]
    inputs = inputs[:6]
    n_in = len(inputs)

    cards = list(spec.get("core", {}).get("cards", []))
    if not cards:
        cards = [{"title": "", "body": "", "icon": "file"} for _ in range(3)]
    cards = cards[:4]
    if len(cards) < 2:
        cards.append({"title": "", "body": "", "icon": "file"})
    n_cards = len(cards)

    has_left = bool(spec.get("left_panel", {}).get("cards"))
    has_center = bool(spec.get("center_panel", {}).get("cards"))
    has_right = bool(spec.get("right_panel", {}).get("cards"))
    any_panel = has_left or has_center or has_right

    # --- input strip -----------------------------------------------------
    if n_in == 4:
        input_xs = [423, 532, 640, 748]  # legacy hand-tuned positions
    else:
        pitch = 108.34
        span = (n_in - 1) * pitch + 78
        first = 624.5 - span / 2
        input_xs = [round(first + i * pitch) for i in range(n_in)]
    box_x = input_xs[0] - 34
    box_w = (input_xs[-1] + 71) - box_x
    input_box = (box_x, 130, box_w, 128)
    arrow_cx = box_x + box_w // 2 + 1

    nodes.append(_node("inputs", "group", *input_box, label=spec.get("input_title", "Source / Input")))
    for i, (x, item) in enumerate(zip(input_xs, inputs)):
        nodes.append(_node(f"input.{i}", "input", x - 5, INPUT_Y, 78, 76,
                           label=item.get("label", ""), icon=item.get("icon", "file"), group="inputs"))
        icons.append(_icon(item.get("icon", "file"), x + 9, INPUT_Y, item.get("color"), "input", i))

    # --- core band ---------------------------------------------------------
    card_w = CORE_CARD_WIDTHS[min(4, max(2, n_cards))]
    if n_cards == 1:
        card_xs = [472]
    else:
        left0, right0 = 95, 1110 - card_w
        card_xs = [round(left0 + (right0 - left0) * i / (n_cards - 1)) for i in range(n_cards)]

    core_group = (53, 317, 1104, 320)
    nodes.append(_node("core", "group", *core_group, label=spec.get("core", {}).get("title", "Archive Core")))
    for i, (x, card) in enumerate(zip(card_xs, cards)):
        nodes.append(_node(f"core.{i}", "card", x, CORE_Y, card_w, CORE_CARD_H,
                           label=card.get("title", ""), icon=card.get("icon", "file"), group="core"))
        icons.append(_icon(card.get("icon", "file"), x + 14, CORE_Y + 13, card.get("color"), "core", 4 + i))

    nodes.append(_node("decision", "decision", *DECISION_BOX, label=spec.get("decision", {}).get("title", "Ready?")))
    output = spec.get("output", {})
    nodes.append(_node("output", "output", *OUTPUT_BOX, label=output.get("label", "Report"), icon=output.get("icon", "file")))
    icons.append(_icon(output.get("icon", "file"), 1035, 537, output.get("color"), "output", 7))

    # --- edges + flow for the top half --------------------------------------
    def add_edge(eid, src, dst, points, color, offset, label=None, style="solid", draw_arrow=True):
        edges.append({"id": eid, "from": src, "to": dst, "points": [tuple(p) for p in points],
                      "color": color, "label": label, "style": style})
        flow.append({"points": [list(p) for p in points], "color": color, "offset": round(offset, 4)})
        return draw_arrow

    add_edge("e.inputs_core", "inputs", "core.0", [(arrow_cx, 239), (arrow_cx, 316)], "green", 0.0)
    for i in range(n_cards - 1):
        pts = [(card_xs[i] + card_w, 411), (card_xs[i + 1], 411)]
        add_edge(f"e.core{i}_core{i+1}", f"core.{i}", f"core.{i+1}", pts, "cyan", 0.10 + 0.14 * i)

    last_cx = card_xs[-1] + card_w // 2 + 2
    first_loop_x = card_xs[0] + card_w // 2 - 3
    add_edge("e.core_last_decision", f"core.{n_cards-1}", "decision",
             [(last_cx, 456), (last_cx, 481), (768, 481), (768, 508)], "core_stroke", 0.38)
    add_edge("e.decision_output", "decision", "output", [(826, 568), (1022, 568)], "green", 0.54,
             label=(spec.get("decision") or {}).get("yes_label", "Yes"))
    add_edge("e.decision_core0", "decision", "core.0",
             [(707, 568), (510, 568), (first_loop_x, 568), (first_loop_x, 456)], "purple", 0.66,
             label=spec.get("retry_label", "No / missing source or conflict"), style="dashed")

    # --- bottom panels -------------------------------------------------------
    present = [name for name, flag in
               [("left_panel", has_left), ("center_panel", has_center), ("right_panel", has_right)] if flag]
    if present == ["left_panel", "center_panel", "right_panel"]:
        panel_x = dict(LEGACY_PANEL_X)
    else:
        total = sum(PANEL_WIDTHS[p] for p in present) + 24 * (len(present) - 1) if present else 0
        start = 39 + (1123 - total) // 2 if present else 0
        panel_x = {}
        for p in present:
            panel_x[p] = start
            start += PANEL_WIDTHS[p] + 24

    panel_boxes = {}
    for p in present:
        panel_boxes[p] = (panel_x[p], PANEL_Y[p], PANEL_WIDTHS[p], PANEL_H[p])
        title_key = {"left_panel": "title", "center_panel": "title", "right_panel": "title"}[p]
        nodes.append(_node(p, "group", *panel_boxes[p], label=spec.get(p, {}).get(title_key, "")))

    if has_left:
        lx = panel_x["left_panel"]
        for i, ((y, h), card) in enumerate(zip(LEFT_CARD_SLOTS, spec.get("left_panel", {}).get("cards", [])[:3])):
            nodes.append(_node(f"left.{i}", "panel-card", lx + 12, y, 258, h,
                               label=card.get("title", ""), icon=card.get("icon", "file"), group="left_panel"))
            icons.append(_icon(card.get("icon", "file"), lx + 22, y + 10, card.get("color"), "panel", 8 + i))
        left_spec = spec.get("left_panel", {})
        add_edge("e.core_left", "core", "left_panel", [(lx + 117, 637), (lx + 117, 736)], "green", 0.18,
                 label=left_spec.get("down_label", "Read"))
        add_edge("e.left_core", "left_panel", "core", [(lx + 166, 736), (lx + 166, 637)], "green", 0.58,
                 label=left_spec.get("up_label", "Context"))

    layer_xs = []
    if has_center:
        cx0 = panel_x["center_panel"]
        layer_cards = list(spec.get("center_panel", {}).get("cards", []))[:4]
        k = max(2, len(layer_cards))
        while len(layer_cards) < k:
            layer_cards.append({"title": "", "body": "", "icon": "file"})
        pitch_layers = 140
        span_layers = (k - 1) * pitch_layers + LAYER_CARD_W
        # +13 reproduces the legacy hand-tuned x=346 at the canonical 4 cards.
        first = cx0 + 13 if k == 4 else cx0 + (PANEL_WIDTHS["center_panel"] - span_layers) // 2
        layer_xs = [first + i * pitch_layers for i in range(k)]
        chain_pts = []
        for i, (x, card) in enumerate(zip(layer_xs, layer_cards)):
            nodes.append(_node(f"layer.{i}", "panel-card", x, LAYER_Y, LAYER_CARD_W, LAYER_CARD_H,
                               label=card.get("title", ""), icon=card.get("icon", "file"), group="center_panel"))
            icons.append(_icon(card.get("icon", "file"), x + 18, 840, card.get("color"), "layer", 11 + i))
            if i:
                pts = [(layer_xs[i - 1] + LAYER_CARD_W, 890), (x, 890)]
                edges.append({"id": f"e.layer{i-1}_layer{i}", "from": f"layer.{i-1}", "to": f"layer.{i}",
                              "points": [tuple(p) for p in pts], "color": "purple", "label": None, "style": "solid"})
                chain_pts.extend(pts)
        if chain_pts:
            flow.append({"points": [list(p) for p in chain_pts], "color": "purple", "offset": 0.32})

    if has_center and has_right:
        rx = panel_x["right_panel"]
        c_right = panel_x["center_panel"] + PANEL_WIDTHS["center_panel"]
        add_edge("e.center_right", "center_panel", "right_panel", [(c_right, 890), (rx, 890)], "white", 0.46,
                 label=spec.get("right_panel", {}).get("incoming_label", "Compile"))
    if has_right:
        rx = panel_x["right_panel"]
        for i, (y, card) in enumerate(zip(PACK_YS, spec.get("right_panel", {}).get("cards", [])[:3])):
            nodes.append(_node(f"pack.{i}", "panel-card", rx + 14, y, 228, PACK_H,
                               label=card.get("title", ""), icon=card.get("icon", "file"), group="right_panel"))
            icons.append(_icon(card.get("icon", "file"), rx + 26, y + 10, card.get("color"), "pack", 15 + i))
        add_edge("e.right_decision", "right_panel", "decision",
                 [(rx + 132, 735), (rx + 132, 691), (766, 691), (766, 628)], "amber", 0.72,
                 label=spec.get("right_panel", {}).get("return_label", "Reusable"))

    # --- canvas + chrome -----------------------------------------------------
    height = CANVAS_H if any_panel else 704
    frame = (18, 117, 1174, height - 144)

    pulses.append({"box": [input_box[0], 138, input_box[0] + input_box[2], 239], "color": "green"})
    for i, x in enumerate(card_xs):
        pulses.append({"box": [x, CORE_Y, x + card_w, CORE_Y + CORE_CARD_H], "color": "green" if i % 2 else "core_stroke"})
    pulses.append({"box": [706, 508, 826, 628], "color": "green"})
    if has_center:
        b = panel_boxes["center_panel"]
        pulses.append({"box": [b[0], b[1], b[0] + b[2], b[1] + b[3]], "color": "purple"})
    if has_right:
        b = panel_boxes["right_panel"]
        pulses.append({"box": [b[0], b[1], b[0] + b[2], b[1] + b[3]], "color": "green"})

    def _glow(box, color, width, light=None):
        return {"box": list(box), "color": color, "light": light or color, "width": width}

    glow = [_glow([18, 117, 1192, height - 27], "frame", 3),
            _glow([53, 317, 1157, 637], "core_stroke", 3)]
    if has_center:
        b = panel_boxes["center_panel"]
        glow.append(_glow([b[0], b[1], b[0] + b[2], b[1] + b[3]], "purple", 3))
    if has_left:
        b = panel_boxes["left_panel"]
        glow.append(_glow([b[0], b[1], b[0] + b[2], b[1] + b[3]], "green", 3))
    if has_right:
        b = panel_boxes["right_panel"]
        glow.append(_glow([b[0], b[1], b[0] + b[2], b[1] + b[3]], "green", 3, light="pink"))
    glow.append(_glow([600, 27, 992, 99], "green", 2, light="pink"))

    return {
        "layout": "panorama",
        "canvas": {"width": spec.get("canvas", {}).get("width", CANVAS_W), "height": height},
        "frame": frame,
        "inputs": {"box": input_box, "xs": input_xs, "items": inputs, "arrow_cx": arrow_cx},
        "core": {"group": core_group, "xs": card_xs, "w": card_w, "cards": cards,
                 "last_cx": last_cx, "first_loop_x": first_loop_x},
        "panels": {"present": present, "x": panel_x, "boxes": panel_boxes, "layer_xs": layer_xs},
        "glow_rects": glow,
        "flow_paths": flow,
        "pulse_targets": pulses,
        "icons": icons,
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Pipeline (2-6 stages, optional decision + output, optional per-stage notes)
# ---------------------------------------------------------------------------

PIPELINE_STROKES = ["core_stroke", "green", "purple", "amber", "pink", "cyan"]
PIPELINE_FILLS = {"core_stroke": "blue_fill", "green": "green_fill", "purple": "purple_fill",
                  "amber": "icon_fill", "pink": "icon_fill", "cyan": "blue_fill"}


def plan_pipeline(spec):
    spec = spec or {}
    nodes, edges, flow, pulses, icons = [], [], [], [], []

    # Copy stage dicts: the plan annotates them (_stroke/_fill) and must not
    # mutate the caller's spec.
    stages = [dict(s) for s in spec.get("stages", [])][:6]
    while len(stages) < 2:
        stages.append({"title": "", "body": "", "icon": "file"})
    n = len(stages)
    decision = spec.get("decision")
    output = spec.get("output")
    has_notes = any(s.get("note") for s in stages)

    # The row gets denser as more elements share it; shrink gaps and the
    # decision/output footprint before shrinking the stage cards.
    total_units = n + (1 if decision else 0) + (1 if output else 0)
    gap = 56 if total_units <= 5 else 40 if total_units <= 6 else 32
    dec_w = 120 if total_units <= 6 else 104
    out_w = 110 if total_units <= 6 else 96
    left, right = 70, 1140
    extra_w = (dec_w + gap if decision else 0) + (out_w + gap if output else 0)
    stage_w = int(min(300, max(100, (right - left - extra_w - (n - 1) * gap) / n)))
    card_h = 160
    card_y = 240

    xs = []
    x = left + (right - left - (n * stage_w + (n - 1) * gap + extra_w)) // 2
    for _ in range(n):
        xs.append(x)
        x += stage_w + gap
    dec_x = x if decision else None
    if decision:
        x += dec_w + gap
    out_x = x if output else None

    mid_y = card_y + card_h // 2
    for i, (sx, stage) in enumerate(zip(xs, stages)):
        color = stage.get("accent") or PIPELINE_STROKES[i % len(PIPELINE_STROKES)]
        stage["_stroke"] = color
        stage["_fill"] = PIPELINE_FILLS.get(color, "blue_fill")
        nodes.append(_node(f"stage.{i}", "card", sx, card_y, stage_w, card_h,
                           label=stage.get("title", ""), icon=stage.get("icon", "file"), group="stages"))
        icons.append(_icon(stage.get("icon", "file"), sx + stage_w // 2 - 25, card_y + 16, stage.get("color"), "stage", i))
        if i:
            pts = [(xs[i - 1] + stage_w, mid_y), (sx, mid_y)]
            edges.append({"id": f"e.stage{i-1}_stage{i}", "from": f"stage.{i-1}", "to": f"stage.{i}",
                          "points": [tuple(p) for p in pts], "color": "white", "label": None, "style": "solid"})
            flow.append({"points": [list(p) for p in pts], "color": PIPELINE_STROKES[(i - 1) % len(PIPELINE_STROKES)], "offset": 0.10 * i})
        pulses.append({"box": [sx, card_y, sx + stage_w, card_y + card_h], "color": color})

    if decision:
        dec_box = (dec_x, mid_y - dec_w // 2, dec_w, dec_w)
        nodes.append(_node("decision", "decision", *dec_box, label=decision.get("title", "OK?")))
        pts = [(xs[-1] + stage_w, mid_y), (dec_x, mid_y)]
        edges.append({"id": "e.laststage_decision", "from": f"stage.{n-1}", "to": "decision",
                      "points": [tuple(p) for p in pts], "color": "white", "label": None, "style": "solid"})
        flow.append({"points": [list(p) for p in pts], "color": "green", "offset": round(0.10 * n, 4)})
        pulses.append({"box": [dec_box[0], dec_box[1], dec_box[0] + dec_w, dec_box[1] + dec_w], "color": "green"})
    if output:
        oy = mid_y - 47
        nodes.append(_node("output", "output", out_x, oy, out_w, 94,
                           label=output.get("label", "Out"), icon=output.get("icon", "file")))
        icons.append(_icon(output.get("icon", "file"), out_x + out_w // 2 - 25, oy + 10, output.get("color"), "output", 20))
        src_x = (dec_x + dec_w) if decision else (xs[-1] + stage_w)
        pts = [(src_x, mid_y), (out_x, mid_y)]
        edges.append({"id": "e.to_output", "from": "decision" if decision else f"stage.{n-1}", "to": "output",
                      "points": [tuple(p) for p in pts], "color": "green",
                      "label": decision.get("yes_label", "Yes") if decision else None, "style": "solid"})
        flow.append({"points": [list(p) for p in pts], "color": "green", "offset": round(0.10 * (n + 1), 4)})

    loop_y = card_y + card_h + (56 if not has_notes else 150)
    if decision and decision.get("no_label") is not None:
        dec_cx = dec_x + dec_w // 2
        if has_notes:
            # Note cards occupy the space under the stages: swing around the
            # left margin and enter the first stage from the side.
            lx = max(34, xs[0] - 24)
            pts = [(dec_cx, mid_y + dec_w // 2), (dec_cx, loop_y), (lx, loop_y), (lx, mid_y), (xs[0], mid_y)]
        else:
            first_cx = xs[0] + stage_w // 2
            pts = [(dec_cx, mid_y + dec_w // 2), (dec_cx, loop_y), (first_cx, loop_y), (first_cx, card_y + card_h)]
        edges.append({"id": "e.decision_loop", "from": "decision", "to": "stage.0",
                      "points": [tuple(p) for p in pts], "color": "muted",
                      "label": decision.get("no_label", "No"), "style": "dashed"})
        flow.append({"points": [list(p) for p in pts], "color": "purple", "offset": 0.62})

    note_y = card_y + card_h + 44
    if has_notes:
        for i, (sx, stage) in enumerate(zip(xs, stages)):
            if stage.get("note"):
                nodes.append(_node(f"note.{i}", "panel-card", sx + 8, note_y, stage_w - 16, 64,
                                   label="", group="stages"))

    bottom = loop_y + 40 if (decision and decision.get("no_label") is not None) else (
        note_y + 100 if has_notes else card_y + card_h + 80)
    height = max(560, bottom + 60)
    frame = (18, 117, 1174, height - 144)
    glow = [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3},
            {"box": [600, 27, 992, 99], "color": "green", "light": "pink", "width": 2}]

    return {
        "layout": "pipeline",
        "canvas": {"width": CANVAS_W, "height": height},
        "frame": frame,
        "stages": {"xs": xs, "w": stage_w, "y": card_y, "h": card_h, "items": stages,
                   "mid_y": mid_y, "note_y": note_y, "loop_y": loop_y},
        "decision_box": (dec_x, mid_y - dec_w // 2, dec_w, dec_w) if decision else None,
        "output_box": (out_x, mid_y - 47, out_w, 94) if output else None,
        "glow_rects": glow,
        "flow_paths": flow,
        "pulse_targets": pulses,
        "icons": icons,
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Layers (2-5 horizontal bands, 1-5 items each, vertical connections)
# ---------------------------------------------------------------------------

LAYER_STROKES = ["green", "core_stroke", "purple", "amber", "pink"]
LAYER_FILLS = {"green": "source_fill", "core_stroke": "core_fill", "purple": "archive_fill",
               "amber": "icon_fill", "pink": "icon_fill"}


def plan_layers(spec):
    spec = spec or {}
    nodes, edges, flow, pulses, icons = [], [], [], [], []

    layers = [dict(l) for l in spec.get("layers", [])][:5]
    while len(layers) < 2:
        layers.append({"title": "", "items": []})
    n = len(layers)

    band_x, band_w = 60, 1090
    band_h, gap = 158, 56
    top = 190

    ordinal = 0
    band_ys = []
    for i, layer in enumerate(layers):
        y = top + i * (band_h + gap)
        band_ys.append(y)
        color = layer.get("accent") or LAYER_STROKES[i % len(LAYER_STROKES)]
        layer["_stroke"] = color
        layer["_fill"] = LAYER_FILLS.get(color, "icon_fill")
        nodes.append(_node(f"band.{i}", "group", band_x, y, band_w, band_h, label=layer.get("title", "")))

        items = [dict(it) for it in layer.get("items", [])][:5]
        layer["items"] = items
        k = len(items)
        if k:
            zone_x, zone_w = band_x + 250, band_w - 274
            item_gap = 18
            item_w = int(min(190, (zone_w - (k - 1) * item_gap) / k))
            total = k * item_w + (k - 1) * item_gap
            ix = zone_x + (zone_w - total) // 2
            for j, item in enumerate(items):
                nodes.append(_node(f"item.{i}.{j}", "panel-card", ix, y + 32, item_w, 94,
                                   label=item.get("label", ""), icon=item.get("icon", "file"), group=f"band.{i}"))
                icons.append(_icon(item.get("icon", "file"), ix + 12, y + 42, item.get("color"), "layer-item", ordinal))
                item["_x"], item["_w"] = ix, item_w
                ordinal += 1
                ix += item_w + item_gap
        pulses.append({"box": [band_x, y, band_x + band_w, y + band_h], "color": color})

        if i:
            prev_y = band_ys[i - 1] + band_h
            for t, frac in enumerate((0.3, 0.5, 0.7)):
                ax = band_x + int(band_w * frac)
                pts = [(ax, prev_y), (ax, y)]
                if t == 1:
                    edges.append({"id": f"e.band{i-1}_band{i}", "from": f"band.{i-1}", "to": f"band.{i}",
                                  "points": [tuple(p) for p in pts], "color": "white", "label": None, "style": "solid"})
                flow.append({"points": [list(p) for p in pts], "color": LAYER_STROKES[(i - 1) % len(LAYER_STROKES)],
                             "offset": 0.14 * i + 0.05 * t})

    height = top + n * band_h + (n - 1) * gap + 90
    frame = (18, 117, 1174, height - 144)
    glow = [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3},
            {"box": [600, 27, 992, 99], "color": "green", "light": "pink", "width": 2}]
    for i, y in enumerate(band_ys):
        stroke = layers[i]["_stroke"]
        glow.append({"box": [band_x, y, band_x + band_w, y + band_h], "color": stroke, "light": stroke, "width": 3})

    return {
        "layout": "layers",
        "canvas": {"width": CANVAS_W, "height": height},
        "frame": frame,
        "bands": {"x": band_x, "w": band_w, "h": band_h, "ys": band_ys, "items": layers},
        "glow_rects": glow,
        "flow_paths": flow,
        "pulse_targets": pulses,
        "icons": icons,
        "nodes": nodes,
        "edges": edges,
    }
