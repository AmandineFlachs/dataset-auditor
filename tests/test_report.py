"""Tests for the HTML report renderer (Triage design).

These pin the behaviors that make the report usable on real audits: aggregation of
identical findings, capping of distinct findings, the summary strip + category rail,
the expandable issue rows, the browser-local triage worklist, the reference panels,
and the safety properties (untrusted evidence escaped; the file is self-contained).
"""

import re

import pandas as pd

from auditor import report
from auditor.datasets import METEORITES
from auditor.models import Finding, Severity


def _f(check, severity, **kw):
    kw.setdefault("message", f"msg for {check}")
    return Finding(check=check, severity=severity, **kw)


# -- header / summary ---------------------------------------------------------


def test_render_includes_header_and_finding_details():
    findings = [
        _f("units.out_of_range", Severity.ERROR, row_id=3, field="year",
           message="year is in the future", evidence="year=2501"),
        _f("schema.high_null_rate", Severity.WARN, field="reclat", evidence="16% null"),
    ]
    html = report.render(findings, METEORITES, n_rows=100, generated_at="2026-06-06")
    assert "meteorites" in html
    assert "100 rows audited" in html
    assert "year is in the future" in html and "year=2501" in html
    assert "units.out_of_range" in html  # the machine name still appears (in the drill-down)
    assert "2026-06-06" in html


def test_summary_strip_leads_with_count_and_severity():
    findings = [_f("units.out_of_range", Severity.ERROR, row_id=i, field="year") for i in range(3)]
    findings += [_f("near_dup.shared_content", Severity.WARN, row_id=99, field="fp")]
    html = report.render(findings, METEORITES, n_rows=100)
    assert 'class="summary-strip"' in html
    assert "issues found" in html
    assert "rows clean" in html              # the clean-rate metric
    assert "Needs fixing" in html and "Worth a look" in html  # plain severity words


def test_category_rail_lists_each_check_with_counts():
    findings = [_f("units.out_of_range", Severity.ERROR, row_id=i, field="year") for i in range(3)]
    findings += [_f("near_dup.shared_content", Severity.WARN, row_id=99, field="fp")]
    html = report.render(findings, METEORITES, n_rows=100)
    assert 'class="cat-nav"' in html
    assert 'data-cat="all"' in html
    assert 'data-cat="units.out_of_range"' in html
    assert "All issues" in html


# -- aggregation / capping ----------------------------------------------------


def test_identical_findings_are_aggregated():
    # 120 findings differing only by row_id collapse to ONE issue carrying the count.
    findings = [_f("units.null_island", Severity.WARN, row_id=i, field="reclat+reclong",
                   evidence="(0, 0)") for i in range(120)]
    html = report.render(findings, METEORITES)
    assert html.count('data-fkey="') == 1     # a single aggregated issue
    assert 'data-count="120"' in html         # carrying the full count
    assert "Affects 120 rows" in html         # and the sample ids in the drill-down


def test_distinct_findings_are_capped():
    # 120 findings with DISTINCT evidence -> 120 signatures, capped to `cap`.
    findings = [_f("near_dup.shared_content", Severity.WARN, row_id=i, field="fp",
                   evidence=f"fp={i}") for i in range(120)]
    html = report.render(findings, METEORITES, cap=50)
    assert html.count('data-fkey="') == 50    # 50 distinct issues shown, rest capped
    assert "70 more distinct findings" in html


def test_groups_ordered_most_severe_first():
    findings = [_f("z.warn_check", Severity.WARN), _f("a.error_check", Severity.ERROR)]
    html = report.render(findings, METEORITES)
    assert html.index("a.error_check") < html.index("z.warn_check")


# -- issue row drill-down -----------------------------------------------------


def test_issue_detail_shows_evidence_fix_and_check():
    html = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year",
                             evidence="year=2501", suggested_fix="verify source")], METEORITES)
    assert 'class="issue-detail"' in html
    assert "Evidence" in html and "year=2501" in html
    assert "Suggested fix" in html and "verify source" in html
    assert "Affects 1 row" in html


def test_found_expected_pair_when_check_has_expected():
    # A check with a concrete target renders a red Found -> green Expected pair, and the
    # fix moves to its own line.
    html = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year",
                             evidence="year=2501", expected="within (-inf, 2025]",
                             suggested_fix="verify source")], METEORITES)
    assert ">Found<" in html and ">Expected<" in html
    assert "within (-inf, 2025]" in html
    assert ">Suggested fix<" not in html  # the fix is a line, not the green box
    assert "verify source" in html


def test_falls_back_to_evidence_fix_without_expected():
    # A judgement-style check with no single right answer keeps Evidence -> Suggested fix.
    html = report.render([_f("near_dup.shared_content", Severity.WARN, row_id=1, field="fp",
                             evidence="fp=aaa", suggested_fix="merge or confirm")], METEORITES)
    assert ">Evidence<" in html and ">Suggested fix<" in html
    assert ">Expected<" not in html


def test_drilldown_shows_example_row_when_dataframe_passed():
    df = pd.DataFrame({"row_id": [0, 1], "year": [2501, 1990], "recclass": ["L5", "H6"]})
    findings = [_f("units.out_of_range", Severity.ERROR, row_id=0, field="year", evidence="year=2501")]
    html = report.render(findings, METEORITES, df=df)
    assert "L5" in html  # the actual offending row's other fields appear in the record context


# -- triage worklist ----------------------------------------------------------


def test_triage_controls_rendered():
    html = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year",
                             evidence="year=2501")], METEORITES)
    assert 'data-fkey="' in html              # stable per-finding key for persistence
    assert 'data-act="keep"' in html and 'data-act="dismiss"' in html  # status actions
    assert "data-status" in html              # the status tag
    assert 'id="export"' in html              # export button
    assert "localStorage" in html             # saved in the browser, no server
    assert 'class="tnote"' in html            # per-finding note field


def test_finding_key_is_stable_and_row_independent():
    a = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year",
                          evidence="year=2501")], METEORITES)
    b = report.render([_f("units.out_of_range", Severity.ERROR, row_id=999, field="year",
                          evidence="year=2501")], METEORITES)
    key_a = re.search(r'data-fkey="([0-9a-f]+)"', a).group(1)
    key_b = re.search(r'data-fkey="([0-9a-f]+)"', b).group(1)
    assert key_a == key_b
    c = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year",
                          evidence="year=3000")], METEORITES)
    key_c = re.search(r'data-fkey="([0-9a-f]+)"', c).group(1)
    assert key_c != key_a


# -- reference panels ---------------------------------------------------------


def test_reference_panels_rendered_with_dataframe():
    df = pd.DataFrame({
        "row_id": [0, 1, 2, 3],
        "mass_g": [1.0, 2.0, None, 4.0],
        "fall": ["Fell", "Found", "Fell", "Fell"],
        "nametype": ["Valid", "Valid", "Relict", "Valid"],
    })
    findings = [_f("schema.high_null_rate", Severity.WARN, field="mass_g")]
    html = report.render(findings, METEORITES, df=df)
    assert "Dataset overview" in html
    assert "mass_g" in html and "25.0%" in html  # 1 of 4 missing
    assert "Fell" in html                         # categorical value-count
    assert "Findings by column" in html


def test_field_summary_ranks_most_affected_column():
    findings = [_f("units.out_of_range", Severity.ERROR, field="reclong") for _ in range(5)]
    findings += [_f("schema.high_null_rate", Severity.WARN, field="mass_g")]
    html = report.render(findings, METEORITES)
    assert "Findings by column" in html
    assert html.index("reclong") < html.index("mass_g")


# -- safety / self-contained --------------------------------------------------


def test_evidence_is_html_escaped():
    findings = [_f("pii.email", Severity.ERROR, row_id=1, field="note",
                   evidence="<script>alert(1)</script>")]
    html = report.render(findings, METEORITES)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_report_has_no_external_resources():
    html = report.render([_f("units.out_of_range", Severity.ERROR, row_id=1, field="year")], METEORITES)
    assert "<style>" in html               # CSS is inline
    assert "src=" not in html              # no external script/img src
    assert 'rel="stylesheet"' not in html  # no external CSS / web fonts
    assert "cdn" not in html.lower()       # no CDN references
    assert "fonts.googleapis" not in html  # fonts stay system / self-contained


def test_clean_dataset_shows_pass_message():
    html = report.render([], METEORITES)
    assert "No findings" in html and "0 findings" in html


def test_clean_dataset_still_shows_health_view():
    # A zero-findings dataset must still surface the health summary (readiness +
    # profile), not just a bare "No findings" card.
    df = pd.DataFrame({
        "row_id": [0, 1, 2, 3],
        "mass_g": [1.0, 2.0, 3.0, 4.0],
        "fall": ["Fell", "Found", "Fell", "Fell"],
        "nametype": ["Valid", "Valid", "Relict", "Valid"],
    })
    html = report.render([], METEORITES, df=df)
    assert "No findings" in html              # still says it's clean
    assert "Dataset readiness" in html        # ...and shows the rubric
    assert "Dataset overview" in html         # ...and the profile
    assert "Fell" in html                     # categorical distribution rendered


def test_design_tokens_and_triage_layout():
    html = report.render([_f("a.b", Severity.WARN, row_id=1)], METEORITES)
    assert "--paper:" in html and "--c-critical:" in html  # the Signal token system
    assert 'class="triage"' in html and 'class="rail"' in html and 'class="stream"' in html


def test_write_creates_a_document(tmp_path):
    out = report.write([_f("units.out_of_range", Severity.ERROR, row_id=1, evidence="e")],
                       METEORITES, tmp_path / "r.html", n_rows=10)
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
