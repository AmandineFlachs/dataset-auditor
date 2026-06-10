"""Turn downloaded benchmark results into a ``model x task -> score`` table.

After ``kaggle b t run`` and ``kaggle b t download -o ./results``, each run is a
``*.run.json`` file (one per task per model). This reads them and prints a Markdown
table so swapping models is a one-glance decision: which model is best placed to advise
on a given dataset's triage.

    python benchmarks/compare.py ./results                 # print the table
    python benchmarks/compare.py ./results -o results/scoreboard.md

Stdlib only (no pandas, no kbench) so it runs anywhere. The score is the fraction of a
run's assertions that PASSED -- the certain part. The model label is best-effort: real
``kaggle b t run`` populates ``modelVersion``; if it is empty (e.g. a local stub run)
the file stem is used, so naming files ``<task>.<model>.run.json`` keeps the table tidy.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

PASS_SUFFIX = "PASSED"  # BENCHMARK_TASK_RUN_ASSERTION_STATUS_PASSED


def score_assertions(data: dict) -> tuple[int, int]:
    """Return ``(passed, total)`` over a run's assertions."""
    assertions = data.get("assertions", []) or []
    passed = sum(1 for a in assertions if str(a.get("status", "")).endswith(PASS_SUFFIX))
    return passed, len(assertions)


def extract_task(data: dict) -> str:
    return (data.get("taskVersion") or {}).get("name") or "unknown-task"


def extract_model(data: dict, fallback: str = "unknown-model") -> str:
    """Best-effort model identifier from a run, else ``fallback``."""
    mv = data.get("modelVersion") or {}
    for key in ("slug", "name", "displayName", "model", "modelSlug", "versionName"):
        val = mv.get(key)
        if val:
            return str(val)
    for conv in data.get("conversations", []) or []:
        slug = conv.get("modelVersionSlug", "")
        if slug and "DEPRECATED" not in slug:  # the per-conversation slug is deprecated
            return slug
    return fallback


def _model_from_filename(path: Path, task: str) -> str:
    """Derive a model label from the file name when the run carries none.

    Strips the task name, a ``-run_id_...``/``-Run_N`` suffix, and the ``.run`` part,
    leaving whatever distinguishes the file (ideally the model slug).
    """
    stem = path.name[: -len(".run.json")] if path.name.endswith(".run.json") else path.stem
    stem = re.sub(r"[-_.]?run[-_]?id.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[-_.]?Run[-_ ]?\d+$", "", stem)
    for sep in (".", "-", "_"):
        stem = stem.replace(f"{task}{sep}", "").replace(f"{sep}{task}", "")
    stem = stem.replace(task, "").strip("-_. ")
    return stem or "unknown-model"


def load_run(path: str | Path) -> dict:
    """Parse one ``*.run.json`` into ``{task, model, passed, total}``."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    task = extract_task(data)
    passed, total = score_assertions(data)
    model = extract_model(data, fallback=_model_from_filename(path, task))
    return {"task": task, "model": model, "passed": passed, "total": total}


def find_runs(results_dir: str | Path) -> list[dict]:
    """Load every ``*.run.json`` under ``results_dir`` (recursively)."""
    paths = sorted(glob.glob(str(Path(results_dir) / "**" / "*.run.json"), recursive=True))
    return [load_run(p) for p in paths]


def _cell(passed: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{passed}/{total} ({passed / total:.0%})"


def build_table(runs: list[dict]) -> str:
    """Render runs as a Markdown ``model x task`` table, best overall first.

    Multiple runs of the same (model, task) are summed, so re-runs accumulate. An
    Overall column aggregates every task for the model.
    """
    if not runs:
        return "_No `*.run.json` files found._"

    cells: dict[tuple[str, str], list[int]] = {}
    for r in runs:
        p, t = cells.setdefault((r["model"], r["task"]), [0, 0])
        cells[(r["model"], r["task"])] = [p + r["passed"], t + r["total"]]

    tasks = sorted({task for _, task in cells})
    models = sorted({model for model, _ in cells})

    totals = {m: [0, 0] for m in models}
    for (m, _t), (p, t) in cells.items():
        totals[m][0] += p
        totals[m][1] += t
    models.sort(key=lambda m: (-(totals[m][0] / totals[m][1]) if totals[m][1] else 0, m))

    header = ["Model", *tasks, "Overall"]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for m in models:
        row = [m]
        for task in tasks:
            row.append(_cell(*cells[(m, task)]) if (m, task) in cells else "—")
        row.append(_cell(*totals[m]))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build a model x task score table from benchmark runs.")
    ap.add_argument("results_dir", nargs="?", default="./results",
                    help="Directory of downloaded *.run.json files (default: ./results).")
    ap.add_argument("-o", "--out", type=Path, help="Write the Markdown table here (else print).")
    args = ap.parse_args(argv)

    runs = find_runs(args.results_dir)
    table = build_table(runs)
    title = f"# Benchmark scoreboard ({len(runs)} run{'s' if len(runs) != 1 else ''})\n\n"
    if args.out:
        args.out.write_text(title + table + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(title + table)


if __name__ == "__main__":
    main()
