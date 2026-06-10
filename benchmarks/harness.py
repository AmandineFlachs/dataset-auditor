"""Pure, model-free plumbing shared by the Kaggle benchmark task files.

This module deliberately imports neither ``kaggle_benchmarks`` nor ``httpx``: it only
loads golden cases from ``cases/<name>/`` and grades a model's (already-parsed) answer
against the labelled ground truth. That keeps it unit-testable in CI with no live model
and no Kaggle SDK (see ``tests/test_benchmark_harness.py``), and lets the kbench task
files stay thin wrappers around it.

The two tasks it serves:

* **labels** - categorical plausibility. A case carries a ``value`` plus ``context``;
  :func:`label_case_to_inputs` turns it into the exact ``(LabelRule, row)`` the shipped
  ``labels.build_label_prompt`` consumes, so the benchmark tests the production prompt.
* **triage-verdict** - real-defect-vs-expected-artifact. A case IS an aggregated issue
  dict (the shape ``triage.issue_groups`` produces); :func:`verdict_case_to_issue`
  hands it straight to ``triage.build_verdict_prompt``.

Ground truth lives in ``cases/<name>/*.jsonl`` (one JSON object per line) plus a
``meta.json`` that names the judged column / vocabulary (labels) or the source
``DatasetSpec`` whose ``domain_context`` grounds the prompt (triage-verdict).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from auditor.datasets import LabelRule, get

CASES_DIR = Path(__file__).resolve().parent / "cases"


def case_dir(name: str) -> Path:
    """Directory holding one benchmark's cases, e.g. ``case_dir("elements")``."""
    return CASES_DIR / name


def load_cases(path: str | Path) -> list[dict]:
    """Read a ``.jsonl`` fixture into a list of case dicts (blank lines skipped)."""
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_meta(name: str) -> dict:
    """Load ``cases/<name>/meta.json`` (the per-benchmark configuration)."""
    return json.loads((case_dir(name) / "meta.json").read_text(encoding="utf-8"))


def resolve_domain_context(meta: dict) -> str:
    """The factual grounding to prepend to a prompt.

    ``llm.py`` injects ``spec.domain_context`` as a separate system message; kbench's
    ``llm.prompt`` takes only a message string, so the task composes it into the prompt.
    A benchmark tied to a real dataset reads it from that ``DatasetSpec`` (no drift); a
    fixture-only benchmark (elements) carries its own ``domain_context`` in meta.json.
    """
    if "spec" in meta:
        return get(meta["spec"]).domain_context
    return meta.get("domain_context", "")


def compose_prompt(domain_context: str, body: str) -> str:
    """Mirror ``llm.py``: domain context first as grounding, then the task prompt."""
    return f"{domain_context}\n\n{body}" if domain_context else body


# -- labels (categorical plausibility) ----------------------------------------


def label_case_to_inputs(case: dict, meta: dict) -> tuple[LabelRule, pd.Series]:
    """Turn a label case into the ``(rule, row)`` that ``build_label_prompt`` expects."""
    context = case.get("context", {})
    rule = LabelRule(
        column=meta["column"],
        context_columns=tuple(context.keys()),
        allowed=tuple(meta.get("allowed", ())),
    )
    row = pd.Series({meta["column"]: case["value"], **context})
    return rule, row


def label_actual(verdict) -> str:
    """Map a parsed ``LabelVerdict`` to the fixture's vocabulary for comparison."""
    return "plausible" if verdict.plausible else "implausible"


def grade_label(verdict, case: dict) -> bool:
    """True when the model's plausibility judgement matches the golden label."""
    return label_actual(verdict) == case["expected"]


# -- triage-verdict (real defect vs expected artifact) ------------------------

_ISSUE_KEYS = ("check", "field", "severity", "count", "message", "samples")


def verdict_case_to_issue(case: dict) -> dict:
    """Project a verdict case onto the issue dict ``build_verdict_prompt`` reads."""
    return {k: case[k] for k in _ISSUE_KEYS if k in case}


def grade_verdict(result, case: dict) -> bool:
    """True when the model's real/expected verdict matches the golden label."""
    return result.verdict == case["expected"]
