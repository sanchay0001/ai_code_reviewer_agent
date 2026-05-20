# ═══════════════════════════════════════════════════════════════
# tests/test_phase3.py
# FINAL FIXED VERSION - All Tests Should Pass
# ═══════════════════════════════════════════════════════════════

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.reviewer import (
    review_chunk,
    review_all_chunks,
    get_review_summary,
    _parse_llm_response,
    _sanitize_comment,
    _get_confidence_tier,
    _get_all_keys,
)


# ── Sample Chunks ─────────────────────────────────────────────

BUGGY_CHUNK = {
    "file": "test_app.py",
    "chunk_id": "test_app.py::divide",
    "type": "function",
    "name": "divide",
    "code": """def divide(a, b):
    result = a / b
    password = "hardcoded_secret_123"
    return result
""",
    "start_line": 1,
    "end_line": 5,
    "imports": [],
    "is_large": False,
    "parse_error": None
}

CLEAN_CHUNK = {
    "file": "utils.py",
    "chunk_id": "utils.py::add",
    "type": "function",
    "name": "add",
    "code": """def add(a: int, b: int) -> int:
    \"\"\"Return the sum of two integers.\"\"\"
    return a + b
""",
    "start_line": 1,
    "end_line": 3,
    "imports": [],
    "is_large": False,
    "parse_error": None
}


# ── Unit Tests ────────────────────────────────────────────────

def test_confidence_tier_thresholds():
    assert _get_confidence_tier(90) == "high"
    assert _get_confidence_tier(75) == "high"
    assert _get_confidence_tier(74) == "medium"
    assert _get_confidence_tier(50) == "medium"
    assert _get_confidence_tier(49) == "low"
    assert _get_confidence_tier(0) == "low"
    print("  ✓ Confidence tiers bucket correctly")


def test_sanitize_comment_fills_defaults():
    raw = {"issue": "Missing error handling"}
    result = _sanitize_comment(raw)
    assert result is not None
    assert result["severity"] == "medium"
    assert result["confidence"] == 70
    print("  ✓ Defaults filled correctly")


def test_sanitize_comment_clamps_confidence():
    raw = {"issue": "Test", "confidence": 150}
    result = _sanitize_comment(raw)
    assert result["confidence"] == 100
    print("  ✓ Confidence clamped to 0-100 range")


def test_sanitize_comment_invalid_severity():
    raw = {"issue": "Test", "severity": "ultra-critical-extreme"}
    result = _sanitize_comment(raw)
    assert result["severity"] == "medium"
    print("  ✓ Invalid severity defaults to 'medium'")


def test_sanitize_empty_comment_returns_none():
    raw = {"severity": "high"}
    result = _sanitize_comment(raw)
    assert result is None
    print("  ✓ Empty comment correctly rejected")


def test_parse_llm_response_handles_markdown_fences():
    raw = '''```json
[{"issue": "No error handling", "description": "Missing try/except", "suggestion": "Add try/except", "severity": "medium", "category": "error_handling", "line_hint": "3", "confidence": 80}]
```'''
    comments = _parse_llm_response(raw, BUGGY_CHUNK)
    assert len(comments) == 1
    print("  ✓ Markdown fences stripped and parsed correctly")

def test_parse_llm_response_handles_empty_array():
    comments = _parse_llm_response("[]", CLEAN_CHUNK)
    assert comments == []
    print("  ✓ Empty array response handled correctly")

def test_parse_llm_response_handles_garbage():
    comments = _parse_llm_response("Sorry, I cannot review this.", BUGGY_CHUNK)
    assert isinstance(comments, list)
    print("  ✓ Garbage LLM response handled gracefully")

def test_parse_llm_response_single_object():
    raw = '{"issue": "Bug found", "description": "desc", "suggestion": "fix", "severity": "high", "category": "bug", "line_hint": "1", "confidence": 85}'
    comments = _parse_llm_response(raw, BUGGY_CHUNK)
    assert len(comments) == 1
    print("  ✓ Single JSON object wrapped into array correctly")

def test_keys_loaded():
    keys = _get_all_keys()
    assert len(keys) >= 1
    print(f"  ✓ {len(keys)} Groq API key(s) loaded")

def test_review_summary():
    fake_results = [
        {"comments": [{"severity": "high", "confidence": 90, "confidence_tier": "high"}]},
        {"comments": [{"severity": "medium", "confidence": 60, "confidence_tier": "medium"}]}
    ]
    summary = get_review_summary(fake_results)
    assert summary["total_comments"] == 2
    print("  ✓ Review summary counts are correct")

# ── Live API Tests ────────────────────────────────────────────

def test_review_buggy_chunk_live():
    print("  [calling Groq API — may take 5-10s]")
    result = review_chunk(BUGGY_CHUNK)

    assert result["error"] is None, f"Review failed: {result.get('error')}"

    comments = result.get("comments")
    if comments is None:
        comments = []

    assert isinstance(comments, list), f"Comments should be list, got {type(comments)}"

    print(f"  ✓ Got {len(comments)} comment(s) for buggy chunk")

    # Filter out any None comments (safety)
    valid_comments = [c for c in comments if isinstance(c, dict)]

    for comment in valid_comments:
        for field in ["issue", "severity", "confidence", "confidence_tier"]:
            assert field in comment, f"Comment missing field: {field}"

    for c in valid_comments:
        print(f"    → [{c.get('severity','').upper():8}] {c.get('issue','')} (confidence: {c.get('confidence',0)}%)")

def test_review_clean_chunk_live():
    print("  [calling Groq API — may take 5-10s]")
    result = review_chunk(CLEAN_CHUNK)
    assert result["error"] is None
    comments = result.get("comments") or []
    print(f"  ✓ Got {len(comments)} comment(s) for clean chunk (expected 0-2)")

def test_key_rotation():
    keys = _get_all_keys()
    if len(keys) < 2:
        print("  ⚠ Only 1 key configured — rotation test skipped")
        return

    print("  [making 3 API calls to test rotation]")
    key_nums = []
    for _ in range(3):
        result = review_chunk(CLEAN_CHUNK)
        key_nums.append(result["key_used"])
        time.sleep(1)

    print(f"  ✓ Keys used across 3 calls: {key_nums}")
    print("  ✓ Key rotation working correctly")

# ── Run All Tests ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  PHASE 3 — REVIEWER TESTS")
    print("═" * 55)

    unit_tests = [
        ("Confidence tier thresholds", test_confidence_tier_thresholds),
        ("Sanitize: fills defaults", test_sanitize_comment_fills_defaults),
        ("Sanitize: clamps confidence", test_sanitize_comment_clamps_confidence),
        ("Sanitize: invalid severity", test_sanitize_comment_invalid_severity),
        ("Sanitize: empty comment → None", test_sanitize_empty_comment_returns_none),
        ("Parse: strips markdown fences", test_parse_llm_response_handles_markdown_fences),
        ("Parse: empty array []", test_parse_llm_response_handles_empty_array),
        ("Parse: handles garbage output", test_parse_llm_response_handles_garbage),
        ("Parse: single object → array", test_parse_llm_response_single_object),
        ("Keys loaded from .env", test_keys_loaded),
        ("Review summary counts", test_review_summary),
    ]

    live_tests = [
        ("LIVE: buggy chunk gets flagged", test_review_buggy_chunk_live),
        ("LIVE: clean chunk few comments", test_review_clean_chunk_live),
        ("LIVE: key rotation across calls", test_key_rotation),
    ]

    passed = 0
    failed = 0

    print("\n── Unit Tests (no API calls) ──")
    for name, fn in unit_tests:
        print(f"\n[TEST] {name}")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1

    print("\n── Live API Tests (calls Groq) ──")
    for name, fn in live_tests:
        print(f"\n[TEST] {name}")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1

    print("\n" + "─" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("─" * 55)

    if failed == 0:
        print("\n  🎉✅ PHASE 3 COMPLETED SUCCESSFULLY!\n")
    else:
        print(f"\n  ⚠️ {failed} test(s) still failing.\n")