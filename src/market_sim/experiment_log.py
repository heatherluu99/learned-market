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


#: Paths whose state determines whether a run is reproducible from its hash:
#: the code, the configuration and the spec that the run was produced by.
SOURCE_PATHS = ("src", "experiments", "tools", "tests", "docs", "ROADMAP.md")


def git_commit(repo_root: Path, source_paths: tuple[str, ...] = SOURCE_PATHS) -> str:
    """Current HEAD, suffixed '-dirty' when the run's *inputs* are uncommitted.

    Dirtiness is judged over source paths only, not the whole tree. The
    question this column has to answer is "was the code that produced this run
    committed", and a run necessarily rewrites its own outputs — results/,
    experiment_log.csv, project_tracking.pptx — while it executes. Checking the
    whole tree marks every run dirty by construction, which is what happened to
    the Phase 1-5 rows: all nine carried the same hash with a '-dirty' suffix,
    so none of them bound results to a reproducible state.

    The suffix is kept, and still means what it says: a run recorded against
    modified source is not reproducible from the hash alone, and that belongs
    in the record rather than hidden.
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
        ["git", "status", "--porcelain", "--", *source_paths],
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
