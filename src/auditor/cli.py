"""Command-line interface — the single entry point a user actually touches.

`auditor run` ties the whole pipeline together (load -> checks -> HTML report) so
nobody has to import the internals. The commands are deliberately thin: each is a
few lines delegating to ``load`` / ``checks`` / ``report``, which are the tested
units. The CLI's own job is just argument parsing and friendly output.

Installed as the ``auditor`` console script (see ``pyproject.toml``); also runnable
as ``python -m auditor.cli``.
"""

from __future__ import annotations

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
    open_report: bool = typer.Option(False, "--open", help="Open the report in a browser when done."),
) -> None:
    """Audit a dataset and write a self-contained HTML report."""
    spec = get(dataset)
    df = load(source, spec=spec)
    findings = run_all(df, spec)
    path = write(findings, spec, out, df=df, cap=cap, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

    by_sev = Counter(f.severity.value for f in findings)
    breakdown = ", ".join(f"{k}={v:,}" for k, v in sorted(by_sev.items())) or "none"
    typer.echo(f"audited {len(df):,} rows of {spec.name!r}: {len(findings):,} findings ({breakdown})")
    typer.echo(f"wrote {path}")
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
) -> None:
    """Write a local-LLM research briefing (column meanings, pitfalls, suggested checks).

    Uses only column metadata, never raw rows. Needs a local LLM server; if none is
    reachable the briefing is skipped (the deterministic audit is unaffected).
    """
    from auditor.llm import LLMTimeout
    from auditor.research import brief as make_briefing, to_markdown

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
) -> None:
    """Run the audit, then ask the local LLM to prioritize its findings (advisory).

    Collapses findings to distinct issues and has the model rank them and flag which
    look like genuine defects vs expected artifacts. Needs a local LLM server; if none
    is reachable the triage is skipped (the findings are unaffected).
    """
    from auditor.llm import LLMTimeout
    from auditor.triage import issue_groups, to_markdown, triage as run_triage

    spec = get(dataset)
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


@app.command()
def capture(
    export: Path = typer.Argument(..., help="decisions-*.json exported from the report."),
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Domain (default: inferred from the export)."),
    source: Optional[Path] = typer.Option(None, "--source", "-s", help="Re-audit this CSV (must match the report's data)."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Cases file (default: benchmarks/cases/<dataset>/triage_verdict.jsonl)."),
    append: bool = typer.Option(True, "--append/--overwrite", help="Merge with existing cases (default) or replace them."),
) -> None:
    """Turn the report's keep/dismiss decisions into labelled benchmark cases.

    keep -> real_defect, dismiss -> expected_artifact. Re-runs the audit to get the
    canonical issue shape (counts, samples) and attaches the human's verdict, writing the
    same JSONL the benchmark grades. Feeds `auditor select-model`.
    """
    from auditor.capture import load_export, to_cases, write_cases
    from auditor.triage import issue_groups

    decisions = load_export(export)
    if dataset is None and decisions:
        dataset = decisions[0].get("dataset")
    spec = get(dataset)

    df = load(source, spec=spec)
    groups = issue_groups(run_all(df, spec))
    cases, summary = to_cases(groups, decisions)
    if not cases:
        typer.echo(
            f"no labelled cases produced ({summary['undecided']} issue(s) undecided, "
            f"{summary['conflict']} conflicted). Keep/dismiss some issues, then export again."
        )
        raise typer.Exit(code=1)

    out_path = out or Path("benchmarks/cases") / spec.name / "triage_verdict.jsonl"
    total = write_cases(cases, out_path, append=append)
    note = f", {summary['conflict']} conflicted" if summary["conflict"] else ""
    typer.echo(
        f"captured {summary['labeled']} case(s) for {spec.name!r}{note} -> {out_path} "
        f"({total} total). Now: auditor select-model -d {spec.name} -m <model>"
    )


@app.command(name="select-model")
def select_model(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Domain whose captured cases to benchmark."),
    cases: Optional[Path] = typer.Option(None, "--cases", help="Cases file (default: benchmarks/cases/<dataset>/triage_verdict.jsonl)."),
    model: list[str] = typer.Option([], "--model", "-m", help="Local model id to score (repeatable). Default: AUDITOR_LLM_MODEL."),
    timeout: float = typer.Option(120.0, "--timeout", help="Per-call timeout (s); reasoning models need headroom."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the scoreboard Markdown here (else print)."),
) -> None:
    """Score local models on a domain's verdict cases and recommend the most reliable.

    Turns the benchmark into a user-facing answer to "which local model should I trust
    for this dataset's hard, model-judged calls?" Reuses the captured/labelled cases as
    ground truth. Needs a local LLM server; with none reachable it says so and stops.
    """
    from auditor.llm import LLMClient
    from auditor.modelselect import load_cases, recommend, render_scoreboard, score_model

    spec = get(dataset)
    cases_path = cases or Path("benchmarks/cases") / spec.name / "triage_verdict.jsonl"
    if not cases_path.exists():
        typer.echo(f"no cases for {spec.name!r} at {cases_path} - run an audit and `auditor capture` first.")
        raise typer.Exit(code=1)
    loaded = load_cases(cases_path)
    if not loaded:
        typer.echo(f"{cases_path} has no cases yet.")
        raise typer.Exit(code=1)

    # Default to the env/configured model when no -m is given.
    models = model or [LLMClient.from_env().model]
    scores = []
    for name in models:
        client = LLMClient.from_env(model=name, timeout=timeout)
        if not client.available():
            typer.echo(f"local LLM not reachable (model={name}); start the vLLM server first")
            raise typer.Exit(code=1)
        typer.echo(f"scoring {name} on {len(loaded)} {spec.name} case(s)...")
        scores.append(score_model(client, loaded, spec))
        client.close()

    md = render_scoreboard(spec.name, scores, recommend(scores))
    if out is not None:
        out.write_text(md + "\n", encoding="utf-8")
        typer.echo(f"wrote scoreboard -> {out}")
    else:
        typer.echo(md)


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
