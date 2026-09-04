"""Append rows to experiment_log.csv.

The column set is fixed by docs/phase_specifications.md ("Logging Schema") and
must not be narrowed for Phases 1-8 just because most fields are "N/A" there —
the whole point is that Phase 1-8 rows and Phase 9+ rows stack into one table
without a migration.

Reading note: the "N/A" placeholders the schema mandates are written as the
literal string "N/A", but `pd.read_csv` converts that to NaN by default — which
silently defeats the reason the spec wants them ("so later filtering/joins work
cleanly"). Read this file with `pd.read_csv(path, keep_default_na=False)` when
the placeholder values matter, which they will from Phase 9 on.

Granularity note: the schema names a singular `seed`, but a Phase 1 experiment
is 30 seeds and the narrative fields (`result_summary`, `decision_implication`,
`next_experiment`) only mean anything at the experiment level. So one row =
one experiment, and `seed` records the seed set (e.g. "0-29"). Per-seed numbers
live in run_summary.csv, which is where the slide generator reads them from.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

COLUMNS = [
    "experiment_id",
    "git_commit",
    "config_file",
    "phase",
    "seed",
    "n_buyers",
    "n_sellers",
    "model_used",
    "decision_type",
    "human_benchmark_id",
    "human_benchmark_status",
    "synthetic_cost_usd",
    "synthetic_latency_seconds",
    "research_question",
    "changed_mechanism",
    "transaction_count",
    "participation_rate",
    "result_summary",
    "decision_implication",
    "next_experiment",
]


def git_commit(repo_root: Path) -> str:
    """Current HEAD, suffixed '-dirty' when the tree has uncommitted changes.

    A run recorded against a dirty tree is not reproducible from the hash
    alone, so the suffix is part of the record rather than something to hide.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return "no_commit_yet"
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return f"{head}-dirty" if dirty else head


def append_row(log_path: Path, row: dict[str, object]) -> None:
    missing = set(COLUMNS) - set(row)
    if missing:
        raise ValueError(f"experiment_log row is missing columns: {sorted(missing)}")
    unexpected = set(row) - set(COLUMNS)
    if unexpected:
        raise ValueError(f"experiment_log row has unknown columns: {sorted(unexpected)}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists()
    with log_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
