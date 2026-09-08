"""Inline the exported decisions into a self-contained Agent Inspector page.

Same shape as the Experiment Explorer's build step: a template with one
placeholder, so the page opens from a filesystem with no server.

    python tools/export_agent_inspector.py && python tools/build_agent_inspector.py
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "viz" / "agent_inspector.template.html"
DATA = REPO_ROOT / "viz" / "agent_inspector_data.json"
OUT = REPO_ROOT / "viz" / "agent_inspector.html"
PLACEHOLDER = "/*__DATA__*/"


def main() -> int:
    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE} has no {PLACEHOLDER} to fill")
    OUT.write_text(template.replace(PLACEHOLDER, DATA.read_text()))
    size = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({size:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
