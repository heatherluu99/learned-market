"""Build the Experiment Explorer page from the log and the git history.

One panel per logged run: the question it asked, the figure it produced, its
provenance, and the commits that made it. The commit bodies are the point -
this project's record of what was *tried* and corrected lives there, not in
the results, and a gallery of final figures would hide exactly the part worth
reading.

Regenerated rather than edited, so it stays current as runs are added:

    python tools/build_experiment_explorer.py
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "viz/experiment_explorer.template.html"
OUT = REPO_ROOT / "viz/experiment_explorer.html"
PLACEHOLDER = "/*__DATA__*/"

#: Human titles. Everything else about a run is read from the log, but the log
#: stores an identifier and not a name, and "phase7b_ucb" is not a title.
TITLES = {
    "phase1_main": "Transaction mechanics",
    "phase1_inventory_pressure": "Inventory pressure (diagnostic arm)",
    "phase2_main": "Buyer heterogeneity",
    "phase2_common_alpha": "Common price sensitivity (diagnostic arm)",
    "phase3_main": "Stall position and visibility",
    "phase4_main": "Promotions, market arm",
    "phase4_forced_promotion": "Promotions, forced arms",
    "phase5_additive": "Budget cliff, additive reading",
    "phase5_cliff_only": "Budget cliff, replace reading",
    "phase6_main": "Repeated interaction, memory ON",
    "phase6_no_loyalty": "Repeated interaction, memory OFF",
    "phase7a_fixed": "Fixed pricing (7a baseline)",
    "phase7a_hill": "Hill-climbing heuristic (7a)",
    "phase7b_eps": "Bandit, epsilon-greedy (7b)",
    "phase7b_ucb": "Bandit, UCB1 (7b)",
    "phase7c_diagnostic": "Context invariance (7c, skipped)",
    "phase7d_rl": "Q-network on a multi-week return (7d)",
    "phase7e1_registered_grid": "Stock loyalty, the registered grid (7e-1)",
    "phase7e1_calibration": "Stock loyalty, calibrated (7e-1)",
    "phase7e2_headroom": "Intertemporal headroom (7e-2)",
    "phase7e3a_context": "Does context pay? (7e-3a)",
    "phase7e3b_horizon": "Does the horizon pay? (7e-3b)",
    "phase8_entry_exit": "Entry, exit and market structure",
    "phase9a_gate_evidence": "Teacher policy and the WTP decision (9a gate)",
}

#: Runs whose figure was later overwritten in place by a successor writing to
#: the same path. The page would otherwise imply the figure shown is the one
#: that run produced.
OVERWRITTEN = {
    "phase7e1_registered_grid":
        "The figure above is its successor's. This run's own figure was written "
        "to the same path and overwritten; it is recoverable at commit 208f785.",
}

#: A run's outcome, which no column in the log records - it is the tag, and
#: for a superseded run the absence of one.
STATUS = {
    "phase7c_diagnostic": "skipped",
    "phase7e1_registered_grid": "superseded",
    "phase7e1_calibration": "calibrated",
    "phase7e2_headroom": "headroom",
    "phase7e3a_context": "headroom",
    "phase7e3b_horizon": "headroom",
    "phase9a_gate_evidence": "open",
}

#: Ordered, and the order matters: "Implement Phase 7e-2: ... headroom gate"
#: is implementation, not a gate commit, and a first-match-wins scan over
#: keywords gets that backwards.
COMMIT_KINDS = (
    ("correction", r"^(correct|redesign|fix|re-run|drop)\b", "#C9922E", "#FBF3E2"),
    ("implementation", r"^(implement|add|build|split|upgrade)\b", "#3B3F8C", "#EEF0FA"),
    ("gate", r"\bgate:", "#7A3B69", "#F5EDF3"),
    ("results", r"\bresults?:|^record\b", "#1E7A4D", "#E8F4EE"),
)


def group_of(identifier: str) -> str:
    """1, 7a, 7e-1 ... derived from the identifier, not hand-listed."""
    m = re.match(r"^phase(\d+)(e\d+|[a-z])?", identifier)
    if not m:
        return "other"
    number, suffix = m.group(1), m.group(2) or ""
    if suffix.startswith("e"):
        return f"{number}e-{suffix[1:]}"
    return f"{number}{suffix}"


def figures() -> dict[str, list[dict]]:
    """Every results PNG, embedded, keyed by the group its directory names.

    Embedded rather than linked because the page has to open from a filesystem
    with no server, which is the same constraint the Phase 6 page is built to.
    """
    out: dict[str, list[dict]] = {}
    for path in sorted((REPO_ROOT / "results").rglob("*.png")):
        group = group_of(path.relative_to(REPO_ROOT / "results").parts[0])
        blob = base64.b64encode(path.read_bytes()).decode()
        out.setdefault(group, []).append({
            "src": f"data:image/png;base64,{blob}",
            "caption": str(path.relative_to(REPO_ROOT)),
        })
    return out


def commits() -> list[dict]:
    raw = subprocess.run(
        ["git", "log", "--format=%h%x1f%ad%x1f%s%x1f%b%x1e", "--date=short"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    out = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        sha, date, subject, body = (record.strip().split("\x1f") + ["", "", "", ""])[:4]
        low = subject.lower()
        kind, colour, background = "work", "#5b616e", "#f6f7f9"
        for name, pattern, c, b in COMMIT_KINDS:
            if re.search(pattern, low):
                kind, colour, background = name, c, b
                break
        out.append({
            "sha": sha, "date": date, "subject": subject, "body": body.strip(),
            "kind": kind, "kindColor": colour, "kindBg": background,
        })
    return out


def commits_for(group: str, history: list[dict]) -> list[dict]:
    """Commits whose subject names this phase.

    Matched on the subject alone. Bodies mention earlier phases constantly -
    that cross-referencing is a feature of the messages and would make body
    matching assign half the history to Phase 1.
    """
    tokens = {group.lower(), group.replace("-", "").lower()}
    if group[0].isdigit() and not group[1:]:
        tokens |= {f"phase {group}"}
    else:
        tokens |= {f"phase {t}" for t in tokens}
    picked = []
    for c in history:
        low = c["subject"].lower()
        if any(re.search(rf"(?<![\w.]){re.escape(t)}(?![\w-])", low) for t in tokens):
            picked.append({**c, "open": c["kind"] in ("correction", "results")})
    return picked


def main() -> int:
    log = pd.read_csv(REPO_ROOT / "experiment_log.csv")
    figs, history = figures(), commits()
    tags = subprocess.run(["git", "tag"], cwd=REPO_ROOT, capture_output=True,
                          text=True, check=True).stdout.split()

    experiments = []
    for _, row in log.iterrows():
        identifier = str(row["experiment_id"])
        group = group_of(identifier)
        if identifier not in TITLES:
            print(f"  warning: {identifier} has no title, using the identifier")
        experiments.append({
            "id": identifier,
            "group": group,
            "title": TITLES.get(identifier, identifier),
            "status": STATUS.get(
                identifier,
                "validated" if f"phase{group.replace('-', '')}-validated" in tags
                else "open",
            ),
            "question": row["research_question"],
            "result": row["result_summary"],
            "mechanism": row["changed_mechanism"],
            "config": row["config_file"],
            "seeds": row["seed"],
            "commit": row["git_commit"],
            "transactions": row["transaction_count"],
            "participation": row["participation_rate"],
            "next": row["next_experiment"],
            "figures": figs.get(group, []),
            "note": OVERWRITTEN.get(identifier, ""),
            "commits": commits_for(group, history),
        })

    # Collected rather than grepped: parametrized cases are separate tests and
    # a count of `def test_` reports about half the real number.
    collected = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    match = re.search(r"(\d+) tests? collected", collected)
    n_tests = int(match.group(1)) if match else 0

    payload = {
        "meta": {"commits": len(history), "tags": len(tags), "tests": n_tests},
        "experiments": experiments,
    }
    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE} has no {PLACEHOLDER} placeholder")
    OUT.write_text(template.replace(PLACEHOLDER, json.dumps(payload, separators=(",", ":"))))
    print(f"Wrote {OUT.relative_to(REPO_ROOT)} "
          f"({OUT.stat().st_size / 1024 / 1024:.1f} MB, {len(experiments)} runs, "
          f"{sum(len(e['figures']) for e in experiments)} figure slots, "
          f"{len(history)} commits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
