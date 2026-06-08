"""Phase D: a local-LLM *research briefing* — context for the human, not auto-rules.

The deterministic checks tell you *what* looks wrong. This phase tells you what the
columns probably *mean*: a domain briefing the auditor reads before authoring
plausibility rules. It is deliberately advisory — it suggests checks, it never
applies them, so a confidently-wrong model can't silently corrupt the audit.

Two hard boundaries:

* **Metadata only, never raw rows.** The model sees column names, dtypes, null rates,
  numeric ranges, and categorical value-counts — aggregates, not individual records.
  No row-level data (and so no PII) is ever sent.
* **Degrade gracefully.** Like every LLM-assisted part, if the local server is offline
  this returns ``None`` and the caller carries on; it never crashes a run.

It is the first piece written to actually run against a live local model (see the
README's local-LLM setup); until a server is up it is exercised with a mocked client.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field

from auditor.datasets import DatasetSpec
from auditor.llm import LLMClient, LLMTimeout, LLMUnavailable
from auditor.models import Finding  # noqa: F401 (kept for parity / future report embedding)

# A briefing is one large single-shot generation (every column at once), so it
# warrants far more headroom than the client's per-call default. Still finite, so a
# genuinely wedged server surfaces as an honest LLMTimeout rather than hanging.
_BRIEF_TIMEOUT = 180.0


class ColumnBriefing(BaseModel):
    """The model's read on one column — meaning, units, plausible range, pitfalls."""

    column: str
    likely_meaning: str
    units: str = ""
    plausible_range: str = ""
    pitfalls: str = ""


class DatasetBriefing(BaseModel):
    """A whole-dataset briefing. ``suggested_checks`` is advisory, not applied."""

    summary: str
    columns: list[ColumnBriefing] = Field(default_factory=list)
    dataset_pitfalls: list[str] = Field(default_factory=list)
    suggested_checks: list[str] = Field(default_factory=list)


def brief(df: pd.DataFrame, spec: DatasetSpec, *, client: LLMClient | None = None) -> DatasetBriefing | None:
    """Generate a domain briefing from column metadata, or ``None`` if offline.

    Returns ``None`` only when the server is genuinely absent (unreachable up front,
    or the connection drops mid-call). A *timeout* is different - the server is there
    but too slow - so it propagates as :class:`LLMTimeout` for the caller to report
    honestly, rather than masquerading as "no server".
    """
    client = client or LLMClient.from_env(timeout=_BRIEF_TIMEOUT)
    if not client.available():
        return None
    try:
        return client.judge(_prompt(df, spec), DatasetBriefing, context=spec.domain_context)
    except LLMTimeout:
        raise  # reachable but too slow - surface it; do not pretend the server is down
    except LLMUnavailable:
        return None  # connection dropped mid-call; treat as "not available", never crash


def _prompt(df: pd.DataFrame, spec: DatasetSpec) -> str:
    return (
        "You are preparing a data-quality briefing for a human auditor who will then "
        "author validation rules. Using ONLY the column metadata below and the domain "
        "context, give: for each column its likely meaning, units (if any), a plausible "
        "value range, and common pitfalls; then dataset-level pitfalls; then suggested "
        "data-quality checks the auditor could author. The suggested checks are ADVISORY "
        "— they are not applied automatically. Reason from the metadata and domain; do "
        "not invent specific values.\n\n" + _metadata_text(df, spec)
    )


def _metadata_text(df: pd.DataFrame, spec: DatasetSpec) -> str:
    """Aggregate metadata only (dtype, null rate, numeric range, categorical counts)."""
    lines = [f"Dataset: {spec.name}", f"Rows: {len(df):,}", "", "Columns:"]
    for col in (c for c in df.columns if c != "row_id"):
        s = df[col]
        null_pct = s.isna().mean() * 100
        if pd.api.types.is_numeric_dtype(s):
            extra = f"min={s.min():.4g}, max={s.max():.4g}, mean={s.mean():.4g}"
        elif col in spec.categorical_columns:
            vc = s.value_counts(dropna=False).head(6)
            extra = "values: " + ", ".join(f"{k} ({v})" for k, v in vc.items())
        else:
            extra = ""
        lines.append(f"- {col} ({s.dtype}, {null_pct:.0f}% missing){': ' + extra if extra else ''}")
    return "\n".join(lines)


def to_markdown(briefing: DatasetBriefing, spec: DatasetSpec) -> str:
    """Render a briefing to Markdown for `auditor brief --out briefing.md`."""
    out = [f"# Research briefing: {spec.name}", "", briefing.summary, ""]
    if briefing.columns:
        out.append("## Columns\n")
        for c in briefing.columns:
            out.append(f"### `{c.column}`")
            out.append(f"- **Likely meaning:** {c.likely_meaning}")
            if c.units:
                out.append(f"- **Units:** {c.units}")
            if c.plausible_range:
                out.append(f"- **Plausible range:** {c.plausible_range}")
            if c.pitfalls:
                out.append(f"- **Pitfalls:** {c.pitfalls}")
            out.append("")
    if briefing.dataset_pitfalls:
        out.append("## Dataset-level pitfalls\n")
        out += [f"- {p}" for p in briefing.dataset_pitfalls]
        out.append("")
    if briefing.suggested_checks:
        out.append("## Suggested checks (advisory — author by hand, not auto-applied)\n")
        out += [f"- {c}" for c in briefing.suggested_checks]
        out.append("")
    out.append("---\n*Generated locally from dataset metadata only (no raw rows). Advisory, not auto-applied.*")
    return "\n".join(out)
