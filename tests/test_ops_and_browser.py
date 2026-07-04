import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpsDocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")
        cls.spec = json.loads((ROOT / "assets" / "default-spec.json").read_text(encoding="utf-8"))
        cls.renderer.apply_style("default")
        _ex, _img, cls.doc = cls.renderer.render_static_with_ops(cls.spec)

    def test_document_shape(self):
        self.assertEqual(self.doc["canvas"]["width"], 1210)
        self.assertEqual(self.doc["style"], "default")
        self.assertIn("finish", self.doc)
        self.assertIn("theme", self.doc)
        self.assertGreater(len(self.doc["ops"]), 50)

    def test_ops_cover_all_primitives(self):
        kinds = {op["op"] for op in self.doc["ops"]}
        self.assertEqual(
            kinds,
            {"rect", "ellipse", "diamond", "line", "text", "icon", "signature"},
        )

    def test_icon_ops_match_icon_instances(self):
        icon_ops = [op for op in self.doc["ops"] if op["op"] == "icon"]
        instances = self.renderer.collect_icon_instances(self.spec)
        self.assertEqual(len(icon_ops), len(instances))
        for op in icon_ops:
            self.assertTrue((ROOT / "assets" / "icons" / "tabler" / f"{op['name']}.svg").is_file(), op["name"])

    def test_animation_block_mirrors_plan(self):
        graph_model = load_module("graph_model")
        plan = graph_model.plan_panorama(self.spec)
        flow = self.doc["animation"]["flow_paths"]
        self.assertEqual(len(flow), len(plan["flow_paths"]))
        for entry, fp in zip(flow, plan["flow_paths"]):
            self.assertEqual(entry["points"], [list(p) for p in fp["points"]])
            self.assertEqual(entry["offset"], fp["offset"])
        pulses = self.doc["animation"]["pulse_targets"]
        self.assertEqual(len(pulses), len(plan["pulse_targets"]))

    def test_graph_block_present(self):
        graph = self.doc["graph"]
        self.assertGreater(len(graph["nodes"]), 10)
        self.assertGreater(len(graph["edges"]), 5)
        node_ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["from"], node_ids)
            self.assertIn(edge["to"], node_ids)

    def test_ops_are_json_serializable(self):
        payload = json.dumps(self.doc)
        self.assertGreater(len(payload), 1000)

    def test_recording_is_off_outside_context(self):
        self.assertIsNone(self.renderer.OPS_SINK)


class BrowserRendererTest(unittest.TestCase):
    """Slow-ish smoke test of the Chromium pipeline (static formats only)."""

    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")
        cls.svg_renderer = load_module("svg_renderer")
        cls.spec = json.loads((ROOT / "assets" / "default-spec.json").read_text(encoding="utf-8"))

    def setUp(self):
        if not self.svg_renderer.is_available():
            self.skipTest("playwright/rough.js unavailable")

    def test_static_svg_png_html_contract(self):
        self.renderer.apply_style("default")
        _ex, _img, doc = self.renderer.render_static_with_ops(self.spec)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.svg_renderer.render_all(doc, Path(tmp), "smoke", formats=("png", "svg", "html"))
            result["canvas"] = dict(doc["canvas"])
            svg_text = Path(result["svg"]).read_text(encoding="utf-8")
            self.assertIn("@font-face", svg_text)
            self.assertIn("data-op", svg_text)
            self.assertIn("data-icon", svg_text)
            html_text = Path(result["html"]).read_text(encoding="utf-8")
            self.assertIn("ARCHSCRIBE_GRAPH", html_text)
            self.assertEqual(html_text.count('class="hotspot"'), len(doc["graph"]["nodes"]))
            checks = self.renderer.check_outputs(result, self.spec)
        self.assertTrue(checks["ok"], checks)

    def test_interactive_html_runs_in_browser(self):
        """The saved HTML must boot its JS (hotspots wired, no errors)."""
        from playwright.sync_api import sync_playwright

        self.renderer.apply_style("default")
        _ex, _img, doc = self.renderer.render_static_with_ops(self.spec)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.svg_renderer.render_all(doc, Path(tmp), "inter", formats=("html",))
            errors = []
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(Path(result["html"]).as_uri())
                page.wait_for_function("() => window.__ready === true")
                # A leaf node: group hotspots are (correctly) covered by their
                # children in the middle, so click one that is fully exposed.
                page.click('.hotspot[data-node="decision"]')
                highlighted = page.evaluate("() => document.querySelectorAll('#highlights *').length")
                page.keyboard.press("Escape")
                cleared = page.evaluate("() => document.querySelectorAll('#highlights *').length")
                browser.close()
            self.assertEqual(errors, [])
            self.assertGreater(highlighted, 0)
            self.assertEqual(cleared, 0)


class NewLayoutOpsTest(unittest.TestCase):
    """The pipeline/layers layouts must produce coherent op streams too."""

    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")

    def _doc(self, spec):
        self.renderer.apply_style("default")
        _ex, _img, doc = self.renderer.render_static_with_ops(spec)
        return doc

    def test_pipeline_ops(self):
        spec = {
            "layout": "pipeline",
            "stages": [{"title": f"S{i}", "body": "do things", "icon": "file"} for i in range(4)],
            "decision": {"title": "OK?", "no_label": "retry"},
            "output": {"label": "Done", "icon": "check"},
        }
        doc = self._doc(spec)
        kinds = {op["op"] for op in doc["ops"]}
        self.assertIn("diamond", kinds)
        icon_ops = [op for op in doc["ops"] if op["op"] == "icon"]
        self.assertEqual(len(icon_ops), 5)  # 4 stages + output
        self.assertEqual(doc["layout"], "pipeline")
        self.assertLess(doc["canvas"]["height"], 800)
        self.assertGreater(len(doc["animation"]["flow_paths"]), 4)

    def test_layers_ops(self):
        spec = {
            "layout": "layers",
            "layers": [
                {"title": f"Layer {i}", "subtitle": "sub", "items": [{"label": f"item {j}", "icon": "db"} for j in range(3)]}
                for i in range(3)
            ],
        }
        doc = self._doc(spec)
        icon_ops = [op for op in doc["ops"] if op["op"] == "icon"]
        self.assertEqual(len(icon_ops), 9)
        self.assertEqual(doc["layout"], "layers")
        self.assertEqual(len(doc["animation"]["pulse_targets"]), 3)

    def test_validate_spec_catches_errors(self):
        bad = {"layout": "pipeline"}
        report = self.renderer.validate_spec(bad)
        self.assertFalse(report["ok"])
        self.assertTrue(any("stages" in e["path"] for e in report["errors"]))

        good = {
            "layout": "pipeline",
            "stages": [{"title": "A", "body": "b"}, {"title": "B", "body": "b"}],
        }
        report = self.renderer.validate_spec(good)
        self.assertTrue(report["ok"], report)

    def test_validate_spec_warns_on_unknown_keys(self):
        spec = {
            "layout": "layers",
            "layers": [{"title": "A", "items": []}, {"title": "B", "items": []}],
            "stages": [],
        }
        report = self.renderer.validate_spec(spec)
        self.assertTrue(report["ok"])
        self.assertTrue(any(w["path"] == "$.stages" for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
