# triage-quality — scaffold only (NOT built)

Phase 5 placeholder. The idea: measure whether `auditor triage`'s per-issue "what to
check" note is genuinely useful and actionable for a flagged issue.

**Not implemented on purpose.** Per `../../EVAL_PROTOCOL.md`, a capability is only
benchmarked after a task that satisfies the protocol exists for it — and the first task
(`labels_plausibility`) must be proven clean first. Adding this task requires, up front:

- a leakage-safe case design (no answer-bearing context; disjoint dev/calibration/test),
- a frozen prompt + versioned scorer,
- and — because "usefulness" is not a clean binary — a defensible grader (likely
  LLM-as-judge), which needs its *own* leakage controls and human-graded validation before
  it can be trusted.

Until that exists, this directory is intentionally empty of cases.
