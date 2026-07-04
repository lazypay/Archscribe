"""Tests for the replication-driven branding features:

- adaptive signature (long signatures shift left + stretch the underline)
- configurable panorama edge labels (down_label / up_label / yes_label)
- custom icons (icon_file -> '@<abs path>' -> icon op with file/custom)
- left panel badge_file (image op, data-uri collection)
- input_style: plain (frameless input tiles)
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def base_panorama_spec():
    return json.loads((ROOT / "assets" / "default-spec.json").read_text(encoding="utf-8"))


class AdaptiveSignatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")
        cls.renderer.apply_style("default")

    def _signature_op(self, spec):
        _ex, _img, doc = self.renderer.render_static_with_ops(spec)
        return next(op for op in doc["ops"] if op["op"] == "signature")

    def test_default_signature_keeps_legacy_position(self):
        op = self._signature_op(base_panorama_spec())
        self.assertEqual(op["x"], self.renderer.SIGNATURE_X)
        self.assertEqual(op["stretch"], 1.0)

    def test_long_signature_shifts_left_and_stretches(self):
        spec = base_panorama_spec()
        spec["signature"] = "DailyDoseofDS.com"
        op = self._signature_op(spec)
        self.assertLess(op["x"], self.renderer.SIGNATURE_X)
        self.assertGreater(op["stretch"], 1.2)
        # The text right edge stays inside the canvas frame.
        _ex, img = self.renderer.render_static(spec)
        self.assertLessEqual(op["x"] + 240, spec.get("canvas", {}).get("width", 1210))


class EdgeLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_model = load_module("graph_model")

    def test_left_panel_labels_default(self):
        plan = self.graph_model.plan_panorama(base_panorama_spec())
        labels = {e["id"]: e["label"] for e in plan["edges"]}
        self.assertEqual(labels["e.core_left"], "Read")
        self.assertEqual(labels["e.left_core"], "Context")
        self.assertEqual(labels["e.decision_output"], "Yes")

    def test_left_panel_labels_override(self):
        spec = base_panorama_spec()
        spec["left_panel"]["down_label"] = "Store"
        spec["left_panel"]["up_label"] = "Recall"
        spec.setdefault("decision", {})["yes_label"] = "Ship"
        plan = self.graph_model.plan_panorama(spec)
        labels = {e["id"]: e["label"] for e in plan["edges"]}
        self.assertEqual(labels["e.core_left"], "Store")
        self.assertEqual(labels["e.left_core"], "Recall")
        self.assertEqual(labels["e.decision_output"], "Ship")


class CustomIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")
        cls.svg_renderer = load_module("svg_renderer")
        cls.renderer.apply_style("default")
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmpdir.name)
        cls.logo = cls.tmp / "logo.png"
        Image.new("RGBA", (32, 32), (200, 60, 60, 255)).save(cls.logo)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _spec_with_custom_icon(self):
        spec = base_panorama_spec()
        spec["inputs"][0]["icon_file"] = self.logo.name
        spec["left_panel"]["badge_file"] = self.logo.name
        return spec

    def test_resolve_custom_icons_rewrites_paths(self):
        spec = self._spec_with_custom_icon()
        self.renderer.resolve_custom_icons(spec, self.tmp)
        self.assertTrue(spec["inputs"][0]["icon"].startswith("@"))
        self.assertTrue(Path(spec["inputs"][0]["icon"][1:]).is_file())
        self.assertTrue(Path(spec["left_panel"]["badge_file"]).is_absolute())

    def test_ops_carry_custom_icon_and_badge_image(self):
        spec = self.renderer.resolve_custom_icons(self._spec_with_custom_icon(), self.tmp)
        _ex, _img, doc = self.renderer.render_static_with_ops(spec)
        custom_ops = [op for op in doc["ops"] if op["op"] == "icon" and op.get("custom")]
        self.assertEqual(len(custom_ops), 1)
        self.assertTrue(custom_ops[0]["file"].endswith("logo.png"))
        image_ops = [op for op in doc["ops"] if op["op"] == "image"]
        self.assertEqual(len(image_ops), 1)

        markups = self.svg_renderer._collect_icon_markups(doc)
        self.assertIn(custom_ops[0]["name"], markups)
        self.assertIn("data:image/png;base64,", markups[custom_ops[0]["name"]])
        hrefs = self.svg_renderer._collect_image_hrefs(doc)
        self.assertIn(image_ops[0]["name"], hrefs)
        self.assertTrue(hrefs[image_ops[0]["name"]].startswith("data:image/png;base64,"))

    def test_validate_spec_checks_icon_files(self):
        spec = self._spec_with_custom_icon()
        report = self.renderer.validate_spec(spec, spec_dir=self.tmp)
        self.assertTrue(report["ok"], report)

        spec["inputs"][0]["icon_file"] = "missing.png"
        report = self.renderer.validate_spec(spec, spec_dir=self.tmp)
        self.assertFalse(report["ok"])
        self.assertTrue(any("icon_file" in e["path"] for e in report["errors"]))

        spec["inputs"][0]["icon_file"] = self.logo.name
        spec["left_panel"]["badge_file"] = "logo.gif"
        report = self.renderer.validate_spec(spec, spec_dir=self.tmp)
        self.assertFalse(report["ok"])
        self.assertTrue(any("badge_file" in e["path"] for e in report["errors"]))


class PlainInputStyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_module("render_animated_diagram")
        cls.renderer.apply_style("default")

    def test_plain_inputs_mark_ops(self):
        spec = base_panorama_spec()
        spec["input_style"] = "plain"
        _ex, _img, doc = self.renderer.render_static_with_ops(spec)
        plain_ops = [op for op in doc["ops"] if op["op"] == "icon" and op.get("plain")]
        self.assertEqual(len(plain_ops), len(spec["inputs"]))
        for op in plain_ops:
            self.assertEqual(op["pad"], self.renderer.ICON_PAD_PLAIN)
            # Frameless glyphs take the item accent color instead of white.
            self.assertNotEqual(op["glyph"], self.renderer.THEME["white"])

    def test_boxed_default_has_no_plain_ops(self):
        _ex, _img, doc = self.renderer.render_static_with_ops(base_panorama_spec())
        self.assertFalse([op for op in doc["ops"] if op["op"] == "icon" and op.get("plain")])

    def test_validate_rejects_unknown_input_style(self):
        spec = base_panorama_spec()
        spec["input_style"] = "fancy"
        report = self.renderer.validate_spec(spec)
        self.assertFalse(report["ok"])
        self.assertTrue(any(e["path"] == "$.input_style" for e in report["errors"]))

    def test_validate_warns_on_long_signature(self):
        spec = base_panorama_spec()
        spec["signature"] = "x" * 40
        report = self.renderer.validate_spec(spec)
        self.assertTrue(report["ok"])
        self.assertTrue(any(w["path"] == "$.signature" for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
