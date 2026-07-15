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
BASE_PACKAGES = ("PIL", "svg.path")
OPTIONAL_PACKAGES = ("playwright",)
REQUIRED_ASSETS = (
    "assets/vendor/rough.js",
    "assets/fonts/Excalifont-Regular.ttf",
    "assets/fonts/NotoSansSC-Regular.ttf",
)


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
for name in BASE_PACKAGES + OPTIONAL_PACKAGES:
    spec = importlib.util.find_spec(name)
    report["packages"][name] = {"available": spec is not None}
ffmpeg = shutil.which("ffmpeg")
report["tools"]["ffmpeg"] = {"available": bool(ffmpeg), "path": ffmpeg, "version": version([ffmpeg, "-version"]) if ffmpeg else None}
for rel in REQUIRED_ASSETS:
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
base_ok = all(x["available"] for x in report["assets"].values()) and all(
    report["packages"][name]["available"] for name in BASE_PACKAGES
)
browser_ok = (
    report["packages"]["playwright"]["available"]
    and report["tools"].get("chromium", {}).get("available", False)
)
publish_ok = browser_ok and report["tools"]["ffmpeg"]["available"]
report["capabilities"] = {
    "base_ok": base_ok,
    "browser_ok": browser_ok,
    "publish_ok": publish_ok,
    "notes": {
        "base_ok": "PNG, GIF, and Excalidraw are available through the Pillow pipeline.",
        "browser_ok": "Browser-rendered PNG, GIF, SVG, and HTML are available.",
        "publish_ok": "Full browser publishing, including MP4, is available.",
    },
}
report["ok"] = base_ok
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["ok"] else 1)
