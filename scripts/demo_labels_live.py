"""Live demonstration of the LLM-judged labels check against a local vLLM server.

Both science flagships leave ``label_rules`` empty on purpose -- their categoricals are
recorded facts, not error-prone human labels -- so the only honest way to show
``checks/labels.py`` working on real label noise is a dataset built for it. This is that
fixture: a handful of chemical elements with a ``phase_at_stp`` label (solid / liquid /
gas at ~25 C, 1 atm), a few deliberately wrong, judged by the live model.

A design note worth keeping: an earlier version of this demo also fed melting and
boiling points as context and asked the model to *derive* the phase. That made it
WORSE (a 14B model does numeric-threshold reasoning unreliably and the check's
conservative "treat uncertain as plausible" bias then lets errors through). The check's
real strength is world knowledge -- "is mercury solid?" is a fact the model knows cold,
no arithmetic -- so this judges from the element name alone, which is both fairer and
the use case the check is actually for.

Unlike ``tests/test_labels.py`` (mocked client, CI-safe) this contacts the real server,
so it proves the "heuristics + local LLM" claim end to end. It writes nothing; it just
prints the model's verdicts. Needs a server up. Run:  python scripts/demo_labels_live.py
"""

from __future__ import annotations

import pandas as pd

from auditor.checks import labels
from auditor.datasets import LabelRule
from auditor.llm import LLMClient

# phase_at_stp is the judged column. The (X) rows are deliberately mislabeled: the value
# is in-vocabulary (solid/liquid/gas) but contradicts the element, so only the model's
# judgement -- not a range check -- can catch it. Melting point is the grounding context.
ROWS = [
    # element, phase_at_stp, note. The planted errors are iconic "surprising phase"
    # facts (the ones chemistry courses stress) -- the model knows them confidently,
    # which is exactly the world-knowledge label noise this check is meant to catch.
    ("Iron",     "solid",  "correct"),
    ("Gold",     "solid",  "correct"),
    ("Oxygen",   "gas",    "correct"),
    ("Sodium",   "solid",  "correct"),
    ("Mercury",  "solid",  "WRONG -> mercury is the liquid metal at 25 C"),
    ("Helium",   "solid",  "WRONG -> helium never solidifies at ambient pressure"),
    ("Bromine",  "gas",    "WRONG -> bromine is one of only two liquid elements"),
]

CONTEXT = (
    "Each row is a chemical element. phase_at_stp is the element's physical state at "
    "standard conditions (about 25 C and 1 atm), one of solid / liquid / gas. Judge it "
    "against the well-known properties of the element."
)

RULE = LabelRule(
    column="phase_at_stp",
    context_columns=("element",),
    allowed=("solid", "liquid", "gas"),
)


def main() -> None:
    df = pd.DataFrame(
        {
            "row_id": list(range(len(ROWS))),
            "element": [r[0] for r in ROWS],
            "phase_at_stp": [r[1] for r in ROWS],
        }
    )

    client = LLMClient.from_env(timeout=60.0)
    if not client.available():
        print("local LLM not reachable - start the vLLM server first.")
        return

    findings = labels.check(df, rules=[RULE], client=client, context=CONTEXT)

    print(f"\njudged {len(df)} rows, {client.calls_made} distinct LLM calls; "
          f"{len(findings)} finding(s):\n")
    flagged = {f.row_id for f in findings}
    for r, (element, phase, note) in zip(range(len(ROWS)), ROWS):
        mark = "FLAG" if r in flagged else "ok  "
        planted = "wrong" if note.startswith("WRONG") else "right"
        print(f"  [{mark}] {element:<8} phase={phase:<7} (planted {planted})")
    print()
    for f in sorted(findings, key=lambda f: (f.row_id is None, f.row_id)):
        print(f"  - [{f.severity.value}] {f.check} row={f.row_id}: {f.evidence}")


if __name__ == "__main__":
    main()
