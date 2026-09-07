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


def _warn_if_dirty(row: dict) -> None:
    """Say so, loudly, when a run is being recorded against modified source.

    The hash then identifies a tree that does not contain the code that
    produced the row, so the result is not reproducible from it. Nine rows
    were written this way before anything said so - the natural workflow is
    to run an experiment and commit it afterwards, which is exactly the
    order that produces a dirty hash.
    """
    if str(row.get("git_commit", "")).endswith("-dirty"):
        import sys

        print(
            f"  ! experiment_log: '{row.get('experiment_id')}' is being "
            f"recorded against MODIFIED source.\n"
            f"    The hash does not identify the code that produced it. "
            f"Commit first, then re-run, to bind the two.",
            file=sys.stderr, flush=True,
        )


def append_row(log_path: Path, row: dict[str, object]) -> None:
    missing = set(COLUMNS) - set(row)
    if missing:
        raise ValueError(f"experiment_log row is missing columns: {sorted(missing)}")
    _warn_if_dirty(row)
    unexpected = set(row) - set(COLUMNS)
    if unexpected:
        raise ValueError(f"experiment_log row has unknown columns: {sorted(unexpected)}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    # An experiment id identifies an experiment, so re-running one *replaces*
    # its row rather than appending a second. Appending left the log with 31
    # rows for 27 experiments and the Experiment Explorer showing a phase
    # twice, because every re-run at a cleaner commit added a row instead of
    # superseding the one it was redoing. Position is kept, so the log stays in
    # the order the experiments were first run.
    existing: list[dict[str, object]] = []
    if log_path.exists():
        with log_path.open(newline="") as handle:
            existing = list(csv.DictReader(handle))

    replaced = False
    for i, previous in enumerate(existing):
        if previous.get("experiment_id") == row.get("experiment_id"):
            existing[i] = {k: row[k] for k in COLUMNS}
            replaced = True
            break
    if not replaced:
        existing.append({k: row[k] for k in COLUMNS})

    with log_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(existing)
