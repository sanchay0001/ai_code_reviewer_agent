# ═══════════════════════════════════════════════════════════════
# tests/test_phase2_parser.py
# PURPOSE: Verify that the AST parser correctly extracts functions,
#          classes, imports, handles syntax errors, and produces
#          chunks with the right shape for the LLM.
#          Run with: python -m pytest tests/test_phase2_parser.py -v
# ═══════════════════════════════════════════════════════════════

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser import parse_files, get_parse_summary, _extract_imports


# ─── Test fixtures (inline Python source strings) ─────────────

SIMPLE_FUNCTION_SOURCE = '''
import os
from pathlib import Path

def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"

def add(a: int, b: int) -> int:
    return a + b
'''

CLASS_SOURCE = '''
import json

class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.history = []

    def add(self, a, b):
        result = a + b
        self.history.append(result)
        return result

    def subtract(self, a, b):
        result = a - b
        self.history.append(result)
        return result
'''

SYNTAX_ERROR_SOURCE = '''
def broken_function(:
    this is not valid python
    return !!!
'''

EMPTY_SOURCE = '''
import os
import sys
'''

MODULE_LEVEL_SOURCE = '''
import os

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if DEBUG:
    print("Debug mode enabled")

MAX_RETRIES = 3
TIMEOUT = 30
'''


# ─── Tests ────────────────────────────────────────────────────

def test_extracts_top_level_functions():
    """Should find both top-level functions in SIMPLE_FUNCTION_SOURCE."""
    files = [{"path": "test.py", "content": SIMPLE_FUNCTION_SOURCE}]
    chunks = parse_files(files)

    names = [c["name"] for c in chunks]
    assert "greet" in names, f"'greet' not found in {names}"
    assert "add" in names, f"'add' not found in {names}"
    print(f"  ✓ Found functions: {names}")


def test_function_chunk_has_correct_keys():
    """Each chunk must have all required keys for the LLM."""
    files = [{"path": "test.py", "content": SIMPLE_FUNCTION_SOURCE}]
    chunks = parse_files(files)

    required_keys = {"file", "chunk_id", "type", "name", "code", "start_line",
                     "end_line", "imports", "is_large", "parse_error"}

    for chunk in chunks:
        missing = required_keys - set(chunk.keys())
        assert not missing, f"Chunk missing keys: {missing}"

    print(f"  ✓ All {len(chunks)} chunks have required keys")


def test_imports_extracted_correctly():
    """Imports should be captured as a list of strings."""
    imports = _extract_imports(SIMPLE_FUNCTION_SOURCE)
    assert "import os" in imports
    assert "from pathlib import Path" in imports
    print(f"  ✓ Extracted imports: {imports}")


def test_class_chunk_type():
    """A class should produce chunk(s) with type='class'."""
    files = [{"path": "calc.py", "content": CLASS_SOURCE}]
    chunks = parse_files(files)

    class_chunks = [c for c in chunks if c["type"] == "class"]
    assert len(class_chunks) >= 1, f"No class chunks found, got: {[c['type'] for c in chunks]}"
    print(f"  ✓ Class chunk found: {class_chunks[0]['name']}")


def test_syntax_error_handled_gracefully():
    """Files with syntax errors should not crash — return a chunk with parse_error set."""
    files = [{"path": "broken.py", "content": SYNTAX_ERROR_SOURCE}]
    chunks = parse_files(files)

    # Must return at least one chunk, even for broken files
    assert len(chunks) >= 1, "Expected at least one chunk for broken file"

    # That chunk should have parse_error populated
    error_chunks = [c for c in chunks if c.get("parse_error")]
    assert len(error_chunks) >= 1, "Expected parse_error to be set"
    print(f"  ✓ Syntax error handled: {error_chunks[0]['parse_error']}")


def test_import_only_file_produces_no_chunks():
    """A file with only imports and no logic should produce no/minimal chunks."""
    files = [{"path": "imports_only.py", "content": EMPTY_SOURCE}]
    chunks = parse_files(files)
    # Should be 0 or 1 chunk (the module_level one with no real logic)
    assert len(chunks) <= 1
    print(f"  ✓ Import-only file produced {len(chunks)} chunks (expected 0-1)")


def test_module_level_code_captured():
    """Module-level assignments and control flow should be captured."""
    files = [{"path": "config.py", "content": MODULE_LEVEL_SOURCE}]
    chunks = parse_files(files)

    module_chunks = [c for c in chunks if c["type"] == "module_level"]
    assert len(module_chunks) >= 1, "Module-level code not captured"
    code = module_chunks[0]["code"]
    assert "DEBUG" in code or "MAX_RETRIES" in code
    print(f"  ✓ Module-level code captured ({len(module_chunks[0]['code'])} chars)")


def test_chunk_id_is_unique():
    """Every chunk_id must be unique within a run."""
    files = [
        {"path": "a.py", "content": SIMPLE_FUNCTION_SOURCE},
        {"path": "b.py", "content": CLASS_SOURCE},
    ]
    chunks = parse_files(files)
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), f"Duplicate chunk_ids found: {ids}"
    print(f"  ✓ All {len(ids)} chunk_ids are unique")


def test_get_parse_summary():
    """Summary dict should have correct counts."""
    files = [
        {"path": "funcs.py", "content": SIMPLE_FUNCTION_SOURCE},
        {"path": "classes.py", "content": CLASS_SOURCE},
    ]
    chunks = parse_files(files)
    summary = get_parse_summary(chunks)

    assert summary["total_files"] == 2
    assert summary["total_chunks"] == len(chunks)
    assert summary["functions"] >= 2  # greet, add
    print(f"  ✓ Summary: {summary}")


def test_code_is_dedented():
    """Code in chunks should not have excessive leading whitespace."""
    files = [{"path": "calc.py", "content": CLASS_SOURCE}]
    chunks = parse_files(files)

    for chunk in chunks:
        lines = chunk["code"].splitlines()
        if lines:
            # First non-empty line should start at column 0 or minimal indent
            first_line = next((l for l in lines if l.strip()), "")
            leading = len(first_line) - len(first_line.lstrip())
            assert leading < 8, f"Excessive indent ({leading} spaces) in chunk '{chunk['name']}'"

    print(f"  ✓ All chunks are properly dedented")


# ─── Run all tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  PHASE 2 — PARSER TESTS")
    print("═" * 55)

    tests = [
        ("Extracts top-level functions", test_extracts_top_level_functions),
        ("Chunks have correct keys", test_function_chunk_has_correct_keys),
        ("Imports extracted correctly", test_imports_extracted_correctly),
        ("Class chunks have type='class'", test_class_chunk_type),
        ("Syntax errors handled gracefully", test_syntax_error_handled_gracefully),
        ("Import-only file → minimal chunks", test_import_only_file_produces_no_chunks),
        ("Module-level code captured", test_module_level_code_captured),
        ("All chunk_ids are unique", test_chunk_id_is_unique),
        ("Parse summary counts are correct", test_get_parse_summary),
        ("Code is properly dedented", test_code_is_dedented),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n[TEST] {name}")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "─" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("─" * 55 + "\n")