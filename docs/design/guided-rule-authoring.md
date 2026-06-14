# Design note: guided rule-authoring (the question atom)

> Status: **built** (`auditor author`). This note captures the original design thinking;
> see the code in `src/auditor/authoring/` for what shipped.

## Context

Adding a dataset to the auditor today means hand-authoring a `DatasetSpec` in
`datasets.py` (range/consistency/formula/etc. rules). That's a coding task, which walls
the tool off from the scientists it's nominally for, and in practice the specs were
authored by an AI with a human steering anyway.

The longer-term goal is a standalone tool that does the prep with minimal human
involvement. The interaction model that keeps the project's trust story intact:
**the model proposes structured rules and asks the human targeted questions; for each
question the human can answer, or say "you choose" to delegate that one decision.**
The model never asserts a finding; it proposes a *check*, a human (or a delegated
policy) approves it, and the deterministic check produces the finding. That preserves
the "model never originates a fact it could be wrong about" principle while shrinking
human involvement to a tunable dial.

This note specifies the **atom** of that system: one rule decision, end to end. Build
the atom for one rule kind (`range`), prove it, then extend to the others by the same
pattern. It is a vertical slice, not the whole standalone product.

## The atom: one decision, six stages

A single rule flows: **propose -> dry-run -> classify -> ask (or auto-decide) ->
resolve -> emit**.

### Data model (new `Candidate` / `Evidence` / `Resolution`)

```
Candidate:                      # one structured, dry-runnable proposal
  kind: "range" | "consistency" | "formula" | "near_dup" | "label" | "key" | ...
  column: str | None            # or columns/group_by depending on kind
  params: dict                  # maps 1:1 onto the real rule object's fields
  rationale: str                # why the model proposes it (shown to the human)
  confidence: float             # model self-rating, [0,1]

Evidence:                       # produced by dry-running the candidate
  flag_count: int
  flag_rate: float              # flagged / total rows
  samples: list[str]            # a few real flagged values

Resolution:
  decided_by: "human" | "model"
  action: "accept" | "edit" | "skip"
  final_params: dict | None
  note: str                     # model rationale when decided_by="model"
```

### Worked example (meteorites, `mass_g`)

1. **Propose.** From column metadata only (reuse `research._metadata_text`), the model
   emits a structured candidate, not prose:
   `Candidate(kind="range", column="mass_g", params={"min":0,"exclusive_min":True},
   rationale="mass is physical; <=0 g is impossible", confidence=0.82)`

2. **Dry-run (the reuse insight).** Build a one-rule fragment and call the *existing*
   check in isolation:
   `units.check(df, rules={"mass_g": {"min":0,"exclusive_min":True}}, null_island=False)`
   The returned findings give `flag_count`, `flag_rate`, and sample evidence. No new
   harness; the evidence is exactly what would happen if the rule shipped.

3. **Classify** using `confidence` + `flag_rate`: ~0% or tiny and high-confidence =
   auto-safe; a small plausible fraction = the interesting "ask" band; ~100% = probably
   a wrong bound, surface with a warning.

4. **Ask** (when the dial says so), evidence attached:
   ```
   [mass_g] Flag non-positive mass?
   Proposed: flag mass_g <= 0.   Why: mass is physical; 0 g is impossible.
   If applied now: flags 19 of 45,716 rows (0.04%).  e.g. id=4321 mass_g=0
   -> [Accept]  [Edit min/max]  [Skip]  [You choose for me]
   ```

5. **Resolve.** Accept -> params adopted. Edit -> human values, optional re-dry-run.
   Skip -> declined. **You choose -> calls the same `model_decide(candidate, evidence)`
   the auto path uses**, logs the pick with its rationale and `decided_by="model"`.

6. **Emit.** Accumulated resolutions assemble into a `DatasetSpec` fragment (a
   `range_rules` dict here) plus a decision transcript. Persistence in the first slice:
   emit a `DatasetSpec(...)` Python snippet and a JSON decision log. Full YAML/JSON spec
   round-trip is the already-deferred ROADMAP "config-file rules" item this builds toward.

### The unification that makes the dial cheap

`model_decide(candidate, evidence)` is the whole brain. "You choose" is a human invoking
it on one question; **auto-resolution is policy invoking the same function**. So one
`--autonomy` knob spans the ladder with no extra machinery:

- `ask-all` (Level 1): every candidate becomes a question.
- `balanced` (Level 2): auto-decide high-confidence + safe flag-rate, ask the rest.
- `hands-off` (Level 3): auto-decide everything, stop only on suspicious/low-confidence,
  hand back a graded report of what it decided and why.

How far the knob can safely turn per rule-kind is a calibration question. Slice 1 uses a
conservative pair of heuristics — the model's self-rated confidence plus the actual
flag-rate from the dry-run — and the safe default is to ask the human whenever either is
unsure. The thresholds can be tuned with experience over time.

## Candidate -> rule mapping (the closed grammar)

| kind | params | becomes | dry-run via |
|---|---|---|---|
| `range` | min/max/exclusive_min/exclusive_max | `range_rules[col]` dict | `units.check` |
| `key` | column | `key_column` | `duplicates.check(df, key=...)` |
| `consistency` | group_by, columns, mode, tolerance | `ConsistencyRule` | `consistency.check` |
| `near_dup` | content_key, identity | `NearDupRule` | `near_dup.check` |
| `formula` | reduced/descriptive/anonymous/elements/nelements | `FormulaRule` | `formula.check` |
| `label` | column, allowed, context_columns | `LabelRule` | `labels.check` (needs LLM) |

All rule dataclasses live in `src/auditor/datasets.py`; every check signature accepts a
single rule in isolation, which is what makes the dry-run free of new infrastructure.

## Scope: build slice 1 = `range` only

Range is the simplest, highest-value kind and dry-runs cleanly. Implement the full atom
for `range`, then the other kinds are the same loop with a different params->rule mapping
and a different check to dry-run. Defer `label` candidates (their dry-run needs a live
LLM and judges values, so evidence is costlier) and the subtle domain calls.

## Critical files (when built)

- **NEW `src/auditor/authoring/proposals.py`** — `Candidate` model; `propose(df, spec)`
  asks the LLM for structured candidates, reusing `research._metadata_text(df, spec)` for
  the metadata prompt and `LLMClient.judge` with a pydantic schema (same pattern as
  `research.brief`). Degrades gracefully (no server -> no candidates).
- **NEW `src/auditor/authoring/dryrun.py`** — `dry_run(candidate, df) -> Evidence`: maps a
  candidate to a one-rule fragment and calls the matching check in `src/auditor/checks/*`,
  summarizing returned `Finding`s into flag_count/flag_rate/samples.
- **NEW `src/auditor/authoring/resolve.py`** — `model_decide(candidate, evidence) ->
  Resolution` (the "you choose" brain) and `ask_human(candidate, evidence) -> Resolution`
  (uses `typer.prompt`/`typer.confirm`; the CLI has no interactive input today).
- **NEW `src/auditor/authoring/session.py`** — drives propose->dry_run->classify->
  (ask|model_decide)->collect; honors `--autonomy`; assembles a spec fragment + JSON log.
- **`src/auditor/cli.py`** — add `auditor author` (Typer command, mirrors `brief`/`triage`
  wiring), with `--autonomy ask-all|balanced|hands-off` and `--out`.
- **`src/auditor/research.py`** — reuse `_metadata_text`; optionally evolve the briefing's
  prose `plausible_range`/`suggested_checks` toward emitting `range` candidates directly
  (the prose `"Integer between 1 and 7"` is already a range rule in disguise). Not required
  for slice 1.
- **NEW `tests/test_authoring.py`** — candidate->rule mapping, `dry_run` against a fixture
  (pure, no LLM), `model_decide` policy on synthetic confidence/flag-rate, and a mocked-LLM
  `propose`. Mirrors the existing mocked-client test posture.

## What this deliberately does NOT do

- No autonomous *remediation*: it proposes checks and reports, never cleans/edits data.
  Autonomy is safe for detection/reporting, not for action.
- No subtle domain judgments (e.g. dropping cross-functional energy comparison). Those
  surface as low-confidence candidates or prose flagged "needs a human / new check type",
  and when auto-decided they are logged as visible assumptions, never silently baked in.
- No `NULL_RATE_THRESHOLD` per-spec change yet (it is global in `schema.py`).

## Verification (when built)

1. `pytest tests/test_authoring.py` green: mapping, dry-run on a fixture, policy logic,
   mocked `propose` — all model-free in CI.
2. End-to-end against the live local model + real data:
   `auditor author --dataset meteorites --autonomy ask-all --out frag.py` and confirm the
   `mass_g`/`year` range questions appear with correct flag counts, and that answering vs
   "you choose" both produce a valid `range_rules` fragment + a decision log.
3. Re-run with `--autonomy hands-off`; confirm it auto-decides, emits the same fragment,
   and the JSON log records `decided_by="model"` with rationales.
4. Feed the emitted fragment into a spec and run `auditor run` to confirm the authored
   rules fire exactly as the dry-run predicted (round-trip integrity).

## Why this feature earns its keep

It turns "add a dataset" from hand-editing a `DatasetSpec` into a guided conversation: the
model proposes bounds, each is dry-run against the real check so the human decides on actual
flag counts, and the `--autonomy` dial controls how much the human is asked. The human stays
in control; the model only ever *proposes* checks, never edits data.
