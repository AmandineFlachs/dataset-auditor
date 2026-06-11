"""Local benchmark runner: score the auditor's two judgement tasks against a LOCAL
LLM, with no Kaggle SDK in the loop.

This is the Phase-2 (local-model) counterpart to the kbench task files. It reuses the
exact same pieces they do -- the model-free ``harness`` (case loading + grading) and the
SHIPPED prompt builders (``labels.build_label_prompt``, ``triage.build_verdict_prompt``)
plus output schemas -- but sends each case prompt through the auditor's own
``LLMClient`` to a local vLLM endpoint instead of ``kbench.llm`` (Kaggle's proxy).

Because the cases, prompts, and grading are identical to the Kaggle tasks, a model's
local score here previews the score it would get on Kaggle Benchmarks. The only
differences are the transport (local vLLM vs Kaggle proxy) and the model.

Run (server up; point at the model via env):

    AUDITOR_LLM_MODEL=Qwen/Qwen3-4B python benchmarks/local_run.py
    AUDITOR_LLM_MODEL=Qwen/Qwen3-4B python benchmarks/local_run.py --task verdict
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# Make `import harness` and `import auditor` work when run as `python benchmarks/...py`.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

from auditor.checks.labels import LabelVerdict, build_label_prompt
from auditor.datasets import get
from auditor.llm import LLMClient, LLMError
from auditor.triage import VerdictResult, build_verdict_prompt

import harness


def _judge(client: LLMClient, body: str, domain: str, schema):
    """Send one case prompt, mirroring the kbench tasks' prompt composition.

    The kbench tasks fold the domain context into the prompt string (their proxy takes
    only a string), so we do the same and pass ``context=""``, keeping the user-visible
    prompt identical to the Kaggle run for apples-to-apples scores.
    """
    return client.judge(harness.compose_prompt(domain, body), schema, context="")


def run_labels(client: LLMClient) -> list[tuple]:
    meta = harness.load_meta("elements")
    domain = harness.resolve_domain_context(meta)
    cases = harness.load_cases(harness.case_dir("elements") / "labels.jsonl")
    rows = []
    for case in cases:
        rule, row = harness.label_case_to_inputs(case, meta)
        body = build_label_prompt(rule, row, list(rule.context_columns))
        try:
            verdict = _judge(client, body, domain, LabelVerdict)
            rows.append((case["id"], case["expected"], harness.label_actual(verdict),
                         harness.grade_label(verdict, case), verdict.reason))
        except LLMError as exc:
            rows.append((case["id"], case["expected"], "ERROR", False, str(exc)[:90]))
    return rows


def run_verdict(client: LLMClient) -> list[tuple]:
    meta = harness.load_meta("lemat_bulk")
    spec = get(meta["spec"])
    cases = harness.load_cases(harness.case_dir("lemat_bulk") / "triage_verdict.jsonl")
    rows = []
    for case in cases:
        issue = harness.verdict_case_to_issue(case)
        body = build_verdict_prompt(issue, spec)
        try:
            result = _judge(client, body, spec.domain_context, VerdictResult)
            rows.append((case["id"], case["expected"], result.verdict,
                         harness.grade_verdict(result, case), result.reason))
        except LLMError as exc:
            rows.append((case["id"], case["expected"], "ERROR", False, str(exc)[:90]))
    return rows


def _report(title: str, rows: list[tuple]) -> tuple[int, int]:
    passed = sum(1 for r in rows if r[3])
    print(f"\n=== {title}: {passed}/{len(rows)} ===")
    for cid, exp, got, ok, note in rows:
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid:32s} expected={exp:18s} got={got:18s}")
        if not ok:
            print(f"         {note}")
    return passed, len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=["labels", "verdict", "all"], default="all")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="Per-call timeout (s). Reasoning models need headroom over the default.")
    args = ap.parse_args()

    client = LLMClient.from_env(timeout=args.timeout)
    if not client.available():
        print(f"local LLM not reachable (model={client.model}); start the vLLM server first")
        raise SystemExit(1)
    print(f"running benchmark cases against local model: {client.model}")

    total_p = total_n = 0
    if args.task in ("labels", "all"):
        p, n = _report("labels-plausibility", run_labels(client))
        total_p, total_n = total_p + p, total_n + n
    if args.task in ("verdict", "all"):
        p, n = _report("triage-verdict", run_verdict(client))
        total_p, total_n = total_p + p, total_n + n
    print(f"\n=== OVERALL: {total_p}/{total_n} ===")


if __name__ == "__main__":
    main()
