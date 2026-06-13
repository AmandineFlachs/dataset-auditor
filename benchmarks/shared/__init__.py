"""Pure, model-free plumbing shared by benchmark tasks.

Nothing in this package imports ``httpx`` or any model SDK: it only loads cases,
builds the SHIPPED prompt, grades verdicts, scores, and checks for leakage. That keeps
it unit-testable in CI with no live model. The single impure consumer is each task's
``run.py`` (the only place ``auditor.llm.LLMClient`` is touched).
"""
