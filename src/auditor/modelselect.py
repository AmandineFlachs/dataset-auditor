"""Per-domain model selection: score local LLMs on a domain's verdict cases.

The benchmark layer measures *which* local model to trust for a dataset's hardest,
model-judged decisions (real defect vs expected artifact). This module is the in-package
home of that scoring, so the user-facing ``auditor select-model`` command and the
developer ``benchmarks/local_run.py`` share one code path and can never drift.

The cases are the same JSONL the benchmark harness grades (one issue per line, with an
``expected`` verdict). Each is turned into the SHIPPED ``triage.build_verdict_prompt`` and
judged through the auditor's own :class:`~auditor.llm.LLMClient`, then graded by a plain
equality against ``expected`` — the model never originates the label, it is only measured
against the human/deterministic ground truth.

Import direction: ``benchmarks/harness.py`` imports ``auditor``, so ``auditor`` must not
import the harness. This module therefore carries its own small case projection + grader
(mirroring ``harness.verdict_case_to_issue`` / ``grade_verdict``); the kbench task files
keep using the harness, ``local_run`` imports :func:`score_model` from here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from auditor.datasets import DatasetSpec
from auditor.llm import LLMClient, LLMError
from auditor.triage import VerdictResult, build_verdict_prompt

# The issue keys a verdict case carries (mirrors ``harness._ISSUE_KEYS``). A case is an
# aggregated issue dict (the shape ``triage.issue_groups`` produces) plus ``expected``.
_ISSUE_KEYS = ("check", "field", "severity", "count", "message", "samples")

# A recommendation needs at least this many cases to be more than a coin toss.
MIN_CASES = 3


@dataclass(frozen=True)
class CaseResult:
    """One graded case: what the model answered vs the ground-truth verdict."""

    id: str
    expected: str
    got: str  # the model's verdict, or "ERROR" if the call failed
    ok: bool
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    """A model's score over one domain's verdict cases."""

    model: str
    rows: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.rows if r.ok)

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_cases(path: str | Path) -> list[dict]:
    """Read a ``.jsonl`` case file into a list of dicts (blank lines skipped).

    Same format the benchmark harness reads; kept here so the package never has to
    import the harness (see module docstring on import direction).
    """
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def case_to_issue(case: dict) -> dict:
    """Project a verdict case onto the issue dict ``build_verdict_prompt`` reads."""
    return {k: case[k] for k in _ISSUE_KEYS if k in case}


def _compose_prompt(domain_context: str, body: str) -> str:
    """Mirror ``llm.py`` / the harness: domain grounding first, then the task prompt."""
    return f"{domain_context}\n\n{body}" if domain_context else body


def score_model(client: LLMClient, cases: list[dict], spec: DatasetSpec) -> ScoreResult:
    """Score one model over a domain's verdict cases, reusing the shipped prompt builder.

    A failed call (server down/slow, unparseable reply) grades as a miss with the error
    recorded, so one flaky case can't abort the sweep. The grade is a plain equality of
    the model's ``verdict`` against the case's ``expected`` label.
    """
    rows: list[CaseResult] = []
    for case in cases:
        body = build_verdict_prompt(case_to_issue(case), spec)
        prompt = _compose_prompt(spec.domain_context, body)
        try:
            result = client.judge(prompt, VerdictResult, context="")
            rows.append(CaseResult(
                case["id"], case["expected"], result.verdict,
                result.verdict == case["expected"], result.reason,
            ))
        except LLMError as exc:
            rows.append(CaseResult(case["id"], case["expected"], "ERROR", False, str(exc)[:90]))
    return ScoreResult(model=client.model, rows=rows)


@dataclass(frozen=True)
class Recommendation:
    """The chosen model (or why no choice is warranted yet)."""

    model: str | None
    reason: str


def recommend(scores: list[ScoreResult], min_cases: int = MIN_CASES) -> Recommendation:
    """Pick the most reliable model, or decline when the evidence is too thin.

    Guards against crowning a model by luck on a tiny domain: with fewer than
    ``min_cases`` cases the ranking is not trustworthy, so no model is recommended.
    Ties (equal pass-rate) are reported honestly rather than broken arbitrarily.
    """
    scored = [s for s in scores if s.total]
    if not scored:
        return Recommendation(None, "no models scored (none reachable, or no cases).")
    total = scored[0].total
    if total < min_cases:
        return Recommendation(
            None,
            f"only {total} case(s) for this domain; need >= {min_cases} to recommend a "
            f"model. Audit and capture more decisions first.",
        )
    best = max(s.rate for s in scored)
    leaders = [s for s in scored if s.rate == best]
    if len(leaders) > 1:
        names = ", ".join(s.model for s in leaders)
        return Recommendation(
            leaders[0].model,
            f"tie at {best:.0%} ({leaders[0].passed}/{total}) between {names}; pick on "
            f"size/latency, or add harder cases to separate them.",
        )
    win = leaders[0]
    return Recommendation(
        win.model,
        f"{win.model} is most reliable here: {win.passed}/{total} ({win.rate:.0%}).",
    )


def render_scoreboard(domain: str, scores: list[ScoreResult], rec: Recommendation) -> str:
    """Render a Markdown ``model -> reliability`` table plus the recommendation.

    A single-task table (one domain's verdict), best first; kept small and in-package
    rather than reusing ``benchmarks/compare.build_table`` (which lives outside the
    package and reads ``*.run.json`` files).
    """
    lines = [f"| model | {domain}-verdict | errors |", "|---|---|---|"]
    for s in sorted(scores, key=lambda s: -s.rate):
        errs = sum(1 for r in s.rows if r.got == "ERROR")
        lines.append(f"| {s.model} | {s.passed}/{s.total} ({s.rate:.0%}) | {errs or ''} |")
    lines.append("")
    lines.append(f"**Recommended:** {rec.model or 'none'} — {rec.reason}")
    return "\n".join(lines)
