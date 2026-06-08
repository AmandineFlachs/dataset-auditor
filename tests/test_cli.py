"""CLI tests. They run on a tiny temp CSV via --source, so no bundled data or
network is needed and they stay fast."""

from typer.testing import CliRunner

from auditor.cli import app

runner = CliRunner()

# Minimal meteorite-shaped CSV with one clearly-bad row (year in the future).
_CSV = "name,id,mass,year,reclat,reclong\nAachen,1,21,1880,50.7,6.0\nFuture,2,5,2501,0.0,0.0\n"


def _write_csv(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(_CSV)
    return p


def test_run_writes_a_report(tmp_path):
    out = tmp_path / "r.html"
    result = runner.invoke(
        app, ["run", "--dataset", "meteorites", "--source", str(_write_csv(tmp_path)), "--out", str(out)]
    )
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert "findings" in result.output  # the summary line


def test_run_reports_the_planted_future_year(tmp_path):
    out = tmp_path / "r.html"
    runner.invoke(
        app, ["run", "--dataset", "meteorites", "--source", str(_write_csv(tmp_path)), "--out", str(out)]
    )
    html = out.read_text(encoding="utf-8")
    assert "units.out_of_range" in html  # year=2501 was caught end-to-end


def test_datasets_lists_known_specs():
    result = runner.invoke(app, ["datasets"])
    assert result.exit_code == 0
    assert "meteorites" in result.output
    assert "lemat_bulk" in result.output
    assert "(default)" in result.output


def test_profile_prints_shape(tmp_path):
    result = runner.invoke(
        app, ["profile", "--dataset", "meteorites", "--source", str(_write_csv(tmp_path))]
    )
    assert result.exit_code == 0
    assert "rows: 2" in result.output


def test_unknown_dataset_exits_nonzero():
    result = runner.invoke(app, ["run", "--dataset", "does-not-exist"])
    assert result.exit_code != 0


def test_brief_reports_timeout_honestly(tmp_path, monkeypatch):
    # A reachable-but-too-slow server must not be reported as "not reachable".
    from auditor.llm import LLMTimeout

    def boom(*a, **k):
        raise LLMTimeout("timed out")

    monkeypatch.setattr("auditor.research.brief", boom)
    out = tmp_path / "b.md"
    result = runner.invoke(
        app, ["brief", "--dataset", "meteorites", "--source", str(_write_csv(tmp_path)), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "timed out" in result.output and "not reachable" not in result.output
    assert not out.exists()


def test_brief_skips_gracefully_with_no_server(tmp_path):
    # Point the client at an unreachable port so available() is deterministically False.
    out = tmp_path / "b.md"
    result = runner.invoke(
        app,
        ["brief", "--dataset", "meteorites", "--source", str(_write_csv(tmp_path)), "--out", str(out)],
        env={"AUDITOR_LLM_BASE_URL": "http://localhost:9/v1"},
    )
    assert result.exit_code == 0
    assert "skipped" in result.output
    assert not out.exists()  # nothing written when the briefing is skipped
