# ═══════════════════════════════════════════════════════════════
# core/parser.py
# PURPOSE: Take the raw Python source files from ingestion.py
#          and break them into reviewable "chunks" using Python's
#          built-in Abstract Syntax Tree (ast) module.
#
#          WHY AST instead of raw string splitting?
#          AST understands Python syntax. It can tell us where a
#          function starts/ends, what it's called, and what it
#          imports — without us writing a single regex.
# ═══════════════════════════════════════════════════════════════

import ast
import textwrap


# ── Constants ─────────────────────────────────────────────────
# Groq's free tier has token limits. We keep each chunk under
# this many characters to stay safe (~800 tokens ≈ 3200 chars).
MAX_CHUNK_CHARS = 3000

# If a single function is longer than this, we still send it but
# flag it as "large" so the LLM knows context may be incomplete.
LARGE_FUNCTION_THRESHOLD = 80  # lines


# ── Main function ─────────────────────────────────────────────
def parse_files(files: list) -> list:
    """
    Parse a list of file dicts (from ingestion.py) and return
    a flat list of chunks ready to send to the LLM.

    Parameters
    ----------
    files : list of {"path": str, "content": str}

    Returns
    -------
    list of chunk dicts, each containing:
        "file"      : str  — relative file path
        "chunk_id"  : str  — unique ID like "myfile.py::MyClass.method"
        "type"      : str  — "function" | "class" | "module_level"
        "name"      : str  — function/class name, or "module_level"
        "code"      : str  — the source code of this chunk
        "start_line": int  — line number in original file
        "end_line"  : int  — line number in original file
        "imports"   : list — module-level imports detected
        "is_large"  : bool — True if chunk exceeds LARGE_FUNCTION_THRESHOLD
        "parse_error": str|None — if AST parsing failed
    """
    all_chunks = []

    for file_dict in files:
        path = file_dict["path"]
        content = file_dict["content"]

        # Parse this file and extend our running list
        chunks = _parse_single_file(path, content)
        all_chunks.extend(chunks)

    print(f"[Parser] Produced {len(all_chunks)} chunks from {len(files)} files")
    return all_chunks


# ── Single-file parser ────────────────────────────────────────

def _parse_single_file(filepath: str, source: str) -> list:
    """
    Parse one Python file with ast.parse() and extract chunks.
    Falls back to a single whole-file chunk if parsing fails.
    """

    # Split source into lines so we can slice code by line numbers
    source_lines = source.splitlines(keepends=True)

    # First, collect all module-level imports for context
    # (we'll attach them to every chunk from this file)
    imports = _extract_imports(source)

    try:
        # ast.parse builds the full syntax tree of the file
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        # If the file has a syntax error, we still want to review it —
        # that IS a bug worth reporting. Return it as one raw chunk.
        return [{
            "file": filepath,
            "chunk_id": f"{filepath}::SYNTAX_ERROR",
            "type": "module_level",
            "name": "SYNTAX_ERROR",
            "code": source[:MAX_CHUNK_CHARS],  # truncate if huge
            "start_line": 1,
            "end_line": len(source_lines),
            "imports": imports,
            "is_large": False,
            "parse_error": f"SyntaxError: {e.msg} (line {e.lineno})"
        }]

    chunks = []

    # Walk only the TOP-LEVEL nodes of the file (not nested nodes)
    # ast.iter_child_nodes gives us direct children of the Module node
    for node in ast.iter_child_nodes(tree):

        # ── Top-level function definitions ──
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunk = _node_to_chunk(node, filepath, source_lines, imports, parent_name=None)
            chunks.append(chunk)

        # ── Top-level class definitions ──
        elif isinstance(node, ast.ClassDef):
            # Option A: send the whole class as one chunk (if small enough)
            # Option B: send each method separately (if class is large)
            class_code = _extract_lines(source_lines, node.lineno, node.end_lineno)

            if len(class_code) <= MAX_CHUNK_CHARS:
                # Small class — review it as one unit
                chunk = _node_to_chunk(node, filepath, source_lines, imports, parent_name=None)
                chunks.append(chunk)
            else:
                # Large class — extract each method separately for focused review
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        chunk = _node_to_chunk(
                            item, filepath, source_lines, imports,
                            parent_name=node.name  # e.g. "MyClass.my_method"
                        )
                        chunks.append(chunk)

    # ── Module-level code (not inside any function/class) ──
    # Collect lines that aren't covered by any top-level function or class
    covered_lines = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                covered_lines.add(ln)

    module_lines = [
        line for i, line in enumerate(source_lines, start=1)
        if i not in covered_lines
    ]
    module_code = "".join(module_lines).strip()

    # Only include module-level code if it's substantial (not just imports)
    non_import_code = _strip_imports(module_code)
    if len(non_import_code.strip()) > 50:
        chunks.append({
            "file": filepath,
            "chunk_id": f"{filepath}::module_level",
            "type": "module_level",
            "name": "module_level",
            "code": module_code[:MAX_CHUNK_CHARS],
            "start_line": 1,
            "end_line": len(source_lines),
            "imports": imports,
            "is_large": False,
            "parse_error": None
        })

    # If nothing was extracted (empty file passed ingestion check), skip
    if not chunks:
        return []

    return chunks


# ── Node → Chunk converter ────────────────────────────────────

def _node_to_chunk(node, filepath: str, source_lines: list, imports: list, parent_name: str | None) -> dict:
    """
    Convert a single AST node (FunctionDef / ClassDef) into a chunk dict.
    """
    # Determine the display name: "ClassName.method" or just "function_name"
    if parent_name:
        name = f"{parent_name}.{node.name}"
    else:
        name = node.name

    # Extract the actual source lines for this node
    start = node.lineno
    end = node.end_lineno or node.lineno
    code = _extract_lines(source_lines, start, end)

    # Dedent so the code doesn't have excessive leading whitespace
    code = textwrap.dedent(code)

    # Truncate if the chunk is absurdly long (keep the start — usually most important)
    if len(code) > MAX_CHUNK_CHARS:
        code = code[:MAX_CHUNK_CHARS] + "\n# ... [truncated for review]"

    line_count = end - start + 1
    is_large = line_count > LARGE_FUNCTION_THRESHOLD

    # Determine type string
    if isinstance(node, ast.ClassDef):
        node_type = "class"
    else:
        node_type = "function"

    return {
        "file": filepath,
        "chunk_id": f"{filepath}::{name}",
        "type": node_type,
        "name": name,
        "code": code,
        "start_line": start,
        "end_line": end,
        "imports": imports,
        "is_large": is_large,
        "parse_error": None
    }


# ── Utility helpers ───────────────────────────────────────────

def _extract_lines(source_lines: list, start: int, end: int) -> str:
    """
    Slice source_lines (1-indexed like AST gives us) from start to end inclusive.
    """
    # source_lines is 0-indexed, AST line numbers are 1-indexed
    return "".join(source_lines[start - 1: end])


def _extract_imports(source: str) -> list:
    """
    Parse the source and return a list of import statement strings.
    e.g. ["import os", "from pathlib import Path"]
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        # ast.Import handles "import os, sys"
        if isinstance(node, ast.Import):
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"import {names}")

        # ast.ImportFrom handles "from pathlib import Path"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {module} import {names}")

    return imports


def _strip_imports(code: str) -> str:
    """
    Remove import lines from a code string.
    Used to check if module-level code has substance beyond just imports.
    """
    lines = [
        line for line in code.splitlines()
        if not line.strip().startswith(("import ", "from "))
    ]
    return "\n".join(lines)


# ── Summary helper (used by Streamlit UI) ────────────────────

def get_parse_summary(chunks: list) -> dict:
    """
    Return a quick stats dict for display in the Streamlit sidebar.
    """
    files = set(c["file"] for c in chunks)
    functions = [c for c in chunks if c["type"] == "function"]
    classes = [c for c in chunks if c["type"] == "class"]
    errors = [c for c in chunks if c.get("parse_error")]

    return {
        "total_chunks": len(chunks),
        "total_files": len(files),
        "functions": len(functions),
        "classes": len(classes),
        "parse_errors": len(errors),
        "large_chunks": len([c for c in chunks if c["is_large"]])
    }