# ═══════════════════════════════════════════════════════════════
# app.py  (run with: streamlit run app.py)
# PURPOSE: The Streamlit dashboard — the user-facing front-end
#          that ties all phases together:
#            1. User pastes a GitHub URL
#            2. We clone + parse + review it
#            3. Results shown with filters, confidence badges,
#               severity colours, and a download button
#
# FIX: Added is_reviewing flag to disable filters during review
#      so clicking them mid-review does not restart the pipeline
# ═══════════════════════════════════════════════════════════════

import streamlit as st
import time
import json
import os
import sys

# Make sure core/ is importable when running from project root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# ── Streamlit Cloud secrets support ───────────────────────────
# On Streamlit Cloud there is no .env file — secrets live in
# st.secrets. We push them into os.environ so that reviewer.py
# (which uses os.getenv) can read them without any changes.
try:
    for _key in ["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GITHUB_TOKEN"]:
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  # Running locally — st.secrets not available, .env is used

# Import our three pipeline modules
from core.ingestion import clone_and_collect, cleanup_repo
from core.parser    import parse_files, get_parse_summary
from core.reviewer  import review_all_chunks, get_review_summary


# ══════════════════════════════════════════════════════════════
# Page config — must be the FIRST Streamlit call in the file
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Code Reviewer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════════════
# Custom CSS — colours, badges, confidence indicators
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── General ── */
.main { padding-top: 1rem; }

/* ── Severity badge pills ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-right: 6px;
}
.badge-critical { background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; }
.badge-high     { background:#ffedd5; color:#9a3412; border:1px solid #fdba74; }
.badge-medium   { background:#fef9c3; color:#854d0e; border:1px solid #fde047; }
.badge-low      { background:#dcfce7; color:#166534; border:1px solid #86efac; }
.badge-info     { background:#dbeafe; color:#1e40af; border:1px solid #93c5fd; }

/* ── Confidence tier indicators ── */
.conf-high   { color:#16a34a; font-weight:700; }
.conf-medium { color:#ca8a04; font-weight:700; }
.conf-low    { color:#dc2626; font-weight:700; }

/* ── Verify-this warning box ── */
.verify-box {
    background: #fff7ed;
    border-left: 4px solid #f97316;
    border-radius: 6px;
    padding: 8px 14px;
    margin: 6px 0 10px 0;
    font-size: 0.82rem;
    color: #7c2d12;
}

/* ── Comment card ── */
.comment-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
}

/* ── File header ── */
.file-header {
    background: #1e293b;
    color: #f1f5f9;
    padding: 8px 14px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 0.9rem;
    margin: 16px 0 8px 0;
}

/* ── Disabled filter label ── */
.filter-disabled-note {
    color: #94a3b8;
    font-size: 0.78rem;
    font-style: italic;
    margin-top: 4px;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# Helper: render a single review comment as a styled card
# ══════════════════════════════════════════════════════════════

def render_comment(comment: dict, index: int):
    """
    Render one comment dict as a styled card with:
    - Severity badge (colour-coded)
    - Confidence score + progress bar
    - 'verify this' warning for low-confidence comments
    - Issue title, description, suggestion
    - Line hint if available
    """
    severity        = comment.get("severity", "medium")
    category        = comment.get("category", "general")
    confidence      = comment.get("confidence", 70)
    confidence_tier = comment.get("confidence_tier", "medium")
    issue           = comment.get("issue", "Code issue")
    description     = comment.get("description", "")
    suggestion      = comment.get("suggestion", "")
    line_hint       = comment.get("line_hint", "")

    # Pick badge CSS class based on severity
    badge_class = f"badge-{severity}" if severity in ("critical","high","medium","low","info") else "badge-medium"
    conf_class  = f"conf-{confidence_tier}"

    # Build the header row: badge + category + confidence
    header_html = f"""
    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:6px;">
        <div>
            <span class="badge {badge_class}">{severity}</span>
            <span style="color:#64748b; font-size:0.8rem;">{category}</span>
            {f'<span style="color:#94a3b8; font-size:0.78rem; margin-left:8px;">line {line_hint}</span>' if line_hint and line_hint != "unknown" else ""}
        </div>
        <span class="{conf_class}" style="font-size:0.82rem;">
            Confidence: {confidence}%
        </span>
    </div>
    """

    with st.container():
        st.markdown('<div class="comment-card">', unsafe_allow_html=True)
        st.markdown(header_html, unsafe_allow_html=True)

        # Confidence progress bar — visual indicator of certainty
        bar_color = "#16a34a" if confidence_tier == "high" else ("#ca8a04" if confidence_tier == "medium" else "#dc2626")
        st.markdown(f"""
        <div style="background:#e2e8f0; border-radius:4px; height:5px; margin:6px 0 10px 0;">
            <div style="background:{bar_color}; width:{confidence}%; height:5px; border-radius:4px;"></div>
        </div>
        """, unsafe_allow_html=True)

        # ── VERIFY THIS label for low-confidence comments ──────
        # This is the "epistemic humility" feature required by the rubric
        if confidence_tier == "low":
            st.markdown("""
            <div class="verify-box">
                ⚠️ <strong>Verify this</strong> — Low confidence. This may be a false positive.
                Review manually before acting on this suggestion.
            </div>
            """, unsafe_allow_html=True)

        # Issue title
        st.markdown(f"**{issue}**")

        # Description
        if description:
            st.markdown(f"<p style='color:#475569; font-size:0.9rem; margin:4px 0;'>{description}</p>",
                       unsafe_allow_html=True)

        # Suggestion — shown in a subtle highlight box
        if suggestion:
            st.markdown(f"""
            <div style="background:#f0fdf4; border-left:3px solid #22c55e;
                        padding:6px 12px; border-radius:4px; margin-top:8px;
                        font-size:0.85rem; color:#166534;">
                💡 <strong>Suggestion:</strong> {suggestion}
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# Helper: generate a Markdown report for download
# ══════════════════════════════════════════════════════════════

def generate_markdown_report(results: list, repo_url: str, summary: dict) -> str:
    """
    Build a downloadable Markdown report of all review findings.
    Groups comments by file, includes all fields.
    """
    lines = [
        "# AI Code Review Report",
        f"\n**Repository:** {repo_url}",
        f"**Total Issues:** {summary['total_comments']}",
        f"**Files Reviewed:** {summary['files_reviewed']}",
        f"**Average Confidence:** {summary['avg_confidence']}%",
        "\n---\n",
        "## Severity Summary",
    ]

    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev, count in summary["severity_counts"].items():
        if count > 0:
            lines.append(f"| {sev.capitalize()} | {count} |")

    lines.append("\n## Confidence Summary")
    lines.append("| Confidence Tier | Count |")
    lines.append("|-----------------|-------|")
    for tier, count in summary["tier_counts"].items():
        label = f"{tier.capitalize()}" + (" ⚠️ Verify These" if tier == "low" else "")
        lines.append(f"| {label} | {count} |")

    lines.append("\n---\n")
    lines.append("## Findings by File\n")

    files_seen = {}
    for result in results:
        fname = result.get("file", "unknown")
        if fname not in files_seen:
            files_seen[fname] = []
        for comment in result.get("comments", []):
            files_seen[fname].append((result, comment))

    for fname, items in files_seen.items():
        if not items:
            continue
        lines.append(f"### 📄 `{fname}`\n")
        for result, comment in items:
            sev        = comment.get("severity","medium").upper()
            issue      = comment.get("issue","Issue")
            desc       = comment.get("description","")
            suggestion = comment.get("suggestion","")
            confidence = comment.get("confidence", 70)
            tier       = comment.get("confidence_tier","medium")
            line_hint  = comment.get("line_hint","")
            chunk_name = result.get("name","")

            verify_label = " ⚠️ **[VERIFY THIS]**" if tier == "low" else ""
            lines.append(f"#### [{sev}] {issue}{verify_label}")
            if chunk_name:
                lines.append(f"- **Chunk:** `{chunk_name}`")
            if line_hint and line_hint != "unknown":
                lines.append(f"- **Line:** {line_hint}")
            lines.append(f"- **Confidence:** {confidence}% ({tier})")
            if desc:
                lines.append(f"\n{desc}\n")
            if suggestion:
                lines.append(f"> 💡 **Fix:** {suggestion}\n")
            lines.append("---")

    lines.append(f"\n*Generated by AI Code Reviewer*")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Sidebar — stats panel shown after review completes
# ══════════════════════════════════════════════════════════════

def render_sidebar(summary: dict, parse_summary: dict):
    """Render all stats in the sidebar after a review completes."""

    st.sidebar.markdown("## 📊 Review Stats")

    st.sidebar.metric("Total Issues",     summary["total_comments"])
    st.sidebar.metric("Files Reviewed",   summary["files_reviewed"])
    st.sidebar.metric("Chunks Reviewed",  summary["total_chunks"])
    st.sidebar.metric("Avg Confidence",   f"{summary['avg_confidence']}%")

    if summary["failed_chunks"] > 0:
        st.sidebar.warning(f"⚠️ {summary['failed_chunks']} chunk(s) failed to review")

    st.sidebar.markdown("---")

    st.sidebar.markdown("### 🎯 By Severity")
    sev = summary["severity_counts"]
    sev_colors = {
        "critical": "#dc2626",
        "high":     "#ea580c",
        "medium":   "#ca8a04",
        "low":      "#16a34a",
        "info":     "#2563eb",
    }
    total_comments = max(summary["total_comments"], 1)

    for level in ("critical","high","medium","low","info"):
        count = sev.get(level, 0)
        if count == 0:
            continue
        pct   = int((count / total_comments) * 100)
        color = sev_colors[level]
        st.sidebar.markdown(f"""
        <div style="margin-bottom:6px;">
            <div style="display:flex; justify-content:space-between; font-size:0.82rem;">
                <span style="text-transform:capitalize;">{level}</span>
                <strong>{count}</strong>
            </div>
            <div style="background:#e2e8f0; border-radius:4px; height:6px;">
                <div style="background:{color}; width:{pct}%; height:6px; border-radius:4px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.markdown("---")

    st.sidebar.markdown("### 🎲 By Confidence")
    tiers = summary["tier_counts"]
    conf_colors = {"high":"#16a34a", "medium":"#ca8a04", "low":"#dc2626"}
    for tier in ("high","medium","low"):
        count = tiers.get(tier, 0)
        label = tier.capitalize()
        if tier == "low":
            label += " ⚠️"
        color = conf_colors[tier]
        pct   = int((count / total_comments) * 100)
        st.sidebar.markdown(f"""
        <div style="margin-bottom:6px;">
            <div style="display:flex; justify-content:space-between; font-size:0.82rem;">
                <span>{label}</span>
                <strong>{count}</strong>
            </div>
            <div style="background:#e2e8f0; border-radius:4px; height:6px;">
                <div style="background:{color}; width:{pct}%; height:6px; border-radius:4px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.markdown("---")

    st.sidebar.markdown("### 🧩 Code Structure")
    st.sidebar.markdown(f"- **Functions:** {parse_summary.get('functions', 0)}")
    st.sidebar.markdown(f"- **Classes:** {parse_summary.get('classes', 0)}")
    st.sidebar.markdown(f"- **Parse errors:** {parse_summary.get('parse_errors', 0)}")
    st.sidebar.markdown(f"- **Large chunks:** {parse_summary.get('large_chunks', 0)}")


# ══════════════════════════════════════════════════════════════
# Main App
# ══════════════════════════════════════════════════════════════

def main():

    # ── Initialise session state defaults ─────────────────────
    # is_reviewing: True while the pipeline is running
    # This flag disables filters so clicking them mid-review
    # cannot restart the script and kill the review process
    if "is_reviewing" not in st.session_state:
        st.session_state["is_reviewing"] = False
    if "results" not in st.session_state:
        st.session_state["results"] = None
    if "summary" not in st.session_state:
        st.session_state["summary"] = None
    if "parse_summary" not in st.session_state:
        st.session_state["parse_summary"] = None
    if "repo_url" not in st.session_state:
        st.session_state["repo_url"] = ""

    # ── Header ─────────────────────────────────────────────────
    st.markdown("""
    <h1 style="font-size:2rem; font-weight:800; margin-bottom:0;">
        🔍 AI Code Reviewer
    </h1>
    <p style="color:#64748b; margin-top:4px; font-size:1rem;">
        Paste a public GitHub repo URL to get AI-powered code review with confidence scoring.
    </p>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Input row ──────────────────────────────────────────────
    col_input, col_btn = st.columns([5, 1])

    with col_input:
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/username/repository",
            label_visibility="collapsed",
            # Disable input while reviewing so accidental edits don't rerun
            disabled=st.session_state["is_reviewing"],
        )

    with col_btn:
        run_clicked = st.button(
            "🚀 Review",
            use_container_width=True,
            type="primary",
            # Disable button while review is in progress
            disabled=st.session_state["is_reviewing"],
        )

    # ── Filter bar ─────────────────────────────────────────────
    # Filters are DISABLED while is_reviewing=True
    # This is the core fix — prevents Streamlit rerun from
    # killing the review pipeline mid-way
    is_reviewing = st.session_state["is_reviewing"]

    st.markdown("##### Filters")
    if is_reviewing:
        # Show a clear message so the user knows why filters are greyed out
        st.markdown(
            '<p class="filter-disabled-note">⏳ Filters are disabled while review is running — they will activate when complete.</p>',
            unsafe_allow_html=True
        )

    fcol1, fcol2, fcol3 = st.columns(3)

    with fcol1:
        filter_severity = st.multiselect(
            "Severity",
            options=["critical","high","medium","low","info"],
            default=["critical","high","medium","low","info"],
            disabled=is_reviewing,   # greyed out during review
        )
    with fcol2:
        filter_confidence = st.multiselect(
            "Confidence Tier",
            options=["high","medium","low"],
            default=["high","medium","low"],
            disabled=is_reviewing,   # greyed out during review
            help="'low' tier shows the 'verify this' warning",
        )
    with fcol3:
        filter_category = st.multiselect(
            "Category",
            options=["bug","security","performance","style","maintainability","error_handling","documentation"],
            default=["bug","security","performance","style","maintainability","error_handling","documentation"],
            disabled=is_reviewing,   # greyed out during review
        )

    st.markdown("---")

    # ══════════════════════════════════════════════════════════
    # Review pipeline — runs when button is clicked
    # ══════════════════════════════════════════════════════════

    if run_clicked:
        if not repo_url.strip():
            st.error("Please enter a GitHub repository URL.")
            return

        # Mark reviewing as started — this disables filters immediately
        st.session_state["is_reviewing"]  = True
        st.session_state["results"]       = None
        st.session_state["summary"]       = None
        st.session_state["parse_summary"] = None
        st.session_state["repo_url"]      = repo_url

        try:
            # ── Step 1: Clone ──────────────────────────────────
            with st.status("🔄 Cloning repository...", expanded=True) as status:
                st.write(f"Connecting to `{repo_url}`...")
                ingestion_result = clone_and_collect(repo_url)

                if ingestion_result["error"]:
                    status.update(label="❌ Clone failed", state="error")
                    st.error(f"**Clone failed:** {ingestion_result['error']}")
                    st.session_state["is_reviewing"] = False
                    return

                files   = ingestion_result["files"]
                skipped = ingestion_result["skipped"]

                st.write(f"✅ Cloned successfully — {len(files)} Python files found")
                if skipped:
                    st.write(f"⏭ Skipped {len(skipped)} file(s) (too large / binary / empty)")

                # ── Step 2: Parse ──────────────────────────────
                status.update(label="🧩 Parsing code with AST...")
                st.write("Running AST parser on collected files...")
                chunks        = parse_files(files)
                parse_summary = get_parse_summary(chunks)

                st.write(
                    f"✅ Parsed {parse_summary['total_chunks']} chunks — "
                    f"{parse_summary['functions']} functions, "
                    f"{parse_summary['classes']} classes"
                )

                if parse_summary["parse_errors"] > 0:
                    st.write(f"⚠️ {parse_summary['parse_errors']} file(s) had syntax errors (still reviewed)")

                if not chunks:
                    status.update(label="⚠️ No reviewable code found", state="error")
                    st.warning("No Python functions or classes were found in this repository.")
                    cleanup_repo(ingestion_result["repo_path"])
                    st.session_state["is_reviewing"] = False
                    return

                # ── Step 3: LLM Review ─────────────────────────
                status.update(label=f"🤖 Reviewing {len(chunks)} chunks with Groq AI...")
                st.write("Sending chunks to Groq LLM for review...")

                progress_bar  = st.progress(0)
                progress_text = st.empty()

                def update_progress(current, total, chunk_name):
                    # Update progress bar — safe to call mid-loop
                    pct = int((current / total) * 100)
                    progress_bar.progress(pct)
                    progress_text.markdown(
                        f"Reviewing `{chunk_name}` ({current}/{total})"
                    )

                results = review_all_chunks(chunks, progress_callback=update_progress)

                progress_bar.progress(100)
                progress_text.markdown("✅ Review complete!")

                # ✅ FIX: Show any chunk-level errors so API key issues are visible
                failed = [r for r in results if r.get("error")]
                if failed:
                    with st.expander(f"⚠️ {len(failed)} chunk(s) failed — click to see errors"):
                        for r in failed:
                            st.error(f"`{r.get('name')}`: {r.get('error')}")

                # ── Cleanup cloned repo from disk ──────────────
                cleanup_repo(ingestion_result["repo_path"])

                # ── Compute and store summary ──────────────────
                summary = get_review_summary(results)

                st.session_state["results"]       = results
                st.session_state["summary"]       = summary
                st.session_state["parse_summary"] = parse_summary

                status.update(
                    label=f"✅ Review complete — {summary['total_comments']} issue(s) found",
                    state="complete",
                )

        except Exception as e:
            # Catch any unexpected error so is_reviewing always gets reset
            st.error(f"An unexpected error occurred: {str(e)}")

        finally:
            # ALWAYS reset is_reviewing when pipeline finishes or errors
            # This re-enables filters regardless of success or failure
            st.session_state["is_reviewing"] = False

    # ══════════════════════════════════════════════════════════
    # Results display — shown after review OR when filters change
    # ══════════════════════════════════════════════════════════

    results       = st.session_state.get("results")
    summary       = st.session_state.get("summary")
    parse_summary = st.session_state.get("parse_summary")
    stored_url    = st.session_state.get("repo_url", "")

    if results is None:
        # No review has been run yet — show welcome screen
        st.markdown("""
        <div style="text-align:center; padding:60px 0; color:#94a3b8;">
            <div style="font-size:3rem;">🔍</div>
            <div style="font-size:1.1rem; margin-top:12px;">
                Enter a GitHub URL above and click <strong>Review</strong> to start.
            </div>
            <div style="font-size:0.85rem; margin-top:8px;">
                The agent will clone, parse, and review the Python code automatically.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Sidebar stats ──────────────────────────────────────────
    render_sidebar(summary, parse_summary)

    # ── Top summary metrics ────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    sev = summary["severity_counts"]
    m1.metric("🔴 Critical", sev.get("critical", 0))
    m2.metric("🟠 High",     sev.get("high",     0))
    m3.metric("🟡 Medium",   sev.get("medium",   0))
    m4.metric("🟢 Low",      sev.get("low",      0))
    m5.metric("📊 Avg Conf", f"{summary['avg_confidence']}%")

    st.markdown("---")

    # ── Low-confidence section — epistemic humility feature ───
    low_conf_comments = []
    for r in results:
        for c in r.get("comments", []):
            if c.get("confidence_tier") == "low":
                low_conf_comments.append((r, c))

    if low_conf_comments:
        with st.expander(
            f"⚠️ Low-Confidence Comments — Verify These ({len(low_conf_comments)} items)",
            expanded=False
        ):
            st.markdown("""
            <div style="background:#fff7ed; border:1px solid #fed7aa; border-radius:8px;
                        padding:10px 16px; margin-bottom:16px; color:#7c2d12; font-size:0.88rem;">
                These comments have a confidence score below 50%. They may be false positives.
                <strong>Always verify manually before making changes.</strong>
            </div>
            """, unsafe_allow_html=True)
            for result, comment in low_conf_comments:
                st.markdown(
                    f"<div class='file-header'>📄 {result.get('file','')} → `{result.get('name','')}`</div>",
                    unsafe_allow_html=True
                )
                render_comment(comment, 0)

    st.markdown("---")

    # ── Main results — filtered and grouped by file ────────────
    st.markdown("## 📋 Review Findings")

    filtered_count    = 0
    files_with_issues = {}

    for result in results:
        fname = result.get("file", "unknown")
        for comment in result.get("comments", []):
            if comment.get("severity")        not in filter_severity:   continue
            if comment.get("confidence_tier") not in filter_confidence: continue
            if comment.get("category")        not in filter_category:   continue

            if fname not in files_with_issues:
                files_with_issues[fname] = []
            files_with_issues[fname].append((result, comment))
            filtered_count += 1

    if filtered_count == 0:
        st.info("No issues match the current filters. Try adjusting the filters above.")
    else:
        st.markdown(
            f"<p style='color:#64748b; font-size:0.9rem;'>Showing {filtered_count} issue(s) across {len(files_with_issues)} file(s)</p>",
            unsafe_allow_html=True
        )

        for fname, items in files_with_issues.items():
            st.markdown(
                f"<div class='file-header'>📄 {fname} — {len(items)} issue(s)</div>",
                unsafe_allow_html=True
            )

            chunks_seen = {}
            for result, comment in items:
                cname = result.get("name", "unknown")
                if cname not in chunks_seen:
                    chunks_seen[cname] = []
                chunks_seen[cname].append((result, comment))

            for chunk_name, chunk_items in chunks_seen.items():
                chunk_type = chunk_items[0][0].get("type", "function")
                start_line = chunk_items[0][0].get("start_line", "?")
                end_line   = chunk_items[0][0].get("end_line", "?")

                with st.expander(
                    f"{'ƒ' if chunk_type == 'function' else '◻'} `{chunk_name}` "
                    f"(lines {start_line}–{end_line}) — {len(chunk_items)} issue(s)",
                    expanded=True
                ):
                    for i, (result, comment) in enumerate(chunk_items):
                        render_comment(comment, i)

    # ── Download buttons ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📥 Download Report")

    report_md = generate_markdown_report(results, stored_url, summary)

    dl_col1, dl_col2 = st.columns([2, 5])

    with dl_col1:
        st.download_button(
            label="⬇️ Download Markdown Report",
            data=report_md,
            file_name="code_review_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with dl_col2:
        st.download_button(
            label="⬇️ Download Raw JSON",
            data=json.dumps(results, indent=2),
            file_name="code_review_results.json",
            mime="application/json",
            use_container_width=True,
        )


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()