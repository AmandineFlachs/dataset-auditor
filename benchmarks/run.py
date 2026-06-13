"""Run a label-plausibility benchmark task against a local LLM (or a mock).

Task-agnostic: pass --task <dir under benchmarks/> (default labels_plausibility). This is
the ONLY impure file in the benchmark layer — the sole consumer of auditor.llm.LLMClient.
The pure grader/metrics/baselines/freeze do the rest, so the scientific logic stays
model-free and CI-testable.

EVAL_PROTOCOL.md gates the held-out split: --split test is refused without --confirm-final
AND a passing prompt-freeze check.

    python benchmarks/run.py --task labels_plausibility   --split dev          --reasoning --model Qwen/Qwen3-4B
    python benchmarks/run.py --task element_classification --split test --confirm-final --reasoning --model Qwen/Qwen3-4B
    python benchmarks/run.py --task labels_plausibility   --split dev --mock        # CI smoke
"""

from __future__ import annotations

import argparse
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent          # benchmarks/
_REPO = _HERE.parent
sys.path.insert(0, str(_HERE))                            # so `import shared` works
sys.path.insert(0, str(_REPO / "src"))                   # so `import auditor` works

import httpx  # noqa: E402

from shared import baselines, cases, freeze, grader, leakage, metrics  # noqa: E402

from auditor.checks.labels import LabelVerdict  # noqa: E402
from auditor.llm import LLMClient, LLMError  # noqa: E402


def _mock_client() -> LLMClient:
    """A model-free stub for CI smoke runs: always 'plausible', low confidence."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        body = '{"plausible": true, "confidence": 0.5, "reason": "mock"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})
    return LLMClient(transport=httpx.MockTransport(handler), model="mock")


def _predict(client: LLMClient, case_list: list[dict], meta: dict) -> list[metrics.Prediction]:
    preds: list[metrics.Prediction] = []
    for c in case_list:
        prompt = grader.case_to_prompt(c, meta)  # NO domain_context (leakage-safe)
        verdict = client.judge(prompt, LabelVerdict)
        preds.append(
            metrics.Prediction(c["id"], grader.verdict_to_label(verdict), c["expected"], verdict.confidence)
        )
    return preds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="label-plausibility benchmark runner")
    ap.add_argument("--task", default="labels_plausibility", help="task dir under benchmarks/")
    ap.add_argument("--split", default="dev", choices=cases.SPLITS)
    ap.add_argument("--model", "-m", default=None, help="LLM id (default: AUDITOR_LLM_MODEL)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--reasoning", action="store_true",
                    help="let a reasoning model think before answering (slower, more accurate)")
    ap.add_argument("--mock", action="store_true", help="use a model-free stub (CI smoke)")
    ap.add_argument("--confirm-final", action="store_true", help="required to run the held-out test split")
    ap.add_argument("--run-at", default="unspecified", help="timestamp string for the manifest")
    args = ap.parse_args(argv)
    task = args.task

    meta = cases.load_meta(task)

    cases.assert_disjoint_splits(task)
    if meta.get("scorer_version") != metrics.SCORER_VERSION:
        print(f"scorer version mismatch: meta={meta.get('scorer_version')} code={metrics.SCORER_VERSION}")
        return 2
    if args.split == "test":
        if not args.confirm_final:
            print("refusing to run the held-out test split without --confirm-final (EVAL_PROTOCOL.md section 4)")
            return 2
        freeze.verify_frozen_prompt(task)

    case_list = cases.load_split(task, args.split)
    rep = leakage.leakage_check(case_list, meta)
    if not rep.ok:
        print("LEAKAGE detected — aborting:\n" + rep.summary())
        return 2

    client = (
        _mock_client()
        if args.mock
        else LLMClient.from_env(model=args.model, timeout=args.timeout, reasoning=args.reasoning)
    )
    model_id = "mock" if args.mock else (args.model or client.model)
    if not args.mock and not client.available():
        print(f"local LLM not reachable (model={model_id}); start the vLLM server first")
        return 1

    try:
        preds = _predict(client, case_list, meta)
    except LLMError as exc:
        print(f"LLM error during run: {exc}")
        return 1
    finally:
        client.close()

    weights = meta.get("class_weights")
    score = metrics.score_split(preds, weights=weights)
    dev_ref = cases.load_split(task, "dev")
    bl = {
        "vocabulary_floor": metrics.score_split(baselines.vocabulary_floor(case_list, meta)),
        "majority_class": metrics.score_split(baselines.majority_class(case_list, dev_ref)),
    }

    manifest = freeze.RunManifest(
        task=task, split=args.split, model=model_id,
        frozen_prompt_hash=(meta.get("frozen_prompt") or {}).get("hash", "UNFROZEN"),
        scorer_version=metrics.SCORER_VERSION, run_at=args.run_at,
        metrics=score, baselines=bl,
        case_predictions=[{"id": p.case_id, "predicted": p.predicted, "expected": p.expected,
                           "confidence": p.confidence, "correct": p.correct} for p in preds],
    )
    out = _REPO / "benchmarks" / task / "results" / freeze.manifest_filename(task, args.split, model_id)
    freeze.write_manifest(manifest, out)

    headline = "HELD-OUT" if args.split == "test" else f"{args.split} (development)"
    print(f"\n{task} - {headline} - model={model_id}")
    print(f"  N={score['n']}  accuracy={score['accuracy']:.3f}  "
          f"95% CI [{score['accuracy_ci95'][0]:.3f}, {score['accuracy_ci95'][1]:.3f}]  "
          f"F1(implausible)={score['f1']:.3f}")
    print(f"  baseline vocabulary_floor accuracy={bl['vocabulary_floor']['accuracy']:.3f}")
    print(f"  baseline majority_class   accuracy={bl['majority_class']['accuracy']:.3f}")
    print(f"  frozen_prompt={manifest.frozen_prompt_hash}")
    print(f"  wrote {out}")
    if args.split != "test":
        print("  (development split — not for reporting; freeze, then run --split test --confirm-final)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
