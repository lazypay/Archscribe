import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "render_animated_diagram", ROOT / "scripts" / "render_animated_diagram.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BundledFontsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = load_renderer()

    def test_bundled_font_files_exist(self):
        for name in [
            "Excalifont-Regular.ttf",
            "NotoSansSC-Regular.ttf",
            "NotoSansSC-Bold.ttf",
            "notosanssc-coverage.json",
        ]:
            self.assertTrue((FONT_DIR / name).is_file(), name)

    def test_hand_font_resolves_to_excalifont(self):
        font = self.renderer.load_font(20, hand=True)
        self.assertIn("Excalifont", Path(font.path).name)

    def test_cjk_font_resolves_to_bundled_noto(self):
        font = self.renderer.load_font(20, cjk=True, text="记忆资产归档流程")
        self.assertIn("NotoSansSC-Regular", Path(font.path).name)
        bold = self.renderer.load_font(20, cjk=True, bold=True, text="架构")
        self.assertIn("NotoSansSC-Bold", Path(bold.path).name)

    def test_plain_font_resolves_to_bundled_noto(self):
        font = self.renderer.load_font(20)
        self.assertIn("NotoSansSC-Regular", Path(font.path).name)

    def test_coverage_accepts_common_and_rejects_rare(self):
        self.assertTrue(self.renderer.bundled_cjk_covers("记忆资产归档流程\n架构图"))
        self.assertTrue(self.renderer.bundled_cjk_covers("Latin mixed 中文 123"))
        # U+20000 sits far outside the GB2312 subset.
        self.assertFalse(self.renderer.bundled_cjk_covers("\U00020000"))

    def test_rare_glyph_falls_back_but_still_returns_font(self):
        font = self.renderer.load_font(20, cjk=True, text="\U00020000")
        self.assertIsNotNone(font)

    def test_render_survives_missing_coverage_cache(self):
        ranges, starts = self.renderer.cjk_coverage_ranges()
        self.assertEqual(len(ranges), len(starts))
        self.assertGreater(len(ranges), 0)


if __name__ == "__main__":
    unittest.main()
