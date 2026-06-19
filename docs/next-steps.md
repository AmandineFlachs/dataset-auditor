# Next steps — dataset-auditor

Active branch: **`v2`** (`main` = v1). `v0.2.0` is shipped, and the benchmark is **published on
Kaggle** as a public cross-model leaderboard.

Status lives in three places, not here:
- **What shipped + what's parked:** [`ROADMAP.md`](../ROADMAP.md)
- **The leaderboard + results:** [`kaggle/README.md`](../kaggle/README.md)
- **The narrative showcase:** [`docs/index.html`](index.html)

## What's next
- Push `v2`, enable GitHub Pages on `docs/`, link the explainer from the README, decide the
  v2 → main merge.
- Config-file (YAML/JSON) plausibility rules so non-coders can add checks.
- A Streamlit front-end (upload a CSV, view the report in-browser).
- A third, non-chemistry dataset to further prove the engine is dataset-agnostic.

Deferred items (more models, a second kind of eval task, further case growth) are gold-plating —
the core claim is already defended. See `ROADMAP.md` for the reasoning before reopening any.
