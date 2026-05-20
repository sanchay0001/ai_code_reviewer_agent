# ═══════════════════════════════════════════════════════════════
# tests/test_phase4_dashboard.py
# PURPOSE: Test all non-UI logic in app.py — report generation,
#          comment filtering, confidence display, markdown output,
#          and the full end-to-end pipeline integration.
#          Run with: python tests/test_phase4_dashboard.py
# ═══════════════════════════════════════════════════════════════

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Import pipeline modules
from core.ingestion import clone_and_collect, cleanup_repo
from core.parser    import parse_files, get_parse_summary
from core.reviewer  import get_review_summary, _get_confidence_tier

# Import dashboard helper functions directly from app.py
from app import generate_markdown_report


# ══════════════════════════════════════════════════════════════
# Shared fake data — used across multiple tests
# ══════════════════════════════════════════════════════════════

# Simulates what review_all_chunks() returns after a real review
FAKE_RESULTS = [
    {
        "chunk_id":   "auth.py::login",
        "file":       "auth.py",
        "name":       "login",
        "type":       "function",
        "start_line": 1,
        "end_line":   10,
        "error":      None,
        "comments": [
            {
                "issue":           "SQL injection vulnerability",
                "description":     "User input is concatenated directly into a SQL query.",
                "suggestion":      "Use parameterised queries instead.",
                "severity":        "critical",
                "category":        "security",
                "line_hint":       "5",
                "confidence":      95,
                "confidence_tier": "high",
            },
            {
                "issue":           "Hardcoded password",
                "description":     "The password 'admin123' is hardcoded in the source.",
                "suggestion":      "Load credentials from environment variables.",
                "severity":        "critical",
                "category":        "security",
                "line_hint":       "2",
                "confidence":      98,
                "confidence_tier": "high",
            },
        ],
    },
    {
        "chunk_id":   "utils.py::process_data",
        "file":       "utils.py",
        "name":       "process_data",
        "type":       "function",
        "start_line": 15,
        "end_line":   40,
        "error":      None,
        "comments": [
            {
                "issue":           "No input validation",
                "description":     "Function does not validate input types.",
                "suggestion":      "Add type checks at the start of the function.",
                "severity":        "medium",
                "category":        "bug",
                "line_hint":       "16",
                "confidence":      72,
                "confidence_tier": "medium",
            },
            {
                # Low-confidence comment — should trigger 'verify this'
                "issue":           "Possible memory leak",
                "description":     "Object may not be released in all code paths.",
                "suggestion":      "Use a context manager or explicit cleanup.",
                "severity":        "high",
                "category":        "performance",
                "line_hint":       "30",
                "confidence":      35,
                "confidence_tier": "low",
            },
        ],
    },
    {
        # A chunk with no issues — clean code
        "chunk_id":   "helpers.py::add",
        "file":       "helpers.py",
        "name":       "add",
        "type":       "function",
        "start_line": 1,
        "end_line":   3,
        "error":      None,
        "comments":   [],
    },
    {
        # A chunk where the LLM call failed
        "chunk_id":   "broken.py::SYNTAX_ERROR",
        "file":       "broken.py",
        "name":       "SYNTAX_ERROR",
        "type":       "module_level",
        "start_line": 1,
        "end_line":   5,
        "error":      "Review failed after 3 attempts: rate limit",
        "comments":   [],
    },
]

FAKE_SUMMARY = get_review_summary(FAKE_RESULTS)
FAKE_PARSE_SUMMARY = {
    "total_chunks": 4,
    "total_files":  3,
    "functions":    3,
    "classes":      0,
    "parse_errors": 1,
    "large_chunks": 0,
}


# ══════════════════════════════════════════════════════════════
# 1. Review Summary Tests
# ══════════════════════════════════════════════════════════════

def test_summary_total_comments():
    """Summary should count all comments across all chunks."""
    assert FAKE_SUMMARY["total_comments"] == 4
    print(f"  ✓ total_comments = 4")


def test_summary_severity_counts():
    """Severity counts should tally correctly."""
    sev = FAKE_SUMMARY["severity_counts"]
    assert sev["critical"] == 2
    assert sev["medium"]   == 1
    assert sev["high"]     == 1
    print(f"  ✓ severity_counts = {sev}")


def test_summary_tier_counts():
    """Confidence tier counts should bucket correctly."""
    tiers = FAKE_SUMMARY["tier_counts"]
    assert tiers["high"]   == 2   # confidence 95 and 98
    assert tiers["medium"] == 1   # confidence 72
    assert tiers["low"]    == 1   # confidence 35
    print(f"  ✓ tier_counts = {tiers}")


def test_summary_avg_confidence():
    """Average confidence should be correct."""
    # (95 + 98 + 72 + 35) / 4 = 75.0
    assert FAKE_SUMMARY["avg_confidence"] == 75.0
    print(f"  ✓ avg_confidence = {FAKE_SUMMARY['avg_confidence']}%")


def test_summary_failed_chunks():
    """Failed chunk count should reflect chunks with errors."""
    assert FAKE_SUMMARY["failed_chunks"] == 1
    print(f"  ✓ failed_chunks = 1")


def test_summary_files_reviewed():
    """Files reviewed should be unique file count."""
    # FAKE_RESULTS has 4 unique files: auth.py, utils.py, helpers.py, broken.py
    assert FAKE_SUMMARY["files_reviewed"] == 4
    print(f"  ✓ files_reviewed = 4 (auth.py, utils.py, helpers.py, broken.py)")


# ══════════════════════════════════════════════════════════════
# 2. Confidence Tier Tests
# ══════════════════════════════════════════════════════════════

def test_confidence_tier_high():
    """Scores 75+ should be 'high' tier."""
    assert _get_confidence_tier(100) == "high"
    assert _get_confidence_tier(75)  == "high"
    print("  ✓ 75-100 → 'high' tier")


def test_confidence_tier_medium():
    """Scores 50-74 should be 'medium' tier."""
    assert _get_confidence_tier(74) == "medium"
    assert _get_confidence_tier(50) == "medium"
    print("  ✓ 50-74 → 'medium' tier")


def test_confidence_tier_low():
    """Scores below 50 should be 'low' tier → triggers 'verify this'."""
    assert _get_confidence_tier(49) == "low"
    assert _get_confidence_tier(0)  == "low"
    print("  ✓ 0-49 → 'low' tier → 'verify this' label shown")


def test_low_confidence_comments_identified():
    """We should be able to find all low-confidence comments in results."""
    low_conf = []
    for r in FAKE_RESULTS:
        for c in r.get("comments", []):
            if c.get("confidence_tier") == "low":
                low_conf.append(c)

    assert len(low_conf) == 1
    assert low_conf[0]["issue"] == "Possible memory leak"
    print(f"  ✓ Found {len(low_conf)} low-confidence comment — 'verify this' will be shown")


# ══════════════════════════════════════════════════════════════
# 3. Filter Logic Tests
# ══════════════════════════════════════════════════════════════

def _apply_filters(results, severities, confidence_tiers, categories):
    """
    Mirror the filter logic from app.py main() so we can test it here.
    Returns filtered list of (result, comment) tuples.
    """
    filtered = []
    for result in results:
        for comment in result.get("comments", []):
            if comment.get("severity")        not in severities:        continue
            if comment.get("confidence_tier") not in confidence_tiers:  continue
            if comment.get("category")        not in categories:        continue
            filtered.append((result, comment))
    return filtered


def test_filter_by_severity():
    """Filtering to only 'critical' should return 2 comments."""
    filtered = _apply_filters(
        FAKE_RESULTS,
        severities=["critical"],
        confidence_tiers=["high","medium","low"],
        categories=["bug","security","performance","style","maintainability","error_handling","documentation"],
    )
    assert len(filtered) == 2
    for _, c in filtered:
        assert c["severity"] == "critical"
    print(f"  ✓ Filter severity=critical → {len(filtered)} comment(s)")


def test_filter_by_confidence_tier():
    """Filtering to only 'low' confidence should return 1 comment."""
    filtered = _apply_filters(
        FAKE_RESULTS,
        severities=["critical","high","medium","low","info"],
        confidence_tiers=["low"],
        categories=["bug","security","performance","style","maintainability","error_handling","documentation"],
    )
    assert len(filtered) == 1
    assert filtered[0][1]["confidence_tier"] == "low"
    print(f"  ✓ Filter confidence_tier=low → {len(filtered)} comment (verify this)")


def test_filter_by_category():
    """Filtering to only 'security' should return 2 comments."""
    filtered = _apply_filters(
        FAKE_RESULTS,
        severities=["critical","high","medium","low","info"],
        confidence_tiers=["high","medium","low"],
        categories=["security"],
    )
    assert len(filtered) == 2
    for _, c in filtered:
        assert c["category"] == "security"
    print(f"  ✓ Filter category=security → {len(filtered)} comment(s)")


def test_filter_all_excluded():
    """Selecting no filters should return 0 comments."""
    filtered = _apply_filters(
        FAKE_RESULTS,
        severities=[],
        confidence_tiers=[],
        categories=[],
    )
    assert len(filtered) == 0
    print("  ✓ Empty filter selection → 0 results")


def test_filter_all_included():
    """Default filters (everything selected) should return all 4 comments."""
    filtered = _apply_filters(
        FAKE_RESULTS,
        severities=["critical","high","medium","low","info"],
        confidence_tiers=["high","medium","low"],
        categories=["bug","security","performance","style","maintainability","error_handling","documentation"],
    )
    assert len(filtered) == 4
    print(f"  ✓ All filters selected → {len(filtered)} comments (all shown)")


# ══════════════════════════════════════════════════════════════
# 4. Markdown Report Tests
# ══════════════════════════════════════════════════════════════

def test_report_generates_without_error():
    """generate_markdown_report should not crash."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert isinstance(report, str)
    assert len(report) > 100
    print(f"  ✓ Report generated ({len(report)} chars)")


def test_report_contains_repo_url():
    """Report must contain the repo URL."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert "https://github.com/test/repo" in report
    print("  ✓ Report contains repo URL")


def test_report_contains_severity_table():
    """Report must include a severity summary table."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert "Severity Summary" in report
    assert "Critical" in report or "critical" in report
    print("  ✓ Severity summary table present")


def test_report_contains_verify_label():
    """Low-confidence comments must be marked with VERIFY THIS in report."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert "VERIFY THIS" in report
    print("  ✓ 'VERIFY THIS' label present for low-confidence comments")


def test_report_contains_all_files():
    """Every reviewed file should appear in the report."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert "auth.py"  in report
    assert "utils.py" in report
    print("  ✓ All files present in report")


def test_report_contains_suggestions():
    """Suggestions must be included in the report."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert "parameterised queries" in report or "Fix" in report
    print("  ✓ Suggestions present in report")


def test_report_is_valid_markdown():
    """Report should have standard Markdown headers."""
    report = generate_markdown_report(
        FAKE_RESULTS, "https://github.com/test/repo", FAKE_SUMMARY
    )
    assert report.startswith("# AI Code Review Report")
    assert "##" in report
    print("  ✓ Report has valid Markdown structure")


# ══════════════════════════════════════════════════════════════
# 5. End-to-End Pipeline Integration Test
# ══════════════════════════════════════════════════════════════

def test_end_to_end_pipeline():
    """
    Run the full pipeline on a tiny real repo:
    clone → parse → review (first 3 chunks only to save tokens) → summary
    Tests that all phases connect properly.
    """
    print("  → Cloning psf/requests (real network call)...")

    # Phase 1: Clone
    ingestion = clone_and_collect("https://github.com/psf/requests")
    assert ingestion["error"] is None, f"Clone failed: {ingestion['error']}"
    assert len(ingestion["files"]) > 0

    # Phase 2: Parse
    chunks = parse_files(ingestion["files"])
    assert len(chunks) > 0
    parse_sum = get_parse_summary(chunks)
    print(f"  → Parsed {parse_sum['total_chunks']} chunks from {parse_sum['total_files']} files")

    # Phase 3: Review only the first 3 chunks to save API tokens
    test_chunks = chunks[:3]
    print(f"  → Reviewing {len(test_chunks)} chunks via Groq...")

    from core.reviewer import review_all_chunks
    results = review_all_chunks(test_chunks)

    assert len(results) == 3
    # Every result must have comments key (even if empty list)
    for r in results:
        assert "comments" in r
        assert isinstance(r["comments"], list)

    # Phase 4: Summary
    summary = get_review_summary(results)
    assert summary["total_chunks"] == 3
    assert "severity_counts" in summary
    assert "tier_counts"     in summary
    assert "avg_confidence"  in summary

    # Cleanup
    cleanup_repo(ingestion["repo_path"])

    total_issues = summary["total_comments"]
    print(f"  ✓ End-to-end pipeline worked — {total_issues} issue(s) found in 3 chunks")
    print(f"  ✓ Summary: {summary['severity_counts']}")
    print(f"  ✓ Confidence tiers: {summary['tier_counts']}")


# ══════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  PHASE 4 — DASHBOARD & INTEGRATION TESTS")
    print("═" * 60)

    unit_tests = [
        # Summary stats
        ("Summary: total comments",              test_summary_total_comments),
        ("Summary: severity counts",             test_summary_severity_counts),
        ("Summary: confidence tier counts",      test_summary_tier_counts),
        ("Summary: average confidence",          test_summary_avg_confidence),
        ("Summary: failed chunks count",         test_summary_failed_chunks),
        ("Summary: files reviewed count",        test_summary_files_reviewed),

        # Confidence tier bucketing
        ("Confidence: high tier 75-100",         test_confidence_tier_high),
        ("Confidence: medium tier 50-74",        test_confidence_tier_medium),
        ("Confidence: low tier 0-49",            test_confidence_tier_low),
        ("Confidence: low comments identified",  test_low_confidence_comments_identified),

        # Filter logic
        ("Filter: by severity=critical",         test_filter_by_severity),
        ("Filter: by confidence_tier=low",       test_filter_by_confidence_tier),
        ("Filter: by category=security",         test_filter_by_category),
        ("Filter: all excluded → 0 results",     test_filter_all_excluded),
        ("Filter: all included → 4 results",     test_filter_all_included),

        # Markdown report
        ("Report: generates without error",      test_report_generates_without_error),
        ("Report: contains repo URL",            test_report_contains_repo_url),
        ("Report: severity table present",       test_report_contains_severity_table),
        ("Report: VERIFY THIS label present",    test_report_contains_verify_label),
        ("Report: all files listed",             test_report_contains_all_files),
        ("Report: suggestions included",         test_report_contains_suggestions),
        ("Report: valid Markdown structure",     test_report_is_valid_markdown),
    ]

    live_tests = [
        ("LIVE: end-to-end pipeline on real repo", test_end_to_end_pipeline),
    ]

    passed = failed = 0

    print("\n── Unit Tests (no API calls) ──────────────────────────")
    for name, fn in unit_tests:
        print(f"\n[TEST] {name}")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR : {type(e).__name__}: {e}")
            failed += 1

    print("\n── Live Integration Test (clones repo + calls Groq) ───")
    for name, fn in live_tests:
        print(f"\n[TEST] {name}")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR : {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "─" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("─" * 60)

    if failed == 0:
        print("\n  🎉 Phase 4 complete — run the dashboard with:")
        print("     streamlit run app.py\n")
    else:
        print(f"\n  ❌ Fix {failed} failure(s) before running the dashboard.\n")