import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_layout_examples_validate_and_render_ops():
    renderer = load("render_animated_diagram")
    for name in ("hub", "swimlane", "sequence"):
        path = ROOT / "assets" / "examples" / f"{name}-spec.json"
        spec = json.loads(path.read_text(encoding="utf-8"))
        report = renderer.validate_spec(spec, path.parent)
        assert report["ok"], report
        renderer.apply_style(spec["style"])
        _ex, _img, doc = renderer.render_static_with_ops(spec)
        assert doc["layout"] == name
        assert doc["graph"]["nodes"]
        assert doc["animation"]["flow_paths"]


def test_interactive_html_includes_search_control():
    renderer = load("render_animated_diagram")
    svg_renderer = load("svg_renderer")
    spec = json.loads((ROOT / "assets" / "examples" / "hub-spec.json").read_text(encoding="utf-8"))
    renderer.apply_style(spec["style"])
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    html = svg_renderer._build_interactive_html(doc, '<svg xmlns="http://www.w3.org/2000/svg"></svg>', "hub")
    assert 'id="search"' in html
    assert "搜索节点" in html


def test_illustrated_icons_are_recorded_and_validated():
    renderer = load("render_animated_diagram")
    path = ROOT / "assets" / "examples" / "illustrated-loop-spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    report = renderer.validate_spec(spec, path.parent)
    assert report["ok"], report
    renderer.apply_style(spec["style"])
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    illustrated = [op for op in doc["ops"] if op.get("op") == "icon" and op.get("iconStyle") in ("illustrated", "hero")]
    assert len(illustrated) >= 10
    assert {op["iconMotion"] for op in illustrated} >= {"think-pulse", "gear-spin", "eye-scan", "memory-write"}


def test_invalid_illustration_fields_return_errors():
    renderer = load("render_animated_diagram")
    spec = {"layout": "pipeline", "stages": [
        {"title": "A", "icon": "brain", "icon_style": "oil"},
        {"title": "B", "icon": "eye", "icon_motion": "blink-random"},
    ]}
    report = renderer.validate_spec(spec)
    assert not report["ok"]
    assert any(e["path"].endswith("icon_style") for e in report["errors"])
    assert any(e["path"].endswith("icon_motion") for e in report["errors"])


def test_illustrated_svg_contains_vector_semantics():
    renderer = load("render_animated_diagram")
    svg_renderer = load("svg_renderer")
    if not svg_renderer.is_available():
        return
    path = ROOT / "assets" / "examples" / "illustrated-loop-spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    renderer.apply_style(spec["style"])
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    with tempfile.TemporaryDirectory() as tmp:
        result = svg_renderer.render_all(doc, Path(tmp), "illustrated", formats=("svg",))
        markup = Path(result["svg"]).read_text(encoding="utf-8")
    assert 'data-icon-illustration="brain"' in markup
    assert 'data-icon-illustration="gear"' in markup
    assert 'data-icon-illustration="eye"' in markup


def test_icon_atlas_uses_25_distinct_semantics():
    renderer = load("render_animated_diagram")
    path = ROOT / "assets" / "examples" / "illustrated-icon-catalog-spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    report = renderer.validate_spec(spec, path.parent)
    assert report["ok"], report
    renderer.apply_style(spec["style"])
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    semantics = [op["semantic"] for op in doc["ops"] if op.get("op") == "icon" and op.get("iconStyle") == "illustrated"]
    assert len(semantics) == 25
    assert len(set(semantics)) == 25


def test_loop_workflow_pack_validates_with_dedicated_semantics():
    renderer = load("render_animated_diagram")
    path = ROOT / "assets" / "examples" / "loop-icon-pack-spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    report = renderer.validate_spec(spec, path.parent)
    assert report["ok"], report
    assert not report["warnings"], report["warnings"]
    renderer.apply_style(spec["style"])
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    semantics = [op["semantic"] for op in doc["ops"] if op.get("op") == "icon" and op.get("iconStyle") == "illustrated"]
    assert len(semantics) == 20
    assert len(set(semantics)) == 20
    expected = {"loop", "decision", "split", "merge", "wait", "orchestrator", "subagent",
                "handoff", "human", "plan", "score", "compare", "sandbox", "checkpoint",
                "error", "rollback", "retry", "ingest", "emit", "trigger"}
    assert set(semantics) == expected


def test_graph_workflow_example_validates_and_renders_ops():
    renderer = load("render_animated_diagram")
    path = ROOT / "assets" / "examples" / "graph-workflow-spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    report = renderer.validate_spec(spec, path.parent)
    assert report["ok"], report
    assert not report["warnings"], report["warnings"]
    renderer.apply_style(spec.get("style", "default"))
    _ex, _img, doc = renderer.render_static_with_ops(spec)
    assert doc["layout"] == "graph"
    assert len(doc["graph"]["nodes"]) == 7
    assert len(doc["animation"]["flow_paths"]) == 9
    dashed = [e for e in doc["graph"]["edges"] if e["style"] == "dashed"]
    assert len(dashed) == 3
    # Every flow color must already be resolved through the theme (hex).
    assert all(fp["color"].startswith("#") for fp in doc["animation"]["flow_paths"])


def test_graph_validation_rejects_bad_refs_kinds_direction():
    renderer = load("render_animated_diagram")
    spec = {
        "layout": "graph",
        "direction": "diagonal",
        "nodes": [
            {"id": "a", "label": "A", "kind": "blob"},
            {"id": "a", "label": "Dup"},
        ],
        "edges": [
            {"from": "a", "to": "ghost"},
            {"from": "a", "to": "a", "kind": "wormhole"},
        ],
    }
    report = renderer.validate_spec(spec)
    assert not report["ok"]
    paths = {e["path"] for e in report["errors"]}
    assert "$.direction" in paths
    assert "$.nodes[0].kind" in paths
    assert "$.nodes[1].id" in paths
    assert "$.edges[0].to" in paths
    assert "$.edges[1].kind" in paths


def test_bad_nested_types_and_canvas_return_structured_errors():
    renderer = load("render_animated_diagram")
    report = renderer.validate_spec({"layout": "panorama", "canvas": {"fps": 0}, "core": "bad"})
    assert not report["ok"]
    assert any(e["path"] == "$.core" for e in report["errors"])


def test_pillow_formats_are_exact_and_unknown_formats_fail():
    script = ROOT / "scripts" / "render_animated_diagram.py"
    spec = ROOT / "assets" / "examples" / "pipeline-spec.json"
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run([sys.executable, str(script), "--renderer", "pillow", "--icon-engine", "pillow",
                               "--spec", str(spec), "--outdir", tmp, "--basename", "only", "--formats", "png"],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert sorted(p.name for p in Path(tmp).iterdir()) == ["only.png"]
        bad = subprocess.run([sys.executable, str(script), "--spec", str(spec), "--outdir", tmp,
                              "--formats", "png,wat"], capture_output=True, text=True)
        assert bad.returncode != 0
        assert "unknown format" in bad.stderr
