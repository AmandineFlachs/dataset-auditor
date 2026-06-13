"""Command-line interface — the single entry point a user actually touches.

`auditor run` ties the whole pipeline together (load -> checks -> HTML report) so
nobody has to import the internals. The commands are deliberately thin: each is a
few lines delegating to ``load`` / ``checks`` / ``report``, which are the tested
units. The CLI's own job is just argument parsing and friendly output.

Installed as the ``auditor`` console script (see ``pyproject.toml``); also runnable
as ``python -m auditor.cli``.
"""

from __future__ import annotations

import os
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from auditor.checks import run_all
from auditor.datasets import DATASETS, DEFAULT, get
from auditor.load import load, profile
from auditor.report import write

app = typer.Typer(
    add_completion=False,
    help="Audit scientific datasets for PII, unit/format issues, label noise, and duplicates.",
)


def _use_model(model: Optional[str]) -> None:
    """Point the LLM layer at ``model`` for this process, via the standard env carrier.

    ``AUDITOR_LLM_MODEL`` is the single carrier of "the chosen model" across every stage
    (``LLMClient.from_env`` reads it), so a ``--model`` flag just sets it here, leaving
    each command's own timeout intact. ``brief``/``triage``/``author`` all read it.
    """
    if model:
        os.environ["AUDITOR_LLM_MODEL"] = model


def _spec_with_rules(dataset: Optional[str], rules: Optional[Path]):
    """Look up the dataset's spec, optionally overlaying an authored rule fragment.

    Closes the authoring loop: rules from ``auditor author`` become a spec the audit uses,
    without hand-editing ``datasets.py``. Reports how many rule fields were applied.
    """
    spec = get(dataset)
    if rules is None:
        return spec
    from auditor.specfrag import apply_fragment, load_fragment

    fields = load_fragment(rules)
    if not fields:
        typer.echo(f"{rules} defined no recognised rule fields; auditing with the base spec.")
        return spec
    typer.echo(f"applied authored rules from {rules}: {', '.join(sorted(fields))}")
    return apply_fragment(spec, fields)


@app.command()
def run(
    dataset: Optional[str] = typer.Option(
        None, "--dataset", "-d", help="Dataset to audit (default: the flagship). See `auditor datasets`."
    ),
    source: Optional[Path] = typer.Option(
        None, "--source", "-s", help="Audit this CSV instead of the dataset's bundled file."
    ),
    out: Path = typer.Option(Path("report.html"), "--out", "-o", help="Where to write the HTML report."),
    cap: int = typer.Option(50, "--cap", help="Max distinct findings shown per check in the report."),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Apply an authored rule fragment (from `auditor author`) to the spec."),
    open_report: bool = typer.Option(False, "--open", help="Open the report in a browser when done."),
) -> None:
    """Audit a dataset and write a self-contained HTML report."""
    spec = _spec_with_rules(dataset, rules)
    df = load(source, spec=spec)
    findings = run_all(df, spec)
    path = write(findings, spec, out, df=df, cap=cap, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

    by_sev = Counter(f.severity.value for f in findings)
    breakdown = ", ".join(f"{k}={v:,}" for k, v in sorted(by_sev.items())) or "none"
    typer.echo(f"audited {len(df):,} rows of {spec.name!r}: {len(findings):,} findings ({breakdown})")
    typer.echo(f"wrote {path}")
    if findings:
        typer.echo(f"next: open {path.name} and review the issues (keep / dismiss / needs-review)")
    if open_report:
        webbrowser.open(path.resolve().as_uri())


@app.command(name="datasets")
def list_datasets() -> None:
    """List the datasets the auditor knows about."""
    for name, spec in sorted(DATASETS.items()):
        marker = "  (default)" if spec is DEFAULT else ""
        typer.echo(f"{name}{marker}")
        if spec.source_url:
            typer.echo(f"    {spec.source_url}")


@app.command()
def brief(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset to brief."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Brief this CSV instead."),
    out: Path = typer.Option(Path("briefing.md"), "--out", "-o", help="Where to write the Markdown briefing."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Local model to use (default: AUDITOR_LLM_MODEL)."),
) -> None:
    """Write a local-LLM research briefing (column meanings, pitfalls, suggested checks).

    Uses only column metadata, never raw rows. Needs a local LLM server; if none is
    reachable the briefing is skipped (the deterministic audit is unaffected).
    """
    from auditor.llm import LLMTimeout
    from auditor.research import brief as make_briefing, to_markdown

    _use_model(model)
    spec = get(dataset)
    df = load(source, spec=spec)
    try:
        briefing = make_briefing(df, spec)
    except LLMTimeout:
        # Reachable but too slow to finish - say so plainly. The usual cause on a
        # single-GPU box is VRAM oversubscription (the driver paging GPU memory to
        # system RAM), which throttles decoding. Distinct from "no server".
        typer.echo(
            "local LLM reachable but the briefing timed out - the model is too slow "
            "to finish.\nLikely VRAM pressure: restart vLLM with a lower "
            "--gpu-memory-utilization (e.g. 0.80) and/or smaller --max-model-len, "
            "or free GPU memory."
        )
        raise typer.Exit(code=1)
    if briefing is None:
        typer.echo("local LLM not reachable - briefing skipped (start the vLLM server first)")
        return
    out.write_text(to_markdown(briefing, spec), encoding="utf-8")
    typer.echo(f"wrote briefing for {len(briefing.columns)} columns -> {out}")


@app.command()
def triage(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset to audit then triage."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Audit this CSV instead."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the triage to this Markdown file (else print)."),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Apply an authored rule fragment (from `auditor author`) to the spec."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Local model to use (default: AUDITOR_LLM_MODEL)."),
) -> None:
    """Run the audit, then ask the local LLM to prioritize its findings (advisory).

    Collapses findings to distinct issues and has the model rank them and flag which
    look like genuine defects vs expected artifacts. Needs a local LLM server; if none
    is reachable the triage is skipped (the findings are unaffected).
    """
    from auditor.llm import LLMTimeout
    from auditor.triage import issue_groups, to_markdown, triage as run_triage

    _use_model(model)
    spec = _spec_with_rules(dataset, rules)
    df = load(source, spec=spec)
    findings = run_all(df, spec)
    groups = issue_groups(findings)
    if not groups:
        typer.echo("no findings to triage.")
        return
    try:
        notes = run_triage(findings, spec)  # advisory layer; None if no LLM
    except LLMTimeout:
        typer.echo(
            "local LLM reachable but triage timed out - the model is too slow to finish.\n"
            "Likely VRAM pressure: restart vLLM with a lower --gpu-memory-utilization, "
            "or free GPU memory."
        )
        raise typer.Exit(code=1)
    if notes is None:
        typer.echo("(local LLM not reachable - priority order shown without the advisory notes)")
    # The deterministic priority/order is always produced; the LLM notes are optional.
    md = to_markdown(notes, spec, groups)
    if out is not None:
        out.write_text(md, encoding="utf-8")
        typer.echo(f"wrote triage of {len(groups)} issues -> {out}")
    else:
        typer.echo(md)


@app.command(name="rubric")
def rubric_cmd(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset to score."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Score this CSV instead."),
    rules: Optional[Path] = typer.Option(None, "--rules", help="Apply an authored rule fragment to the spec."),
    json_out: bool = typer.Option(False, "--json", help="Emit the rubric as JSON instead of a table."),
) -> None:
    """Score dataset readiness: per-dimension clean rates from the deterministic findings.

    Aggregates the deterministic checks into completeness / consistency / plausibility /
    duplication / privacy, plus an overall readiness. This is a deterministic roll-up of
    facts: LLM-judged labels are advisory only and never move a score. A dimension whose
    checks did not run for this dataset shows 'n/a', never a misleading 100.
    """
    import json

    from auditor import rubric as rubric_mod

    spec = _spec_with_rules(dataset, rules)
    df = load(source, spec=spec)
    findings = run_all(df, spec)
    r = rubric_mod.score(findings, len(df), not_assessed=rubric_mod.unassessed_dimensions(spec))

    if json_out:
        typer.echo(json.dumps(r.as_dict(), indent=2))
        return

    head = f"{r.readiness:.0f}/100" if r.readiness is not None else "n/a"
    typer.echo(f"readiness: {head}   ({spec.name}, {r.n_rows:,} rows)")
    for d in r.dimensions:
        if not d.assessed:
            typer.echo(f"  {d.name:<13} n/a   (not assessed for this dataset)")
        else:
            if d.affected_rows:
                tail = f"{d.affected_rows:,} rows affected"
            elif d.n_findings:
                tail = f"{d.n_findings} dataset-level issue(s)"
            else:
                tail = "clean"
            typer.echo(f"  {d.name:<13} {d.score:5.1f}   ({tail})")
        if d.advisory:
            typer.echo(
                f"  {'':13}       advisory: {d.advisory['labels_flagged_rows']} rows "
                f"LLM-flagged (not scored)"
            )


@app.command()
def author(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset to author range rules for."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Author from this CSV instead."),
    autonomy: str = typer.Option("balanced", "--autonomy", help="ask-all | balanced | hands-off."),
    out: Path = typer.Option(Path("authored_rules.py"), "--out", "-o", help="Where to write the spec fragment (a .log.json sits beside it)."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Local model to use (default: AUDITOR_LLM_MODEL)."),
) -> None:
    """Guided rule-authoring: the model proposes range rules, you approve them (slice 1).

    For each numeric column the model proposes a bound, which is dry-run against the real
    check so you decide on actual flag counts. Under --autonomy ask-all you answer every
    question (or say 'you choose'); balanced auto-decides the safe ones; hands-off decides
    all and reports what it did. Needs a local LLM server. Emits a range_rules fragment
    plus a JSON decision log. Never edits data -- it only proposes checks.
    """
    import json

    from auditor.authoring import AUTONOMY, run_session, summarize

    _use_model(model)
    if autonomy not in AUTONOMY:
        typer.echo(f"--autonomy must be one of {', '.join(AUTONOMY)}")
        raise typer.Exit(code=2)

    spec = get(dataset)
    df = load(source, spec=spec)
    result = run_session(df, spec, autonomy)
    if not result.log:
        typer.echo("local LLM not reachable, or no candidates proposed - nothing to author "
                   "(start the vLLM server, e.g. AUDITOR_LLM_MODEL=...).")
        raise typer.Exit(code=1)

    out.write_text(result.fragment, encoding="utf-8")
    log_path = out.with_suffix(".log.json")
    log_path.write_text(json.dumps(result.log, indent=2), encoding="utf-8")
    typer.echo(summarize(result))
    typer.echo(f"wrote {out} (+ decision log {log_path.name})")


@app.command(name="profile")
def show_profile(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Dataset to profile."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Profile this CSV instead."),
) -> None:
    """Print an exploratory profile of a dataset (no findings, just shape and smells)."""
    spec = get(dataset)
    typer.echo(profile(load(source, spec=spec), spec))


if __name__ == "__main__":
    app()
