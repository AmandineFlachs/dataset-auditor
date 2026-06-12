"""Cross-model sweep over the Kaggle model proxy, run LOCALLY.

Same cases, prompts, and grading as the kbench task files and ``local_run.py``, but
routes each case through ``kbench.llms[<model>]`` for every model the proxy exposes. The
task code (which imports ``auditor`` + ``harness``) therefore runs on this machine and
only inference goes to Kaggle, sidestepping server-side ``kaggle b t run`` imports. The
result is the model x task scoreboard.

Needs ``kaggle b init`` first (writes ``.env`` proxy creds; they expire ~hourly). Run:

    PYTHONIOENCODING=utf-8 python benchmarks/proxy_sweep.py
"""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import time

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))


def _load_env() -> None:
    """Load the repo-root ``.env`` into the environment before importing kbench.

    ``kaggle b init`` writes ``.env`` at the repo root, but kbench discovers it relative
    to the entry script's directory (``benchmarks/`` when this file is run directly), not
    the CWD. Without the model-proxy creds in the environment ``kbench.llms`` comes up
    empty. Inject the vars first (``setdefault``, so a real env var still wins).
    """
    env = _HERE.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


_load_env()

import kaggle_benchmarks as kbench

from auditor.checks.labels import LabelVerdict, build_label_prompt
from auditor.datasets import get
from auditor.triage import VerdictResult, build_verdict_prompt

import harness


def _registry() -> list[tuple[str, object]]:
    """Snapshot ``kbench.llms`` to ``(name, model)`` pairs, ONCE.

    ``kbench.llms`` is repopulated lazily by a background thread, so reading
    ``.keys()`` and then re-indexing ``kbench.llms[name]`` in a loop races: a key the
    snapshot saw can be transiently absent when indexed, surfacing as ``KeyError``.
    Copying the dict in one shot captures stable name->model pairs and never re-indexes.
    Retry the copy briefly until it is non-empty so we don't snapshot mid-population.
    """
    for _ in range(50):
        snapshot = list(dict(kbench.llms).items())
        if snapshot:
            return snapshot
        time.sleep(0.1)
    return []


def _ask(model, prompt: str, schema):
    # kbench echoes the whole conversation to stdout; mute it so only the scoreboard shows.
    with contextlib.redirect_stdout(io.StringIO()):
        return model.prompt(prompt, schema=schema)


def score_labels(model) -> tuple[int, int, int]:
    meta = harness.load_meta("elements")
    domain = harness.resolve_domain_context(meta)
    cases = harness.load_cases(harness.case_dir("elements") / "labels.jsonl")
    ok = err = 0
    for c in cases:
        rule, row = harness.label_case_to_inputs(c, meta)
        body = build_label_prompt(rule, row, list(rule.context_columns))
        try:
            ok += harness.grade_label(_ask(model, harness.compose_prompt(domain, body), LabelVerdict), c)
        except Exception:
            err += 1
    return ok, len(cases), err


def score_verdict(model) -> tuple[int, int, int]:
    meta = harness.load_meta("lemat_bulk")
    spec = get(meta["spec"])
    domain = spec.domain_context
    cases = harness.load_cases(harness.case_dir("lemat_bulk") / "triage_verdict.jsonl")
    ok = err = 0
    for c in cases:
        body = build_verdict_prompt(harness.verdict_case_to_issue(c), spec)
        try:
            ok += harness.grade_verdict(_ask(model, harness.compose_prompt(domain, body), VerdictResult), c)
        except Exception:
            err += 1
    return ok, len(cases), err


def main() -> None:
    registry = _registry()
    if not registry:
        print("no models in kbench.llms; run `kaggle b init` first to refresh .env creds")
        raise SystemExit(1)
    rows = []
    skipped = []
    for name, model in registry:
        try:
            lo, ln, le = score_labels(model)
            vo, vn, ve = score_verdict(model)
        except Exception as exc:  # one inaccessible model must not sink the whole sweep
            skipped.append((name, type(exc).__name__))
            print(f"{name:42s} SKIPPED ({type(exc).__name__})", flush=True)
            continue
        rows.append((name, lo, ln, vo, vn, le + ve))
        tail = f"  (errors {le + ve})" if le + ve else ""
        print(f"{name:42s} labels {lo}/{ln}  verdict {vo}/{vn}{tail}", flush=True)
    rows.sort(key=lambda r: -(r[1] + r[3]))
    print("\n| model | labels | triage-verdict | overall |")
    print("|---|---|---|---|")
    for name, lo, ln, vo, vn, _ in rows:
        print(f"| {name} | {lo}/{ln} | {vo}/{vn} | {lo + vo}/{ln + vn} |")
    if skipped:
        print("\nskipped (inaccessible this run): "
              + ", ".join(f"{n} [{e}]" for n, e in skipped))


if __name__ == "__main__":
    main()
