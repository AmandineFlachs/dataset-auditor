"""Plain-language names for checks and severities — the report's human layer.

The checks emit machine ids (``near_dup.shared_content``) and three terse severity
words (``error``/``warn``/``info``). Those are right for code and the CLI, but a
non-specialist opening the HTML report should not have to decode them. This module
is the one place that maps each machine id to a friendly **title** and one plain
**sentence** saying what it means and why it matters.

It stays deliberately generic: the map is keyed by check id (which is the same across
every dataset), so meteorites, LeMat-Bulk, and any dataset added later all get the
plain-language layer for free. Unknown ids degrade to a readable title derived from
the id, so a new check is never *worse* than the raw name — it just lacks a sentence
until someone writes one here.
"""

from __future__ import annotations

# severity value -> the words shown to a reader (colour is handled by CSS, by class).
SEVERITY_LABEL: dict[str, str] = {
    "error": "Needs fixing",
    "warn": "Worth a look",
    "info": "For information",
}

# severity value -> the design's three-tier severity class (drives colour in the report).
SEV_CLASS: dict[str, str] = {
    "error": "critical",
    "warn": "warning",
    "info": "minor",
}

# check family -> short three-letter code shown as a category tag in the report rail.
_CHECK_CODE: dict[str, str] = {
    "schema": "SCH",
    "units": "VAL",
    "duplicates": "DUP",
    "near_dup": "NDP",
    "consistency": "CON",
    "formula": "FOR",
    "pii": "PII",
    "labels": "LBL",
}


def check_code(check_id: str) -> str:
    """A short uppercase category tag for a check (the part before the dot)."""
    family = check_id.split(".", 1)[0]
    return _CHECK_CODE.get(family, family[:3].upper())

# check id -> (title, one plain sentence). Keep the sentence dataset-agnostic: it
# explains the *kind* of problem, not one dataset's specifics (those live in the
# per-finding message and evidence).
_CHECK_INFO: dict[str, tuple[str, str]] = {
    "schema.high_null_rate": (
        "Lots of missing values",
        "A column is empty for a large share of rows, so anything that relies on it "
        "is working from partial data.",
    ),
    "units.out_of_range": (
        "Impossible values",
        "A number falls outside the range that is physically or logically possible, "
        "which usually points to a data-entry error.",
    ),
    "units.null_island": (
        "Placeholder location (0, 0)",
        "Coordinates sit at exactly (0, 0) - the usual stand-in for 'location "
        "unknown', not a real place in the ocean off Africa.",
    ),
    "duplicates.exact_row": (
        "Identical rows",
        "A row is a character-for-character copy of an earlier one, so the same "
        "record was most likely entered twice.",
    ),
    "duplicates.duplicate_key": (
        "Repeated identifier",
        "An ID that is meant to be unique appears on more than one row, so something "
        "is double-counted or two records have been linked by mistake.",
    ),
    "near_dup.shared_content": (
        "Possible duplicate records",
        "Different records carry identical content, which usually means the same "
        "thing was recorded more than once under separate IDs.",
    ),
    "consistency.group_mismatch": (
        "Records that should match but don't",
        "Rows that share an identifier disagree on a detail that ought to be the "
        "same for a single entity.",
    ),
    "consistency.value_spread": (
        "Values that drift apart",
        "Rows that should agree carry numbers that differ by more than the allowed "
        "tolerance.",
    ),
    "formula.mismatch": (
        "Chemical formula disagreement",
        "The columns that describe the same chemical composition contradict each "
        "other, so at least one of them is wrong.",
    ),
    "formula.unparseable": (
        "Unreadable chemical formula",
        "A formula could not be read, so we could not confirm it agrees with the "
        "other formula columns.",
    ),
    "labels.implausible": (
        "Doubtful category label",
        "A local AI judged a category value unlikely given the rest of the row - "
        "worth a human glance.",
    ),
    "labels.uncertain": (
        "Possibly-off category label",
        "A local AI was unsure about a category value and flagged it for a human to "
        "confirm.",
    ),
    "labels.out_of_vocab": (
        "Unexpected category value",
        "A value falls outside the list of values this column is supposed to use.",
    ),
    "labels.skipped": (
        "AI label check skipped",
        "The local AI was not reachable, so the label checks were skipped; every "
        "other check ran normally.",
    ),
}

# Fallback by check family (the part before the dot), for ids without an exact entry.
# ``pii.email``, ``pii.ssn``, ``pii.credit_card`` ... all share one plain explanation.
_FAMILY_INFO: dict[str, tuple[str, str]] = {
    "pii": (
        "Possible personal data",
        "Something shaped like personal information (an email, phone number, ID "
        "number, and so on) turned up in free text and may need to be removed before "
        "sharing.",
    ),
    "schema": ("Data shape issue", "A column's shape or completeness looks off."),
    "units": ("Out-of-range value", "A value sits outside its plausible range."),
    "duplicates": ("Duplicate record", "The same record appears to be repeated."),
    "near_dup": ("Possible duplicate", "Two records look like the same thing."),
    "consistency": (
        "Inconsistent records",
        "Records that should agree with each other do not.",
    ),
    "formula": ("Formula issue", "A chemical-formula column looks inconsistent."),
    "labels": ("Category-label issue", "A category value looks questionable."),
}


def severity_label(severity: str) -> str:
    """Plain words for a severity value; the value itself if it is unknown."""
    return SEVERITY_LABEL.get(severity, severity)


def describe_check(check_id: str) -> tuple[str, str]:
    """Return ``(title, sentence)`` for a check id.

    Exact id first, then the check family (text before the dot), then a readable
    title derived from the id with an empty sentence. Never raises, so a brand-new
    check still renders with a sensible heading.
    """
    if check_id in _CHECK_INFO:
        return _CHECK_INFO[check_id]
    family = check_id.split(".", 1)[0]
    if family in _FAMILY_INFO:
        return _FAMILY_INFO[family]
    # Last resort: turn "foo.bar_baz" into "Bar baz" so it is at least legible.
    tail = check_id.split(".", 1)[-1].replace("_", " ").replace(".", " ").strip()
    return (tail.capitalize() or check_id, "")
