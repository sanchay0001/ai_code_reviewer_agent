# ═══════════════════════════════════════════════════════════════
# tests/test_phase1_ingestion.py
# PURPOSE: Verify that the ingestion module correctly clones repos,
#          validates URLs, collects files, and handles edge cases.
#          Run with: python -m pytest tests/test_phase1_ingestion.py -v
# ═══════════════════════════════════════════════════════════════

import os
import sys
import tempfile

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.ingestion import clone_and_collect, cleanup_repo, _validate_github_url, _collect_files


# ─── URL Validation Tests ─────────────────────────────────────

def test_valid_github_url():
    """A proper HTTPS GitHub URL should return None (no error)."""
    result = _validate_github_url("https://github.com/pallets/flask")
    assert result is None, f"Expected no error but got: {result}"
    print("  ✓ Valid URL passes validation")


def test_invalid_url_empty():
    """Empty string should return an error."""
    result = _validate_github_url("")
    assert result is not None
    print(f"  ✓ Empty URL rejected: {result}")


def test_invalid_url_ssh():
    """SSH URLs should be rejected (we only support HTTPS)."""
    result = _validate_github_url("git@github.com:user/repo.git")
    assert result is not None
    print(f"  ✓ SSH URL rejected: {result}")


def test_invalid_url_not_github():
    """Non-GitHub URLs should be rejected."""
    result = _validate_github_url("https://gitlab.com/user/repo")
    assert result is not None
    print(f"  ✓ Non-GitHub URL rejected: {result}")


# ─── File Collection Tests ────────────────────────────────────

def test_collect_files_finds_python():
    """Should find .py files and ignore non-Python files."""
    # Create a temporary directory with a mix of files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a valid Python file
        py_file = os.path.join(tmpdir, "hello.py")
        with open(py_file, "w") as f:
            f.write("def hello():\n    return 'world'\n")

        # Create a non-Python file (should be ignored)
        txt_file = os.path.join(tmpdir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("This is a readme")

        # Create an empty Python file (should be skipped)
        empty_file = os.path.join(tmpdir, "empty.py")
        with open(empty_file, "w") as f:
            f.write("   \n  ")

        collected, skipped = _collect_files(tmpdir)

        assert len(collected) == 1, f"Expected 1 file, got {len(collected)}"
        assert collected[0]["path"] == "hello.py"
        assert "def hello" in collected[0]["content"]
        # empty.py should appear in skipped
        skipped_paths = [s["path"] for s in skipped]
        assert "empty.py" in skipped_paths
        print(f"  ✓ Collected {len(collected)} .py files, skipped {len(skipped)}")


def test_collect_files_skips_venv():
    """Files inside .venv / venv directories should be ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # File in root — should be collected
        root_file = os.path.join(tmpdir, "main.py")
        with open(root_file, "w") as f:
            f.write("print('hello')\n")

        # File inside venv — should be skipped entirely
        venv_dir = os.path.join(tmpdir, ".venv", "lib")
        os.makedirs(venv_dir)
        venv_file = os.path.join(venv_dir, "site_pkg.py")
        with open(venv_file, "w") as f:
            f.write("# venv internal\n")

        collected, _ = _collect_files(tmpdir)

        paths = [c["path"] for c in collected]
        assert "main.py" in paths
        assert not any(".venv" in p for p in paths)
        print(f"  ✓ .venv directory correctly ignored")


# ─── Live Clone Test ──────────────────────────────────────────

def test_clone_real_repo():
    """
    Clone a tiny real public repo and check we get files back.
    Using 'github-changelog-generator' as it's tiny.
    WARNING: This test requires internet access.
    """
    # We use a known tiny public repo for testing
    result = clone_and_collect("https://github.com/psf/requests")

    assert result["error"] is None, f"Clone failed: {result['error']}"
    assert len(result["files"]) > 0, "No files collected from repo"
    assert result["repo_path"] is not None

    print(f"  ✓ Cloned repo successfully")
    print(f"  ✓ Collected {len(result['files'])} Python files")
    print(f"  ✓ Skipped {len(result['skipped'])} files")

    # Sample one file to make sure content was read
    sample = result["files"][0]
    assert "path" in sample
    assert "content" in sample
    assert len(sample["content"]) > 0
    print(f"  ✓ Sample file: {sample['path']} ({len(sample['content'])} chars)")

    # Always clean up after ourselves
    cleanup_repo(result["repo_path"])
    print(f"  ✓ Temp directory cleaned up")


def test_clone_invalid_repo():
    """A non-existent repo URL should return an error, not crash."""
    result = clone_and_collect("https://github.com/this-user-does-not-exist-xyz/no-repo-here")
    assert result["error"] is not None
    assert result["files"] == []
    print(f"  ✓ Invalid repo handled gracefully: {result['error'][:60]}...")


# ─── Run all tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  PHASE 1 — INGESTION TESTS")
    print("═" * 55)

    tests = [
        ("URL: valid GitHub URL", test_valid_github_url),
        ("URL: empty string rejected", test_invalid_url_empty),
        ("URL: SSH format rejected", test_invalid_url_ssh),
        ("URL: non-GitHub rejected", test_invalid_url_not_github),
        ("Files: finds Python files", test_collect_files_finds_python),
        ("Files: skips .venv dirs", test_collect_files_skips_venv),
        ("Clone: real repo (needs internet)", test_clone_real_repo),
        ("Clone: handles bad repo URL", test_clone_invalid_repo),
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