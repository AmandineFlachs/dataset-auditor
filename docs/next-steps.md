# Next steps — dataset-auditor

_Updated 2026-06-13. Branch: `v2-kaggle-benchmarks` (the benchmark/loop work that named
this branch has since been removed — see below; consider renaming or merging to `main`)._

## Where things stand

The project is back to its **sound core**: a deterministic data-quality auditor plus a
strictly-bounded, advisory local-LLM layer. All tests pass.

- **Eight deterministic checks** (schema, units, duplicates, near-dup, consistency, PII,
  labels, formula) → `Finding` objects → a single self-contained HTML triage report.
- **Advisory LLM, never overriding a fact:** `auditor brief` (metadata-only domain
  briefing), `auditor triage` (deterministic priority + a neutral per-issue "what to
  check" note), and the opt-in, off-by-default `labels` check.
- **Guided rule-authoring** (`auditor author`): the model proposes range/key/consistency/
  near_dup/formula rules, each dry-run against the real check; `--autonomy ask-all|
  balanced|hands-off`; decision log; re-dry-run-on-edit.
- **Fragment wiring.** `auditor run/triage --rules <fragment.py>` overlays an authored
  fragment onto a dataset's spec — no hand-editing `datasets.py`.

## Removed on 2026-06-13 (and why)

The **Kaggle benchmark layer** and the **self-improving loop** (`capture` →
`select-model`) were deleted. Two reasons:

1. **Leakage.** The `triage-verdict` benchmark fed the model a domain-context grounding
   that effectively stated the answers, so it measured "can the model read a sentence,"
   not domain reasoning. A high score didn't mean what it claimed.
2. **Unproven.** Conclusions rested on tiny case counts (N≈5–17), and the self-improving
   loop had no experiment showing it actually improves model selection.

Git history on this branch preserves it if any piece is revived later — but only against
a larger, leakage-controlled case set, and with the grounding split so an *unaided* score
can be measured separately from a product-faithful one.

## Feature work remaining (still valid)

- **Persist authored rules as a named spec** — today a fragment is pasted or `--rules`'d;
  a round-trip to a saved spec (the ROADMAP "config-file rules" item) would let
  `auditor run -d <authored-name>` work directly.
- **`label` authoring candidates** — the deferred 6th rule kind; its dry-run needs a live
  LLM that judges values, so add it once the other kinds are battle-tested.
- **Merge / rename the branch** — the `v2-kaggle-benchmarks` name no longer fits.

## Operational notes / gotchas

- Commit email **must** stay `AmandineFlachs@users.noreply.github.com` (keep the work
  email out of public history).
- Run from the repo root with `PYTHONPATH=src` (package isn't installed); the `auditor`
  console script exists once installed.
- Report screenshots via headless Chrome:
  `chrome.exe --headless --disable-gpu --screenshot=out.png --window-size=1500,1300 file:///<abs>/report.html`.
- `demo/` holds throwaway artifacts (report.html/png) — untracked.
- A leftover `.env` (Kaggle model-proxy credentials) is now unused by the codebase; safe
  to delete if you don't want the stray key around.
