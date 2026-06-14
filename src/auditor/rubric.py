"""Dataset-readiness rubric: aggregate deterministic findings into per-dimension scores.

This answers "is this dataset fit for use?" rather than only "what's wrong?". It is a
**deterministic aggregation of facts** — the same `Finding` objects the report already
shows, grouped into dimensions and turned into a clean-rate per dimension. The LLM-judged
`labels.*` findings never move a score; they appear only as a clearly-marked advisory
sub-signal (so the rubric stays defensible, per EVAL_PROTOCOL.md scope tiers).

Honesty rule: a dimension whose checks did not actually run for this dataset scores
``None`` ("not assessed"), never a misleading 100. The caller passes which dimensions were
not assessed; :func:`unassessed_dimensions` derives that from a `DatasetSpec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from auditor.models import Finding, Severity

# Each deterministic check id belongs to exactly one dimension. ``test_rubric.py`` asserts
# every id `run_all` can emit is mapped here, so a new check can't silently go unscored.
DIMENSIONS: dict[str, tuple[str, ...]] = {
    "completeness": ("schema.high_null_rate",),
    "consistency": (
        "consistency.group_mismatch",
        "consistency.value_spread",
        "formula.mismatch",
        "formula.unparseable",
    ),
    "plausibility": ("units.out_of_range", "units.null_island"),
    "duplication": (
        "duplicates.exact_row",
        "duplicates.duplicate_key",
        "near_dup.shared_content",
    ),
    "privacy": ("pii.email", "pii.ssn", "pii.credit_card", "pii.phone", "pii.ipv4"),
}
DIMENSION_ORDER = ("completeness", "consistency", "plausibility", "duplication", "privacy")

# Advisory (LLM-judged) ids — counted, never scored.
ADVISORY_IDS = ("labels.implausible", "labels.uncertain", "labels.out_of_vocab", "labels.skipped")

# How much an affected row counts against its dimension, by worst severity on that row.
_SEV_WEIGHT = {Severity.ERROR: 1.0, Severity.WARN: 0.5, Severity.INFO: 0.2}
# Dataset-level findings (row_id is None, e.g. "column X ~37% null") aren't tied to one
# row, so they can't reduce a row fraction; apply a flat penalty per such finding instead.
_DATASET_FINDING_PENALTY = 5.0

_ID_TO_DIM = {cid: dim for dim, ids in DIMENSIONS.items() for cid in ids}


@dataclass(frozen=True)
class DimensionScore:
    name: str
    score: float | None  # 0..100, or None when not assessed
    affected_rows: int
    weighted_affected: float
    n_findings: int
    assessed: bool
    advisory: dict | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "affected_rows": self.affected_rows,
            "weighted_affected": self.weighted_affected,
            "n_findings": self.n_findings,
            "assessed": self.assessed,
            "advisory": self.advisory,
        }


@dataclass(frozen=True)
class Rubric:
    dimensions: list[DimensionScore]
    readiness: float | None
    n_rows: int | None

    def as_dict(self) -> dict:
        return {
            "readiness": self.readiness,
            "n_rows": self.n_rows,
            "dimensions": [d.as_dict() for d in self.dimensions],
        }


def _advisory_for(advisory_findings: list[Finding]) -> dict | None:
    if not advisory_findings:
        return None
    flagged = len({f.row_id for f in advisory_findings if f.row_id is not None})
    return {
        "labels_flagged_rows": flagged,
        "note": "LLM-judged, advisory only - not part of the score",
    }


def score(
    findings: list[Finding],
    n_rows: int | None,
    *,
    not_assessed: tuple[str, ...] = (),
) -> Rubric:
    """Aggregate deterministic findings into per-dimension scores + an overall readiness.

    ``not_assessed`` names dimensions whose checks did not run for this dataset; they score
    ``None`` and are excluded from readiness. The advisory ``labels.*`` findings attach to
    the plausibility dimension as a sub-signal but never change any score.
    """
    not_assessed_set = set(not_assessed)
    per_dim: dict[str, list[Finding]] = {d: [] for d in DIMENSIONS}
    advisory_findings: list[Finding] = []
    for f in findings:
        if f.check in ADVISORY_IDS or f.check.startswith("labels."):
            advisory_findings.append(f)
            continue
        dim = _ID_TO_DIM.get(f.check)
        if dim is not None:
            per_dim[dim].append(f)
        # Unknown deterministic ids are ignored at runtime; test_rubric.py guards coverage.

    advisory = _advisory_for(advisory_findings)
    dims: list[DimensionScore] = []
    for name in DIMENSION_ORDER:
        dim_advisory = advisory if name == "plausibility" else None
        if name in not_assessed_set:
            dims.append(DimensionScore(name, None, 0, 0.0, 0, assessed=False, advisory=dim_advisory))
            continue

        fs = per_dim[name]
        row_worst: dict[int, float] = {}
        dataset_findings = 0
        for f in fs:
            w = _SEV_WEIGHT.get(f.severity, 0.5)
            if f.row_id is None:
                dataset_findings += 1
            else:
                row_worst[f.row_id] = max(row_worst.get(f.row_id, 0.0), w)
        weighted = sum(row_worst.values())
        base = 100.0 * (1 - weighted / n_rows) if (n_rows and n_rows > 0) else 100.0
        value = max(0.0, min(100.0, round(base - _DATASET_FINDING_PENALTY * dataset_findings, 1)))
        dims.append(
            DimensionScore(
                name,
                value,
                affected_rows=len(row_worst),
                weighted_affected=round(weighted, 2),
                n_findings=len(fs),
                assessed=True,
                advisory=dim_advisory,
            )
        )

    assessed_scores = [d.score for d in dims if d.assessed and d.score is not None]
    readiness = round(sum(assessed_scores) / len(assessed_scores), 1) if assessed_scores else None
    return Rubric(dims, readiness, n_rows)


def unassessed_dimensions(spec, df=None) -> tuple[str, ...]:
    """Which dimensions a given spec does not meaningfully assess (so they score None).

    Derived from what `build_checks` actually runs for this spec: schema and duplicates
    always run (completeness / duplication always assessed); the rest are gated by spec
    config. Privacy is special: the PII check always runs (auto-scanning text columns when
    none are declared), so privacy is unassessed only when there is genuinely no text to
    scan — which needs ``df`` to tell. Without ``df`` it falls back to the spec-only rule.
    """
    na: list[str] = []
    if not (spec.consistency_rules or spec.formula_rules):
        na.append("consistency")
    if not (spec.range_rules or spec.null_island):
        na.append("plausibility")
    if not spec.pii_text_columns:
        from auditor.checks import pii

        if df is None or not pii.scannable_columns(df):
            na.append("privacy")
    return tuple(na)
