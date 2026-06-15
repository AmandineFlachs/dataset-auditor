"""Phase-2 local validation: run a generated Kaggle task file against the local vLLM.

Usage (needs the vLLM server up, same as the auditor's LLM checks)::

    PYTHONUTF8=1 python kaggle/run_local.py kaggle/labels_plausibility_open_task.py

It imports the (self-contained) task module, runs ``task.evaluate`` through the
``LocalVLLM`` adapter, then scores with the module's own ported scorer and prints the
deterministic baselines alongside — so we can confirm the port reproduces the held-out
numbers (baselines ~0.5, a knowledgeable model well above).

Binary trick: the task returns ``True/False`` (correct/incorrect), not the label. Because
the label space is binary, the predicted label is recoverable: ``expected`` if correct,
else the other class. That lets us report precision/recall/F1 without re-calling the model.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so local_adapter imports
from local_adapter import LocalVLLM

FLIP = {"plausible": "implausible", "implausible": "plausible"}


def _load(path: str):
    # Suppress the task file's top-level auto-evaluation (which targets kb.llm / the Kaggle
    # Model Proxy) so we can drive it ourselves against the local adapter below.
    import os
    os.environ["KAGGLE_BENCH_NOAUTORUN"] = "1"
    spec = importlib.util.spec_from_file_location("kaggle_task_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_file", help="path to a generated *_task.py")
    args = ap.parse_args()

    mod = _load(args.task_file)
    adapter = LocalVLLM()
    if not adapter.available():
        sys.exit(
            f"local vLLM not reachable at {adapter._http.base_url} — start the server "
            f"(or set AUDITOR_LLM_BASE_URL/MODEL) and retry."
        )

    print(f"running {mod.TASK_NAME}: {len(mod.CASES)} cases vs model={adapter.name!r} ...")
    model_score, preds = mod._score_all(adapter)
    vf, mc = mod.score(mod.vocabulary_floor()), mod.score(mod.majority_class())
    print(f"\n=== {mod.TASK_NAME} ===")
    a = model_score
    print(f"  MODEL accuracy   = {a['accuracy']:.3f}  CI95 {a['accuracy_ci95']}  "
          f"F1(implausible)={a['f1']:.3f}  (n={a['n']})")
    print(f"  vocabulary-floor = {vf['accuracy']:.3f}   majority-class = {mc['accuracy']:.3f}")
    beat = a["accuracy"] > max(vf["accuracy"], mc["accuracy"]) + 0.05
    print(f"  -> {'BEATS' if beat else 'does NOT clearly beat'} the deterministic baselines")


if __name__ == "__main__":
    main()
