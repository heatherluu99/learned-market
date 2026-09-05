"""Inject the exported season data into the Phase 6 page template.

The template is the diffable source; the built page is a single self-contained
artifact that opens from the filesystem with no server, which is what
docs/phase_specifications.md asks for. Keeping them separate means a 19 KB
blob of run data never shows up in a review of the page's own code.

    python tools/export_phase6_viz.py --seed 0
    python tools/build_phase6_viz.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "/*__DATA__*/"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=REPO_ROOT / "viz/phase6_market.template.html")
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "viz/phase6_data.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "viz/phase6_market.html")
    args = parser.parse_args()

    template = args.template.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"{args.template} has no {PLACEHOLDER} placeholder")
    payload = json.loads(args.data.read_text())  # parsed to fail loudly on bad JSON

    page = template.replace(PLACEHOLDER, json.dumps(payload, separators=(",", ":")))
    args.out.write_text(page)
    print(
        f"Wrote {args.out.relative_to(REPO_ROOT)} "
        f"({args.out.stat().st_size / 1024:.0f} KB, seed {payload['meta']['seed']}, "
        f"{payload['meta']['weeks']} weeks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
