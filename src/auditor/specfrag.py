"""Load an authored rule fragment and overlay it onto a DatasetSpec.

``auditor author`` emits a Python fragment (``range_rules={...}``, ``ConsistencyRule(...)``
tuples, ...). This module is the last link of the loop: it reads that fragment and produces
a spec that actually uses the authored rules, so ``auditor run --rules frag.py`` audits with
them -- no hand-editing ``datasets.py``.

The fragment is the user's own, locally generated file, so it is executed as Python (it may
contain ``ConsistencyRule(...)`` etc.). Only the recognised rule fields are read back out;
anything else the file happens to define is ignored. The overlay replaces just those rule
fields, leaving the spec's identity (name, filename, rename_map, numeric_columns,
domain_context, ...) intact.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from auditor.datasets import ConsistencyRule, DatasetSpec, FormulaRule, NearDupRule

# The DatasetSpec rule fields an authored fragment may set (the closed grammar's outputs).
RULE_FIELDS = ("range_rules", "key_column", "consistency_rules", "near_dup_rules", "formula_rules")


def load_fragment(path: str | Path) -> dict:
    """Execute an authored fragment and return the rule fields it defines.

    The rule classes are pre-bound so a fragment that omits the import line still resolves
    them; a fragment that includes the import simply re-binds the same names.
    """
    namespace: dict = {"ConsistencyRule": ConsistencyRule, "NearDupRule": NearDupRule,
                       "FormulaRule": FormulaRule}
    code = Path(path).read_text(encoding="utf-8")
    exec(compile(code, str(path), "exec"), namespace)  # noqa: S102 - user's own authored file
    return {k: namespace[k] for k in RULE_FIELDS if k in namespace}


def apply_fragment(spec: DatasetSpec, fields: dict) -> DatasetSpec:
    """Return a copy of ``spec`` with the authored rule fields overlaid (others unchanged)."""
    overlay = {k: v for k, v in fields.items() if k in RULE_FIELDS}
    return dataclasses.replace(spec, **overlay) if overlay else spec
