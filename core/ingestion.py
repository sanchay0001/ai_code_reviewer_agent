# ═══════════════════════════════════════════════════════════════
# core/ingestion.py
# PURPOSE: Clone a GitHub repo to a temp folder, walk its file
#          tree, and return only the Python source files we care
#          about. This is the entry-point of the whole pipeline.
# ═══════════════════════════════════════════════════════════════

import os
import shutil
import tempfile
import re

# git.Repo is GitPython's main class for all repo operations
from git import Repo, GitCommandError


# ── Constants ────────────────────────────────────────────────
# Only analyse these extensions (expand later for JS/Go support)
SUPPORTED_EXTENSIONS = {".py"}

# Skip these folders entirely — they have no user-written logic
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", "dist", "build", ".tox", "migrations",
    ".mypy_cache", ".pytest_cache",
}

# Skip files larger than this (bytes) — 200 KB is ~5000 lines
MAX_FILE_SIZE_BYTES = 200_000


# ── Main function ─────────────────────────────────────────────
def clone_and_collect(repo_url: str) -> dict:
    """
    Clone a public GitHub repo and return a dict of source files.

    Parameters
    ----------
    repo_url : str
        Full HTTPS URL, e.g. "https://github.com/user/repo"

    Returns
    -------
    dict with keys:
        "repo_path"  : str   — path to the cloned temp directory
        "files"      : list  — each item is {"path": str, "content": str}
        "skipped"    : list  — files we deliberately skipped with reasons
        "error"      : str|None — populated only when something goes wrong
    """

    # Validate the URL before hitting the network
    validation_error = _validate_github_url(repo_url)
    if validation_error:
        return {"repo_path": None, "files": [], "skipped": [], "error": validation_error}

    # Create a throw-away temp directory — deleted in the Streamlit UI after review
    temp_dir = tempfile.mkdtemp(prefix="code_reviewer_")

    print(f"[Ingestion] Cloning {repo_url} → {temp_dir}")

    try:
        # GitPython clones the repo; depth=1 fetches only the latest
        # commit — much faster than full history for large repos
        Repo.clone_from(
            repo_url.strip(),
            temp_dir,
            depth=1,           # shallow clone = faster
            single_branch=True # only the default branch
        )
    except GitCommandError as e:
        # Clean up the empty temp dir if the clone failed
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "repo_path": None,
            "files": [],
            "skipped": [],
            "error": f"Git clone failed: {str(e)}"
        }

    # Walk the cloned directory and collect Python files
    collected_files, skipped_files = _collect_files(temp_dir)

    print(f"[Ingestion] Found {len(collected_files)} files, skipped {len(skipped_files)}")

    return {
        "repo_path": temp_dir,
        "files": collected_files,
        "skipped": skipped_files,
        "error": None
    }


def cleanup_repo(repo_path: str):
    """
    Delete the cloned temp directory when we're done with it.
    Always call this after the review pipeline completes to free disk space.
    """
    if repo_path and os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
        print(f"[Ingestion] Cleaned up {repo_path}")


# ── Private helpers ───────────────────────────────────────────

def _validate_github_url(url: str) -> str | None:
    """
    Return an error message string if the URL is invalid,
    or None if it looks like a real GitHub HTTPS URL.
    """
    url = url.strip()

    if not url:
        return "Please enter a GitHub URL."

    # Must start with https://github.com/
    pattern = r"^https://github\.com/[\w\-\.]+/[\w\-\.]+$"
    if not re.match(pattern, url):
        return (
            "URL must be a public GitHub repo in the form: "
            "https://github.com/username/reponame"
        )

    return None  # None means "no error"


def _collect_files(root_dir: str) -> tuple[list, list]:
    """
    Recursively walk root_dir and separate files into:
      - collected : {"path": relative_path, "content": file_text}
      - skipped   : {"path": relative_path, "reason": why_we_skipped}

    Uses os.walk which yields (dirpath, subdirs, filenames).
    We mutate the subdirs list in-place to prune SKIP_DIRS early
    (this prevents os.walk from descending into them at all).
    """
    collected = []
    skipped = []

    for dirpath, subdirs, filenames in os.walk(root_dir):
        # Prune unwanted subdirectories IN-PLACE so os.walk skips them
        # [:] slice assignment mutates the list that os.walk reads
        subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS]

        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            # Make the path relative to the repo root for cleaner display
            rel_path = os.path.relpath(full_path, root_dir)
            _, ext = os.path.splitext(filename)

            # ── Skip checks (ordered cheapest → most expensive) ──

            # 1. Wrong extension
            if ext.lower() not in SUPPORTED_EXTENSIONS:
                continue  # silently skip — no need to log these

            # 2. File too large
            try:
                size = os.path.getsize(full_path)
            except OSError:
                skipped.append({"path": rel_path, "reason": "Cannot read file size"})
                continue

            if size > MAX_FILE_SIZE_BYTES:
                skipped.append({
                    "path": rel_path,
                    "reason": f"File too large ({size // 1024} KB > {MAX_FILE_SIZE_BYTES // 1024} KB limit)"
                })
                continue

            # 3. Try to read the file as UTF-8
            try:
                with open(full_path, "r", encoding="utf-8", errors="strict") as f:
                    content = f.read()
            except UnicodeDecodeError:
                skipped.append({"path": rel_path, "reason": "Binary or non-UTF-8 encoding"})
                continue
            except OSError as e:
                skipped.append({"path": rel_path, "reason": f"Read error: {e}"})
                continue

            # 4. Empty file — nothing to review
            if not content.strip():
                skipped.append({"path": rel_path, "reason": "Empty file"})
                continue

            # ── All checks passed — add to collected ──
            collected.append({"path": rel_path, "content": content})

    return collected, skipped