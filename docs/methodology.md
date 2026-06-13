# Methodology — why the evaluation is built this way

This is the explanatory companion to [`EVAL_PROTOCOL.md`](../EVAL_PROTOCOL.md) (the rules)
and [`leakage_checklist.md`](leakage_checklist.md) (the pre-freeze checklist). It explains
the reasoning, so the rules don't read as arbitrary.

## The mistake we are designing against

An earlier version of this project had a benchmark that asked a model to judge whether a
flagged data issue was a *real defect* or an *expected artifact*. Every capable model
scored a perfect 5/5, which looked like success. It wasn't.

The benchmark prepended a block of "domain context" to the prompt — the same grounding the
product uses — and that text **stated the rules that decided the answers**. For example, it
said "the same id can recur across methods (expected)", and one of the cases was exactly
"the same id recurs — defect or expected?". The model didn't need to reason; it needed to
read one sentence. A high score measured reading comprehension, not domain judgement.

That is **leakage**: the answer was hidden inside the question. The whole task was removed
rather than patched, because a number that doesn't mean what it claims is worse than no
number. Everything below exists so that failure cannot recur.

## Why we reuse the shipped prompt, but drop the grounding

Two ideas that sound contradictory but aren't:

- **Reuse the production prompt builder.** The benchmark calls the exact
  `build_label_prompt` and `LabelVerdict` the product ships. This keeps the test honest in
  a *different* way: it can never measure a prettier prompt than the one users actually get.
- **Pass no answer-bearing context.** The leak lived in the *separate* `domain_context`
  system message (`llm._build_messages` injects `context=` as its own message). The label
  task passes none. The model gets the value, the allowed vocabulary, and a few
  deliberately answer-free context fields — nothing that states the answer.

So we keep the part that prevents drift and remove the part that caused the leak.

## Why curated/planted cases, not raw public rows

If we scored a model on famous public examples, a good score could just be memorisation
(pretraining contamination). By planting defects ourselves — a real element with a
deliberately wrong phase label — we control the ground truth and reduce the chance the
exact (row, label) pair was in the model's training data. It also lets us balance the
classes so accuracy is meaningful.

## Why three splits

- **dev** is where we iterate on the prompt and framing. Looking at it is fine.
- **calibration** is where we set any threshold (e.g. a confidence cut-off). Looking at it
  is fine.
- **test** is opened *once*, after everything is frozen, and only its numbers are reported.

If we tuned against the test set — even informally, by peeking and adjusting — we'd be
fitting to the answers and the "held-out" number would be a fiction. The freeze + the
disjointness check + the `--confirm-final` gate make that hard to do by accident.

## Why exact-match on a binary label

The judgement is genuinely binary (plausible / not). Exact match is the simplest scorer
that can't be gamed and is trivial to explain. We additionally report precision/recall/F1
for the "implausible" class, because catching the planted defects is the job the check
actually exists for; accuracy alone can hide a model that just says "plausible" to
everything.

## Why we insist on confidence intervals and baselines

We can only hand-curate a modest number of cases, so the test set is small and the
confidence interval is wide (roughly ±15 percentage points at N≈40). Reporting the
interval is not a weakness to hide — it is the honest statement of how much the number can
support. And a raw accuracy is meaningless without a floor: a deterministic
vocabulary baseline and a majority-class baseline tell us whether the model is adding
anything over trivial strategies. A model that doesn't clearly beat both, on held-out data,
is not yet worth trusting for that task.

## What this buys us

A benchmark whose score means what it says: *on cases it was not tuned on, with no answer
in the prompt, the model beats the trivial baselines by this much, give or take this much.*
That is a claim we can defend.
