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

LAYOUTS = ("panorama", "pipeline", "layers", "hub", "swimlane", "sequence", "graph")

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
    if layout == "hub":
        return plan_hub(spec)
    if layout == "swimlane":
        return plan_swimlane(spec)
    if layout == "sequence":
        return plan_sequence(spec)
    if layout == "graph":
        return plan_graph(spec)
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


# ---------------------------------------------------------------------------
# Hub (central platform with 3-8 surrounding capabilities)
# ---------------------------------------------------------------------------

def plan_hub(spec):
    import math
    spec = spec or {}
    center = dict(spec.get("center") or {"title": "Core", "body": "", "icon": "brain"})
    satellites = [dict(x) for x in spec.get("satellites", [])][:8]
    while len(satellites) < 3:
        satellites.append({"title": "", "body": "", "icon": "file"})
    width, height = 1210, 820
    cx, cy = 605, 455
    center_box = (cx - 130, cy - 82, 260, 164)
    nodes = [_node("hub", "card", *center_box, label=center.get("title", "Core"), icon=center.get("icon", "brain"))]
    icons = [_icon(center.get("icon", "brain"), cx - 25, cy - 55, center.get("color"), "hub", 0)]
    edges, flow, pulses, satellite_boxes = [], [], [], []
    rx, ry = 430, 220
    for i, item in enumerate(satellites):
        angle = -math.pi / 2 + 2 * math.pi * i / len(satellites)
        sx, sy = round(cx + rx * math.cos(angle)), round(cy + ry * math.sin(angle))
        box = (sx - 95, sy - 55, 190, 110)
        satellite_boxes.append(box)
        nodes.append(_node(f"satellite.{i}", "card", *box, label=item.get("title", ""), icon=item.get("icon", "file"), group="hub"))
        icons.append(_icon(item.get("icon", "file"), box[0] + 14, box[1] + 15, item.get("color"), "satellite", i + 1))
        start = (cx + round(130 * math.cos(angle)), cy + round(82 * math.sin(angle)))
        end = (sx - round(95 * math.cos(angle)), sy - round(55 * math.sin(angle)))
        pts = [start, end]
        edges.append({"id": f"e.hub_{i}", "from": "hub", "to": f"satellite.{i}", "points": pts,
                      "color": "green" if i % 2 == 0 else "purple", "label": item.get("connection_label"),
                      "style": item.get("line_style", "solid")})
        flow.append({"points": [list(p) for p in pts], "color": "green" if i % 2 == 0 else "purple", "offset": i / len(satellites)})
        pulses.append({"box": [box[0], box[1], box[0] + box[2], box[1] + box[3]], "color": "core_stroke"})
    pulses.append({"box": [center_box[0], center_box[1], center_box[0] + center_box[2], center_box[1] + center_box[3]], "color": "green"})
    return {"layout": "hub", "canvas": {"width": width, "height": height}, "frame": (18, 117, 1174, height - 144),
            "center": {"box": center_box, "item": center}, "satellites": {"boxes": satellite_boxes, "items": satellites},
            "glow_rects": [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3},
                           {"box": list(center_box), "color": "green", "light": "green", "width": 3}],
            "flow_paths": flow, "pulse_targets": pulses, "icons": icons, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Swimlane (2-5 owners, ordered steps)
# ---------------------------------------------------------------------------

def plan_swimlane(spec):
    spec = spec or {}
    lanes = [dict(x) for x in spec.get("lanes", [])][:5]
    while len(lanes) < 2:
        lanes.append({"title": "", "steps": []})
    width, lane_x, lane_w, lane_h, gap, top = 1210, 55, 1100, 122, 18, 190
    nodes, edges, flow, pulses, icons, ys = [], [], [], [], [], []
    step_nodes = {}
    ordinal = 0
    for i, lane in enumerate(lanes):
        y = top + i * (lane_h + gap); ys.append(y)
        nodes.append(_node(f"lane.{i}", "group", lane_x, y, lane_w, lane_h, label=lane.get("title", "")))
        steps = [dict(s) for s in lane.get("steps", [])][:5]; lane["steps"] = steps
        zone_x, zone_w = lane_x + 190, lane_w - 220
        count = max(1, len(steps)); card_w = min(170, int((zone_w - (count - 1) * 28) / count))
        total = count * card_w + (count - 1) * 28; x = zone_x + (zone_w - total) // 2
        for j, step in enumerate(steps):
            box = (x, y + 20, card_w, 82); step["_box"] = box
            node_id = step.get("id") or f"step.{i}.{j}"; step_nodes[node_id] = box
            nodes.append(_node(node_id, "card", *box, label=step.get("title", ""), icon=step.get("icon", "file"), group=f"lane.{i}"))
            icons.append(_icon(step.get("icon", "file"), x + 9, y + 35, step.get("color"), "swimlane", ordinal)); ordinal += 1
            pulses.append({"box": [x, y + 20, x + card_w, y + 102], "color": "green" if i % 2 == 0 else "purple"})
            x += card_w + 28
    connections = spec.get("connections") or []
    if not connections:
        ordered = [n["id"] for n in nodes if n["kind"] == "card"]
        connections = [{"from": a, "to": b} for a, b in zip(ordered, ordered[1:])]
    for i, edge in enumerate(connections):
        a, b = step_nodes.get(edge.get("from")), step_nodes.get(edge.get("to"))
        if not a or not b: continue
        ac = (a[0] + a[2] // 2, a[1] + a[3] // 2); bc = (b[0] + b[2] // 2, b[1] + b[3] // 2)
        if abs(bc[1] - ac[1]) > abs(bc[0] - ac[0]):
            down = bc[1] > ac[1]
            p1 = (ac[0], a[1] + a[3] if down else a[1])
            p2 = (bc[0], b[1] if down else b[1] + b[3])
            mid = (p1[1] + p2[1]) // 2; pts = [p1, (p1[0], mid), (p2[0], mid), p2]
        else:
            right = bc[0] > ac[0]
            p1 = (a[0] + a[2] if right else a[0], ac[1])
            p2 = (b[0] if right else b[0] + b[2], bc[1])
            mid = (p1[0] + p2[0]) // 2; pts = [p1, (mid, p1[1]), (mid, p2[1]), p2]
        edges.append({"id": f"e.swim.{i}", "from": edge["from"], "to": edge["to"], "points": pts,
                      "color": edge.get("color", "white"), "label": edge.get("label"), "style": edge.get("style", "solid")})
        flow.append({"points": [list(p) for p in pts], "color": edge.get("accent", "green"), "offset": i / max(1, len(connections))})
    height = top + len(lanes) * (lane_h + gap) + 40
    return {"layout": "swimlane", "canvas": {"width": width, "height": height}, "frame": (18, 117, 1174, height - 144),
            "lanes": {"x": lane_x, "w": lane_w, "h": lane_h, "ys": ys, "items": lanes},
            "glow_rects": [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3}],
            "flow_paths": flow, "pulse_targets": pulses, "icons": icons, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Sequence (2-6 participants, ordered messages)
# ---------------------------------------------------------------------------

def plan_sequence(spec):
    spec = spec or {}
    participants = [dict(x) for x in spec.get("participants", [])][:6]
    while len(participants) < 2:
        participants.append({"id": f"p{len(participants)}", "label": "", "icon": "server"})
    messages = [dict(x) for x in spec.get("messages", [])][:12]
    width, top, card_y = 1210, 190, 185
    left, right = 95, 1115; gap = (right - left) / max(1, len(participants) - 1)
    xs = [round(left + i * gap) for i in range(len(participants))]
    height = max(620, 330 + len(messages) * 52)
    nodes, edges, flow, pulses, icons = [], [], [], [], []
    id_to_x = {}
    for i, (x, item) in enumerate(zip(xs, participants)):
        pid = item.get("id") or f"p{i}"; item["id"] = pid; id_to_x[pid] = x
        nodes.append(_node(f"participant.{pid}", "card", x - 70, card_y, 140, 78, label=item.get("label", ""), icon=item.get("icon", "server")))
        icons.append(_icon(item.get("icon", "server"), x - 58, card_y + 14, item.get("color"), "participant", i))
        pulses.append({"box": [x - 70, card_y, x + 70, card_y + 78], "color": "core_stroke"})
    rows = []
    for i, msg in enumerate(messages):
        y = 310 + i * 52; a, b = id_to_x.get(msg.get("from")), id_to_x.get(msg.get("to"))
        if a is None or b is None: continue
        direction = 1 if b > a else -1; pts = [(a, y), (b, y)]
        rows.append((y, msg, a, b))
        edges.append({"id": f"message.{i}", "from": f"participant.{msg['from']}", "to": f"participant.{msg['to']}",
                      "points": pts, "color": msg.get("color", "white"), "label": msg.get("label"), "style": msg.get("style", "solid")})
        flow.append({"points": [list(p) for p in pts], "color": msg.get("accent", "green" if direction > 0 else "purple"), "offset": i / max(1, len(messages))})
    return {"layout": "sequence", "canvas": {"width": width, "height": height}, "frame": (18, 117, 1174, height - 144),
            "sequence": {"participants": participants, "xs": xs, "card_y": card_y, "rows": rows, "bottom": height - 55},
            "glow_rects": [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3}],
            "flow_paths": flow, "pulse_targets": pulses, "icons": icons, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Graph (free-form workflow: nodes + edges, auto DAG layout, loop channels)
# ---------------------------------------------------------------------------

GRAPH_STROKES = ["core_stroke", "green", "purple", "amber", "cyan", "pink"]
GRAPH_LOOP_STROKES = ["purple", "pink", "amber"]
GRAPH_FILLS = {"core_stroke": "blue_fill", "green": "green_fill", "purple": "purple_fill",
               "amber": "icon_fill", "pink": "icon_fill", "cyan": "blue_fill"}
GRAPH_NODE_KINDS = ("card", "decision", "terminal")
# THEME keys accepted for node/edge "accent" (flow beams + pulses resolve
# these through the active style's palette).
GRAPH_ACCENTS = {"core_stroke", "green", "purple", "amber", "cyan", "pink", "white", "muted"}


def _graph_accent(item, fallback):
    accent = (item or {}).get("accent")
    return accent if accent in GRAPH_ACCENTS else fallback


def _graph_prepare(spec):
    """Normalize nodes/edges: unique string ids, drop dangling edges, flag loops.

    Loop edges are either declared (kind: "loop") or detected back edges: any
    forward edge that would close a cycle is treated as a loop so the layered
    layout never breaks, whatever topology the caller sends.
    """
    raw_nodes = [dict(n) for n in (spec.get("nodes") or []) if isinstance(n, dict)][:24]
    if not raw_nodes:
        raw_nodes = [{"id": "a", "label": "Step A"}, {"id": "b", "label": "Step B"}]
    seen = set()
    for i, node in enumerate(raw_nodes):
        nid = str(node.get("id") or f"n{i}")
        while nid in seen:
            nid += "_"
        node["id"] = nid
        seen.add(nid)
    by_id = {n["id"]: n for n in raw_nodes}

    raw_edges = [dict(e) for e in (spec.get("edges") or []) if isinstance(e, dict)]
    raw_edges = [e for e in raw_edges if e.get("from") in by_id and e.get("to") in by_id][:40]
    for edge in raw_edges:
        edge["_loop"] = edge.get("kind") == "loop" or edge["from"] == edge["to"]

    # Detect remaining back edges (DFS in declaration order, forward edges only).
    out = {nid: [] for nid in by_id}
    for edge in raw_edges:
        if not edge["_loop"]:
            out[edge["from"]].append(edge)
    state = {nid: 0 for nid in by_id}  # 0 new, 1 on stack, 2 done

    def visit(nid):
        state[nid] = 1
        for edge in out[nid]:
            if edge["_loop"]:
                continue
            nxt = edge["to"]
            if state[nxt] == 1:
                edge["_loop"] = True
            elif state[nxt] == 0:
                visit(nxt)
        state[nid] = 2

    for node in raw_nodes:
        if state[node["id"]] == 0:
            visit(node["id"])
    return raw_nodes, raw_edges, by_id


def _graph_layers(raw_nodes, raw_edges, by_id):
    """Longest-path layer per node + barycenter row order within each layer."""
    forward = [e for e in raw_edges if not e["_loop"]]
    indeg = {n["id"]: 0 for n in raw_nodes}
    out = {n["id"]: [] for n in raw_nodes}
    preds = {n["id"]: [] for n in raw_nodes}
    for e in forward:
        out[e["from"]].append(e["to"])
        indeg[e["to"]] += 1
        preds[e["to"]].append(e["from"])

    layer = {}
    ready = [n["id"] for n in raw_nodes if indeg[n["id"]] == 0]
    for nid in ready:
        layer[nid] = 0
    pending = dict(indeg)
    while ready:
        nid = ready.pop(0)
        for nxt in out[nid]:
            layer[nxt] = max(layer.get(nxt, 0), layer[nid] + 1)
            pending[nxt] -= 1
            if pending[nxt] == 0:
                ready.append(nxt)
    for n in raw_nodes:  # safety: anything untouched sits at layer 0
        layer.setdefault(n["id"], 0)

    manual = {n["id"] for n in raw_nodes if isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float))}
    order_index = {n["id"]: i for i, n in enumerate(raw_nodes)}
    cols = {}
    for n in raw_nodes:
        if n["id"] not in manual:
            cols.setdefault(layer[n["id"]], []).append(n["id"])
    for l in cols:
        cols[l].sort(key=lambda nid: order_index[nid])
    for _ in range(2):
        for l in sorted(cols):
            if l - 1 not in cols:
                continue
            prev_row = {nid: r for r, nid in enumerate(cols[l - 1])}
            cur_row = {nid: r for r, nid in enumerate(cols[l])}

            def key(nid):
                ps = [prev_row[p] for p in preds[nid] if p in prev_row]
                return sum(ps) / len(ps) if ps else float(cur_row[nid])

            cols[l].sort(key=key)
    return layer, cols, manual


def plan_graph(spec):
    spec = spec or {}
    horizontal = spec.get("direction", "right") != "down"
    raw_nodes, raw_edges, by_id = _graph_prepare(spec)
    layer, cols, manual = _graph_layers(raw_nodes, raw_edges, by_id)
    n_layers = (max(cols) + 1) if cols else 1

    loops = [e for e in raw_edges if e["_loop"]]
    skips = [e for e in raw_edges if not e["_loop"] and e["from"] not in manual and e["to"] not in manual
             and layer[e["to"]] - layer[e["from"]] >= 2]
    lane_pitch = 36

    has_body = any(n.get("body") for n in raw_nodes if n.get("kind", "card") == "card")
    card_h = 96 if has_body else 78

    # Grid geometry along the flow axis (u) and the cross axis (v). For
    # direction "right": u = x, v = y (loops below, skips above). For
    # direction "down": u = y, v = x (loops right, skips left).
    if horizontal:
        u_lo, u_hi = 60, 1150
        gap_u = 70 if n_layers <= 4 else 56 if n_layers <= 6 else 46
        cu = min(210, max(120, (u_hi - u_lo - (n_layers - 1) * gap_u) / n_layers))
        total_u = n_layers * cu + (n_layers - 1) * gap_u
        u0 = u_lo + (u_hi - u_lo - total_u) / 2
        if cu < 150 and any(n.get("icon") for n in raw_nodes):
            # Narrow cards stack icon above label and need the extra height.
            card_h = max(card_h, 100)
        cv, gap_v = card_h, 52
        v_lo = 190 + (len(skips) * lane_pitch + 16 if skips else 0)
    else:
        cu, gap_u = card_h, 64
        u0 = 190
        max_rows = max((len(v) for v in cols.values()), default=1)
        v_left = 60 + (len(skips) * lane_pitch + 14 if skips else 0)
        v_right = 1150 - (len(loops) * lane_pitch + 14 if loops else 0)
        gap_v = 40
        cv = min(210, max(130, (v_right - v_left - (max_rows - 1) * gap_v) / max_rows))
        v_lo = v_left

    max_rows_all = max((len(v) for v in cols.values()), default=1)
    grid_span_v = max_rows_all * cv + (max_rows_all - 1) * gap_v
    if not horizontal:
        # The canvas width is fixed, so center the grid between the side lanes.
        v_lo = v_left + max(0, (v_right - v_left - grid_span_v) / 2)

    def cell_center(col, row, rows_in_col):
        span = rows_in_col * cv + (rows_in_col - 1) * gap_v
        u_c = u0 + col * (cu + gap_u) + cu / 2
        v_c = v_lo + (grid_span_v - span) / 2 + row * (cv + gap_v) + cv / 2
        return u_c, v_c

    def to_xy(u, v):
        return (u, v) if horizontal else (v, u)

    # --- node boxes ---------------------------------------------------------
    card_w_xy = cu if horizontal else cv
    card_h_xy = cv if horizontal else cu
    gnodes = []
    boxes = {}
    for n in raw_nodes:
        kind = n.get("kind", "card")
        if kind not in GRAPH_NODE_KINDS:
            kind = "card"
        if n["id"] in manual:
            cx, cy = float(n["x"]), float(n["y"])
        else:
            col = layer[n["id"]]
            row = cols[col].index(n["id"])
            u_c, v_c = cell_center(col, row, len(cols[col]))
            cx, cy = to_xy(u_c, v_c)
        if kind == "decision":
            side = min(card_w_xy, card_h_xy) + 22
            box = (cx - side / 2, cy - side / 2, side, side)
        elif kind == "terminal":
            box = (cx - card_w_xy * 0.42, cy - card_h_xy * 0.36, card_w_xy * 0.84, card_h_xy * 0.72)
        else:
            box = (cx - card_w_xy / 2, cy - card_h_xy / 2, card_w_xy, card_h_xy)
        box = tuple(round(v) for v in box)
        accent = _graph_accent(n, GRAPH_STROKES[layer[n["id"]] % len(GRAPH_STROKES)])
        record = dict(n)
        record.update({"_box": box, "_kind": kind, "_accent": accent,
                       "_fill": GRAPH_FILLS.get(accent, "icon_fill"), "_center": (cx, cy)})
        gnodes.append(record)
        boxes[n["id"]] = box

    # --- edge routing --------------------------------------------------------
    def port(box, side, offset=0.0):
        x, y, w, h = box
        if side == "left":
            return (x, y + h / 2 + offset)
        if side == "right":
            return (x + w, y + h / 2 + offset)
        if side == "top":
            return (x + w / 2 + offset, y)
        return (x + w / 2 + offset, y + h)  # bottom

    for e in raw_edges:
        if e["_loop"]:
            e["_class"] = "loop"
        elif e["from"] in manual or e["to"] in manual:
            e["_class"] = "manual"
        elif layer[e["to"]] - layer[e["from"]] >= 2:
            e["_class"] = "skip"
        else:
            e["_class"] = "straight"

    out_seq, in_seq = {}, {}
    for e in raw_edges:
        out_seq.setdefault(e["from"], []).append(e)
        in_seq.setdefault(e["to"], []).append(e)

    def spread(edge, seq_map, nid):
        # Only edges leaving/entering through the same face compete for the
        # port; loops use the bottom/right face, skips the top/left one, etc.
        peers = [p for p in seq_map.get(nid, []) if p["_class"] == edge["_class"]]
        if len(peers) < 2:
            return 0.0
        k = next(j for j, p in enumerate(peers) if p is edge)
        return (k - (len(peers) - 1) / 2) * 14

    # Vertical (cross-axis) segments in a column gap fan out so parallel
    # edges never overlap; count them per gap first.
    gap_traffic, gap_seen = {}, {}
    for e in raw_edges:
        if e["_loop"] or e["from"] in manual or e["to"] in manual:
            continue
        if layer[e["to"]] - layer[e["from"]] == 1:
            gap_traffic[layer[e["from"]]] = gap_traffic.get(layer[e["from"]], 0) + 1

    def elbow(a, b):
        """Generic orthogonal connector between two free boxes (manual nodes)."""
        ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
        bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
        if abs(by - ay) > abs(bx - ax):
            down = by > ay
            p1 = (ax, a[1] + a[3] if down else a[1])
            p2 = (bx, b[1] if down else b[1] + b[3])
            mid = (p1[1] + p2[1]) / 2
            return [p1, (p1[0], mid), (p2[0], mid), p2]
        right = bx > ax
        p1 = (a[0] + a[2] if right else a[0], ay)
        p2 = (b[0] if right else b[0] + b[2], by)
        mid = (p1[0] + p2[0]) / 2
        return [p1, (mid, p1[1]), (mid, p2[1]), p2]

    grid_v_hi = v_lo + grid_span_v
    if horizontal:
        # Lanes must clear every box, including manually placed ones.
        loop_lane_v = max([grid_v_hi] + [b[1] + b[3] for b in boxes.values()]) + 46
        skip_lane_v = 190 + 10
    else:
        loop_lane_v = max(1150 - len(loops) * lane_pitch + 8,
                          max(b[0] + b[2] for b in boxes.values()) + 26)
        skip_lane_v = 60 + 10

    gedges, flow, loop_i, skip_i = [], [], 0, 0
    for i, e in enumerate(raw_edges):
        src, dst = boxes[e["from"]], boxes[e["to"]]
        label = e.get("label")
        if e["_loop"]:
            lane = loop_lane_v + loop_i * lane_pitch
            loop_i += 1
            if e["from"] == e["to"]:
                s_off, t_off = 20, -20
            else:
                s_off, t_off = spread(e, out_seq, e["from"]), spread(e, in_seq, e["to"])
            if horizontal:
                p1, p4 = port(src, "bottom", s_off), port(dst, "bottom", t_off)
                pts = [p1, (p1[0], lane), (p4[0], lane), p4]
            else:
                p1, p4 = port(src, "right", s_off), port(dst, "right", t_off)
                pts = [p1, (lane, p1[1]), (lane, p4[1]), p4]
            accent = _graph_accent(e, GRAPH_LOOP_STROKES[(loop_i - 1) % len(GRAPH_LOOP_STROKES)])
            color, style = e.get("color", "muted"), "dashed"
            n_loops = max(1, len(loops))
            offset = 0.80 if n_loops == 1 else 0.78 + 0.18 * (loop_i - 1) / (n_loops - 1)
        elif e["from"] in manual or e["to"] in manual:
            pts = elbow(src, dst)
            accent = _graph_accent(e, next(g["_accent"] for g in gnodes if g["id"] == e["from"]))
            color, style = e.get("color", "white"), e.get("style", "solid")
            offset = 0.66 * layer[e["from"]] / n_layers
        elif layer[e["to"]] - layer[e["from"]] >= 2:
            lane = skip_lane_v + skip_i * lane_pitch
            skip_i += 1
            s_off, t_off = spread(e, out_seq, e["from"]), spread(e, in_seq, e["to"])
            if horizontal:
                p1, p4 = port(src, "top", s_off), port(dst, "top", t_off)
                pts = [p1, (p1[0], lane), (p4[0], lane), p4]
            else:
                p1, p4 = port(src, "left", s_off), port(dst, "left", t_off)
                pts = [p1, (lane, p1[1]), (lane, p4[1]), p4]
            accent = _graph_accent(e, next(g["_accent"] for g in gnodes if g["id"] == e["from"]))
            color, style = e.get("color", "white"), e.get("style", "solid")
            offset = 0.66 * layer[e["from"]] / n_layers
        else:
            s_off, t_off = spread(e, out_seq, e["from"]), spread(e, in_seq, e["to"])
            gap_col = layer[e["from"]]
            seen = gap_seen.get(gap_col, 0)
            gap_seen[gap_col] = seen + 1
            m = gap_traffic.get(gap_col, 1)
            mid_off = (seen - (m - 1) / 2) * 12
            if horizontal:
                p1, p4 = port(src, "right", s_off), port(dst, "left", t_off)
                if abs(p1[1] - p4[1]) < 3 and layer[e["to"]] > layer[e["from"]]:
                    pts = [p1, p4]
                elif layer[e["to"]] == layer[e["from"]]:
                    pts = elbow(src, dst)
                else:
                    mid = (p1[0] + p4[0]) / 2 + mid_off
                    pts = [p1, (mid, p1[1]), (mid, p4[1]), p4]
            else:
                p1, p4 = port(src, "bottom", s_off), port(dst, "top", t_off)
                if abs(p1[0] - p4[0]) < 3 and layer[e["to"]] > layer[e["from"]]:
                    pts = [p1, p4]
                elif layer[e["to"]] == layer[e["from"]]:
                    pts = elbow(src, dst)
                else:
                    mid = (p1[1] + p4[1]) / 2 + mid_off
                    pts = [p1, (p1[0], mid), (p4[0], mid), p4]
            accent = _graph_accent(e, next(g["_accent"] for g in gnodes if g["id"] == e["from"]))
            color, style = e.get("color", "white"), e.get("style", "solid")
            offset = 0.66 * layer[e["from"]] / n_layers

        pts = [(round(px), round(py)) for px, py in pts]
        gedges.append({"id": f"e.{i}.{e['from']}_{e['to']}", "from": e["from"], "to": e["to"],
                       "points": pts, "color": color, "label": label, "style": style,
                       "loop": e["_loop"]})
        flow.append({"points": [list(p) for p in pts], "color": accent, "offset": round(offset, 4)})

    # --- plan assembly --------------------------------------------------------
    nodes, icons, pulses = [], [], []
    ordinal = 0
    for g in gnodes:
        x, y, w, h = g["_box"]
        nodes.append(_node(g["id"], g["_kind"], x, y, w, h, label=g.get("label", ""),
                           icon=g.get("icon"), group=None))
        pulses.append({"box": [x, y, x + w, y + h], "color": g["_accent"]})
        if g["_kind"] == "card" and g.get("icon"):
            narrow = w < 150
            ix = x + (w - 50) // 2 if narrow else x + 12  # icon tile is 50px
            iy = y + 8 if narrow else y + (h - 50) // 2
            g["_icon_xy"] = (ix, iy)
            icons.append(_icon(g["icon"], ix, iy, g.get("color"), "graph", ordinal))
            ordinal += 1

    if horizontal:
        content_bottom = max([grid_v_hi] + [b[1] + b[3] for b in boxes.values()])
        if loops:
            content_bottom = max(content_bottom, loop_lane_v + (len(loops) - 1) * lane_pitch)
    else:
        content_bottom = max([u0 + n_layers * (cu + gap_u) - gap_u] + [b[1] + b[3] for b in boxes.values()])
    if spec.get("footer"):
        content_bottom += 30
    height = max(560, int(content_bottom) + 84)
    frame = (18, 117, 1174, height - 144)
    glow = [{"box": [18, 117, 1192, height - 27], "color": "frame", "light": "frame", "width": 3},
            {"box": [600, 27, 992, 99], "color": "green", "light": "pink", "width": 2}]

    return {
        "layout": "graph",
        "canvas": {"width": CANVAS_W, "height": height},
        "frame": frame,
        "graph_nodes": gnodes,
        "graph_edges": gedges,
        "graph_meta": {"layers": layer, "n_layers": n_layers, "horizontal": horizontal,
                       "loops": len(loops), "skips": len(skips), "card_h": card_h},
        "glow_rects": glow,
        "flow_paths": flow,
        "pulse_targets": pulses,
        "icons": icons,
        "nodes": nodes,
        "edges": gedges,
    }
