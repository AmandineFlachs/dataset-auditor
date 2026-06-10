"""Offline tests for the benchmark scoreboard generator (``benchmarks/compare.py``).

Built against the real ``*.run.json`` schema produced by kbench: a ``taskVersion.name``,
a (possibly empty) ``modelVersion``, and an ``assertions`` list whose ``status`` ends in
``PASSED``/``FAILED``. No model or Kaggle SDK is touched.
"""

import json

import compare


def _run(task, statuses, model_version=None):
    return {
        "taskVersion": {"name": task},
        "modelVersion": model_version or {},
        "assertions": [{"status": f"BENCHMARK_TASK_RUN_ASSERTION_STATUS_{s}"} for s in statuses],
    }


def test_score_assertions_counts_passed():
    assert compare.score_assertions(_run("t", ["PASSED", "FAILED", "PASSED"])) == (2, 3)
    assert compare.score_assertions({"assertions": []}) == (0, 0)
    assert compare.score_assertions({}) == (0, 0)


def test_extract_task_and_model():
    assert compare.extract_task(_run("labels-plausibility", [])) == "labels-plausibility"
    assert compare.extract_model(_run("t", [], {"slug": "gemini-3.5-flash"})) == "gemini-3.5-flash"
    assert compare.extract_model(_run("t", []), fallback="fb") == "fb"  # empty modelVersion


def test_extract_model_ignores_deprecated_conversation_slug():
    data = _run("t", [])
    data["conversations"] = [{"modelVersionSlug": "model_version_slug ... is DEPRECATED"}]
    assert compare.extract_model(data, fallback="fb") == "fb"


def test_model_from_filename_strips_task_and_runid(tmp_path):
    from pathlib import Path
    p = Path("results/triage-verdict.gemini-3.5-flash.run.json")
    assert compare._model_from_filename(p, "triage-verdict") == "gemini-3.5-flash"
    p2 = Path("labels-plausibility-run_id_Run_1.run.json")
    assert compare._model_from_filename(p2, "labels-plausibility") == "unknown-model"


def test_load_run_uses_modelversion_then_filename(tmp_path):
    f = tmp_path / "labels-plausibility.claude.run.json"
    f.write_text(json.dumps(_run("labels-plausibility", ["PASSED", "PASSED", "FAILED"],
                                  {"slug": "claude-x"})), encoding="utf-8")
    run = compare.load_run(f)
    assert run == {"task": "labels-plausibility", "model": "claude-x", "passed": 2, "total": 3}

    g = tmp_path / "labels-plausibility.beta.run.json"  # no modelVersion -> filename
    g.write_text(json.dumps(_run("labels-plausibility", ["PASSED"])), encoding="utf-8")
    assert compare.load_run(g)["model"] == "beta"


def test_build_table_orders_by_overall_and_marks_missing():
    runs = [
        {"task": "labels-plausibility", "model": "alpha", "passed": 12, "total": 12},
        {"task": "triage-verdict", "model": "alpha", "passed": 4, "total": 5},
        {"task": "labels-plausibility", "model": "beta", "passed": 6, "total": 12},
    ]
    table = compare.build_table(runs)
    assert "| Model | labels-plausibility | triage-verdict | Overall |" in table
    assert "12/12 (100%)" in table and "16/17 (94%)" in table
    assert "—" in table  # beta has no triage-verdict run
    # best overall (alpha) is listed before beta
    assert table.index("| alpha ") < table.index("| beta ")


def test_build_table_sums_repeat_runs():
    runs = [
        {"task": "t", "model": "m", "passed": 3, "total": 5},
        {"task": "t", "model": "m", "passed": 4, "total": 5},
    ]
    assert "7/10 (70%)" in compare.build_table(runs)


def test_build_table_empty():
    assert "No `*.run.json`" in compare.build_table([])
