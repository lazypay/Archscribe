import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The original hand-tuned panorama animation geometry. plan_panorama() must
# reproduce it exactly for the default spec (4 inputs / 3 cards / 3 panels).
LEGACY_FLOW_PATHS = [
    ([(605, 239), (605, 316)], "green", 0.00),
    ([(355, 411), (472, 411)], "cyan", 0.10),
    ([(732, 411), (850, 411)], "cyan", 0.24),
    ([(982, 456), (982, 481), (768, 481), (768, 508)], "core_stroke", 0.38),
    ([(826, 568), (1022, 568)], "green", 0.54),
    ([(707, 568), (510, 568), (222, 568), (222, 456)], "purple", 0.66),
    ([(156, 637), (156, 736)], "green", 0.18),
    ([(205, 736), (205, 637)], "green", 0.58),
    ([(458, 890), (486, 890), (598, 890), (626, 890), (738, 890), (766, 890)], "purple", 0.32),
    ([(855, 890), (904, 890)], "white", 0.46),
    ([(1036, 735), (1036, 691), (766, 691), (766, 628)], "amber", 0.72),
]

LEGACY_PULSE_BOXES = [
    (389, 138, 819, 239),
    (95, 366, 355, 456),
    (472, 366, 732, 456),
    (850, 366, 1110, 456),
    (706, 508, 826, 628),
    (333, 734, 855, 1080),
    (904, 735, 1162, 1079),
]


class PanoramaPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")
        cls.renderer = load_module("render_animated_diagram")
        cls.spec = json.loads((ROOT / "assets" / "default-spec.json").read_text(encoding="utf-8"))
        cls.plan = cls.graph_model.plan_panorama(cls.spec)
        cls.graph = cls.graph_model.build_graph(cls.spec)

    def test_node_ids_unique(self):
        ids = [n["id"] for n in self.graph["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_edges_reference_existing_nodes(self):
        ids = {n["id"] for n in self.graph["nodes"]}
        for edge in self.graph["edges"]:
            self.assertIn(edge["from"], ids, edge["id"])
            self.assertIn(edge["to"], ids, edge["id"])

    def test_default_spec_produces_full_panorama(self):
        by_kind = {}
        for node in self.graph["nodes"]:
            by_kind.setdefault(node["kind"], []).append(node)
        self.assertEqual(len(by_kind["group"]), 5)
        self.assertEqual(len(by_kind["input"]), 4)
        self.assertEqual(len(by_kind["card"]), 3)
        self.assertEqual(len(by_kind["decision"]), 1)
        self.assertEqual(len(by_kind["output"]), 1)
        self.assertEqual(len(by_kind["panel-card"]), 10)

    def test_default_plan_matches_legacy_flow_paths(self):
        plan_flow = {
            (tuple(tuple(p) for p in fp["points"]), fp["color"], fp["offset"])
            for fp in self.plan["flow_paths"]
        }
        legacy = {(tuple(pts), color, offset) for pts, color, offset in LEGACY_FLOW_PATHS}
        self.assertEqual(plan_flow, legacy)

    def test_default_plan_matches_legacy_pulse_targets(self):
        plan_boxes = [tuple(pt["box"]) for pt in self.plan["pulse_targets"]]
        self.assertEqual(plan_boxes, LEGACY_PULSE_BOXES)

    def test_default_plan_matches_legacy_positions(self):
        self.assertEqual(self.plan["inputs"]["box"], (389, 130, 430, 128))
        self.assertEqual(self.plan["inputs"]["xs"], [423, 532, 640, 748])
        self.assertEqual(self.plan["inputs"]["arrow_cx"], 605)
        self.assertEqual(self.plan["core"]["xs"], [95, 472, 850])
        self.assertEqual(self.plan["core"]["w"], 260)
        self.assertEqual(self.plan["panels"]["x"], {"left_panel": 39, "center_panel": 333, "right_panel": 904})
        self.assertEqual(self.plan["panels"]["layer_xs"], [346, 486, 626, 766])
        self.assertEqual(self.plan["canvas"], {"width": 1210, "height": 1138})
        self.assertEqual(self.plan["frame"], (18, 117, 1174, 994))

    def test_icon_instances_sit_inside_graph_nodes(self):
        tile = self.renderer.ICON_TILE
        ordinal_to_node = {}
        for i in range(4):
            ordinal_to_node[i] = f"input.{i}"
        for i in range(3):
            ordinal_to_node[4 + i] = f"core.{i}"
        ordinal_to_node[7] = "output"
        for i in range(3):
            ordinal_to_node[8 + i] = f"left.{i}"
        for i in range(4):
            ordinal_to_node[11 + i] = f"layer.{i}"
        for i in range(3):
            ordinal_to_node[15 + i] = f"pack.{i}"

        nodes = {n["id"]: n for n in self.graph["nodes"]}
        instances = self.renderer.collect_icon_instances(self.spec)
        self.assertEqual(len(instances), 18)
        for inst in instances:
            node = nodes[ordinal_to_node[inst["ordinal"]]]
            size = tile * inst.get("scale", 1.0)
            self.assertGreaterEqual(inst["x"], node["x"], node["id"])
            self.assertGreaterEqual(inst["y"], node["y"], node["id"])
            self.assertLessEqual(inst["x"] + size, node["x"] + node["w"], node["id"])
            self.assertLessEqual(inst["y"] + size, node["y"] + node["h"], node["id"])

    def test_canvas_matches_renderer_defaults(self):
        self.assertEqual(self.graph["canvas"]["width"], self.renderer.DEFAULT_W)
        self.assertEqual(self.graph["canvas"]["height"], self.renderer.DEFAULT_H)

    def test_adjacency_is_symmetric(self):
        neighbors = self.graph_model.adjacency(self.graph)
        for node_id, adjacent in neighbors.items():
            for other in adjacent:
                self.assertIn(node_id, neighbors[other])
        self.assertIn("core.1", neighbors["core.0"])
        self.assertIn("decision", neighbors["output"])


class ElasticPanoramaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")

    def test_omitted_panels_shrink_canvas(self):
        bare = {
            "inputs": [{"label": "a"}, {"label": "b"}],
            "core": {"cards": [{"title": "x"}, {"title": "y"}]},
        }
        plan = self.graph_model.plan_panorama(bare)
        self.assertLess(plan["canvas"]["height"], 800)
        self.assertEqual(plan["panels"]["present"], [])
        ids = {n["id"] for n in plan["nodes"]}
        self.assertNotIn("left_panel", ids)
        edge_ids = {e["id"] for e in plan["edges"]}
        self.assertNotIn("e.core_left", edge_ids)
        self.assertNotIn("e.right_decision", edge_ids)

    def test_input_counts_stay_inside_box(self):
        for n in (2, 3, 5, 6):
            spec = {"inputs": [{"label": f"i{k}"} for k in range(n)]}
            plan = self.graph_model.plan_panorama(spec)
            box_x, _y, box_w, _h = plan["inputs"]["box"]
            xs = plan["inputs"]["xs"]
            self.assertEqual(len(xs), n)
            self.assertGreaterEqual(xs[0], box_x, n)
            self.assertLessEqual(xs[-1] + 78, box_x + box_w + 12, n)

    def test_core_card_counts_fit_band(self):
        for n in (2, 3, 4):
            spec = {"core": {"cards": [{"title": f"c{k}"} for k in range(n)]}}
            plan = self.graph_model.plan_panorama(spec)
            xs, w = plan["core"]["xs"], plan["core"]["w"]
            self.assertEqual(len(xs), n)
            self.assertGreaterEqual(xs[0], 53)
            self.assertLessEqual(xs[-1] + w, 1157)
            for a, b in zip(xs, xs[1:]):
                self.assertGreater(b, a + w, "cards must not overlap")

    def test_two_panel_subset_is_centered(self):
        spec = {
            "inputs": [{"label": "a"}, {"label": "b"}],
            "core": {"cards": [{"title": "x"}, {"title": "y"}]},
            "center_panel": {"cards": [{"title": "l1"}, {"title": "l2"}]},
            "right_panel": {"cards": [{"title": "p1"}]},
        }
        plan = self.graph_model.plan_panorama(spec)
        self.assertEqual(plan["panels"]["present"], ["center_panel", "right_panel"])
        boxes = plan["panels"]["boxes"]
        left_edge = boxes["center_panel"][0]
        right_edge = boxes["right_panel"][0] + boxes["right_panel"][2]
        # Roughly centered inside [39, 1162]
        self.assertAlmostEqual(left_edge - 39, 1162 - right_edge, delta=30)
        self.assertEqual(plan["canvas"]["height"], 1138)


class SwimlanePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")

    def _spec(self, connections=None, subtitles=False):
        lanes = [
            {"title": "Lane A", "steps": [
                {"id": "a1", "title": "A1"}, {"id": "a2", "title": "A2"}, {"id": "a3", "title": "A3"}]},
            {"title": "Lane B", "steps": [
                {"id": "b1", "title": "B1"}, {"id": "b2", "title": "B2"}]},
        ]
        if subtitles:
            for lane in lanes:
                lane["subtitle"] = "Triggered by: something"
        spec = {"layout": "swimlane", "lanes": lanes}
        if connections is not None:
            spec["connections"] = connections
        return spec

    def test_alternating_tints(self):
        plan = self.graph_model.plan_swimlane(self._spec())
        tints = [lane["_tint"]["stroke"] for lane in plan["lanes"]["items"]]
        self.assertEqual(tints, ["green", "purple"])

    def test_subtitle_grows_lane(self):
        base = self.graph_model.plan_swimlane(self._spec())
        tall = self.graph_model.plan_swimlane(self._spec(subtitles=True))
        h_base = base["lanes"]["items"][0]["_h"]
        h_tall = tall["lanes"]["items"][0]["_h"]
        self.assertGreater(h_tall, h_base)

    def test_loopback_uses_dashed_channel(self):
        plan = self.graph_model.plan_swimlane(self._spec(connections=[
            {"from": "a1", "to": "a2"}, {"from": "a2", "to": "a3"},
            {"from": "a3", "to": "a1", "label": "retry"},
        ]))
        loop = next(e for e in plan["edges"] if e["loop"])
        self.assertEqual(loop["style"], "dashed")
        lane = plan["lanes"]["items"][0]
        self.assertTrue(lane["_has_channel"])
        # Channel runs under the cards but inside the lane.
        channel_y = loop["points"][1][1]
        card_bottom = max(s["_box"][1] + s["_box"][3] for s in lane["steps"])
        self.assertGreater(channel_y, card_bottom)
        self.assertLess(channel_y, lane["_y"] + lane["_h"])

    def test_cards_stay_inside_lane_after_channel_shift(self):
        plan = self.graph_model.plan_swimlane(self._spec(connections=[
            {"from": "a3", "to": "a1"}, {"from": "b2", "to": "b1"},
        ]))
        for lane in plan["lanes"]["items"]:
            for step in lane["steps"]:
                _, sy, _, sh = step["_box"]
                self.assertGreaterEqual(sy, lane["_y"])
                self.assertLessEqual(sy + sh, lane["_y"] + lane["_h"])

    def test_default_connections_chain_all_steps(self):
        plan = self.graph_model.plan_swimlane(self._spec())
        self.assertEqual(len(plan["edges"]), 4)


class GraphPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")

    def _loop_spec(self, direction="right"):
        return {
            "layout": "graph",
            "direction": direction,
            "nodes": [
                {"id": "ingest", "label": "Ingest", "icon": "ingest"},
                {"id": "plan", "label": "Plan", "icon": "plan"},
                {"id": "act", "label": "Act", "icon": "agent"},
                {"id": "gate", "label": "Pass?", "kind": "decision"},
                {"id": "ship", "label": "Ship", "kind": "terminal"},
            ],
            "edges": [
                {"from": "ingest", "to": "plan"},
                {"from": "plan", "to": "act"},
                {"from": "act", "to": "gate"},
                {"from": "gate", "to": "ship", "label": "yes"},
                {"from": "gate", "to": "act", "kind": "loop", "label": "retry"},
                {"from": "gate", "to": "plan", "kind": "loop", "label": "replan"},
            ],
        }

    def test_chain_layers_are_monotonic(self):
        plan = self.graph_model.plan_graph(self._loop_spec())
        boxes = {n["id"]: n["_box"] for n in plan["graph_nodes"]}
        order = ["ingest", "plan", "act", "gate", "ship"]
        centers = [boxes[i][0] + boxes[i][2] / 2 for i in order]
        self.assertEqual(centers, sorted(centers))
        self.assertEqual(plan["graph_meta"]["n_layers"], 5)

    def test_loop_edges_are_dashed_and_routed_below(self):
        plan = self.graph_model.plan_graph(self._loop_spec())
        loops = [e for e in plan["graph_edges"] if e["loop"]]
        self.assertEqual(len(loops), 2)
        grid_bottom = max(n["_box"][1] + n["_box"][3] for n in plan["graph_nodes"])
        for edge in loops:
            self.assertEqual(edge["style"], "dashed")
            lane_y = max(p[1] for p in edge["points"])
            self.assertGreater(lane_y, grid_bottom)
        # Distinct lanes so parallel loops never overlap.
        lanes = {max(p[1] for p in e["points"]) for e in loops}
        self.assertEqual(len(lanes), 2)

    def test_loops_fire_after_the_forward_wave(self):
        plan = self.graph_model.plan_graph(self._loop_spec())
        loop_pts = {tuple(map(tuple, e["points"])) for e in plan["graph_edges"] if e["loop"]}
        forward_offsets, loop_offsets = [], []
        for fp in plan["flow_paths"]:
            pts = tuple(map(tuple, fp["points"]))
            (loop_offsets if pts in loop_pts else forward_offsets).append(fp["offset"])
        self.assertLess(max(forward_offsets), min(loop_offsets))

    def test_back_edge_without_kind_is_detected_as_loop(self):
        spec = {"layout": "graph",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}]}
        plan = self.graph_model.plan_graph(spec)
        loops = [e for e in plan["graph_edges"] if e["loop"]]
        self.assertEqual(len(loops), 1)
        self.assertEqual((loops[0]["from"], loops[0]["to"]), ("c", "a"))
        self.assertEqual(plan["graph_meta"]["n_layers"], 3)

    def test_fork_and_join_share_a_column(self):
        spec = {"layout": "graph",
                "nodes": [{"id": "s", "label": "S"}, {"id": "f1", "label": "F1"},
                          {"id": "f2", "label": "F2"}, {"id": "j", "label": "J"}],
                "edges": [{"from": "s", "to": "f1"}, {"from": "s", "to": "f2"},
                          {"from": "f1", "to": "j"}, {"from": "f2", "to": "j"}]}
        plan = self.graph_model.plan_graph(spec)
        boxes = {n["id"]: n["_box"] for n in plan["graph_nodes"]}
        self.assertEqual(boxes["f1"][0], boxes["f2"][0])
        self.assertNotEqual(boxes["f1"][1], boxes["f2"][1])

    def test_manual_coordinates_override_auto_layout(self):
        spec = self._loop_spec()
        spec["nodes"][1].update({"x": 400, "y": 480})
        plan = self.graph_model.plan_graph(spec)
        box = next(n["_box"] for n in plan["graph_nodes"] if n["id"] == "plan")
        self.assertAlmostEqual(box[0] + box[2] / 2, 400, delta=1)
        self.assertAlmostEqual(box[1] + box[3] / 2, 480, delta=1)

    def test_direction_down_stacks_vertically_and_centers(self):
        plan = self.graph_model.plan_graph(self._loop_spec(direction="down"))
        boxes = {n["id"]: n["_box"] for n in plan["graph_nodes"]}
        order = ["ingest", "plan", "act", "gate", "ship"]
        centers = [boxes[i][1] + boxes[i][3] / 2 for i in order]
        self.assertEqual(centers, sorted(centers))
        cx = boxes["ingest"][0] + boxes["ingest"][2] / 2
        self.assertGreater(cx, 350)
        self.assertLess(cx, 850)
        self.assertGreater(plan["canvas"]["height"], 700)

    def test_nodes_edges_flow_are_consistent_and_serializable(self):
        plan = self.graph_model.plan_graph(self._loop_spec())
        ids = [n["id"] for n in plan["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        for edge in plan["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)
        self.assertEqual(len(plan["flow_paths"]), len(plan["graph_edges"]))
        self.assertEqual(len(plan["pulse_targets"]), len(plan["graph_nodes"]))
        json.dumps({"nodes": plan["nodes"], "edges": [dict(e, points=[list(p) for p in e["points"]]) for e in plan["edges"]],
                    "flow": plan["flow_paths"], "pulse": plan["pulse_targets"]})

    def test_icons_registered_for_pillow_motion_layer(self):
        plan = self.graph_model.plan_graph(self._loop_spec())
        kinds = {i["kind"] for i in plan["icons"]}
        self.assertEqual(kinds, {"ingest", "plan", "agent"})


class BuildPlanDispatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")

    def test_dispatch(self):
        self.assertEqual(self.graph_model.build_plan({})["layout"], "panorama")
        self.assertEqual(self.graph_model.build_plan({"layout": "swimlane"})["layout"], "swimlane")
        self.assertEqual(self.graph_model.build_plan({"layout": "graph", "nodes": [], "edges": []})["layout"], "graph")

    def test_layout_registry_is_trimmed(self):
        self.assertEqual(self.graph_model.LAYOUTS, ("panorama", "swimlane", "graph"))

    def test_plans_are_json_serializable(self):
        for layout in ("panorama", "swimlane"):
            plan = self.graph_model.build_plan({"layout": layout})
            json.dumps({"nodes": plan["nodes"], "edges": [dict(e, points=[list(p) for p in e["points"]]) for e in plan["edges"]],
                        "flow": plan["flow_paths"], "pulse": plan["pulse_targets"]})


if __name__ == "__main__":
    unittest.main()
