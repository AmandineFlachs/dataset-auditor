"""Load benchmark cases and enforce split integrity. Pure: stdlib only.

A *case* is one JSON object per line: ``{"id", "value", "context", "expected", ...}``.
A *task* is a directory under ``benchmarks/`` holding ``meta.json`` plus ``dev.jsonl``,
``calibration.jsonl`` and ``test.jsonl`` (the three splits in EVAL_PROTOCOL.md §4).
"""

from __future__ import annotations

import json
from pathlib import Path

CASES_ROOT = Path(__file__).resolve().parents[1]  # the benchmarks/ directory
SPLITS = ("dev", "calibration", "test")
REQUIRED_CASE_KEYS = ("id", "value", "context", "expected")
DEFAULT_EXPECTED = ("plausible", "implausible")


def task_dir(task: str) -> Path:
    return CASES_ROOT / task


def load_jsonl(path: str | Path) -> list[dict]:
    """Read a ``.jsonl`` file into case dicts. Blank lines, ``//`` comments, and a
    sentinel ``{"_warning": ...}`` guard record (used to discourage casual peeking at
    the test split) are skipped."""
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        obj = json.loads(line)
        if isinstance(obj, dict) and "_warning" in obj:
            continue
        out.append(obj)
    return out


def load_meta(task: str) -> dict:
    return json.loads((task_dir(task) / "meta.json").read_text(encoding="utf-8"))


def load_split(task: str, split: str) -> list[dict]:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; choose from {SPLITS}")
    return load_jsonl(task_dir(task) / f"{split}.jsonl")


def validate_cases(cases: list[dict], meta: dict) -> list[str]:
    """Return a list of problems (empty == valid). Structural only; see leakage.py."""
    errors: list[str] = []
    allowed = set(meta.get("allowed", ()))
    expected_values = set(meta.get("expected_values", DEFAULT_EXPECTED))
    seen: set = set()
    for i, c in enumerate(cases):
        where = c.get("id", f"#{i}")
        for k in REQUIRED_CASE_KEYS:
            if k not in c:
                errors.append(f"{where}: missing required key {k!r}")
        cid = c.get("id")
        if cid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(cid)
        if not isinstance(c.get("context", {}), dict):
            errors.append(f"{where}: context must be an object")
        if c.get("expected") not in expected_values:
            errors.append(f"{where}: expected {c.get('expected')!r} not in {sorted(expected_values)}")
        if allowed and c.get("value") not in allowed:
            errors.append(f"{where}: value {c.get('value')!r} not in allowed vocab")
    return errors


def _signature(case: dict) -> tuple:
    ctx = case.get("context", {}) or {}
    return (case.get("value"), tuple(sorted((k, str(v)) for k, v in ctx.items())))


def assert_disjoint_splits(task: str) -> None:
    """Raise if any case id or ``(value, context)`` signature spans more than one split.

    This is the hard guard behind EVAL_PROTOCOL.md §4: a case used to develop the prompt
    or tune thresholds must never also be a held-out test case.
    """
    by_id: dict = {}
    by_sig: dict = {}
    for split in SPLITS:
        path = task_dir(task) / f"{split}.jsonl"
        if not path.exists():
            continue
        for c in load_jsonl(path):
            cid = c.get("id")
            if cid in by_id and by_id[cid] != split:
                raise AssertionError(f"id {cid!r} appears in both {by_id[cid]!r} and {split!r}")
            by_id[cid] = split
            sig = _signature(c)
            if sig in by_sig and by_sig[sig] != split:
                raise AssertionError(
                    f"case signature {sig} spans {by_sig[sig]!r} and {split!r}"
                )
            by_sig[sig] = split
