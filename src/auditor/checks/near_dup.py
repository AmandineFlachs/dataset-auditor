"""Near-duplicate detection: distinct identities that share the same content.

Exact-key duplicates live in ``checks/duplicates.py``. This check is the inverse of
``checks/consistency.py``: consistency asks "rows with the *same id* should agree";
near-dup asks "rows with the *same content* but *different ids* are probably the same
thing recorded twice." Group by a content key (a structural hash, a fingerprint, a
normalized string); if one content key carries several distinct identities, flag them.

On LeMat-Bulk the content key is ``entalpic_fingerprint`` (a hash of the structure)
and the identity is ``immutable_id``. A fingerprint shared by several ids means the
same material was ingested from more than one source database — a real
deduplication signal, not necessarily an error, so these are ``warn``: a human
decides whether the cross-source records are intentional.

This is the **exact** (hash-collision) tier. Fuzzy similarity via sentence-embeddings
— the "near" in near-duplicate for free text — is the deferred extension; it needs a
heavyweight model and barely applies to these scientific columns, so it is not built
yet. The engine stays generic: rules come from the spec, no rules means silence.
"""

from __future__ import annotations

import pandas as pd

from auditor.models import Finding, Severity


def check(df: pd.DataFrame, rules=()) -> list[Finding]:
    """Run every near-duplicate rule and concatenate the Findings."""
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(_apply(df, rule))
    return findings


def _apply(df: pd.DataFrame, rule) -> list[Finding]:
    if rule.content_key not in df.columns:
        return []
    has_identity = bool(rule.identity) and rule.identity in df.columns

    findings: list[Finding] = []
    # dropna=True: a missing content key is not evidence of shared content, so null
    # fingerprints never group together.
    for content, group in df.groupby(rule.content_key, dropna=True):
        if len(group) < 2:
            continue
        if has_identity:
            ids = sorted({str(v) for v in group[rule.identity]})
            # A single identity repeating (e.g. one material across functionals) is
            # the *expected* recurrence, handled elsewhere — not a near-duplicate.
            if len(ids) < 2:
                continue
            detail = f"{rule.identity} in {{{', '.join(ids)}}}"
        else:
            detail = f"{len(group)} rows"
        evidence = f"{rule.content_key}={_short(content)} shared by {detail}"

        for row_id in group["row_id"]:
            findings.append(
                Finding(
                    check="near_dup.shared_content",
                    severity=Severity.WARN,
                    row_id=int(row_id),
                    field=rule.content_key,
                    message=(
                        "Distinct records share identical content; likely the same "
                        "entity recorded more than once."
                    ),
                    evidence=evidence,
                    suggested_fix="Confirm whether these are intentional cross-source records or duplicates to merge.",
                )
            )
    return findings


def _short(value, width: int = 24) -> str:
    """Truncate a long content key (hashes are unwieldy) for readable evidence."""
    s = str(value)
    return s if len(s) <= width else s[:width] + "..."
