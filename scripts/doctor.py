#!/usr/bin/env python3
"""Report Archscribe runtime capabilities without changing the environment."""
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
    except Exception:
        return None


report = {
    "ok": True,
    "python": {"version": platform.python_version(), "executable": sys.executable},
    "packages": {},
    "tools": {},
    "assets": {},
}
for name in ("PIL", "svg.path", "playwright"):
    spec = importlib.util.find_spec(name)
    report["packages"][name] = {"available": spec is not None}
ffmpeg = shutil.which("ffmpeg")
report["tools"]["ffmpeg"] = {"available": bool(ffmpeg), "path": ffmpeg, "version": version([ffmpeg, "-version"]) if ffmpeg else None}
for rel in ("assets/vendor/rough.js", "assets/fonts/Excalifont-Regular.ttf", "assets/fonts/NotoSansSC-Regular.ttf"):
    path = ROOT / rel
    report["assets"][rel] = {"available": path.is_file(), "bytes": path.stat().st_size if path.is_file() else 0}
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        report["tools"]["chromium"] = {"available": True, "version": browser.version}
        browser.close()
except Exception as exc:
    report["tools"]["chromium"] = {"available": False, "error": str(exc)[:300]}
report["ok"] = all(x["available"] for x in report["assets"].values()) and report["packages"]["PIL"]["available"] and report["packages"]["svg.path"]["available"]
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["ok"] else 1)
