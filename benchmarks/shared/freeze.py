"""Prompt-freeze + run-manifest machinery (EVAL_PROTOCOL.md §5-§6). Pure.

``prompt_identity`` hashes the SHIPPED prompt *template* (builder + schema + the rendered
prompt with case values masked), so the hash changes iff the production prompt changes —
not when case data changes. Recording it in ``meta.json`` and checking it before the test
run means you cannot quietly tune the prompt against the held-out set.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from auditor.checks.labels import LabelVerdict, build_label_prompt
from auditor.datasets import LabelRule

from . import cases as cases_mod


class FrozenPromptDrift(Exception):
    """Raised when the live prompt no longer matches the frozen hash in meta.json."""


def _masked_template(meta: dict) -> str:
    """Render the shipped prompt with placeholder values so the hash tracks the TEMPLATE
    (and the allowed vocabulary), not any specific case."""
    fields = tuple(meta.get("context_fields", ()))
    rule = LabelRule(
        column=meta["column"],
        context_columns=fields,
        allowed=tuple(meta.get("allowed", ())),
    )
    row = pd.Series({meta["column"]: "<VALUE>", **{k: "<CTX>" for k in fields}})
    return build_label_prompt(rule, row, list(fields))


def prompt_identity(meta: dict) -> str:
    """A stable SHA-256 over (builder id, output schema, masked prompt template)."""
    payload = json.dumps(
        {
            "builder": "auditor.checks.labels.build_label_prompt",
            "schema": LabelVerdict.model_json_schema(),
            "template": _masked_template(meta),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_frozen_prompt(task: str) -> None:
    """Raise FrozenPromptDrift unless meta.frozen_prompt.hash matches the live prompt."""
    meta = cases_mod.load_meta(task)
    recorded = (meta.get("frozen_prompt") or {}).get("hash")
    if not recorded:
        raise FrozenPromptDrift(f"{task}: no frozen_prompt.hash recorded in meta.json")
    current = prompt_identity(meta)
    if current != recorded:
        raise FrozenPromptDrift(
            f"{task}: prompt drifted from the frozen hash — re-freeze and re-run.\n"
            f"  recorded={recorded}\n  current ={current}"
        )


@dataclass
class RunManifest:
    task: str
    split: str
    model: str
    frozen_prompt_hash: str
    scorer_version: str
    run_at: str
    metrics: dict
    baselines: dict = field(default_factory=dict)
    case_predictions: list = field(default_factory=list)


def manifest_filename(task: str, split: str, model: str) -> str:
    safe_model = model.replace("/", "_").replace(":", "_")
    return f"{task}.{split}.{safe_model}.run.json"


def write_manifest(manifest: RunManifest, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    return p
